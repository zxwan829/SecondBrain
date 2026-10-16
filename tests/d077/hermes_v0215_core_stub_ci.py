#!/usr/bin/env python3
"""Isolated Hermes v0.21.5 + SecondBrain Core contract test using a local stub.

This harness sends synthetic requests only. Hermes runs in an internal Docker
network with no external route; a runner-host OpenAI-compatible stub is its only
provider. It never reads credentials or production paths.
"""
from __future__ import annotations

import http.server
import json
import os
import pathlib
import re
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import httpx


IMAGE = "nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db"
EXPECTED_IMAGE_ID = "sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6"
EXPECTED_REVISION = "749220ef0007f8d87bd1531f1c24b0fe93816385"
RUN_SUFFIX = f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
NETWORK = f"d077-v0215-core-{RUN_SUFFIX}"
CONTAINER = f"d077-v0215-hermes-{RUN_SUFFIX}"
GATEWAY = "172.29.78.1"
SUBNET = "172.29.78.0/24"
STUB_PORT = 19002
HERMES_PORT = 8642
CORE_PORT = 8000
STUB_NAME = f"d077-v0215-stub-{RUN_SUFFIX}"
CORE_CONTAINER = f"d077-v0215-core-{RUN_SUFFIX}"
OFF_CORE_CONTAINER = f"d077-v0215-core-off-{RUN_SUFFIX}"
CORE_IMAGE = f"d077-v0215-core:{RUN_SUFFIX}"
MODEL = "d077-deterministic-stub"
API_KEY = "d077-hermes-synthetic-api-key-only"
API_SERVER_KEY = "d077-hermes-api-server-synthetic-key"
APP_PASSWORD = "d077-synthetic-owner-password"

CAPTURE_LOCK = threading.Lock()
CAPTURED = []
STUB_COUNTER = {"calls": 0, "fail_remaining": 0, "delay_next": False}
STUB_BLOCKED = threading.Event()
STUB_RELEASE = threading.Event()


def run(*args, timeout=60, check=True, capture=True):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
                            timeout=timeout, check=False)
    if check and result.returncode:
        raise RuntimeError(f"command_failed:{pathlib.Path(args[0]).name}:{result.returncode}")
    return result


class StubHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        return

    def respond(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        if self.path in {"/health", "/__test/health"}:
            self.respond(200, b'{"status":"ok"}')
        elif self.path == "/__test/state":
            with CAPTURE_LOCK:
                state = {"calls": STUB_COUNTER["calls"], "request_count": len(CAPTURED),
                         "requests": list(CAPTURED), "blocked": STUB_BLOCKED.is_set()}
            self.respond(200, json.dumps(state).encode())
        elif self.path == "/v1/models":
            body = {"object": "list", "data": [{"id": MODEL, "object": "model"}]}
            self.respond(200, json.dumps(body).encode())
        else:
            self.respond(404, b'{"error":"route_not_allowed"}')

    def do_POST(self):
        if self.path == "/__test/control":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048:
                    self.respond(413, b'{"error":"control_size_limit"}')
                    return
                control = json.loads(self.rfile.read(size))
                with CAPTURE_LOCK:
                    if "fail_remaining" in control:
                        STUB_COUNTER["fail_remaining"] = int(control["fail_remaining"])
                    if "delay_next" in control:
                        STUB_COUNTER["delay_next"] = bool(control["delay_next"])
                if control.get("reset_blocked"):
                    STUB_BLOCKED.clear()
                    STUB_RELEASE.clear()
                if control.get("release"):
                    STUB_RELEASE.set()
                self.respond(200, b'{"ok":true}')
            except Exception as exc:
                self.respond(400, json.dumps({"error": type(exc).__name__}).encode())
            return
        if self.path != "/v1/chat/completions":
            self.respond(403, b'{"error":"route_not_allowed"}')
            return
        try:
            if self.headers.get("Authorization") != f"Bearer {API_KEY}":
                self.respond(401, b'{"error":"invalid_synthetic_key"}')
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 100_000:
                self.respond(413, b'{"error":"request_size_limit"}')
                return
            payload = json.loads(self.rfile.read(size))
            if payload.get("model") != MODEL:
                self.respond(400, b'{"error":"model_not_allowed"}')
                return
            with CAPTURE_LOCK:
                CAPTURED.append(payload)
                STUB_COUNTER["calls"] += 1
                fail = STUB_COUNTER["fail_remaining"] > 0
                if fail:
                    STUB_COUNTER["fail_remaining"] -= 1
                delay = STUB_COUNTER["delay_next"]
                STUB_COUNTER["delay_next"] = False
            if delay:
                STUB_BLOCKED.set()
                STUB_RELEASE.wait(timeout=15)
            if fail:
                self.respond(503, b'{"error":"synthetic_provider_failure"}')
                return
            created = int(time.time())
            response_id = "chatcmpl-d077-stub"
            if payload.get("stream") is True:
                chunks = [
                    {"id": response_id, "object": "chat.completion.chunk", "created": created,
                     "model": MODEL, "choices": [{"index": 0,
                     "delta": {"role": "assistant", "content": "Synthetic deterministic response."},
                     "finish_reason": None}]},
                    {"id": response_id, "object": "chat.completion.chunk", "created": created,
                     "model": MODEL, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ]
                body = b"".join((b"data: " + json.dumps(item).encode() + b"\n\n") for item in chunks)
                body += b"data: [DONE]\n\n"
                self.respond(200, body, "text/event-stream")
            else:
                body = {"id": response_id, "object": "chat.completion", "created": created,
                        "model": MODEL, "choices": [{"index": 0,
                        "message": {"role": "assistant", "content": "Synthetic deterministic response."},
                        "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 4, "total_tokens": 5}}
                self.respond(200, json.dumps(body).encode())
        except Exception as exc:
            self.respond(500, json.dumps({"error": type(exc).__name__}).encode())


def probe_http(url, *, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=3) as response:
            return f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        return f"http_{exc.code}"
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError):
            return "connection_refused"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "connect_or_read_timeout"
        return f"url_error_{type(reason).__name__}"
    except (TimeoutError, socket.timeout):
        return "connect_or_read_timeout"
    except ConnectionRefusedError:
        return "connection_refused"
    except Exception as exc:
        return f"probe_error_{type(exc).__name__}"


class HealthProbeError(RuntimeError):
    def __init__(self, summary):
        super().__init__("hermes_health_probe_failed")
        self.summary = summary


def wait_http(url, *, headers=None, expected=200, timeout=90):
    deadline = time.monotonic() + timeout
    counts = {}
    last = "not_probed"
    while time.monotonic() < deadline:
        last = probe_http(url, headers=headers)
        counts[last] = counts.get(last, 0) + 1
        if last == f"http_{expected}":
            return {"probe": "host_published", "result": last, "counts": counts}
        time.sleep(1)
    if any(key.startswith("http_") for key in counts):
        category = "http_status_not_ok"
    elif counts.get("connection_refused") == sum(counts.values()):
        category = "host_connection_refused"
    elif any("timeout" in key for key in counts):
        category = "connection_or_response_timeout"
    else:
        category = "no_successful_http_response"
    raise HealthProbeError({"probe": "host_published", "category": category,
                            "last": last, "counts": counts, "timeout_seconds": timeout})


def capture_hermes_diagnostics(health_summary):
    """Emit bounded startup diagnostics without exposing config or credentials."""
    state = run("docker", "inspect", CONTAINER, "--format", "{{json .State}}", check=False)
    try:
        raw_state = json.loads(state.stdout) if state.returncode == 0 else {}
        state_json = {key: raw_state.get(key) for key in
                      ("Status", "Running", "ExitCode", "OOMKilled", "StartedAt", "FinishedAt")}
        state_json["error_present"] = bool(raw_state.get("Error"))
        if state.returncode != 0:
            state_json = {"inspect": "unavailable"}
    except json.JSONDecodeError:
        state_json = {"inspect": "invalid_json"}

    local_probe_code = r'''import json, os, socket, urllib.error, urllib.request
try:
    req=urllib.request.Request("http://127.0.0.1:8642/health", headers={"Authorization":"Bearer "+os.environ.get("API_SERVER_KEY", "")})
    with urllib.request.urlopen(req, timeout=2) as r: result="http_%d" % r.status
except urllib.error.HTTPError as e: result="http_%d" % e.code
except urllib.error.URLError as e:
    reason=e.reason
    result="connection_refused" if isinstance(reason, ConnectionRefusedError) else ("timeout" if isinstance(reason, (TimeoutError, socket.timeout)) else "url_error_"+type(reason).__name__)
except (TimeoutError, socket.timeout): result="timeout"
except ConnectionRefusedError: result="connection_refused"
except Exception as e: result="probe_error_"+type(e).__name__
print(result)'''
    local = run("docker", "exec", CONTAINER, "/opt/hermes/.venv/bin/python3", "-c",
                local_probe_code, check=False)
    local_result = local.stdout.strip() if local.returncode == 0 else "exec_unavailable"
    host_result = probe_http(f"http://127.0.0.1:{HERMES_PORT}/health",
                             headers={"Authorization": f"Bearer {API_SERVER_KEY}"})

    inspect_code = r'''import json, os, pathlib, subprocess
paths=["/opt/hermes/.venv/bin/hermes", "/opt/data", "/opt/data/config.yaml", "/opt/data/gateway.log"]
meta={}
for value in paths:
 p=pathlib.Path(value)
 try:
  s=p.stat(); meta[value]={"exists":True,"mode":oct(s.st_mode & 0o777),"uid":s.st_uid,"gid":s.st_gid,"is_dir":p.is_dir()}
 except Exception as e: meta[value]={"exists":False,"error":type(e).__name__}
procs=subprocess.run(["ps","-eo","pid=,stat=,comm="],text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
processes=[line.strip() for line in procs.stdout.splitlines() if "hermes" in line.lower() or "gateway" in line.lower()][:12]
port_hex=f"{8642:04X}"
listeners=[]
for name in ("/proc/net/tcp","/proc/net/tcp6"):
 try:
  for line in pathlib.Path(name).read_text().splitlines()[1:]:
   cols=line.split()
   if len(cols)>3 and cols[1].rsplit(":",1)[-1].upper()==port_hex and cols[3]=="0A": listeners.append(name)
 except Exception: pass
try:
 lines=pathlib.Path("/opt/data/gateway.log").read_text(errors="replace").splitlines()
 excerpt="\n".join(lines[-40:])[-6000:]
except Exception as e: excerpt="<unavailable:"+type(e).__name__+">"
print(json.dumps({"euid":os.geteuid(),"paths":meta,"processes":processes,"port_8642_listening":bool(listeners),"listener_tables":listeners,"gateway_log_excerpt":excerpt},sort_keys=True))'''
    details = run("docker", "exec", CONTAINER, "/opt/hermes/.venv/bin/python3", "-c",
                  inspect_code, check=False)
    payload = {}
    if details.returncode == 0:
        try:
            payload = json.loads(details.stdout)
        except json.JSONDecodeError:
            payload = {"container_diagnostics": "invalid_json"}
    else:
        payload = {"container_diagnostics": "exec_unavailable"}

    excerpt = payload.pop("gateway_log_excerpt", "")
    for secret in (API_KEY, API_SERVER_KEY, APP_PASSWORD):
        excerpt = excerpt.replace(secret, "[REDACTED]")
    excerpt = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", excerpt)
    excerpt = re.sub(r"(?i)(api[_-]?server[_-]?key|api[_-]?key|token|secret|password)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", excerpt)
    excerpt = re.sub(r"https?://\S+", "[URL_REDACTED]", excerpt)
    excerpt = "\n".join(excerpt.splitlines()[-30:])[:4000]
    payload["gateway_log_excerpt_redacted"] = excerpt
    print(json.dumps({"event": "hermes_startup_diagnostic", "health": health_summary,
                      "container_local_probe": local_result, "host_published_probe": host_result,
                      "container_state": state_json, "details": payload}, sort_keys=True), flush=True)


def create_hermes(container_data, uid, gid):
    run("docker", "run", "-d", "--name", CONTAINER, "--network", NETWORK,
        "--network-alias", "hermes",
        "--label", "d077.issue=7", "--label", f"d077.run={RUN_SUFFIX}",
        "--user", f"{uid}:{gid}", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--memory", "2g", "--cpus", "1",
        "--pids-limit", "128", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=96m,mode=1777",
        "--mount", f"type=bind,src={container_data},dst=/opt/data",
        "-e", "HERMES_HOME=/opt/data", "-e", "HOME=/opt/data",
        "-e", f"API_SERVER_KEY={API_SERVER_KEY}", "-e", "API_SERVER_HOST=0.0.0.0",
        "-e", "API_SERVER_PORT=8642", "--entrypoint", "/bin/sh", IMAGE,
        "-c", "sleep 1200")
    config = f"""model:
  provider: custom
  default: {MODEL}
  base_url: http://stub:{STUB_PORT}/v1
  api_key: {API_KEY}
  api_mode: chat_completions
memory:
  memory_enabled: false
  user_profile_enabled: false
agent:
  enabled_toolsets: []
  max_iterations: 1
  max_tool_calls: 1
auxiliary:
  background_review:
    enabled: false
mcp_servers: {{}}
"""
    # Config is synthetic and written only in this run's private temporary home.
    proc = subprocess.run(["docker", "exec", "-i", CONTAINER, "/bin/sh", "-c",
                           "umask 077; cat > /opt/data/config.yaml"],
                          input=config, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    if proc.returncode:
        raise RuntimeError("hermes_profile_write_failed")
    run("docker", "exec", "-d", CONTAINER, "/bin/sh", "-c",
        "/opt/hermes/.venv/bin/hermes gateway run --no-supervise >/opt/data/gateway.log 2>&1", timeout=10)


def start_core_container(temp_root, script_path, uid, gid, *, memory_enabled=True, label="core"):
    data_root = temp_root / f"{label}-data"
    data_root.mkdir(mode=0o700)
    roots = {name: data_root / name for name in ("review", "knowledge", "promote", "raw", "memory")}
    for path in roots.values():
        if path.name.endswith("memory") and not memory_enabled:
            continue
        path.mkdir(mode=0o700)
        path.chmod(0o700)
    pass_file = data_root / "app-password"
    key_file = data_root / "hermes-key"
    for path, content in ((pass_file, APP_PASSWORD), (key_file, API_SERVER_KEY)):
        path.write_text(content + "\n", encoding="utf-8")
        path.chmod(0o600)
    core_home = data_root / "home"
    core_home.mkdir(mode=0o700)
    env = {
        "HOME": "/test-data/home", "LANG": "C.UTF-8", "PORT": str(CORE_PORT),
        "SB_REVIEW_ROOT": "/test-data/review", "SB_KNOWLEDGE_ROOT": "/test-data/knowledge",
        "SB_PROMOTE_STATE_ROOT": "/test-data/promote", "SB_CAPTURE_RAW_ROOT": "/test-data/raw",
        "SB_DASHBOARD_ORIGINS": f"http://127.0.0.1:{CORE_PORT}",
        "SB_CORE_ALLOWED_HOSTS": "127.0.0.1", "SB_APP_PASSWORD_FILE": "/test-data/app-password",
        "SB_HERMES_API_KEY_FILE": "/test-data/hermes-key", "SB_HERMES_API_URL": "http://hermes:8642",
        "SB_PERSONAL_MEMORY_ENABLED": "true" if memory_enabled else "false",
        "SB_PERSONAL_LEARNING_ENABLED": "true" if memory_enabled else "false",
        "SB_PERSONAL_MEMORY_ROOT": "/test-data/memory", "SB_PROMOTE_ENABLED": "false",
        "SB_ORGANIZER_MODEL_ENABLED": "false", "SB_ORGANIZER_SCHEDULER_ENABLED": "false",
        "API_SERVER_KEY": API_SERVER_KEY, "D077_STUB_URL": "http://stub:19002",
    }
    name = CORE_CONTAINER if memory_enabled else OFF_CORE_CONTAINER
    alias = "core" if memory_enabled else "core-off"
    args = ["docker", "run", "-d", "--name", name, "--network", NETWORK, "--network-alias", alias,
            "--label", "d077.issue=7", "--label", f"d077.run={RUN_SUFFIX}",
            "--user", f"{uid}:{gid}", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "0.75",
            "--pids-limit", "128", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=96m,mode=1777",
            "--mount", f"type=bind,src={data_root},dst=/test-data",
            "--mount", f"type=bind,src={script_path},dst=/tmp/harness.py,readonly"]
    for key, value in env.items():
        args.extend(["-e", f"{key}={value}"])
    args.extend([CORE_IMAGE, "/bin/sh", "-c",
                 "python -m secondbrain_core >/test-data/core.log 2>&1 & exec sleep 1200"])
    run(*args)
    return roots, data_root


def model_requests_since(index):
    return stub_state()["requests"][index:]


def stub_state():
    url = os.environ.get("D077_STUB_URL", "http://stub:19002") + "/__test/state"
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def control_stub(payload):
    url = os.environ.get("D077_STUB_URL", "http://stub:19002") + "/__test/control"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("stub_control_failed")


def wait_stub_blocked(timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stub_state().get("blocked"):
            return True
        time.sleep(0.2)
    return False


def contains_text(request, needle):
    messages = request.get("messages", [])
    return needle in "\n".join(str(row.get("content", "")) for row in messages if isinstance(row, dict))


def start_chat(client, session_id, text, key):
    response = client.post(f"/api/chat/sessions/{session_id}/runs", json={"input": text},
                           headers={"Idempotency-Key": key})
    response.raise_for_status()
    return response.json()["run_id"]


def run_chat(client, session_id, text, key):
    started = time.monotonic()
    run_id = start_chat(client, session_id, text, key)
    events = client.get(f"/api/chat/runs/{run_id}/events", timeout=180)
    events.raise_for_status()
    state = client.get(f"/api/chat/runs/{run_id}")
    state.raise_for_status()
    return run_id, state.json().get("status"), round(time.monotonic() - started, 3), events.text


def direct_messages(session_id, *, order, limit=100, offset=0):
    response = httpx.get(f"http://hermes:{HERMES_PORT}/api/sessions/{session_id}/messages",
                         params={"inline_images": "false", "limit": limit, "offset": offset, "order": order},
                         headers={"Authorization": f"Bearer {API_SERVER_KEY}"}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", payload.get("messages", [])) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("hermes_message_page_shape_invalid")
    return rows


def enabled_scenario():
    started = time.monotonic()
    roots = {"memory": pathlib.Path(os.environ["SB_PERSONAL_MEMORY_ROOT"])}
    client = httpx.Client(base_url=f"http://127.0.0.1:{CORE_PORT}", timeout=30)
    login = client.post("/api/auth/login", json={"password": APP_PASSWORD},
                        headers={"Origin": f"http://127.0.0.1:{CORE_PORT}"})
    login.raise_for_status()
    created = client.post("/api/chat/sessions", json={})
    created.raise_for_status()
    session_a = created.json()["session_id"]

    initial = "I prefer concise summaries and metric units."
    before_calls = stub_state()["request_count"]
    run_a, status_a, latency_a, events_a = run_chat(client, session_a, initial, "d077-v0215-learn-a")
    if status_a != "completed" or "run.completed" not in events_a:
        raise RuntimeError("initial_run_not_completed")
    req_a = model_requests_since(before_calls)
    if not req_a or contains_text(req_a[-1], "personal_memory_json"):
        raise RuntimeError("unexpected_first_run_memory_context")
    items = client.get("/api/personal-memory").json()["items"]
    learned = {row["content"]["text"]: row for row in items}
    if not {"concise summaries", "metric units"}.issubset(learned):
        raise RuntimeError("synthetic_learning_candidates_missing")
    message_page = client.get(f"/api/chat/sessions/{session_a}/messages").json()
    messages = message_page.get("messages", [])
    source_rows = [row for row in messages if row.get("role") == "user" and row.get("text") == initial]
    if not source_rows or not source_rows[0].get("id") or not source_rows[0].get("timestamp"):
        raise RuntimeError("persisted_source_message_contract_missing")
    if any(row.get("source_ref") != f"{session_a}:{source_rows[0]['id']}" for row in learned.values()
           if row.get("content", {}).get("text") in {"concise summaries", "metric units"}):
        raise RuntimeError("memory_source_ref_mismatch")

    latest = direct_messages(session_a, order="latest")
    oldest = direct_messages(session_a, order="oldest")
    latest_ids = [str(row.get("id", "")) for row in latest]
    oldest_ids = [str(row.get("id", "")) for row in oldest]
    if not latest_ids or latest_ids != list(reversed(oldest_ids)) or len(set(latest_ids)) != len(latest_ids):
        raise RuntimeError("message_order_or_stable_id_contract_failed")
    first_page = direct_messages(session_a, order="latest", limit=1, offset=0)
    if not first_page or str(first_page[0].get("id", "")) != latest_ids[0]:
        raise RuntimeError("message_pagination_contract_failed")

    # Same text creates a new persistent user message but must not duplicate memory.
    memory_count_before_repeat = len(client.get("/api/personal-memory").json()["items"])
    run_repeat, status_repeat, latency_repeat, events_repeat = run_chat(
        client, session_a, initial, "d077-v0215-duplicate-text-repeat")
    if status_repeat != "completed" or "run.completed" not in events_repeat:
        raise RuntimeError("repeated_text_run_failed")
    repeated_page = client.get(f"/api/chat/sessions/{session_a}/messages").json()
    repeated_users = [row for row in repeated_page.get("messages", []) if row.get("role") == "user"]
    repeated_ids = [str(row.get("id", "")) for row in repeated_users if row.get("text") == initial]
    if len(repeated_ids) < 2 or repeated_ids[0] == repeated_ids[1]:
        raise RuntimeError("duplicate_text_message_ids_not_distinct")
    if len(client.get("/api/personal-memory").json()["items"]) != memory_count_before_repeat:
        raise RuntimeError("duplicate_text_created_duplicate_memory")

    session_b = client.post("/api/chat/sessions", json={}).json()["session_id"]
    related = "How should you format my summaries and units?"
    before_calls = stub_state()["request_count"]
    run_b, status_b, latency_b, events_b = run_chat(client, session_b, related, "d077-v0215-recall-b")
    req_b = model_requests_since(before_calls)
    if status_b != "completed" or "run.completed" not in events_b or not req_b:
        raise RuntimeError("cross_session_run_failed")
    if not contains_text(req_b[-1], "personal_memory_json") or not contains_text(req_b[-1], "concise summaries"):
        raise RuntimeError("cross_session_instructions_not_observed_by_stub")
    if not contains_text(req_b[-1], related):
        raise RuntimeError("input_was_rewritten_or_missing")

    correction = "I used to prefer concise summaries, but now I prefer concise paragraphs."
    run_c, status_c, latency_c, events_c = run_chat(client, session_a, correction, "d077-v0215-correct-c")
    if status_c != "completed" or "run.completed" not in events_c:
        raise RuntimeError("correction_run_failed")
    current = client.get("/api/personal-memory").json()["items"]
    active_text = {row.get("content", {}).get("text") for row in current}
    if "concise summaries" in active_text or "concise paragraphs" not in active_text:
        raise RuntimeError("correction_state_not_updated")
    session_corrected = client.post("/api/chat/sessions", json={}).json()["session_id"]
    before_calls = stub_state()["request_count"]
    corrected_question = "How should you format my summaries now?"
    run_d, status_d, latency_d, events_d = run_chat(
        client, session_corrected, corrected_question, "d077-v0215-correct-recall-d")
    req_d = model_requests_since(before_calls)
    if status_d != "completed" or "run.completed" not in events_d or not req_d:
        raise RuntimeError("corrected_recall_run_failed")
    corrected_prompt = "\n".join(str(row.get("content", ""))
                                  for row in req_d[-1].get("messages", []))
    if "concise paragraphs" not in corrected_prompt or "concise summaries" in corrected_prompt:
        raise RuntimeError("corrected_context_stale")

    # Revoke, expiry, and unconfirmed inference stay out of model-facing context.
    metric_row = next(row for row in current if row.get("content", {}).get("text") == "metric units")
    revoked = client.post(f"/api/personal-memory/{metric_row['memory_id']}/revoke", json={
        "source_type": "user_confirmed", "source_ref": "synthetic-correction",
    })
    revoked.raise_for_status()
    expired = client.post("/api/personal-memory", json={
        "content": {"text": "Prefers imaginary unit labels"}, "category": "preference",
        "fact_kind": "user_stated", "source_type": "user_confirmed", "source_ref": "synthetic-expiry",
        "expires_at": "2000-01-01T00:00:00Z",
    })
    expired.raise_for_status()
    inferred = client.post("/api/personal-memory", json={
        "content": {"text": "Prefers cobalt project names"}, "category": "preference",
        "fact_kind": "inference", "source_type": "session_note", "source_ref": "synthetic-inference",
    })
    inferred.raise_for_status()
    session_c = client.post("/api/chat/sessions", json={}).json()["session_id"]
    before_calls = stub_state()["request_count"]
    gated_question = "Which metric units and imaginary unit labels do I prefer?"
    run_e, status_e, latency_e, events_e = run_chat(
        client, session_c, gated_question, "d077-v0215-gated-context-e")
    req_e = model_requests_since(before_calls)
    if status_e != "completed" or "run.completed" not in events_e or not req_e:
        raise RuntimeError("gated_context_run_failed")
    gated_prompt = "\n".join(str(row.get("content", ""))
                              for row in req_e[-1].get("messages", []))
    if ("metric units" in gated_prompt or "imaginary unit labels" in gated_prompt
            or "cobalt project names" in gated_prompt):
        raise RuntimeError("inactive_or_inferred_memory_injected")

    # Provider failure is deterministic and must not teach from a failed run.
    failure_session = client.post("/api/chat/sessions", json={}).json()["session_id"]
    control_stub({"fail_remaining": 20})
    run_failed, status_failed, latency_failed, events_failed = run_chat(
        client, failure_session, "I prefer neon section headings.", "d077-v0215-provider-failure")
    control_stub({"fail_remaining": 0})
    if status_failed not in {"failed", "interrupted"}:
        raise RuntimeError("provider_failure_did_not_fail_run")
    if "neon section headings" in {row.get("content", {}).get("text")
                                   for row in client.get("/api/personal-memory").json()["items"]}:
        raise RuntimeError("failed_run_was_learned")

    # Stop a Run while its provider request is blocked at the local stub.
    stop_session = client.post("/api/chat/sessions", json={}).json()["session_id"]
    control_stub({"reset_blocked": True, "delay_next": True})
    stop_started = time.monotonic()
    run_stopped = start_chat(client, stop_session, "I prefer amber section headers.",
                             "d077-v0215-stop-run")
    if not wait_stub_blocked(timeout=12):
        raise RuntimeError("stub_did_not_observe_stop_test_request")
    stop_response = client.post(f"/api/chat/runs/{run_stopped}/stop", json={})
    stop_response.raise_for_status()
    control_stub({"release": True})
    stop_status = "unknown"
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        polled = client.get(f"/api/chat/runs/{run_stopped}")
        if polled.status_code == 200:
            stop_status = polled.json().get("status", "unknown")
            if stop_status in {"stopped", "cancelled", "canceled", "failed", "interrupted", "completed"}:
                break
        time.sleep(0.5)
    if stop_status in {"unknown", "running", "queued", "started", "completed"}:
        raise RuntimeError("stop_run_terminal_state_unverified")
    if "amber section headers" in {row.get("content", {}).get("text")
                                    for row in client.get("/api/personal-memory").json()["items"]}:
        raise RuntimeError("stopped_run_was_learned")
    latency_stop = round(time.monotonic() - stop_started, 3)

    session_unrelated = client.post("/api/chat/sessions", json={}).json()["session_id"]
    before_calls = stub_state()["request_count"]
    run_f, status_f, latency_f, events_f = run_chat(
        client, session_unrelated, "What is 13 plus 5?", "d077-v0215-unrelated-f")
    req_f = model_requests_since(before_calls)
    if status_f != "completed" or "run.completed" not in events_f or not req_f:
        raise RuntimeError("unrelated_run_failed")
    if contains_text(req_f[-1], "personal_memory_json"):
        raise RuntimeError("unrelated_topic_received_memory_context")

    # A deterministic exact fact is present only as a source-verification pointer.
    fact = client.post("/api/personal-memory", json={
        "content": {"text": "Project code is NOVA-17"}, "category": "fact",
        "fact_kind": "user_stated", "source_type": "original_file", "source_ref": "project.md",
        "exact": True,
    })
    fact.raise_for_status()
    session_f = client.post("/api/chat/sessions", json={}).json()["session_id"]
    fact_question = "What is the exact project code from my project file?"
    before_calls = stub_state()["request_count"]
    run_g, status_g, latency_g, events_g = run_chat(
        client, session_f, fact_question, "d077-v0215-fact-g")
    req_g = model_requests_since(before_calls)
    if status_g != "completed" or "run.completed" not in events_g or not req_g:
        raise RuntimeError("exact_fact_run_failed")
    fact_prompt = "\n".join(str(row.get("content", "")) for row in req_g[-1].get("messages", []))
    if "Source verification required" not in fact_prompt or "NOVA-17" in fact_prompt:
        raise RuntimeError("exact_fact_not_redacted_or_source_required")


    client.close()
    state = stub_state()
    print("D077_ENABLED_RESULT " + json.dumps({
        "status": "PASS", "source_message_id": source_rows[0]["id"],
        "initial_latest_message_ids": latest_ids, "duplicate_input_message_ids": repeated_ids[:2],
        "learned_source_refs": sorted({row.get("source_ref", "") for row in learned.values()
                                        if row.get("content", {}).get("text") in {"concise summaries", "metric units"}}),
        "run_ids": [run_a, run_repeat, run_b, run_c, run_d, run_e, run_failed, run_stopped, run_f, run_g],
        "session_count": 8, "run_count": 10,
        "run_statuses": [status_a, status_repeat, status_b, status_c, status_d, status_e, status_failed,
                         "stop:" + stop_status, status_f, status_g],
        "latency_seconds": [latency_a, latency_repeat, latency_b, latency_c, latency_d, latency_e,
                            latency_failed, latency_stop, latency_f, latency_g],
        "stub_provider_calls": state["calls"], "external_provider_calls": 0,
        "memory_file_bytes": (roots["memory"] / "personal-memory.jsonl").stat().st_size,
        "assertions": ["API_RUN_SSE", "SOURCE_MESSAGE_ID", "CORE_LEARNING", "CROSS_SESSION_INSTRUCTIONS",
                       "CORRECTION", "CORRECTED_CROSS_SESSION_RECALL", "REVOKED_EXPIRED_INFERENCE_FILTERED",
                       "UNRELATED_NO_INJECTION", "EXACT_FACT_SOURCE_REQUIRED", "DUPLICATE_TEXT_IDS_AND_PAGINATION",
                       "FAILED_RUN_NO_LEARNING", "STOP_NO_LEARNING"],
    }, sort_keys=True), flush=True)


def flags_off_scenario():
    client = httpx.Client(base_url=f"http://127.0.0.1:{CORE_PORT}", timeout=30)
    login = client.post("/api/auth/login", json={"password": APP_PASSWORD},
                        headers={"Origin": f"http://127.0.0.1:{CORE_PORT}"})
    login.raise_for_status()
    session = client.post("/api/chat/sessions", json={}).json()["session_id"]
    before = stub_state()["request_count"]
    run_id, status, latency, events = run_chat(
        client, session, "I prefer lavender section titles.", "d077-v0215-flags-off")
    requests = model_requests_since(before)
    memory_root = pathlib.Path(os.environ["SB_PERSONAL_MEMORY_ROOT"])
    if status != "completed" or "run.completed" not in events or not requests:
        raise RuntimeError("flags_off_chat_failed")
    if memory_root.exists() or contains_text(requests[-1], "personal_memory_json"):
        raise RuntimeError("flags_off_created_memory_or_injected_context")
    client.close()
    print("D077_FLAGS_OFF_RESULT " + json.dumps({
        "status": "PASS", "run_id": run_id, "run_status": status,
        "latency_seconds": latency, "provider_calls": len(requests),
        "memory_root_exists": memory_root.exists(),
    }, sort_keys=True), flush=True)


def external_tcp_probe():
    try:
        connection = socket.create_connection(("1.1.1.1", 443), timeout=2)
        connection.close()
        return "reachable"
    except Exception as exc:
        return "blocked_" + type(exc).__name__


def network_preflight():
    deadline = time.monotonic() + 90
    counts = {"core_local": {}, "core_to_hermes": {}, "core_to_stub": {}}
    core_health = hermes_health = stub_health = "not_probed"
    headers = {"Authorization": f"Bearer {API_SERVER_KEY}"}
    while time.monotonic() < deadline:
        core_health = probe_http(f"http://127.0.0.1:{CORE_PORT}/health")
        hermes_health = probe_http(f"http://hermes:{HERMES_PORT}/health", headers=headers)
        stub_health = probe_http("http://stub:19002/__test/health")
        for name, value in (("core_local", core_health), ("core_to_hermes", hermes_health),
                            ("core_to_stub", stub_health)):
            counts[name][value] = counts[name].get(value, 0) + 1
        if core_health == hermes_health == stub_health == "http_200":
            break
        time.sleep(1)
    result = {"core_local_health": core_health, "core_to_hermes_health": hermes_health,
              "core_to_stub_health": stub_health, "probe_counts": counts,
              "core_public_tcp_egress": external_tcp_probe()}
    print("D077_NETWORK_PREFLIGHT " + json.dumps(result, sort_keys=True), flush=True)
    if (core_health != "http_200" or hermes_health != "http_200" or stub_health != "http_200"
            or result["core_public_tcp_egress"] == "reachable"):
        raise RuntimeError("network_preflight_failed")


def egress_probe_mode():
    result = external_tcp_probe()
    print(json.dumps({"public_tcp_egress": result}, sort_keys=True), flush=True)
    if result == "reachable":
        raise RuntimeError("public_egress_not_blocked")


def serve_stub():
    server = http.server.ThreadingHTTPServer(("0.0.0.0", STUB_PORT), StubHandler)
    server.serve_forever()


def run_in_container(container, mode, *, check=True):
    result = run("docker", "exec", container, "python", "/tmp/harness.py", mode, check=False, timeout=900)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if check and result.returncode:
        raise RuntimeError(f"isolated_peer_failed:{mode}:{result.returncode}")
    return result


def assert_internal_only(name):
    result = run("docker", "inspect", name, "--format",
                 "{{json .NetworkSettings.Networks}}|{{json .HostConfig.PortBindings}}")
    networks, bindings = result.stdout.strip().split("|", 1)
    networks = json.loads(networks)
    bindings = json.loads(bindings)
    if set(networks) != {NETWORK} or bindings:
        raise RuntimeError(f"container_isolation_assertion_failed:{name}")


def assert_network_boundary():
    network = run("docker", "network", "inspect", NETWORK, "--format", "{{.Internal}}")
    if network.stdout.strip().lower() != "true":
        raise RuntimeError("docker_network_not_internal")
    for name in (CONTAINER, CORE_CONTAINER, STUB_NAME):
        assert_internal_only(name)
    stub_probe = run_in_container(STUB_NAME, "--egress-probe", check=False)
    if stub_probe.returncode:
        raise RuntimeError("stub_egress_preflight_failed")
    hermes_probe_code = r'''import json,socket,urllib.request
try:
 with urllib.request.urlopen("http://stub:19002/__test/health",timeout=3) as r: stub="http_%d"%r.status
except Exception as e: stub="error_"+type(e).__name__
try:
 s=socket.create_connection(("1.1.1.1",443),timeout=2); s.close(); egress="reachable"
except Exception as e: egress="blocked_"+type(e).__name__
print(json.dumps({"hermes_to_stub_health":stub,"hermes_public_tcp_egress":egress},sort_keys=True))
if stub!="http_200" or egress=="reachable": raise SystemExit(1)'''
    hermes = run("docker", "exec", CONTAINER, "/opt/hermes/.venv/bin/python3", "-c",
                 hermes_probe_code, check=False)
    if hermes.stdout:
        print("D077_HERMES_NETWORK_PREFLIGHT " + hermes.stdout.strip(), flush=True)
    if hermes.returncode:
        raise RuntimeError("hermes_network_preflight_failed")
    core = run_in_container(CORE_CONTAINER, "--network-preflight", check=False)
    if core.returncode:
        raise RuntimeError("core_network_preflight_failed")
    print(json.dumps({"docker_network_internal": True, "containers_only_on_test_network": True,
                      "host_port_bindings": False, "stub_public_egress": "blocked"}, sort_keys=True), flush=True)


def controller_main():
    if sys.platform != "linux" or not shutil.which("docker"):
        raise RuntimeError("requires_ephemeral_linux_runner_with_docker")
    inspect = run("docker", "image", "inspect", IMAGE,
                  "--format", "{{.Id}}|{{index .Config.Labels \"org.opencontainers.image.revision\"}}")
    image_id, revision = inspect.stdout.strip().split("|", 1)
    if image_id != EXPECTED_IMAGE_ID or revision != EXPECTED_REVISION:
        raise RuntimeError("fixed_hermes_image_identity_mismatch")
    core_image = run("docker", "image", "inspect", CORE_IMAGE, "--format", "{{.Id}}")

    temp_obj = tempfile.TemporaryDirectory(prefix="d077-v0215-")
    temp_root = pathlib.Path(temp_obj.name).resolve()
    temp_root.chmod(0o700)
    hermes_home = temp_root / "hermes-home"
    hermes_home.mkdir(mode=0o700)
    uid, gid = os.getuid(), os.getgid()
    created_network = False
    created_names = []
    started = time.monotonic()
    try:
        names = (CONTAINER, CORE_CONTAINER, OFF_CORE_CONTAINER, STUB_NAME)
        for name in names:
            if run("docker", "container", "inspect", name, check=False).returncode == 0:
                raise RuntimeError("test_container_name_already_exists")
        if run("docker", "network", "inspect", NETWORK, check=False).returncode == 0:
            raise RuntimeError("test_network_name_already_exists")
        run("docker", "network", "create", "--internal", "--label", "d077.issue=7",
            "--label", f"d077.run={RUN_SUFFIX}", "--subnet", SUBNET, "--gateway", GATEWAY, NETWORK)
        created_network = True
        script_path = str(pathlib.Path(__file__).resolve())
        run("docker", "run", "-d", "--name", STUB_NAME, "--network", NETWORK,
            "--network-alias", "stub", "--label", "d077.issue=7", "--label", f"d077.run={RUN_SUFFIX}",
            "--user", f"{uid}:{gid}", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "512m", "--cpus", "0.25",
            "--pids-limit", "64", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
            "--mount", f"type=bind,src={script_path},dst=/tmp/harness.py,readonly",
            CORE_IMAGE, "python", "/tmp/harness.py", "--stub")
        created_names.append(STUB_NAME)
        created_names.append(CONTAINER)
        create_hermes(str(hermes_home), uid, gid)
        _, data_root = start_core_container(temp_root, script_path, uid, gid, label="enabled")
        created_names.append(CORE_CONTAINER)

        assert_network_boundary()
        run_in_container(CORE_CONTAINER, "--enabled-scenario")
        run("docker", "rm", "-f", CORE_CONTAINER, check=False)
        created_names.remove(CORE_CONTAINER)

        start_core_container(temp_root, script_path, uid, gid, memory_enabled=False, label="disabled")
        created_names.append(OFF_CORE_CONTAINER)
        run_in_container(OFF_CORE_CONTAINER, "--flags-off")
        print("D077_V0215_RESULT " + json.dumps({
            "status": "PASS", "image_id": image_id, "revision": revision,
            "core_image_id": core_image.stdout.strip(), "network": "single_internal",
            "e2e": "synthetic_stub_only", "elapsed_seconds": round(time.monotonic() - started, 3),
        }, sort_keys=True), flush=True)
    finally:
        for name in reversed(created_names):
            run("docker", "rm", "-f", name, timeout=30, check=False)
        if created_network:
            run("docker", "network", "rm", NETWORK, timeout=30, check=False)
        temp_obj.cleanup()


def main():
    if "--stub" in sys.argv:
        serve_stub()
    elif "--network-preflight" in sys.argv:
        network_preflight()
    elif "--egress-probe" in sys.argv:
        egress_probe_mode()
    elif "--enabled-scenario" in sys.argv:
        enabled_scenario()
    elif "--flags-off" in sys.argv:
        flags_off_scenario()
    else:
        controller_main()
