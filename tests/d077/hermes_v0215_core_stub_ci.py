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
CORE_ORIGIN = f"http://127.0.0.1:{CORE_PORT}"
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
SCENARIO_STAGE = "startup"


DIAGNOSTIC_MODES = {"--network-preflight", "--hermes-network-preflight", "--enabled-scenario",
                    "--flags-off", "--egress-probe"}
SAFE_STAGE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FAILURE_CODES = {
    "cross_session_run_failed",
    "stub_request_ambiguous",
    "cross_session_instructions_not_observed_by_stub",
    "input_was_rewritten_or_missing",
    "correction_run_failed",
    "correction_state_not_updated",
    "corrected_recall_run_failed",
    "corrected_context_stale",
    "revoked_expired_inference_filter_failed",
    "provider_failure_wrong_terminal_state",
    "provider_failure_not_observed_by_stub",
    "failed_run_was_learned",
    "stop_request_not_observed",
    "stop_request_not_accepted",
    "stop_not_terminal",
    "stop_terminal_state_not_cancelled",
    "stopped_run_was_learned",
    "unrelated_run_failed",
    "unrelated_topic_received_memory_context",
    "exact_fact_run_failed",
    "exact_fact_source_gate_failed",
    "flags_off_chat_failed",
    "flags_off_memory_enabled",
    "api_setup_failed",
    "initial_run_failed",
    "initial_memory_not_learned",
    "initial_run_had_memory_context",
    "source_message_contract_failed",
    "message_pagination_contract_failed",
    "duplicate_text_run_failed",
    "duplicate_text_message_contract_failed",
    "duplicate_text_memory_created",
    "prerequisite_not_passed",
    "scenario_execution_error",
    "scenario_result_missing",
}


class HarnessAssertionError(RuntimeError):
    def __init__(self, failure_code):
        if failure_code not in FAILURE_CODES:
            raise ValueError("unsupported_failure_code")
        super().__init__(failure_code)
        self.failure_code = failure_code


def set_scenario_stage(value):
    global SCENARIO_STAGE
    SCENARIO_STAGE = value if SAFE_STAGE_RE.fullmatch(value) else "unknown_stage"


def http_status_from_exception(exc):
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "code", None)
    return status if isinstance(status, int) and 100 <= status <= 599 else None


def failure_record(mode, stage_name, exc, *, exit_code=1):
    safe_mode = mode if mode in DIAGNOSTIC_MODES else "unknown_mode"
    safe_stage = stage_name if SAFE_STAGE_RE.fullmatch(stage_name) else "unknown_stage"
    class_name = type(exc).__name__ if exc is not None else None
    if class_name is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", class_name):
        class_name = "UnknownException"
    return {"mode": safe_mode, "stage": safe_stage, "exception_class": class_name,
            "http_status": http_status_from_exception(exc) if exc is not None else None,
            "failure_code": getattr(exc, "failure_code", None)
            if getattr(exc, "failure_code", None) in FAILURE_CODES else None,
            "exit_code": exit_code}


def emit_failure(mode, stage_name, exc, *, exit_code=1):
    print("D077_HARNESS_FAILURE " + json.dumps(
        failure_record(mode, stage_name, exc, exit_code=exit_code), sort_keys=True), flush=True)


def run_diagnostic_mode(mode, action):
    set_scenario_stage("startup")
    try:
        action()
        return 0
    except Exception as exc:
        emit_failure(mode, SCENARIO_STAGE, exc)
        return 1


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
        match = re.fullmatch(r"http_(\d{3})", summary.get("last", ""))
        self.status_code = int(match.group(1)) if match else None


class ProbeHTTPStatusError(RuntimeError):
    def __init__(self, status_code):
        super().__init__("http_probe_status_not_ok")
        self.status_code = status_code


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


def model_requests_for_input(requests, input_text):
    """Associate captured Stub requests with a Run using its unchanged user input."""
    return [request for request in requests if contains_text(request, input_text)]


