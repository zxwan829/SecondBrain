"""Synthetic Vite same-origin HTTP gate for the Stage 3 planning flow.

This runs the actual Core app through Uvicorn and proxies the real frontend via Vite.
All stores and credentials are created under a private temporary directory.
"""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.hermes_api import HermesAPI
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore
from secondbrain_core.modules.tasks import TaskStore, task_source_version


ROOT = Path(tempfile.mkdtemp(prefix="sb-p3-gate-", dir="/private/tmp"))
for name in ("review", "raw", "knowledge", "state", "memory", "projects", "briefs", "tasks", "journal", "notes"):
    (ROOT / name).mkdir(mode=0o700)
password_file = ROOT / "password"
password_file.write_text("synthetic-only-password\n", encoding="utf-8")
password_file.chmod(0o600)


def reserve_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


core_port, vite_port = reserve_port(), reserve_port()
core_origin, vite_origin = f"http://127.0.0.1:{core_port}", f"http://127.0.0.1:{vite_port}"
for key, value in {
    "SB_REVIEW_ROOT": str(ROOT / "review"), "SB_CAPTURE_RAW_ROOT": str(ROOT / "raw"),
    "SB_KNOWLEDGE_ROOT": str(ROOT / "knowledge"), "SB_PROMOTE_STATE_ROOT": str(ROOT / "state"),
    "SB_APP_PASSWORD_FILE": str(password_file), "SB_DASHBOARD_ORIGINS": vite_origin,
    "SB_CORE_ALLOWED_HOSTS": "127.0.0.1", "SB_HERMES_API_URL": "", "SB_PROMOTE_ENABLED": "false",
    "SB_PERSONAL_MEMORY_ENABLED": "true", "SB_PERSONAL_MEMORY_ROOT": str(ROOT / "memory"),
    "SB_PERSONAL_LEARNING_ENABLED": "false", "SB_PROJECTS_INDEX_ROOT": str(ROOT / "projects"),
    "SB_DAILY_BRIEF_STORE_ROOT": str(ROOT / "briefs"), "SB_TASK_ROOT": str(ROOT / "tasks"),
    "SB_JOURNAL_ROOT": str(ROOT / "journal"), "SB_NOTES_DRAFTS_ROOT": str(ROOT / "notes"),
    "SB_CORE_PROXY_TARGET": core_origin, "SB_NOTES_AUTHORIZED_ROOTS": "{}",
}.items():
    os.environ[key] = value


async def fake_session(self, session_id):
    return {"session_id": session_id, "title": "Synthetic planning session"}


HermesAPI.get_session = fake_session
HermesAPI._client = lambda self, timeout=30: httpx.AsyncClient(
    base_url="http://unused", transport=httpx.MockTransport(lambda request: httpx.Response(500)))
HermesAPI.start_run = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model call forbidden"))

task_store = TaskStore(ROOT / "tasks")
task = task_store.create("Synthetic P3 task", "2026-10-22", "p3-gate-source")['task']
task_ref = {"kind": "task", "id": task["id"], "version": task_source_version(task)}
task_file = ROOT / "tasks" / "tasks.json"
project_doc = {"id": "project-p3-synthetic", "title": "Synthetic P3 project", "status": "active",
               "next_step": "Synthetic next step", "updated_at": "2026-10-22T00:00:00Z"}
project_file = ROOT / "projects" / f"{project_doc['id']}.json"
project_file.write_text(json.dumps(project_doc, sort_keys=True, separators=(",", ":")), encoding="utf-8")
project_file.chmod(0o600)
project_snapshot = next(row for row in ProjectsSourceReadStore(str(ROOT / "projects")).read_snapshot().documents
                        if row.project_id == project_doc["id"])
