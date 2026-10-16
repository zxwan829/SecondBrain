#!/usr/bin/env python3
"""D077 synthetic-only Hermes API learning evaluation on an ephemeral GitHub runner.

Security boundaries: a Docker INTERNAL bridge with no external egress; the real
SiliconFlow key lives only in this runner-side proxy, never in the container.
The proxy only forwards Chat Completions to one hard-coded HTTPS provider,
caps output tokens, request count and conservative estimated USD exposure.
"""
import http.client
import json
import os
import pathlib
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IMAGE = "nousresearch/hermes-agent@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05"
MODEL = "deepseek-ai/DeepSeek-V4-Flash"
NETWORK = "d077-live-internal"
CONTAINER = "d077-live-agent"
GATEWAY = "172.29.77.1"
PROXY_PORT = 19001
HERMES_PORT = 18642
API_KEY = "d077-synthetic-session-only-key"
BUDGET_USD_UPPER = 0.22  # Safety estimate only; NOT an external hard spending limit
MAX_REQUESTS = 60
MAX_OUTPUT_TOKENS = 512
MAX_REQUEST_BYTES = 70000
SECRET = os.environ.get("SILICONFLOW_D077_KEY", "")
LOCK = threading.Lock()
counter = {"requests": 0, "worst_usd": 0.0, "reported_input_tokens": 0,
           "reported_output_tokens": 0, "errors": 0}
records = []

def cmd(*args, input=None, timeout=100, check=True):
    return subprocess.run(args, input=input, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=check)