def unique_model_request_for_input(requests, input_text):
    matched = model_requests_for_input(requests, input_text)
    if not matched:
        raise HarnessAssertionError("input_was_rewritten_or_missing")
    if len(matched) != 1:
        raise HarnessAssertionError("stub_request_ambiguous")
    return matched[0]


def personal_memory_context_for_input(request, input_text):
    """Return only Core's tagged system memory block after verifying exact user input."""
    messages = request.get("messages", [])
    user_contents = [row.get("content") for row in messages
                     if isinstance(row, dict) and row.get("role") == "user"]
    if user_contents.count(input_text) != 1:
        raise HarnessAssertionError("input_was_rewritten_or_missing")

    blocks = []
    for row in messages:
        if not isinstance(row, dict) or row.get("role") != "system":
            continue
        content = row.get("content")
        if not isinstance(content, str):
            continue
        starts = content.count("<personal_memory_json>")
        ends = content.count("</personal_memory_json>")
        if starts != ends:
            raise HarnessAssertionError("revoked_expired_inference_filter_failed")
        blocks.extend(re.findall(r"<personal_memory_json>(.*?)</personal_memory_json>",
                                 content, flags=re.DOTALL))
    return "\n".join(blocks)


def assert_memory_candidates_filtered(request, input_text, candidates):
    memory_context = personal_memory_context_for_input(request, input_text)
    if any(candidate in memory_context for candidate in candidates):
        raise HarnessAssertionError("revoked_expired_inference_filter_failed")


def run_scenario(results, name, action, *, requires=()):
    """Run an independent synthetic scene and preserve fail-closed dependencies."""
    if any(results.get(required, {}).get("status") != "PASS" for required in requires):
        results[name] = {"status": "BLOCKED", "failure_code": "prerequisite_not_passed"}
        return None
    try:
        value = action()
    except Exception as exc:
        code = getattr(exc, "failure_code", None)
        if code not in FAILURE_CODES:
            code = "scenario_execution_error"
        results[name] = {"status": "FAIL", "failure_code": code}
        return None
    results[name] = {"status": "PASS", "failure_code": None}
    return value


def scenario_status(results):
    statuses = {row["status"] for row in results.values()}
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "PARTIAL"
    return "PASS"


def scenario_result_from_output(output, marker):
    prefix = marker + " "
    rows = [line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)]
    if not rows:
        return {"status": "FAIL", "scenarios": {
            "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
        }}
    try:
        result = json.loads(rows[-1])
    except (TypeError, ValueError):
        return {"status": "FAIL", "scenarios": {
            "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
        }}
    if not isinstance(result, dict) or not isinstance(result.get("scenarios"), dict):
        return {"status": "FAIL", "scenarios": {
            "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
        }}
    raw_scenarios = result["scenarios"]
    if not raw_scenarios or len(raw_scenarios) > 32:
        return {"status": "FAIL", "scenarios": {
            "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
        }}
    scenarios = {}
    for name, row in raw_scenarios.items():
        if (not isinstance(name, str) or not SAFE_STAGE_RE.fullmatch(name)
                or not isinstance(row, dict) or row.get("status") not in {"PASS", "FAIL", "BLOCKED"}):
            return {"status": "FAIL", "scenarios": {
                "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
            }}
        code = row.get("failure_code")
        if code is not None and code not in FAILURE_CODES:
            return {"status": "FAIL", "scenarios": {
                "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
            }}
        if row["status"] == "PASS" and code is not None:
            return {"status": "FAIL", "scenarios": {
                "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
            }}
        if row["status"] != "PASS" and code is None:
            return {"status": "FAIL", "scenarios": {
                "scenario_result": {"status": "FAIL", "failure_code": "scenario_result_missing"}
            }}
        scenarios[name] = {"status": row["status"], "failure_code": code}
    return {"status": scenario_status(scenarios), "scenarios": scenarios}


def is_provider_failure_status(status):
    return status == "failed"