project_ref = {"kind": "project", "id": project_doc["id"], "version": project_snapshot.sha256}
journal_day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
journal_store = JournalStore(ROOT / "journal")
journal_store.append(journal_day, "记一下：SYNTHETIC_P3_PRIVATE_JOURNAL_BODY", "p3-gate-journal")
journal_row = next(iter(journal_store.read_source_day(journal_day)["entries"].values()))
journal_ref = {"kind": "journal", "id": f"{journal_day}:{journal_row['record']['id']}",
               "version": journal_row["version"]}
source_snapshots = {task_file: task_file.read_bytes(), project_file: project_file.read_bytes(),
                    ROOT / "journal" / f"{journal_day}.jsonl": (ROOT / "journal" / f"{journal_day}.jsonl").read_bytes()}


def start_core():
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", core_port))
    listener.listen(32)
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=core_port,
        log_level="critical", lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "Core Uvicorn did not start"
    return app, server, thread, listener


def wait_http(url):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=0.5, trust_env=False) as client:
                response = client.get(url)
                if response.status_code < 500:
                    return response
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"server did not start: {url}")


app, server, core_thread, core_listener = start_core()
repo_root = Path(__file__).resolve().parents[3]
frontend = repo_root / "web-app" / "secondbrain-frontend"
vite = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
    cwd=frontend, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
candidate_id = None

