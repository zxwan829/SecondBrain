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
from datetime import datetime, timedelta, timezone
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
journal_store.append(journal_day, "记一下：SYNTHETIC_P3_PRIVATE_JOURNAL_BODY", "p3-gate-journal", session_id="session-A")
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

        home = client.get("/api/home")
        assert home.status_code == 200 and home.json().get("status") == "ok"
        assert "no-store" in home.headers.get("cache-control", "")

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

        # Exercise the real Today/Task API over Vite -> Core, including exact
        # create replay, CAS update replay, and authoritative list readback.
        today_tasks = client.get(f"/api/tasks?status=open&due_date={journal_day}")
        assert today_tasks.status_code == 200 and isinstance(today_tasks.json().get("tasks"), list)
        create_task_body = {"title": "Synthetic Today task", "due_date": journal_day,
                            "original_command": "synthetic explicit Task action", "session_id": "session-A"}
        create_task_headers = headers(**{"Idempotency-Key": "p3-gate-task-create-001"})
        created_task_response = client.post("/api/tasks", headers=create_task_headers, json=create_task_body)
        replay_task_response = client.post("/api/tasks", headers=create_task_headers, json=create_task_body)
        assert created_task_response.status_code == replay_task_response.status_code == 200
        created_task = created_task_response.json()["task"]
        replayed_task = replay_task_response.json()["task"]
        assert created_task_response.json()["status"] == "created"
        assert replay_task_response.json()["status"] == "duplicate"
        assert created_task["id"] == replayed_task["id"]
        update_task_body = {"title": "Synthetic Today task updated", "expected_updated_at": created_task["updated_at"]}
        # Task updates use an expected_updated_at compare-and-swap contract,
        # not an Idempotency-Key replay contract. The first update succeeds;
        # replaying its stale version must fail with 409 without overwriting.
        updated_task_response = client.patch(f"/api/tasks/{created_task['id']}",
                                             headers=headers(), json=update_task_body)
        replay_update_response = client.patch(f"/api/tasks/{created_task['id']}",
                                              headers=headers(), json=update_task_body)
        assert updated_task_response.status_code == 200
        assert replay_update_response.status_code == 409
        assert replay_update_response.json() == {
            "detail": "Task changed since it was loaded; reload before editing"
        }
        updated_task = updated_task_response.json()["task"]
        assert updated_task["title"] == "Synthetic Today task updated"
        task_readback = client.get("/api/tasks?status=all")
        assert task_readback.status_code == 200
        assert any(row.get("id") == created_task["id"] and row.get("title") == updated_task["title"]
                   for row in task_readback.json()["tasks"])
        task_ref = {"kind": "task", "id": updated_task["id"], "version": task_source_version(updated_task)}
        assert len(task_ref["version"]) == 64
        source_snapshots[task_file] = task_file.read_bytes()

        journal_readback = client.get(f"/api/journal/{journal_day}")
        assert journal_readback.status_code == 200
        assert any(row.get("id") == journal_row["record"]["id"]
                   for row in journal_readback.json().get("entries", []))

        calendar = client.get(f"/api/calendar?from={journal_day}&to={journal_day}&timezone=Asia%2FShanghai")
        assert calendar.status_code == 200 and calendar.json().get("status") == "ok"
        assert {item.get("kind") for item in calendar.json().get("items", [])} >= {"journal", "task"}

        # Seed one exact, private synthetic historical Brief record, then use
        # the same approved_import selector/header contract as the Web UI.
        business_day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        brief_source_day = (business_day - timedelta(days=1)).isoformat()
        brief_target_day = (business_day - timedelta(days=2)).isoformat()
        brief_source_record = {
            "brief_id": "p3-source-brief", "date": brief_source_day,
            "timezone": "Asia/Shanghai",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "generation_status": "generated", "categories": ["synthetic"],
            "summary": "SYNTHETIC_P3_APPROVED_IMPORT_SOURCE",
            "source_refs": [task_ref],
        }
        brief_source_file = ROOT / "briefs" / f"{brief_source_day}.json"
        brief_source_file.write_text(json.dumps(brief_source_record, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        brief_source_file.chmod(0o600)
        same_origin_get_headers = headers(**{"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors",
                                             "Sec-Fetch-Dest": "empty"})
        brief_options = client.get(
            f"/api/daily-brief/source-options/brief?date={brief_source_day}&limit=1",
            headers=same_origin_get_headers,
        )
        assert brief_options.status_code == 200 and brief_options.json().get("status") == "real"
        brief_option = brief_options.json()["items"][0]
        brief_detail = client.get(
            f"/api/daily-brief?date={brief_source_day}&timezone=Asia%2FShanghai",
            headers=same_origin_get_headers,
        )
        assert brief_detail.status_code == 200 and brief_detail.json().get("status") == "real"
        detail_record = brief_detail.json()["items"][0]
        assert detail_record["brief_id"] == brief_source_record["brief_id"]
        assert "no-store" in brief_detail.headers.get("cache-control", "")
        approved_import_body = {
            "mode": "approved_import", "date": brief_target_day, "timezone": "Asia/Shanghai",
            "categories": detail_record["categories"], "summary": detail_record["summary"],
            "source_refs": detail_record["source_refs"], "approved": True,
            "import_ref": {"kind": "existing_brief", "id": brief_option["id"], "version": brief_option["version"]},
        }
        approved_import_headers = headers(**{"Idempotency-Key": "p3-gate-brief-import-001"})
        imported = client.post("/api/daily-brief", headers=approved_import_headers, json=approved_import_body)
        imported_replay = client.post("/api/daily-brief", headers=approved_import_headers, json=approved_import_body)
        assert imported.status_code == 201 and imported.json().get("status") == "created"
        assert imported_replay.status_code == 200 and imported_replay.json().get("status") == "duplicate"
        assert imported_replay.json().get("brief_id") == imported.json().get("brief_id")
        imported_readback = client.get(
            f"/api/daily-brief?date={brief_target_day}&timezone=Asia%2FShanghai",
            headers=same_origin_get_headers,
        )
        assert imported_readback.status_code == 200 and imported_readback.json().get("status") == "real"
        assert imported_readback.json()["items"][0]["brief_id"] == imported.json()["brief_id"]
        assert imported_readback.json()["items"][0]["summary"] == brief_source_record["summary"]
        assert "no-store" in imported_readback.headers.get("cache-control", "")
        conflict = client.post("/api/daily-brief",
            headers=headers(**{"Idempotency-Key": "p3-gate-brief-import-002"}), json=approved_import_body)
        assert conflict.status_code == 409

        activity = client.get(f"/api/activity?from={brief_target_day}&to={journal_day}&limit=50&offset=0")
        assert activity.status_code == 200 and isinstance(activity.json().get("items"), list)
        assert "no-store" in activity.headers.get("cache-control", "")
        activity_kinds = {item.get("kind") for item in activity.json()["items"]}
        assert {"task", "journal", "daily_brief"} <= activity_kinds

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
            step_kind = preview.json()["steps"][position - 1]["kind"]
            expected_effect = "planning_ledger" if step_kind == "review_source" else "task_created" if step_kind == "create_task" else "none"
            assert execute.status_code == 200 and execute.json()["effect"] == expected_effect
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

        # The frozen Planning contract supports an explicit proposed_tasks
        # action. Approve and execute each returned step, then prove the
        # task_created receipt is durable and does not create a duplicate on
        # an exact replay.
        task_action_candidate = client.post(path + "/candidates", headers=headers(), json={
            "objective": "Synthetic approved Task action", "source_refs": [task_ref],
            "calendar_window": None,
            "proposed_tasks": [{"title": "Synthetic Planning Task", "due_date": journal_day}],
        })
        assert task_action_candidate.status_code == 200
        task_action_id = task_action_candidate.json()["candidate_id"]
        task_action_path = f"{path}/candidates/{task_action_id}"
        task_action_preview = client.get(task_action_path)
        assert task_action_preview.status_code == 200
        task_action_steps = task_action_preview.json()["steps"]
        assert [item["kind"] for item in task_action_steps] == ["review_source", "create_task"]
        revision = task_action_preview.json()["revision"]
        task_created_receipt = None
        task_execute_headers = None
        task_execute_body = None
        for position, step in enumerate(task_action_steps, 1):
            decision = client.post(task_action_path + f"/steps/{position}/decision",
                headers=headers(**{"Idempotency-Key": f"p3-gate-task-action-approve-{position}"}),
                json={"decision": "approved", "expected_revision": revision})
            assert decision.status_code == 200 and decision.json()["execution_status"] == "not_started"
            revision = decision.json()["revision"]
            execute_key = f"p3-gate-task-action-execute-{position}"
            execute_headers = headers(**{"Idempotency-Key": execute_key})
            execute_body = {"expected_revision": revision}
            executed = client.post(task_action_path + f"/steps/{position}/execute",
                                   headers=execute_headers, json=execute_body)
            expected_effect = "task_created" if step["kind"] == "create_task" else "planning_ledger"
            assert executed.status_code == 200 and executed.json().get("effect") == expected_effect
            assert executed.json().get("status") == "completed"
            if step["kind"] == "create_task":
                task_created_receipt = executed.json()
                task_execute_headers = execute_headers
                task_execute_body = execute_body
            revision = executed.json()["revision"]
        assert task_created_receipt is not None and task_execute_headers is not None
        task_action_replay = client.post(task_action_path + "/steps/2/execute",
                                         headers=task_execute_headers, json=task_execute_body)
        assert task_action_replay.status_code == 200
        assert task_action_replay.json() == task_created_receipt
        task_action_readback = client.get("/api/tasks?status=all")
        assert task_action_readback.status_code == 200
        assert any(row.get("id") == task_created_receipt["task_id"]
                   and row.get("title") == "Synthetic Planning Task"
                   for row in task_action_readback.json()["tasks"])

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
        original_execute = service._execute_step
        execution_attempts = [0]
        def fail_once(step, **kwargs):
            execution_attempts[0] += 1
            if execution_attempts[0] == 1:
                raise OSError("synthetic injected executor failure")
            return original_execute(step, **kwargs)
        service._execute_step = fail_once
        failed = client.post(recoverable_path + "/steps/1/execute",
            headers=headers(**{"Idempotency-Key": "p3-gate-failure"}),
            json={"expected_revision": approved.json()["revision"]})
        assert failed.status_code == 200 and failed.json()["status"] == "failed" and failed.json()["effect"] == "planning_ledger"
        retry_ready = client.post(recoverable_path + "/control",
            headers=headers(**{"Idempotency-Key": "p3-gate-retry-ready"}),
            json={"command": "retry", "expected_revision": failed.json()["revision"]})
        assert retry_ready.status_code == 200
        service._execute_step = original_execute
        recovered = client.post(recoverable_path + "/steps/1/execute",
            headers=headers(**{"Idempotency-Key": "p3-gate-recovered-execute"}),
            json={"expected_revision": retry_ready.json()["revision"]})
        assert recovered.status_code == 200 and recovered.json()["status"] == "completed"
        assert recovered.json()["effect"] == "planning_ledger"

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
        source_task = next(item for item in task_store.list_for_projection()["tasks"]
                           if item["id"] == task_ref["id"])
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
        print("P3_1_5_HTTP: PASS_WITH_LIMITS; fixed Web -> same-origin Vite proxy -> fixed Core create_app/Uvicorn; Home, Activity, Projects, Today/Task create replay/update-CAS conflict/readback, Journal read, Calendar projection, Brief exact-date approved_import/create/replay/readback/409, Planning review plus approved create_task/receipt/replay/readback, session isolation, feedback replay/conflict, pause/resume/cancel, injected failure/retry, concurrent CAS, stale source rejection, permission denied before source verify, and persistence after app restart.")
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