def is_user_stop_status(status):
    return status == "cancelled"


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


def core_client(*, transport=None):
    options = {
        "base_url": CORE_ORIGIN,
        "headers": {"Origin": CORE_ORIGIN},
        "timeout": 30,
    }
    if transport is not None:
        options["transport"] = transport
    return httpx.Client(**options)


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


def assert_message_order_contract(latest, oldest, latest_page, oldest_page):
    latest_ids = [str(row.get("id", "")) for row in latest]
    oldest_ids = [str(row.get("id", "")) for row in oldest]
    if (not latest_ids or any(not message_id for message_id in latest_ids + oldest_ids)
            or latest_ids != oldest_ids or len(set(latest_ids)) != len(latest_ids)):
        raise RuntimeError("message_order_or_stable_id_contract_failed")
    if (len(latest_page) != 1 or str(latest_page[0].get("id", "")) != latest_ids[-1]
            or len(oldest_page) != 1 or str(oldest_page[0].get("id", "")) != oldest_ids[0]):
        raise RuntimeError("message_pagination_contract_failed")


def enabled_scenario():
    results = {}
    client = core_client()
    def setup():
        set_scenario_stage("login")
        client.post("/api/auth/login", json={"password": APP_PASSWORD},
                    headers={"Origin": f"http://127.0.0.1:{CORE_PORT}"}).raise_for_status()
        set_scenario_stage("create_initial_session")
        created = client.post("/api/chat/sessions", json={})
        created.raise_for_status()
        session_id = created.json().get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise HarnessAssertionError("api_setup_failed")
        return session_id

    session_a = run_scenario(results, "api_setup", setup)
    if session_a is None:
        blocked = ("initial_learning_source", "source_message_contract", "message_pagination_dedup",
                   "duplicate_text_dedup", "cross_session_recall", "correction_update",
                   "corrected_cross_session_recall", "revoked_expired_inference_filter",
                   "unrelated_topic_filter", "exact_fact_source_gate", "failed_run_no_learning",
                   "stopped_run_no_learning")
        for name in blocked:
            run_scenario(results, name, lambda: None, requires=("api_setup",))
        client.close()
        summary = {"status": scenario_status(results), "scenarios": results}
        print("D077_ENABLED_RESULT " + json.dumps(summary, sort_keys=True), flush=True)
        raise HarnessAssertionError("scenario_execution_error")

    initial = "I prefer concise summaries and metric units."
    def initial_learning_source():
        before = stub_state()["request_count"]
        set_scenario_stage("initial_run_learning")
        _, status, _, events = run_chat(client, session_a, initial, "d077-v0215-learn-a")
        if status != "completed" or "run.completed" not in events:
            raise HarnessAssertionError("initial_run_failed")
        requests = model_requests_since(before)
        if not requests:
            raise HarnessAssertionError("initial_run_failed")
        target_request = unique_model_request_for_input(requests, initial)
        if contains_text(target_request, "personal_memory_json"):
            raise HarnessAssertionError("initial_run_had_memory_context")
        rows = client.get("/api/personal-memory").json()["items"]
        learned = {row["content"]["text"]: row for row in rows}
        if not {"concise summaries", "metric units"}.issubset(learned):
            raise HarnessAssertionError("initial_memory_not_learned")
        return learned

    set_scenario_stage("initial_run_learning")
    run_scenario(results, "initial_learning_source", initial_learning_source, requires=("api_setup",))

    def source_message_contract():
        message_page = client.get(f"/api/chat/sessions/{session_a}/messages").json()
        messages = message_page.get("messages", [])
        source_rows = [row for row in messages if row.get("role") == "user" and row.get("text") == initial]
        if not source_rows or not source_rows[0].get("id") or not source_rows[0].get("timestamp"):
            raise HarnessAssertionError("source_message_contract_failed")
        learned = client.get("/api/personal-memory").json()["items"]
        if any(row.get("source_ref") != f"{session_a}:{source_rows[0]['id']}" for row in learned
               if row.get("content", {}).get("text") in {"concise summaries", "metric units"}):
            raise HarnessAssertionError("source_message_contract_failed")

    set_scenario_stage("source_message_contract")
    run_scenario(results, "source_message_contract", source_message_contract,
                 requires=("initial_learning_source",))

    def message_pagination_dedup_contract():
        set_scenario_stage("message_order_pagination")
        latest = direct_messages(session_a, order="latest")
        oldest = direct_messages(session_a, order="oldest")
        latest_page = direct_messages(session_a, order="latest", limit=1, offset=0)
        oldest_page = direct_messages(session_a, order="oldest", limit=1, offset=0)
        try:
            assert_message_order_contract(latest, oldest, latest_page, oldest_page)
        except RuntimeError as exc:
            raise HarnessAssertionError("message_pagination_contract_failed") from exc

    set_scenario_stage("message_order_pagination")
    run_scenario(results, "message_pagination_dedup", message_pagination_dedup_contract,
                 requires=("initial_learning_source",))

    def duplicate_text_dedup():
        before_count = len(client.get("/api/personal-memory").json()["items"])
        _, status, _, events = run_chat(client, session_a, initial, "d077-v0215-duplicate-text-repeat")
        if status != "completed" or "run.completed" not in events:
            raise HarnessAssertionError("duplicate_text_run_failed")
        repeated_page = client.get(f"/api/chat/sessions/{session_a}/messages").json()
        repeated_users = [row for row in repeated_page.get("messages", []) if row.get("role") == "user"]
        repeated_ids = [str(row.get("id", "")) for row in repeated_users if row.get("text") == initial]
        if len(repeated_ids) < 2 or repeated_ids[0] == repeated_ids[1]:
            raise HarnessAssertionError("duplicate_text_message_contract_failed")
        if len(client.get("/api/personal-memory").json()["items"]) != before_count:
            raise HarnessAssertionError("duplicate_text_memory_created")

    set_scenario_stage("duplicate_text_dedup")
    run_scenario(results, "duplicate_text_dedup", duplicate_text_dedup,
                 requires=("initial_learning_source",))

    set_scenario_stage("cross_session_recall")

    def cross_session():
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        question = "How should you format my summaries and units?"
        before = stub_state()["request_count"]
        _, status, _, events = run_chat(client, session, question, "d077-v0215-recall-b")
        requests = model_requests_since(before)
        if status != "completed" or "run.completed" not in events or not requests:
            raise HarnessAssertionError("cross_session_run_failed")
        target_request = unique_model_request_for_input(requests, question)
        if (not contains_text(target_request, "personal_memory_json")
                or not contains_text(target_request, "concise summaries")):
            raise HarnessAssertionError("cross_session_instructions_not_observed_by_stub")

    run_scenario(results, "cross_session_recall", cross_session, requires=("initial_learning_source",))

    def correction_update():
        correction = "I used to prefer concise summaries, but now I prefer concise paragraphs."
        _, status, _, events = run_chat(client, session_a, correction, "d077-v0215-correct-c")
        if status != "completed" or "run.completed" not in events:
            raise HarnessAssertionError("correction_run_failed")
        active = client.get("/api/personal-memory").json()["items"]
        active_text = {row.get("content", {}).get("text") for row in active}
        if "concise summaries" in active_text or "concise paragraphs" not in active_text:
            raise HarnessAssertionError("correction_state_not_updated")

    set_scenario_stage("correction_update")
    run_scenario(results, "correction_update", correction_update, requires=("initial_learning_source",))

    def corrected_recall():
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        question = "How should you format my summaries now?"
        before = stub_state()["request_count"]
        _, status, _, events = run_chat(client, session, question, "d077-v0215-correct-recall-d")
        requests = model_requests_since(before)
        if status != "completed" or "run.completed" not in events or not requests:
            raise HarnessAssertionError("corrected_recall_run_failed")
        target_request = unique_model_request_for_input(requests, question)
        prompt = "\n".join(str(row.get("content", "")) for row in target_request.get("messages", []))
        if "concise paragraphs" not in prompt or "concise summaries" in prompt:
            raise HarnessAssertionError("corrected_context_stale")

    set_scenario_stage("corrected_cross_session_recall")
    run_scenario(results, "corrected_cross_session_recall", corrected_recall,
                 requires=("correction_update",))

    def inactive_memory_filter():
        current = client.get("/api/personal-memory").json()["items"]
        metric_row = next(row for row in current if row.get("content", {}).get("text") == "metric units")
        client.post(f"/api/personal-memory/{metric_row['memory_id']}/revoke", json={
            "source_type": "user_confirmed", "source_ref": "synthetic-correction",
        }).raise_for_status()
        client.post("/api/personal-memory", json={
            "content": {"text": "Prefers imaginary unit labels"}, "category": "preference",
            "fact_kind": "user_stated", "source_type": "user_confirmed", "source_ref": "synthetic-expiry",
            "expires_at": "2000-01-01T00:00:00Z",
        }).raise_for_status()
        client.post("/api/personal-memory", json={
            "content": {"text": "Prefers cobalt project names"}, "category": "preference",
            "fact_kind": "inference", "source_type": "session_note", "source_ref": "synthetic-inference",
        }).raise_for_status()
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        question = "Which metric units, imaginary unit labels, and project names do I prefer?"
        before = stub_state()["request_count"]
        _, status, _, events = run_chat(client, session, question, "d077-v0215-gated-context-e")
        requests = model_requests_since(before)
        if status != "completed" or "run.completed" not in events or not requests:
            raise HarnessAssertionError("revoked_expired_inference_filter_failed")
        target_request = unique_model_request_for_input(requests, question)
        assert_memory_candidates_filtered(target_request, question,
                                          ("metric units", "imaginary unit labels", "cobalt project names"))

    set_scenario_stage("revoked_expired_inference_filter")
    run_scenario(results, "revoked_expired_inference_filter", inactive_memory_filter,
                 requires=("initial_learning_source",))

    def failed_run_no_learning():
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        question = "I prefer neon section headings."
        before = stub_state()["request_count"]
        control_stub({"fail_remaining": 20})
        try:
            _, status, _, events = run_chat(client, session, question, "d077-v0215-provider-failure")
        finally:
            control_stub({"fail_remaining": 0})
        requests = model_requests_since(before)
        if not model_requests_for_input(requests, question):
            raise HarnessAssertionError("provider_failure_not_observed_by_stub")
        if not is_provider_failure_status(status) or "run.failed" not in events:
            raise HarnessAssertionError("provider_failure_wrong_terminal_state")
        active_text = {row.get("content", {}).get("text")
                       for row in client.get("/api/personal-memory").json()["items"]}
        if "neon section headings" in active_text:
            raise HarnessAssertionError("failed_run_was_learned")

    set_scenario_stage("provider_failure_no_learning")
    run_scenario(results, "failed_run_no_learning", failed_run_no_learning, requires=("api_setup",))

    def stopped_run_no_learning():
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        control_stub({"reset_blocked": True, "delay_next": True})
        before = stub_state()["request_count"]
        run_id = None
        try:
            question = "I prefer amber section headers."
            run_id = start_chat(client, session, question, "d077-v0215-stop-run")
            if not wait_stub_blocked(timeout=12):
                raise HarnessAssertionError("stop_request_not_observed")
            if not model_requests_for_input(model_requests_since(before), question):
                raise HarnessAssertionError("stop_request_not_observed")
            stopped = client.post(f"/api/chat/runs/{run_id}/stop", json={})
            stopped.raise_for_status()
            if stopped.json().get("status") != "stopping":
                raise HarnessAssertionError("stop_request_not_accepted")
        finally:
            control_stub({"release": True})
        if not run_id:
            raise HarnessAssertionError("stop_request_not_observed")
        status = "unknown"
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            polled = client.get(f"/api/chat/runs/{run_id}")
            if polled.status_code == 200:
                status = polled.json().get("status", "unknown")
                if status in {"completed", "failed", "cancelled", "interrupted"}:
                    break
            time.sleep(0.5)
        if status not in {"completed", "failed", "cancelled", "interrupted"}:
            raise HarnessAssertionError("stop_not_terminal")
        if not is_user_stop_status(status):
            raise HarnessAssertionError("stop_terminal_state_not_cancelled")
        active_text = {row.get("content", {}).get("text")
                       for row in client.get("/api/personal-memory").json()["items"]}
        if "amber section headers" in active_text:
            raise HarnessAssertionError("stopped_run_was_learned")

    set_scenario_stage("stopped_run_no_learning")
    run_scenario(results, "stopped_run_no_learning", stopped_run_no_learning, requires=("api_setup",))

    def unrelated_topic_filter():
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        question = "What is 13 plus 5?"
        before = stub_state()["request_count"]
        _, status, _, events = run_chat(client, session, question, "d077-v0215-unrelated-f")
        requests = model_requests_since(before)
        if status != "completed" or "run.completed" not in events or not requests:
            raise HarnessAssertionError("unrelated_run_failed")
        target_request = unique_model_request_for_input(requests, question)
        if contains_text(target_request, "personal_memory_json"):
            raise HarnessAssertionError("unrelated_topic_received_memory_context")

    set_scenario_stage("unrelated_topic_filter")
    run_scenario(results, "unrelated_topic_filter", unrelated_topic_filter,
                 requires=("initial_learning_source",))

    def exact_fact_source_gate():
        client.post("/api/personal-memory", json={
            "content": {"text": "Project code is NOVA-17"}, "category": "fact",
            "fact_kind": "user_stated", "source_type": "original_file", "source_ref": "project.md",
            "exact": True,
        }).raise_for_status()
        session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        question = "What is the exact project code from my project file?"
        before = stub_state()["request_count"]
        _, status, _, events = run_chat(client, session, question, "d077-v0215-fact-g")
        requests = model_requests_since(before)
        if status != "completed" or "run.completed" not in events or not requests:
            raise HarnessAssertionError("exact_fact_run_failed")
        target_request = unique_model_request_for_input(requests, question)
        prompt = "\n".join(str(row.get("content", "")) for row in target_request.get("messages", []))
        if "Source verification required" not in prompt or "NOVA-17" in prompt:
            raise HarnessAssertionError("exact_fact_source_gate_failed")

    set_scenario_stage("exact_fact_source_gate")
    run_scenario(results, "exact_fact_source_gate", exact_fact_source_gate, requires=("api_setup",))

    client.close()
    summary = {"status": scenario_status(results), "scenarios": results}
    print("D077_ENABLED_RESULT " + json.dumps(summary, sort_keys=True), flush=True)
    if summary["status"] != "PASS":
        raise HarnessAssertionError("scenario_execution_error")


