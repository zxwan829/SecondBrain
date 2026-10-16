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
HERMES_PORT = 18642
CORE_PORT = 18000
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
        if self.path == "/health":
            self.respond(200, b'{"status":"ok"}')
        elif self.path == "/v1/models":
            body = {"object": "list", "data": [{"id": MODEL, "object": "model"}]}
            self.respond(200, json.dumps(body).encode())
        else:
            self.respond(404, b'{"error":"route_not_allowed"}')

    def do_POST(self):
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


def wait_http(url, *, headers=None, expected=200, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == expected:
                    return response.read()
        except Exception:
            time.sleep(1)
    raise RuntimeError("http_health_timeout")


def assert_stub_only_egress(container):
    snippet = """import urllib.request
assert urllib.request.urlopen('http://172.29.78.1:19002/health', timeout=3).status == 200
try:
    urllib.request.urlopen('https://example.com/', timeout=3)
except Exception:
    print('EXTERNAL_EGRESS_DENIED')
else:
    raise SystemExit('unexpected_external_egress')
"""
    result = run("docker", "exec", container, "/opt/hermes/.venv/bin/python3", "-c", snippet)
    if "EXTERNAL_EGRESS_DENIED" not in result.stdout:
        raise RuntimeError("egress_boundary_not_proven")


def create_hermes(container_data, uid, gid):
    run("docker", "run", "-d", "--name", CONTAINER, "--network", NETWORK,
        "--label", "d077.issue=7", "--label", f"d077.run={RUN_SUFFIX}",
        "--user", f"{uid}:{gid}", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--memory", "2g", "--cpus", "1",
        "--pids-limit", "128", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=96m,mode=1777",
        "--mount", f"type=bind,src={container_data},dst=/opt/data",
        "--publish", f"127.0.0.1:{HERMES_PORT}:8642",
        "-e", "HERMES_HOME=/opt/data", "-e", "HOME=/opt/data",
        "-e", f"API_SERVER_KEY={API_SERVER_KEY}", "-e", "API_SERVER_HOST=0.0.0.0",
        "-e", "API_SERVER_PORT=8642", "--entrypoint", "/bin/sh", IMAGE,
        "-c", "sleep 1200")
    config = f"""model:
  provider: custom
  default: {MODEL}
  base_url: http://{GATEWAY}:{STUB_PORT}/v1
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
    try:
        run("docker", "exec", "-d", CONTAINER, "/bin/sh", "-c",
            "/opt/hermes/.venv/bin/hermes gateway run --no-supervise >/opt/data/gateway.log 2>&1", timeout=10)
        headers = {"Authorization": f"Bearer {API_SERVER_KEY}"}
        wait_http(f"http://127.0.0.1:{HERMES_PORT}/health", headers=headers)
    except Exception:
        run("docker", "rm", "-f", CONTAINER, timeout=30, check=False)
        raise


def start_core(temp_root, core_root, *, memory_enabled=True, port=CORE_PORT, label="core"):
    roots = {name: temp_root / f"{label}-{name}"
             for name in ("review", "knowledge", "promote", "raw", "memory")}
    for path in roots.values():
        if path.name.endswith("memory") and not memory_enabled:
            continue
        path.mkdir(mode=0o700)
        path.chmod(0o700)
    pass_file = temp_root / f"{label}-app-password"
    key_file = temp_root / f"{label}-hermes-key"
    for path, content in ((pass_file, APP_PASSWORD), (key_file, API_SERVER_KEY)):
        path.write_text(content + "\n", encoding="utf-8")
        path.chmod(0o600)
    core_home = temp_root / f"{label}-home"
    core_home.mkdir(mode=0o700)
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
           "HOME": str(core_home), "LANG": "C.UTF-8"}
    env.update({
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
        "SB_PROMOTE_STATE_ROOT": str(roots["promote"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_DASHBOARD_ORIGINS": f"http://127.0.0.1:{port}", "SB_CORE_ALLOWED_HOSTS": "127.0.0.1",
        "SB_APP_PASSWORD_FILE": str(pass_file), "SB_HERMES_API_KEY_FILE": str(key_file),
        "SB_HERMES_API_URL": f"http://127.0.0.1:{HERMES_PORT}",
        "SB_PERSONAL_MEMORY_ENABLED": "true" if memory_enabled else "false",
        "SB_PERSONAL_LEARNING_ENABLED": "true" if memory_enabled else "false",
        "SB_PERSONAL_MEMORY_ROOT": str(roots["memory"]), "SB_PROMOTE_ENABLED": "false",
        "SB_ORGANIZER_MODEL_ENABLED": "false", "SB_ORGANIZER_SCHEDULER_ENABLED": "false",
    })
    log = open(temp_root / f"{label}.log", "wb")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "secondbrain_core.app:app",
                                "--host", "127.0.0.1", "--port", str(port)],
                               cwd=core_root, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        wait_http(f"http://127.0.0.1:{port}/health")
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()
        raise
    return process, roots, log


def model_requests_since(index):
    with CAPTURE_LOCK:
        return list(CAPTURED[index:])


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
    response = httpx.get(f"http://127.0.0.1:{HERMES_PORT}/api/sessions/{session_id}/messages",
                         params={"inline_images": "false", "limit": limit, "offset": offset, "order": order},
                         headers={"Authorization": f"Bearer {API_SERVER_KEY}"}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", payload.get("messages", [])) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("hermes_message_page_shape_invalid")
    return rows


def main():
    if sys.platform != "linux" or not shutil.which("docker"):
        raise RuntimeError("requires_ephemeral_linux_runner_with_docker")
    inspect = run("docker", "image", "inspect", IMAGE,
                  "--format", "{{.Id}}|{{index .Config.Labels \"org.opencontainers.image.revision\"}}")
    image_id, revision = inspect.stdout.strip().split("|", 1)
    if image_id != EXPECTED_IMAGE_ID or revision != EXPECTED_REVISION:
        raise RuntimeError("fixed_hermes_image_identity_mismatch")

    temp_obj = tempfile.TemporaryDirectory(prefix="d077-v0215-")
    temp_root = pathlib.Path(temp_obj.name).resolve()
    temp_root.chmod(0o700)
    hermes_home = temp_root / "hermes-home"
    hermes_home.mkdir(mode=0o700)
    uid, gid = os.getuid(), os.getgid()
    stub = None
    stub_thread = None
    core_process = None
    core_log = None
    off_process = None
    off_log = None
    created_container = False
    created_network = False
    started = time.monotonic()
    try:
        # Docker network is created here, so cleanup owns only these exact names.
        if run("docker", "network", "inspect", NETWORK, check=False).returncode == 0:
            raise RuntimeError("network_name_already_exists")
        if run("docker", "container", "inspect", CONTAINER, check=False).returncode == 0:
            raise RuntimeError("container_name_already_exists")
        run("docker", "network", "create", "--internal", "--label", "d077.issue=7",
            "--label", f"d077.run={RUN_SUFFIX}",
            "--subnet", SUBNET, "--gateway", GATEWAY, NETWORK)
        created_network = True
        stub = http.server.ThreadingHTTPServer((GATEWAY, STUB_PORT), StubHandler)
        stub_thread = threading.Thread(target=stub.serve_forever, daemon=True)
        stub_thread.start()
        with urllib.request.urlopen(f"http://{GATEWAY}:{STUB_PORT}/health", timeout=3) as response:
            if response.status != 200:
                raise RuntimeError("stub_health_failed")
        created_container = True
        create_hermes(str(hermes_home), uid, gid)
        assert_stub_only_egress(CONTAINER)

        core_root = pathlib.Path(__file__).resolve().parents[2] / "web-app" / "secondbrain-core"
        core_process, roots, core_log = start_core(temp_root, core_root)
        client = httpx.Client(base_url=f"http://127.0.0.1:{CORE_PORT}", timeout=30)
        login = client.post("/api/auth/login", json={"password": APP_PASSWORD},
                            headers={"Origin": f"http://127.0.0.1:{CORE_PORT}"})
        login.raise_for_status()
        created = client.post("/api/chat/sessions", json={})
        created.raise_for_status()
        session_a = created.json()["session_id"]

        initial = "I prefer concise summaries and metric units."
        before_calls = len(CAPTURED)
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
        before_calls = len(CAPTURED)
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
        before_calls = len(CAPTURED)
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
        before_calls = len(CAPTURED)
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
        with CAPTURE_LOCK:
            STUB_COUNTER["fail_remaining"] = 20
        run_failed, status_failed, latency_failed, events_failed = run_chat(
            client, failure_session, "I prefer neon section headings.", "d077-v0215-provider-failure")
        with CAPTURE_LOCK:
            STUB_COUNTER["fail_remaining"] = 0
        if status_failed not in {"failed", "interrupted"}:
            raise RuntimeError("provider_failure_did_not_fail_run")
        if "neon section headings" in {row.get("content", {}).get("text")
                                       for row in client.get("/api/personal-memory").json()["items"]}:
            raise RuntimeError("failed_run_was_learned")

        # Stop a Run while its provider request is blocked at the local stub.
        stop_session = client.post("/api/chat/sessions", json={}).json()["session_id"]
        STUB_BLOCKED.clear()
        STUB_RELEASE.clear()
        with CAPTURE_LOCK:
            STUB_COUNTER["delay_next"] = True
        stop_started = time.monotonic()
        run_stopped = start_chat(client, stop_session, "I prefer amber section headers.",
                                 "d077-v0215-stop-run")
        if not STUB_BLOCKED.wait(timeout=12):
            raise RuntimeError("stub_did_not_observe_stop_test_request")
        stop_response = client.post(f"/api/chat/runs/{run_stopped}/stop", json={})
        stop_response.raise_for_status()
        STUB_RELEASE.set()
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
        before_calls = len(CAPTURED)
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
        before_calls = len(CAPTURED)
        run_g, status_g, latency_g, events_g = run_chat(
            client, session_f, fact_question, "d077-v0215-fact-g")
        req_g = model_requests_since(before_calls)
        if status_g != "completed" or "run.completed" not in events_g or not req_g:
            raise RuntimeError("exact_fact_run_failed")
        fact_prompt = "\n".join(str(row.get("content", "")) for row in req_g[-1].get("messages", []))
        if "Source verification required" not in fact_prompt or "NOVA-17" in fact_prompt:
            raise RuntimeError("exact_fact_not_redacted_or_source_required")

        enabled_core_request_count = STUB_COUNTER["calls"]
        client.close()
        core_process.terminate()
        core_process.wait(timeout=10)
        core_log.close()
        core_process = None
        core_log = None

        # Flag-off must leave its distinct Memory root absent and omit injected context.
        off_process, off_roots, off_log = start_core(temp_root, core_root, memory_enabled=False,
                                                     port=CORE_PORT + 1, label="disabled")
        off_client = httpx.Client(base_url=f"http://127.0.0.1:{CORE_PORT + 1}", timeout=30)
        off_login = off_client.post("/api/auth/login", json={"password": APP_PASSWORD},
                                    headers={"Origin": f"http://127.0.0.1:{CORE_PORT + 1}"})
        off_login.raise_for_status()
        off_session = off_client.post("/api/chat/sessions", json={}).json()["session_id"]
        before_calls = len(CAPTURED)
        run_off, status_off, latency_off, events_off = run_chat(
            off_client, off_session, "I prefer lavender section titles.", "d077-v0215-flags-off")
        off_requests = model_requests_since(before_calls)
        if status_off != "completed" or "run.completed" not in events_off or not off_requests:
            raise RuntimeError("flags_off_chat_failed")
        if off_roots["memory"].exists() or contains_text(off_requests[-1], "personal_memory_json"):
            raise RuntimeError("flags_off_created_memory_or_injected_context")
        off_client.close()
        off_process.terminate()
        off_process.wait(timeout=10)
        off_log.close()

        print("D077_V0215_RESULT " + json.dumps({
            "status": "PASS", "image_id": image_id, "revision": revision,
            "source_message_id": source_rows[0]["id"],
            "initial_latest_message_ids": latest_ids,
            "duplicate_input_message_ids": repeated_ids[:2],
            "learned_source_refs": sorted({row.get("source_ref", "") for row in learned.values()
                                            if row.get("content", {}).get("text")
                                            in {"concise summaries", "metric units"}}),
            "run_ids": [run_a, run_repeat, run_b, run_c, run_d, run_e, run_failed,
                        run_stopped, run_f, run_g, run_off],
            "session_count": 9, "run_count": 11,
            "run_statuses": [status_a, status_repeat, status_b, status_c, status_d, status_e,
                             status_failed, "stop:" + stop_status, status_f, status_g, status_off],
            "latency_seconds": [latency_a, latency_repeat, latency_b, latency_c, latency_d, latency_e,
                                latency_failed, latency_stop, latency_f, latency_g, latency_off],
            "stub_provider_calls": STUB_COUNTER["calls"], "external_provider_calls": 0,
            "enabled_core_stub_calls": enabled_core_request_count,
            "memory_file_bytes": (roots["memory"] / "personal-memory.jsonl").stat().st_size,
            "assertions": ["API_RUN_SSE", "SOURCE_MESSAGE_ID", "CORE_LEARNING", "CROSS_SESSION_INSTRUCTIONS",
                           "CORRECTION", "CORRECTED_CROSS_SESSION_RECALL", "REVOKED_EXPIRED_INFERENCE_FILTERED",
                           "UNRELATED_NO_INJECTION", "EXACT_FACT_SOURCE_REQUIRED", "DUPLICATE_TEXT_IDS_AND_PAGINATION",
                           "FAILED_RUN_NO_LEARNING", "STOP_NO_LEARNING", "FLAGS_OFF_NO_MEMORY_ROOT_OR_INJECTION",
                           "STUB_ONLY_EGRESS"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }, sort_keys=True), flush=True)
    finally:
        if core_process:
            core_process.terminate()
            try:
                core_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                core_process.kill()
                core_process.wait(timeout=5)
        if core_log:
            core_log.close()
        if off_process:
            off_process.terminate()
            try:
                off_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                off_process.kill()
                off_process.wait(timeout=5)
        if off_log:
            off_log.close()
        if created_container:
            run("docker", "rm", "-f", CONTAINER, timeout=30, check=False)
        STUB_RELEASE.set()
        if stub_thread and stub_thread.ident is not None:
            stub.shutdown()
        if stub:
            stub.server_close()
        if created_network:
            run("docker", "network", "rm", NETWORK, timeout=30, check=False)
        temp_obj.cleanup()


if __name__ == "__main__":
    main()