def api_json(path, data=None, method=None, timeout=12):
    req = urllib.request.Request("http://127.0.0.1:%s%s" % (HERMES_PORT, path),
        data=(json.dumps(data).encode() if data is not None else None),
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
        method=method or ("POST" if data is not None else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.load(resp)

class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *_args):
        pass
    def respond(self, status, data, kind="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True
    def do_GET(self):
        if self.path == "/health":
            self.respond(200, b'{"status":"ok"}')
        elif self.path == "/v1/models":
            self.respond(200, json.dumps({"object":"list","data":[{"id":MODEL,"object":"model"}]}).encode())
        else:
            self.respond(404, b'{"error":"route_not_allowed"}')
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.respond(403, b'{"error":"route_not_allowed"}')
            return
        try:
            n = int(self.headers.get("Content-Length", "-1"))
            if n <= 0 or n > MAX_REQUEST_BYTES:
                self.respond(413, b'{"error":"request_size_limit"}')
                return
            data = json.loads(self.rfile.read(n))
            if data.get("model") != MODEL:
                self.respond(400, b'{"error":"model_not_allowed"}')
                return
            # Force limited model generation even if agent requests more.
            data.pop("max_completion_tokens", None)
            data["max_tokens"] = min(int(data.get("max_tokens") or MAX_OUTPUT_TOKENS), MAX_OUTPUT_TOKENS)
            # Preserve provider's SSE streaming contract.
            outgoing = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
            if len(outgoing) > MAX_REQUEST_BYTES:
                self.respond(413, b'{"error":"request_size_limit"}')
                return
            # Overestimate input tokens with request bytes, then assume full output budget.
            predicted = (len(outgoing) * 0.13 + MAX_OUTPUT_TOKENS * 0.28) / 1_000_000
            with LOCK:
                if counter["requests"] >= MAX_REQUESTS or counter["worst_usd"] + predicted > BUDGET_USD_UPPER:
                    self.respond(429, b'{"error":"local_budget_limit"}')
                    return
                counter["requests"] += 1
                counter["worst_usd"] += predicted
                seq = counter["requests"]
            conn = http.client.HTTPSConnection("api.siliconflow.cn", timeout=90)
            try:
                conn.request("POST", "/v1/chat/completions", body=outgoing,
                    headers={"Content-Type":"application/json",
                             "Accept":"text/event-stream",
                             "Authorization":"Bearer " + SECRET})
                remote = conn.getresponse()
                raw = remote.read(3_000_001)
                if len(raw) > 3_000_000:
                    raise RuntimeError("response_size_limit")
                status = remote.status
                kind = remote.getheader("Content-Type", "text/event-stream")
                if status == 200:
                    for line in raw.splitlines():
                        if not line.startswith(b"data:"):
                            continue
                        try:
                            msg = json.loads(line[5:])
                            usage = msg.get("usage") or {}
                            if usage:
                                with LOCK:
                                    counter["reported_input_tokens"] += usage.get("prompt_tokens", 0) or 0
                                    counter["reported_output_tokens"] += usage.get("completion_tokens", 0) or 0
                        except (ValueError, TypeError):
                            pass
                else:
                    with LOCK:
                        counter["errors"] += 1
                records.append({"request":seq,"http":status,"bytes":len(outgoing)})
                # Do not forward arbitrary external endpoints or authentication headers.
                self.respond(status, raw, kind=kind)
            finally:
                conn.close()
        except Exception as exc:
            with LOCK:
                counter["errors"] += 1
            # No request body, model response, or credentials in logs.
            print("D077_PROXY_ERROR:" + type(exc).__name__, flush=True)
            try:
                self.respond(502, b'{"error":"upstream_failed"}')
            except (BrokenPipeError, ConnectionResetError):
                pass

def memory_snapshot():
    result = {}
    for label in ("MEMORY.md", "USER.md"):
        p = "/opt/data/memories/" + label
        read = cmd("docker","exec",CONTAINER,"/bin/sh","-c","cat " + p + " 2>/dev/null || true")
        result[label] = read.stdout[:6000]
    return result

def wait_gateway():
    for _ in range(65):
        try:
            status, data = api_json("/health")
            if status == 200 and data.get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Hermes API health check failed")

def one_run(case, sid, prompt):
    started = time.monotonic()
    try:
        s, answer = api_json("/v1/runs", {"input":prompt,"session_id":sid}, timeout=10)
        if s != 202:
            raise RuntimeError("run not accepted")
        run_id = answer["run_id"]
        state = "running"
        final = {}
        for _ in range(42):
            time.sleep(2)
            _, final = api_json("/v1/runs/" + run_id)
            state = final.get("status")
            if state in ("completed","failed","cancelled","interrupted"):
                break
        snippet = str(final.get("output") or "")[:260]
        return {"case":case,"status":state,"seconds":round(time.monotonic()-started,1),
                "output":snippet,"usage":final.get("usage") or {},
                "runtime":final.get("runtime") or {}}
    except Exception as exc:
        return {"case":case,"status":"harness_error","detail":type(exc).__name__}

def main():
    if len(SECRET) < 12:
        raise RuntimeError("SILICONFLOW_D077_KEY secret missing; no provider requests made")
    created_net = created_container = None
    proxy = None
    try:
        cmd("docker","network","create","--internal","--subnet","172.29.77.0/24",
            "--gateway",GATEWAY,NETWORK)
        created_net = NETWORK
        proxy = ThreadingHTTPServer((GATEWAY,PROXY_PORT),Proxy)
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        r = cmd("docker","run","--rm","-d","--name",CONTAINER,
            "--network",NETWORK,"--user","10001:10001",
            "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
            "--memory","2g","--cpus","1","--pids-limit","128",
            "--tmpfs","/tmp:rw,nosuid,nodev,size=96m,mode=1777",
            "--tmpfs","/opt/data:rw,nosuid,nodev,size=512m,mode=0700,uid=10001,gid=10001",
            "-e","HERMES_HOME=/opt/data","-e","HOME=/opt/data",
            "-e","API_SERVER_ENABLED=true","-e","API_SERVER_HOST=0.0.0.0",
            "-e","API_SERVER_KEY="+API_KEY,
            "-p","127.0.0.1:%s:8642" % HERMES_PORT,
            "--entrypoint","/bin/sh",IMAGE,"-c","sleep 1100")
        created_container = CONTAINER
        conf = """model:
  provider: custom
  default: deepseek-ai/DeepSeek-V4-Flash
  base_url: http://172.29.77.1:19001/v1
  api_key: runner-proxy-placeholder
  api_mode: chat_completions
memory:
  memory_enabled: true
  user_profile_enabled: true
  write_approval: false
agent:
  enabled_toolsets: [memory]
  max_iterations: 3
  max_tool_calls: 4
auxiliary:
  background_review:
    enabled: true
mcp_servers: {}
"""
        cmd("docker","exec","-i",CONTAINER,"/bin/sh","-c",
            "umask 077; cat > /opt/data/config.yaml",input=conf)
        # Verify network paths: container reaches only ephemeral bridge gateway.
        probe = cmd("docker","exec",CONTAINER,"/opt/hermes/.venv/bin/python3","-c",
            "import urllib.request;print(urllib.request.urlopen('http://172.29.77.1:19001/health',timeout=4).status)",
            check=False)
        if probe.returncode != 0 or probe.stdout.strip() != "200":
            raise RuntimeError("isolated runner-side proxy unreachable")
        cmd("docker","exec","-d",CONTAINER,"/bin/sh","-c",
            "/opt/hermes/.venv/bin/hermes gateway run --no-supervise >/opt/data/gateway.log 2>&1",
            timeout=10)
        try:
            wait_gateway()
        except Exception:
            diag = cmd("docker","exec",CONTAINER,"/bin/sh","-c",
                "tail -n 65 /opt/data/gateway.log 2>/dev/null || true",check=False)
            # Container has no real provider key, only a synthetic placeholder.
            for line in diag.stdout.splitlines()[-40:]:
                if any(word in line.lower() for word in
                       ("error", "fail", "traceback", "exception", "api server",
                        "port", "gateway", "usage", "invalid", "permission")):
                    print("D077_GATEWAY_DIAG", line[:350], flush=True)
            raise

        # 15 synthetic turns: learning, natural cross-session recall, correction,
        # relevance, unknown exact facts. Never insert real-person information.
        cases = [
            ("learn_format","a","For my future project summaries, I prefer bullet points and very short sentences."),
            ("learn_hobby","b","I organize a fictional neighborhood pottery club called Cedar Kiln. We make small bowls."),
            ("learn_units","c","For measurement, I prefer metric units instead of imperial units."),
            ("learn_schedule","d","My fictional Cedar Kiln club usually meets on the first Saturday of each month."),
            ("learn_work","e","I'm coordinating beginner pottery workshops as a volunteer, not as a paid job."),
            ("recall_format","f","How should you format my next project summary?"),
            ("recall_hobby","g","What kind of activities would suit the club I organize?"),
            ("recall_units","h","Which measurement units should you use when describing material quantities for me?"),
            ("relevance_math","i","What is 7 plus 9?"),
            ("correct_format","j","My writing preference has changed. I no longer want bullet points in project summaries. Use short connected paragraphs instead."),
            ("recall_correction","k","How do I currently want project summaries formatted?"),
            ("recall_old_new","l","Did my summary formatting preference change? What is current?"),
            ("unknown_receipt","m","What was the exact invoice amount on fictional receipt CEDAR-991? If you lack a source, say so."),
            ("recall_schedule","n","When does my pottery club normally meet?"),
            ("relevance_general","o","Name two planets in our solar system.")
        ]
        completed = []
        for case, session, question in cases:
            if counter["requests"] >= MAX_REQUESTS - 3:
                break
            res = one_run(case, "d077-" + session, question)
            completed.append(res)
            # No raw private content: all snippets and stored memory are synthetic.
            print("D077_CASE",json.dumps(res,ensure_ascii=False),flush=True)
            if res["status"] != "completed":
                print("D077_STOP_AFTER_UNSUCCESSFUL_RUN",case,res["status"],flush=True)
                break
        mem = memory_snapshot()
        # Report only synthetic memory-derived flags, not files or credentials.
        merged = (mem["MEMORY.md"] + "\n" + mem["USER.md"]).lower()
        flags = {"format": "bullet" in merged or "paragraph" in merged,
                 "club": "cedar kiln" in merged or "pottery" in merged,
                 "metric": "metric" in merged,
                 "correction": "paragraph" in merged and "no longer" in merged or
                               "short connected paragraph" in merged,
                 "memory_chars": len(mem["MEMORY.md"]),
                 "user_chars": len(mem["USER.md"])}
        print("D077_FINAL",json.dumps({"case_count":len(completed),
                "statuses":[x["status"] for x in completed],
                "memory":flags,"provider":counter,"provider_http":records},
                ensure_ascii=False),flush=True)
        if not completed:
            raise RuntimeError("no_hermes_runs")
    finally:
        if created_container:
            cmd("docker","rm","-f",created_container,timeout=30,check=False)
        if proxy:
            proxy.shutdown()
            proxy.server_close()
        if created_net:
            cmd("docker","network","rm",created_net,timeout=30,check=False)

if __name__ == "__main__":
    main()