def flags_off_scenario():
    results = {}

    def chat_with_memory_disabled():
        client = core_client()
        try:
            set_scenario_stage("flags_off_login")
            client.post("/api/auth/login", json={"password": APP_PASSWORD},
                        headers={"Origin": f"http://127.0.0.1:{CORE_PORT}"}).raise_for_status()
            set_scenario_stage("flags_off_run")
            session = client.post("/api/chat/sessions", json={}).json()["session_id"]
            before = stub_state()["request_count"]
            _, status, _, events = run_chat(
                client, session, "I prefer lavender section titles.", "d077-v0215-flags-off")
            requests = model_requests_since(before)
            memory_root = pathlib.Path(os.environ["SB_PERSONAL_MEMORY_ROOT"])
            if status != "completed" or "run.completed" not in events or not requests:
                raise HarnessAssertionError("flags_off_chat_failed")
            target_request = unique_model_request_for_input(requests, "I prefer lavender section titles.")
            if memory_root.exists() or contains_text(target_request, "personal_memory_json"):
                raise HarnessAssertionError("flags_off_memory_enabled")
        finally:
            client.close()

    run_scenario(results, "flags_off", chat_with_memory_disabled)
    summary = {"status": scenario_status(results), "scenarios": results}
    print("D077_FLAGS_OFF_RESULT " + json.dumps(summary, sort_keys=True), flush=True)
    if summary["status"] != "PASS":
        raise HarnessAssertionError(results["flags_off"]["failure_code"])