try:
    page = wait_http(vite_origin + "/")
    assert page.status_code == 200 and "/src/main.tsx" in page.text
    panel_module = wait_http(vite_origin + "/src/PlanningPanel.tsx")
    assert panel_module.status_code == 200 and "Open planning" in panel_module.text
    with httpx.Client(base_url=vite_origin, timeout=5, trust_env=False) as client:
        def headers(**extra):
            return {"Origin": vite_origin, **extra}

        path = "/api/chat/sessions/session-A/planning"
        unauth = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic objective", "source_refs": [task_ref], "calendar_window": None})
        assert unauth.status_code == 401 and "no-store" in unauth.headers.get("cache-control", "")
        login = client.post("/api/auth/login", headers=headers(), json={"password": "synthetic-only-password"})
        assert login.status_code == 200, login.text

        # The client source-choice projections and the planning candidate share this origin.
        task_choices = client.get("/api/tasks?status=all")
        project_choices = client.get("/api/projects?limit=50&offset=0")
        journal_choices = client.get(f"/api/daily-brief/source-options/journal?date={journal_day}&limit=50",
                                     headers={"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors",
                                              "Sec-Fetch-Dest": "empty"})
        assert task_choices.status_code == project_choices.status_code == 200, (
            task_choices.status_code, task_choices.text, project_choices.status_code, project_choices.text)
        assert journal_choices.status_code == 200 and journal_choices.json()["items"]
        assert "SYNTHETIC_P3_PRIVATE_JOURNAL_BODY" not in journal_choices.text
        assert "no-store" in task_choices.headers.get("cache-control", "")

        created = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic end-to-end review", "source_refs": [task_ref, project_ref, journal_ref], "calendar_window": None})
        assert created.status_code == 200, created.text
        candidate_id = created.json()["candidate_id"]
        assert "no-store" in created.headers.get("cache-control", "")
        assert "SYNTHETIC_P3_PRIVATE_JOURNAL_BODY" not in created.text
        assert str(ROOT) not in created.text
        assert len(created.content) <= 16 * 1024 and created.json()["steps"]
        wrong_session = client.get(f"/api/chat/sessions/session-B/planning/candidates/{candidate_id}")
        assert wrong_session.status_code == 404
        candidate_path = f"{path}/candidates/{candidate_id}"
        preview = client.get(candidate_path)
        assert preview.status_code == 200 and preview.json()["session_id"] == "session-A"

        revision = preview.json()["revision"]
        for position in range(1, len(preview.json()["steps"]) + 1):
            decision = client.post(candidate_path + f"/steps/{position}/decision",
                headers=headers(**{"Idempotency-Key": f"p3-gate-approve-{position}"}),
                json={"decision": "approved", "expected_revision": revision})
            assert decision.status_code == 200 and decision.json()["decision"] == "approved"
            revision = decision.json()["revision"]
            execute = client.post(candidate_path + f"/steps/{position}/execute",
                headers=headers(**{"Idempotency-Key": f"p3-gate-execute-{position}"}),
                json={"expected_revision": revision})
            assert execute.status_code == 200 and execute.json()["effect"] == "none"
            revision = execute.json()["revision"]
        recap = client.get(candidate_path + "/retrospective")
        assert recap.status_code == 200 and recap.json()["counts"]["completed"] == len(preview.json()["steps"])
        feedback = client.post(candidate_path + "/retrospective/feedback", headers=headers(**{"Idempotency-Key": "p3-gate-feedback"}),
                               json={"rating": "useful", "expected_revision": recap.json()["revision"]})
        replay = client.post(candidate_path + "/retrospective/feedback", headers=headers(**{"Idempotency-Key": "p3-gate-feedback"}),
                             json={"rating": "useful", "expected_revision": recap.json()["revision"]})
        assert feedback.status_code == replay.status_code == 200 and feedback.json() == replay.json()
        changed_replay = client.post(candidate_path + "/retrospective/feedback", headers=headers(**{"Idempotency-Key": "p3-gate-feedback"}),
                                     json={"rating": "not_useful", "expected_revision": recap.json()["revision"]})
        assert changed_replay.status_code == 409
        assert all(file.read_bytes() == snapshot for file, snapshot in source_snapshots.items()), (
            "Planning workflow changed a business source")

        controlled = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic workflow controls", "source_refs": [task_ref], "calendar_window": None}).json()
        control_url = f"{path}/candidates/{controlled['candidate_id']}/control"
        paused = client.post(control_url, headers=headers(**{"Idempotency-Key": "p3-gate-pause"}),
                             json={"command": "pause", "expected_revision": controlled["revision"]})
        resumed = client.post(control_url, headers=headers(**{"Idempotency-Key": "p3-gate-resume"}),
                              json={"command": "resume", "expected_revision": paused.json()["revision"]})
        cancelled = client.post(control_url, headers=headers(**{"Idempotency-Key": "p3-gate-cancel"}),
                                json={"command": "cancel", "expected_revision": resumed.json()["revision"]})
        assert [paused.status_code, resumed.status_code, cancelled.status_code] == [200, 200, 200]
        assert cancelled.json()["workflow_status"] == "cancelled"

        recoverable = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic failure and recovery", "source_refs": [task_ref], "calendar_window": None}).json()
        recoverable_path = f"{path}/candidates/{recoverable['candidate_id']}"
        approved = client.post(recoverable_path + "/steps/1/decision",
            headers=headers(**{"Idempotency-Key": "p3-gate-recovery-approve"}),
            json={"decision": "approved", "expected_revision": recoverable["revision"]})
        assert approved.status_code == 200
        service = app.state.planning_candidate_service
        original_execute = service._synthetic_execute
        execution_attempts = [0]
        def fail_once(step):
            execution_attempts[0] += 1
            if execution_attempts[0] == 1:
                raise OSError("synthetic injected executor failure")
            return original_execute(step)
        service._synthetic_execute = fail_once
        failed = client.post(recoverable_path + "/steps/1/execute",
            headers=headers(**{"Idempotency-Key": "p3-gate-failure"}),
            json={"expected_revision": approved.json()["revision"]})
        assert failed.status_code == 200 and failed.json()["status"] == "failed" and failed.json()["effect"] == "none"
        retry_ready = client.post(recoverable_path + "/control",
            headers=headers(**{"Idempotency-Key": "p3-gate-retry-ready"}),
            json={"command": "retry", "expected_revision": failed.json()["revision"]})
        assert retry_ready.status_code == 200
        service._synthetic_execute = original_execute
        recovered = client.post(recoverable_path + "/steps/1/execute",
            headers=headers(**{"Idempotency-Key": "p3-gate-recovered-execute"}),
            json={"expected_revision": retry_ready.json()["revision"]})
        assert recovered.status_code == 200 and recovered.json()["status"] == "simulated"

        concurrent_candidate = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic concurrent CAS", "source_refs": [task_ref], "calendar_window": None}).json()
        concurrent_url = f"{path}/candidates/{concurrent_candidate['candidate_id']}/steps/1/decision"
        def approve(key):
            with httpx.Client(base_url=vite_origin, timeout=5, trust_env=False, cookies=client.cookies) as concurrent_client:
                return concurrent_client.post(concurrent_url, headers=headers(**{"Idempotency-Key": key}),
                    json={"decision": "approved", "expected_revision": concurrent_candidate["revision"]})
        with ThreadPoolExecutor(max_workers=2) as pool:
            cas_responses = list(pool.map(approve, ("p3-gate-cas-a", "p3-gate-cas-b")))
        assert sorted(response.status_code for response in cas_responses) == [200, 409]

        stale_candidate = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic stale source", "source_refs": [task_ref], "calendar_window": None}).json()
        source_task = task_store.list_for_projection()["tasks"][0]
        task_store.update(source_task["id"], {"title": "Synthetic source drift", "expected_updated_at": source_task["updated_at"]})
        stale_decision = client.post(
            f"{path}/candidates/{stale_candidate['candidate_id']}/steps/1/decision",
            headers=headers(**{"Idempotency-Key": "p3-gate-stale-approve"}),
            json={"decision": "approved", "expected_revision": stale_candidate["revision"]})
        assert stale_decision.status_code == 409

        # Permission denial occurs before source verification; revoked access is fail-closed.
        from secondbrain_core.modules.source_reference_authority import SourceReferenceAuthority
        verify_calls = []
        original_verify = SourceReferenceAuthority.verify
        SourceReferenceAuthority.verify = lambda authority, ref: (verify_calls.append(ref), original_verify(authority, ref))[1]
        original_require = app.state.app_auth.require_action
        def deny_planning_read(request, action):
            if action == "planning.read":
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Action is not enabled")
            return original_require(request, action)
        app.state.app_auth.require_action = deny_planning_read
        denied = client.get(candidate_path)
        assert denied.status_code == 403 and verify_calls == []
        app.state.app_auth.require_action = original_require
        SourceReferenceAuthority.verify = original_verify

        # App reconstruction proves persistent readback over only the synthetic state root.
        server.should_exit = True
        core_thread.join(timeout=5)
        core_listener.close()
        assert not core_thread.is_alive()
        app2, server, core_thread, core_listener = start_core()
        relogin = client.post("/api/auth/login", headers=headers(), json={"password": "synthetic-only-password"})
        assert relogin.status_code == 200, relogin.text
        restored = client.get(candidate_path)
        restored_recap = client.get(candidate_path + "/retrospective")
        assert restored.status_code == 200 and restored.json()["workflow_status"] == "completed", (restored.status_code, restored.text)
        assert restored_recap.status_code == 200 and restored_recap.json()["feedback"] == "useful"
        print("P3_1_5_HTTP: PASS_WITH_LIMITS; Vite same-origin proxy -> real create_app/Uvicorn; synthetic login, no-store, Task/Project/Journal metadata projections, no Journal body, candidate create/preview, cross-session 404, approve/execute effect=none, retrospective/feedback replay and conflict, pause/resume/cancel, injected failure -> explicit retry-ready -> recovered synthetic execution, concurrent CAS single winner, stale source rejection, permission denied before source verify, all selected business-source bytes stable, app-restart readback.")
        print(f"P3_SYNTHETIC_ROOT={ROOT}; browser/model/production/user acceptance not implied")
finally:
    vite.terminate()
    try:
        vite.wait(timeout=5)
    except subprocess.TimeoutExpired:
        vite.kill()
    server.should_exit = True
    core_thread.join(timeout=5)
    core_listener.close()
