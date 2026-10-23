"""Synthetic Uvicorn + Vite same-origin HTTP gate for PR #181."""
import asyncio
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.hermes_api import HermesAPI

ROOT = Path(tempfile.mkdtemp(prefix="sb-p2-4-5-gate-", dir="/private/tmp"))
for name in ("review", "raw", "knowledge", "state", "memory", "projects", "briefs", "tasks", "journal", "notes"):
    (ROOT / name).mkdir(mode=0o700)
password = ROOT / "password"
password.write_bytes(b"synthetic-only-password\n")
password.chmod(0o600)

def reserve_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

core_port, vite_port = reserve_port(), reserve_port()
core_origin = f"http://127.0.0.1:{core_port}"
vite_origin = f"http://127.0.0.1:{vite_port}"
vite_host = f"127.0.0.1:{vite_port}"
for key, value in {
    "SB_REVIEW_ROOT": str(ROOT / "review"), "SB_CAPTURE_RAW_ROOT": str(ROOT / "raw"),
    "SB_KNOWLEDGE_ROOT": str(ROOT / "knowledge"), "SB_PROMOTE_STATE_ROOT": str(ROOT / "state"),
    "SB_APP_PASSWORD_FILE": str(password), "SB_DASHBOARD_ORIGINS": vite_origin,
    "SB_CORE_ALLOWED_HOSTS": "127.0.0.1", "SB_HERMES_API_URL": "", "SB_PROMOTE_ENABLED": "false",
    "SB_PERSONAL_MEMORY_ENABLED": "false", "SB_PERSONAL_LEARNING_ENABLED": "false",
    "SB_PROJECTS_INDEX_ROOT": str(ROOT / "projects"), "SB_DAILY_BRIEF_STORE_ROOT": str(ROOT / "briefs"),
    "SB_TASK_ROOT": str(ROOT / "tasks"), "SB_JOURNAL_ROOT": str(ROOT / "journal"),
    "SB_NOTES_DRAFTS_ROOT": str(ROOT / "notes"), "SB_CORE_PROXY_TARGET": core_origin,
    "SB_NOTES_AUTHORIZED_ROOTS": "{}",
}.items():
    os.environ[key] = value

async def fake_session(self, session_id):
    return {"session_id": session_id, "title": "synthetic"}
HermesAPI.get_session = fake_session
HermesAPI._client = lambda self, timeout=30: httpx.AsyncClient(
    base_url="http://unused", transport=httpx.MockTransport(lambda req: httpx.Response(500)))

app = create_app()
store = app.state.knowledge_read_store
reads = []
source_path = "20-Knowledge/synthetic.md"
def recall(query, **kwargs):
    reads.append((query, kwargs))
    if query == "no-match":
        return {"status": "none", "items": []}
    return {"status": "available", "items": [{
        "relative_path": source_path, "title": "Synthetic verified source", "sha256": "a" * 64,
        "content": "synthetic source text must never leave Core", "provenance_status": "verified"}]}
store.chat_recall = recall
store.verify_chat_reference = lambda path, digest: "version_verified" if digest == "a" * 64 else "stale"

core_listener = socket.socket()
core_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
core_listener.bind(("127.0.0.1", core_port)); core_listener.listen(32)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=core_port,
    log_level="critical", lifespan="off", access_log=False, proxy_headers=False))
core_thread = threading.Thread(target=server.run, kwargs={"sockets": [core_listener]}, daemon=True)
core_thread.start()
repo_root = Path(__file__).resolve().parents[3]
frontend = repo_root / "web-app" / "secondbrain-frontend"
vite = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
    cwd=frontend, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_http(url):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=0.5) as c:
                response = c.get(url)
                if response.status_code < 500:
                    return response
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"server did not start: {url}")