def external_tcp_probe():
    try:
        connection = socket.create_connection(("1.1.1.1", 443), timeout=2)
        connection.close()
        return "reachable"
    except Exception as exc:
        return "blocked_" + type(exc).__name__


def configured_egress_targets():
    targets = []
    for value in filter(None, os.environ.get("D077_DENY_EGRESS_TARGETS", "").split(",")):
        match = re.fullmatch(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})", value.strip())
        if not match or any(int(octet) > 255 for octet in match.group(1).split(".")):
            raise ValueError("invalid_egress_target")
        port = int(match.group(2))
        if not 1 <= port <= 65535:
            raise ValueError("invalid_egress_target")
        targets.append((match.group(1), port))
    return targets


def tcp_target_probe(host, port):
    try:
        connection = socket.create_connection((host, port), timeout=2)
        connection.close()
        return "reachable"
    except Exception as exc:
        return "blocked_" + type(exc).__name__


def configured_egress_probe_results():
    return {f"{host}:{port}": tcp_target_probe(host, port)
            for host, port in configured_egress_targets()}


def network_preflight():
    set_scenario_stage("network_health_probes")
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
              "core_public_tcp_egress": external_tcp_probe(),
              "configured_egress_targets": configured_egress_probe_results()}
    print("D077_NETWORK_PREFLIGHT " + json.dumps(result, sort_keys=True), flush=True)
    if (core_health != "http_200" or hermes_health != "http_200" or stub_health != "http_200"
            or result["core_public_tcp_egress"] == "reachable"
            or any(value == "reachable" for value in result["configured_egress_targets"].values())):
        set_scenario_stage("network_preflight_assertions")
        failed_http_status = next((int(value[5:]) for value in
                                   (core_health, hermes_health, stub_health)
                                   if re.fullmatch(r"http_\d{3}", value) and value != "http_200"), None)
        if failed_http_status is not None:
            raise ProbeHTTPStatusError(failed_http_status)
        raise RuntimeError("network_preflight_failed")


def egress_probe_mode():
    set_scenario_stage("public_egress_probe")
    result = {"public_tcp_egress": external_tcp_probe(),
              "configured_targets": configured_egress_probe_results()}
    print(json.dumps(result, sort_keys=True), flush=True)
    if result["public_tcp_egress"] == "reachable" or any(
            value == "reachable" for value in result["configured_targets"].values()):
        raise RuntimeError("public_egress_not_blocked")


def hermes_network_preflight():
    set_scenario_stage("hermes_to_stub_health")
    stub_health = probe_http("http://stub:19002/__test/health")
    egress = {"public_tcp_egress": external_tcp_probe(),
              "configured_targets": configured_egress_probe_results()}
    result = {"hermes_to_stub_health": stub_health, **egress}
    print("D077_HERMES_NETWORK_PREFLIGHT " + json.dumps(result, sort_keys=True), flush=True)
    if (stub_health != "http_200" or egress["public_tcp_egress"] == "reachable"
            or any(value == "reachable" for value in egress["configured_targets"].values())):
        if re.fullmatch(r"http_\d{3}", stub_health) and stub_health != "http_200":
            raise ProbeHTTPStatusError(int(stub_health[5:]))
        raise RuntimeError("hermes_network_preflight_failed")


def serve_stub():
    server = http.server.ThreadingHTTPServer(("0.0.0.0", STUB_PORT), StubHandler)
    server.serve_forever()