try:
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    wait_http(vite_origin + "/")
    with httpx.Client(base_url=vite_origin, timeout=5.0) as client:
        def post(path, **kwargs):
            return client.post(path, headers={"Origin": vite_origin, **kwargs.pop("headers", {})}, **kwargs)
        unauth = post("/api/chat/sessions/session-A/grounding-candidates", json={"query": "amount"})
        assert unauth.status_code == 401 and "no-store" in unauth.headers.get("cache-control", ""), (unauth.status_code, dict(unauth.headers), unauth.text)
        login = post("/api/auth/login", json={"password": "synthetic-only-password"})
        assert login.status_code == 200, login.text

        p24 = post("/api/chat/sessions/session-A/grounding-candidates", json={"query": "amount"})
        assert p24.status_code == 200, p24.text
        body = p24.json()
        assert body["session_id"] == "session-A" and body["status"] == "available"
        assert body["answer_attribution"] == "not_established"
        assert body["items"][0]["knowledge_status"] == "version_verified"
        assert "source text" not in p24.text and "20-Knowledge" not in p24.text
        assert "no-store" in p24.headers["cache-control"]
        none = post("/api/chat/sessions/session-A/grounding-candidates", json={"query": "no-match"})
        assert none.status_code == 200 and none.json()["status"] == "none" and not none.json()["items"]
        store.verify_chat_reference = lambda _path, _digest: "stale"
        drifted = post("/api/chat/sessions/session-A/grounding-candidates", json={"query": "amount"})
        assert drifted.status_code == 200 and drifted.json()["status"] == "partial" and not drifted.json()["items"]
        store.verify_chat_reference = lambda path, digest: "version_verified" if digest == "a" * 64 else "stale"

        # Session mismatch fails before Knowledge IO; revoked action is fail-closed.
        before = len(reads)
        HermesAPI.get_session = lambda self, sid: asyncio.sleep(0, result={"session_id": "other-session"})
        mismatch = post("/api/chat/sessions/session-A/grounding-candidates", json={"query": "amount"})
        assert mismatch.status_code == 404 and len(reads) == before
        HermesAPI.get_session = fake_session
        original_require = app.state.app_auth.require_action
        def deny_knowledge(request, action):
            from fastapi import HTTPException
            if action == "knowledge.read":
                raise HTTPException(status_code=403, detail="Action is not enabled")
            return original_require(request, action)
        app.state.app_auth.require_action = deny_knowledge
        denied = post("/api/chat/sessions/session-A/grounding-candidates", json={"query": "amount"})
        assert denied.status_code == 403 and len(reads) == before
        app.state.app_auth.require_action = original_require

        # P2-5 default-off, explicit preference, evaluation, exact idempotent feedback replay.
        pref = client.get("/api/companion/preferences", headers={"Origin": vite_origin})
        assert pref.status_code == 200 and pref.json()["enabled"] is False
        off = post("/api/companion/suggestions/evaluate", json={})
        assert off.status_code == 200 and off.json()["status"] == "disabled"
        due = (date.today() + timedelta(days=1)).isoformat()
        app.state.task_store.create("Synthetic due task", due, "synthetic-task-create")
        lock = ROOT / "tasks" / ".tasks.lock"
        lock.unlink(missing_ok=True)
        categories = ["task_due"]
        saved = client.put("/api/companion/preferences", headers={"Origin": vite_origin, "Idempotency-Key": "prefs-01"},
            json={"enabled": True, "categories": categories, "expected_revision": pref.json()["revision"]})
        assert saved.status_code == 200, saved.text
        get_rows = client.get("/api/companion/suggestions", headers={"Origin": vite_origin})
        assert get_rows.status_code == 200 and not lock.exists()
        evaluated = post("/api/companion/suggestions/evaluate", json={})
        assert evaluated.status_code == 200 and evaluated.json()["items"]
        assert "no-store" in evaluated.headers["cache-control"]
        first_item = evaluated.json()["items"][0]
        assert first_item["revision"] == 1
        reevaluated = post("/api/companion/suggestions/evaluate", json={})
        assert reevaluated.status_code == 200
        item = next(row for row in reevaluated.json()["items"] if row["id"] == first_item["id"])
        assert item["revision"] == 2
        fb_path = f"/api/companion/suggestions/{item['id']}/feedback"
        fb_headers = {"Origin": vite_origin, "Idempotency-Key": "feedback-01"}
        stale = client.post(fb_path, headers={"Origin": vite_origin, "Idempotency-Key": "feedback-stale"},
            json={"decision": "accepted", "expected_revision": 1})
        assert stale.status_code == 409
        first = client.post(fb_path, headers=fb_headers, json={"decision": "accepted", "expected_revision": item["revision"]})
        replay = client.post(fb_path, headers=fb_headers, json={"decision": "accepted", "expected_revision": item["revision"]})
        assert first.status_code == replay.status_code == 200 and first.json() == replay.json(), (first.status_code, first.text, replay.status_code, replay.text)
        changed = client.post(fb_path, headers=fb_headers, json={"decision": "dismissed", "expected_revision": item["revision"]})
        assert changed.status_code == 409
        stale_task = app.state.task_store.create("Synthetic drift task", due, "synthetic-task-create-2")["task"]
        second_eval = post("/api/companion/suggestions/evaluate", json={})
        assert second_eval.status_code == 200 and any(row["title"] == "Synthetic drift task" for row in second_eval.json()["items"])
        app.state.task_store.update(stale_task["id"], {"status": "completed", "expected_updated_at": stale_task["updated_at"]})
        after_drift = client.get("/api/companion/suggestions", headers={"Origin": vite_origin})
        assert after_drift.status_code == 200 and all(row["title"] != "Synthetic drift task" for row in after_drift.json()["items"])
        latest = client.get("/api/companion/preferences", headers={"Origin": vite_origin}).json()
        disabled_save = client.put("/api/companion/preferences", headers={"Origin": vite_origin, "Idempotency-Key": "prefs-02"},
            json={"enabled": False, "categories": [], "expected_revision": latest["revision"]})
        assert disabled_save.status_code == 200
        hidden = client.get("/api/companion/suggestions", headers={"Origin": vite_origin})
        assert hidden.status_code == 200 and hidden.json()["items"] == []
        print(f"P2_4_HTTP: login={login.status_code}; candidates unauth={unauth.status_code}, available={p24.status_code}/{body['status']}, none={none.status_code}/{none.json()['status']}, drift={drifted.status_code}/{drifted.json()['status']}, session-mismatch={mismatch.status_code}, permission-denied={denied.status_code}; cache={p24.headers['cache-control']}")
        print(f"P2_5_HTTP: prefs-default={pref.status_code}/off, evaluate-off={off.status_code}/{off.json()['status']}, save={saved.status_code}, get-no-lock={get_rows.status_code}/{not lock.exists()}, evaluate={evaluated.status_code}, re-evaluate-revision={item['revision']}, stale-feedback={stale.status_code}, feedback={first.status_code}, replay-equal={first.json() == replay.json()}, changed-replay={changed.status_code}, source-complete-hides={after_drift.status_code}, disable={disabled_save.status_code}, hidden={hidden.status_code}/{len(hidden.json()['items'])}")
        print("P2_4_CORE_HTTP_GATE=PASS_WITH_LIMITS: Vite same-origin proxy -> create_app/Uvicorn; 401/403/404/200; verified metadata, no-match, source drift, no-store, no source text/path, permission/session before Knowledge IO")
        print("P2_5_CORE_HTTP_GATE=PASS_WITH_LIMITS: default-off -> explicit preferences/evaluate -> per-item revision increments on re-evaluation -> stale CAS 409/current CAS succeeds/exact replay -> source completion invalidates -> disable hides; no-store; GET projection did not create .tasks.lock")
        print(f"SYNTHETIC_ROOT={ROOT}; no real data, model, writer or Promote")
finally:
    vite.terminate()
    try: vite.wait(timeout=5)
    except subprocess.TimeoutExpired: vite.kill()
    server.should_exit = True
    core_thread.join(timeout=5)
    core_listener.close()