def run_in_container(container, mode, *, check=True):
    try:
        result = run("docker", "exec", container, "python", "/tmp/harness.py", mode,
                     check=False, timeout=900)
    except subprocess.TimeoutExpired as exc:
        emit_failure(mode, "peer_process_timeout", exc, exit_code=124)
        raise RuntimeError("isolated_peer_timeout") from None
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if check and result.returncode:
        if not any(line.startswith("D077_HARNESS_FAILURE ") for line in result.stdout.splitlines()):
            emit_failure(mode, "peer_process_exit", None, exit_code=result.returncode)
        raise RuntimeError("isolated_peer_failed")
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
    hermes_probe_code = r'''import json,os,socket
results={"public_tcp_egress":"blocked"}
try:
 s=socket.create_connection(("1.1.1.1",443),timeout=2); s.close(); results["public_tcp_egress"]="reachable"
except Exception as e: results["public_tcp_egress"]="blocked_"+type(e).__name__
targets={}
for value in filter(None,os.environ.get("D077_DENY_EGRESS_TARGETS","").split(",")):
 host,port=value.rsplit(":",1)
 try:
  s=socket.create_connection((host,int(port)),timeout=2); s.close(); targets[value]="reachable"
 except Exception as e: targets[value]="blocked_"+type(e).__name__
results["configured_targets"]=targets
print(json.dumps(results,sort_keys=True))
if results["public_tcp_egress"]=="reachable" or any(v=="reachable" for v in targets.values()): raise SystemExit(1)'''
    hermes = run("docker", "exec", CONTAINER, "/opt/hermes/.venv/bin/python3", "-c",
                 hermes_probe_code, check=False)
    if hermes.stdout:
        for line in hermes.stdout.splitlines():
            print("D077_HERMES_EGRESS " + line, flush=True)
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
        enabled_execution = run_in_container(CORE_CONTAINER, "--enabled-scenario", check=False)
        run("docker", "rm", "-f", CORE_CONTAINER, check=False)
        created_names.remove(CORE_CONTAINER)

        start_core_container(temp_root, script_path, uid, gid, memory_enabled=False, label="disabled")
        created_names.append(OFF_CORE_CONTAINER)
        flags_off_execution = run_in_container(OFF_CORE_CONTAINER, "--flags-off", check=False)
        enabled_result = scenario_result_from_output(enabled_execution.stdout, "D077_ENABLED_RESULT")
        flags_off_result = scenario_result_from_output(flags_off_execution.stdout, "D077_FLAGS_OFF_RESULT")
        scenario_results = {**enabled_result["scenarios"], **flags_off_result["scenarios"]}
        overall_status = scenario_status(scenario_results)
        print("D077_V0215_RESULT " + json.dumps({
            "status": overall_status, "scenarios": scenario_results,
            "image_id": image_id, "revision": revision,
            "core_image_id": core_image.stdout.strip(), "network": "single_internal",
            "e2e": "synthetic_stub_only", "elapsed_seconds": round(time.monotonic() - started, 3),
        }, sort_keys=True), flush=True)
        if overall_status != "PASS":
            raise RuntimeError("synthetic_scenarios_not_passed")
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
        raise SystemExit(run_diagnostic_mode("--network-preflight", network_preflight))
    elif "--egress-probe" in sys.argv:
        raise SystemExit(run_diagnostic_mode("--egress-probe", egress_probe_mode))
    elif "--hermes-network-preflight" in sys.argv:
        raise SystemExit(run_diagnostic_mode("--hermes-network-preflight", hermes_network_preflight))
    elif "--enabled-scenario" in sys.argv:
        raise SystemExit(run_diagnostic_mode("--enabled-scenario", enabled_scenario))
    elif "--flags-off" in sys.argv:
        raise SystemExit(run_diagnostic_mode("--flags-off", flags_off_scenario))
    else:
        controller_main()


if __name__ == "__main__":
    main()
