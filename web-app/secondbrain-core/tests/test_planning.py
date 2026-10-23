"""P3-1 deterministic planning candidate contract and localhost regression."""
import asyncio
import hashlib
import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from secondbrain_core.app import create_app
from secondbrain_core.modules.hermes_api import HermesAPI
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore
from secondbrain_core.modules.tasks import TaskStore, task_source_version


ORIGIN = "https://planning.test"
PASSWORD = "synthetic-planning-password"


def _private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


async def _fake_session(self, session_id):
    return {"session_id": session_id, "title": "Synthetic session"}


def _configured_app(tmp_path, monkeypatch, origin=ORIGIN, host="planning.test"):
    roots = {name: _private_dir(tmp_path / name) for name in
             ("review", "raw", "knowledge", "state", "memory", "projects", "briefs", "tasks", "journal", "notes")}
    password = tmp_path / "app-password"
    password.write_text(PASSWORD + "\n", encoding="utf-8")
    os.chmod(password, 0o600)
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]), "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password), "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host, "SB_HERMES_API_URL": "",
        "SB_PROMOTE_ENABLED": "false", "SB_PERSONAL_MEMORY_ENABLED": "true",
        "SB_PERSONAL_MEMORY_ROOT": str(roots["memory"]), "SB_PERSONAL_LEARNING_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]), "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]), "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(HermesAPI, "get_session", _fake_session)
    monkeypatch.setattr(HermesAPI, "_client", lambda self, timeout=30: httpx.AsyncClient(
        base_url="http://unused", transport=httpx.MockTransport(lambda req: httpx.Response(500))))
    return create_app(), roots


def _seed_sources(app, roots):
    tasks = TaskStore(roots["tasks"])
    created = tasks.create("Synthetic task", "2026-10-22", "p3-task-idempotency")
    task = created["task"]
    task_ref = {"kind": "task", "id": task["id"], "version": task_source_version(task)}

    project = {
        "id": "project-p3-synthetic", "title": "Synthetic project", "status": "active",
        "next_step": "Review synthetic plan", "updated_at": "2026-10-22T00:00:00Z",
    }
    project_path = roots["projects"] / "project-p3-synthetic.json"
    project_payload = json.dumps(project, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8")
    project_path.write_bytes(project_payload)
    os.chmod(project_path, 0o600)
    project_doc = next(item for item in ProjectsSourceReadStore(str(roots["projects"])).read_snapshot().documents
                       if item.project_id == project["id"])
    project_ref = {"kind": "project", "id": project["id"], "version": project_doc.sha256}

    day = "2026-10-22"
    journal = JournalStore(roots["journal"])
    journal.append(day, "记一下：SYNTHETIC_PRIVATE_JOURNAL_BODY", "p3-journal-idempotency")
    row = next(iter(journal.read_source_day(day)["entries"].values()))
    journal_ref = {"kind": "journal", "id": f"{day}:{row['record']['id']}",
                   "version": row["version"]}
    return task_ref, project_ref, journal_ref


def _login(client, origin=ORIGIN):
    response = client.post("/api/auth/login", headers={"Origin": origin}, json={"password": PASSWORD})
    assert response.status_code == 200, response.text


def test_candidate_contract_real_localhost_http_and_calendar_projection(tmp_path, monkeypatch):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    app, roots = _configured_app(tmp_path, monkeypatch, origin, host)
    task_ref, project_ref, journal_ref = _seed_sources(app, roots)

    async def forbidden_run(self, *args, **kwargs):
        raise AssertionError("P3-1 must not start a Hermes Run")

    monkeypatch.setattr(HermesAPI, "start_run", forbidden_run)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            anonymous = client.post("/api/chat/sessions/session-A/planning/candidates",
                                    headers={"Origin": origin}, json={})
            assert anonymous.status_code == 401
            assert not (roots["state"] / ".planning-candidates.lock").exists()
            _login(client, origin)
            empty_calendar = client.post(
                "/api/chat/sessions/session-A/planning/candidates", headers={"Origin": origin}, json={
                    "objective": "Review empty sources", "source_refs": [],
                    "calendar_window": {"from": "2026-10-22", "to": "2026-10-22",
                                        "timezone": "Asia/Shanghai"},
                })
            assert empty_calendar.status_code == 400, empty_calendar.text
            malformed_kind = client.post(
                "/api/chat/sessions/session-A/planning/candidates", headers={"Origin": origin}, json={
                    "objective": "Review malformed kind", "source_refs": [
                        {"kind": [], "id": "a" * 32, "version": "b" * 64}],
                    "calendar_window": {"from": "2026-10-22", "to": "2026-10-22",
                                        "timezone": "Asia/Shanghai"},
                })
            assert malformed_kind.status_code == 400, malformed_kind.text
            body = {
                "objective": "Review this synthetic week",
                "source_refs": [task_ref, project_ref, journal_ref],
                "calendar_window": None,
            }
            response = client.post("/api/chat/sessions/session-A/planning/candidates",
                                   headers={"Origin": origin}, json=body)
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "private, no-store"
            result = response.json()
            assert set(result) == {"event", "version", "session_id", "candidate_id", "revision",
                                   "expires_at", "status", "objective", "steps", "workflow_status"}
            assert result["event"] == "planning.candidate" and result["version"] == 1
            assert result["session_id"] == "session-A" and result["revision"] == 0
            assert result["status"] == "ready"
            assert 0 < len(result["steps"]) <= 20
            assert [item["position"] for item in result["steps"]] == list(range(1, len(result["steps"]) + 1))
            assert {item["reason"] for item in result["steps"]} == {
                "review_task", "review_project", "review_journal",
            }
            assert all(set(item) == {"position", "kind", "source_ref", "reason", "priority", "depends_on",
                                     "decision", "execution_status"}
                       for item in result["steps"])
            assert all(item["kind"] == "review_source" and item["priority"] == "unspecified"
                       and item["depends_on"] == [] and item["decision"] == "pending"
                       and item["execution_status"] == "not_started" for item in result["steps"])
            assert "SYNTHETIC_PRIVATE_JOURNAL_BODY" not in response.text
            assert str(roots["journal"]) not in response.text
            assert "next_step" not in response.text and "Review synthetic plan" not in response.text
            assert len(response.content) <= 16 * 1024
            candidate_id = result["candidate_id"]
            invalid_decision = client.post(
                f"/api/chat/sessions/session-A/planning/candidates/{candidate_id}/steps/1/decision",
                headers={"Origin": origin, "Idempotency-Key": "bad-decision-type"},
                json={"decision": [], "expected_revision": 0})
            assert invalid_decision.status_code == 400, invalid_decision.text
            invalid_command = client.post(
                f"/api/chat/sessions/session-A/planning/candidates/{candidate_id}/control",
                headers={"Origin": origin, "Idempotency-Key": "bad-command-type"},
                json={"command": [], "expected_revision": 0})
            assert invalid_command.status_code == 400, invalid_command.text
            invalid_rating = client.post(
                f"/api/chat/sessions/session-A/planning/candidates/{candidate_id}/retrospective/feedback",
                headers={"Origin": origin, "Idempotency-Key": "bad-rating-type"},
                json={"rating": [], "expected_revision": 0})
            assert invalid_rating.status_code == 400, invalid_rating.text
            stored = app.state.planning_candidate_store._read_unlocked()["candidates"][result["candidate_id"]]
            assert stored["session_id"] == "session-A"
            assert stored["objective_sha256"] == hashlib.sha256(body["objective"].encode()).hexdigest()
            assert stored["objective"] == body["objective"]
            assert "SYNTHETIC_PRIVATE_JOURNAL_BODY" not in json.dumps(stored)
            assert all(item["session_id"] == "session-A" for item in
                       app.state.planning_candidate_store._read_unlocked()["candidates"].values())
            calendar_response = client.post(
                "/api/chat/sessions/session-A/planning/candidates", headers={"Origin": origin}, json={
                    "objective": "Review calendar metadata", "source_refs": [project_ref],
                    "calendar_window": {"from": "2026-10-22", "to": "2026-10-22",
                                        "timezone": "Asia/Shanghai"},
                })
            assert calendar_response.status_code == 200, calendar_response.text
            calendar_steps = calendar_response.json()["steps"]
            assert {step["reason"] for step in calendar_steps} == {"review_project", "review_calendar"}
            assert all(step["source_ref"]["kind"] in {"task", "project", "journal"}
                       for step in calendar_steps)
            assert "SYNTHETIC_PRIVATE_JOURNAL_BODY" not in calendar_response.text
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
    assert not thread.is_alive()


def test_auth_body_and_schema_failures_do_not_read_sources_or_create_candidate_state(tmp_path, monkeypatch):
    app, roots = _configured_app(tmp_path, monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        _login(client)
        task_store = app.state.planning_candidate_store
        original = app.state.app_auth.require_action
        calls = []

        def deny_task_read(request, action):
            calls.append(action)
            if action == "task.read":
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Action is not enabled")
            return original(request, action)

        app.state.app_auth.require_action = deny_task_read
        denied = client.post("/api/chat/sessions/session-A/planning/candidates",
                             headers={"Origin": ORIGIN}, json={
                                 "objective": "x", "source_refs": [{"kind": "task", "id": "a" * 32,
                                                                         "version": "b" * 64}],
                                 "calendar_window": None,
                             })
        assert denied.status_code == 403
        assert calls == ["chat.read", "planning.write", "task.read"]
        assert not (roots["state"] / ".planning-candidates.lock").exists()
        app.state.app_auth.require_action = original

        extra = client.post("/api/chat/sessions/session-A/planning/candidates",
                            headers={"Origin": ORIGIN}, json={"objective": "x", "source_refs": [],
                                                               "calendar_window": None, "session_id": "forged"})
        assert extra.status_code == 400
        dup = client.post("/api/chat/sessions/session-A/planning/candidates",
                          headers={"Origin": ORIGIN}, content=(
                              b'{"objective":"x","objective":"y","source_refs":[],"calendar_window":null}'))
        assert dup.status_code == 400
        invalid = client.post("/api/chat/sessions/session-A/planning/candidates",
                              headers={"Origin": ORIGIN}, json={"objective": "x", "source_refs": [],
                                                                 "calendar_window": {"from": "2026-10-22",
                                                                                     "to": "2026-11-01",
                                                                                     "timezone": "Asia/Shanghai"}})
        assert invalid.status_code == 400
        too_large = client.post("/api/chat/sessions/session-A/planning/candidates",
                                headers={"Origin": ORIGIN, "Content-Type": "application/json"},
                                content=b" " * (16 * 1024 + 1))
        assert too_large.status_code == 413
        assert not (roots["state"] / ".planning-candidates.lock").exists()


def test_source_drift_between_initial_and_final_verification_fails_closed(tmp_path, monkeypatch):
    app, roots = _configured_app(tmp_path, monkeypatch)
    task_ref, _, _ = _seed_sources(app, roots)
    task_store = TaskStore(roots["tasks"])
    real_list = task_store.list_for_projection
    snapshots = 0

    def change_after_first_read():
        nonlocal snapshots
        snapshots += 1
        tasks = real_list()["tasks"]
        if snapshots > 1:
            tasks[0]["title"] = "Synthetic task changed during plan generation"
        return {"tasks": tasks}

    service = app.state.planning_candidate_service
    service.task_store.list_for_projection = change_after_first_read

    with TestClient(app, base_url=ORIGIN) as client:
        _login(client)
        response = client.post("/api/chat/sessions/session-A/planning/candidates",
                               headers={"Origin": ORIGIN}, json={
                                   "objective": "Check source drift", "source_refs": [task_ref],
                                   "calendar_window": None,
                               })
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "stale"
    assert response.json()["steps"] == []
    assert snapshots == 2


def test_inactive_source_is_retained_only_as_needs_review(tmp_path, monkeypatch):
    app, roots = _configured_app(tmp_path, monkeypatch)
    tasks = TaskStore(roots["tasks"])
    task = tasks.create("Synthetic completed Task", None, "p3-completed-task")["task"]
    updated = tasks.update(task["id"], {"expected_updated_at": task["updated_at"],
                                        "status": "completed"})["task"]
    ref = {"kind": "task", "id": updated["id"], "version": task_source_version(updated)}
    with TestClient(app, base_url=ORIGIN) as client:
        _login(client)
        response = client.post("/api/chat/sessions/session-A/planning/candidates",
                               headers={"Origin": ORIGIN}, json={
                                   "objective": "Review completed work", "source_refs": [ref],
                                   "calendar_window": None,
                               })
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "needs_review"
    assert len(response.json()["steps"]) == 1


def test_preview_per_step_decision_and_synthetic_execute_are_cas_idempotent_and_session_scoped(
        tmp_path, monkeypatch):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    app, roots = _configured_app(tmp_path, monkeypatch, origin, host)
    task_ref, _, _ = _seed_sources(app, roots)

    async def forbidden_run(self, *args, **kwargs):
        raise AssertionError("Planning must never start a Hermes Run")

    monkeypatch.setattr(HermesAPI, "start_run", forbidden_run)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    path = "/api/chat/sessions/session-A/planning"
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            _login(client, origin)
            headers = {"Origin": origin}
            task_file = roots["tasks"] / "tasks.json"
            source_bytes_before = task_file.read_bytes()
            base = {"objective": "Review synthetic action", "source_refs": [task_ref],
                    "calendar_window": None}
            created = client.post(f"{path}/candidates", headers=headers, json=base)
            assert created.status_code == 200, created.text
            candidate_id = created.json()["candidate_id"]

            preview = client.get(f"{path}/candidates/{candidate_id}", headers=headers)
            assert preview.status_code == 200, preview.text
            assert preview.headers["cache-control"] == "private, no-store"
            preview_body = preview.json()
            assert set(preview_body) == {"event", "version", "session_id", "candidate_id", "revision",
                                         "expires_at", "status", "objective", "steps", "workflow_status"}
            assert preview_body["event"] == "planning.preview"
            assert preview_body["session_id"] == "session-A" and preview_body["revision"] == 0
            assert preview_body["steps"][0]["decision"] == "pending"
            assert preview_body["steps"][0]["execution_status"] == "not_started"
            assert str(roots["tasks"]) not in preview.text

            cross_session = client.get(f"/api/chat/sessions/session-B/planning/candidates/{candidate_id}",
                                       headers=headers)
            assert cross_session.status_code == 404

            decision_body = {"decision": "approved", "expected_revision": 0}
            decision_headers = {**headers, "Idempotency-Key": "p3-approve-1"}
            decision = client.post(f"{path}/candidates/{candidate_id}/steps/1/decision",
                                   headers=decision_headers, json=decision_body)
            assert decision.status_code == 200, decision.text
            decision_receipt = decision.json()
            assert set(decision_receipt) == {"event", "version", "session_id", "candidate_id",
                                             "revision", "position", "decision", "execution_status"}
            assert decision_receipt["revision"] == 1
            assert decision_receipt["decision"] == "approved"
            assert decision_receipt["execution_status"] == "not_started"
            assert client.post(f"{path}/candidates/{candidate_id}/steps/1/decision",
                               headers=decision_headers, json=decision_body).json() == decision_receipt
            changed_replay = client.post(f"{path}/candidates/{candidate_id}/steps/1/decision",
                                         headers=decision_headers,
                                         json={"decision": "rejected", "expected_revision": 0})
            assert changed_replay.status_code == 409
            stale_cas = client.post(f"{path}/candidates/{candidate_id}/steps/1/decision",
                                    headers={**headers, "Idempotency-Key": "p3-approve-stale"},
                                    json=decision_body)
            assert stale_cas.status_code == 409
            after_approval = client.get(f"{path}/candidates/{candidate_id}", headers=headers).json()
            assert after_approval["steps"][0]["decision"] == "approved"
            assert after_approval["steps"][0]["execution_status"] == "not_started"

            execute_body = {"expected_revision": 1}
            execute_headers = {**headers, "Idempotency-Key": "p3-execute-1"}
            execution = client.post(f"{path}/candidates/{candidate_id}/steps/1/execute",
                                    headers=execute_headers, json=execute_body)
            assert execution.status_code == 200, execution.text
            execution_receipt = execution.json()
            assert set(execution_receipt) == {"event", "version", "session_id", "candidate_id",
                                              "revision", "position", "status", "execution_mode", "effect"}
            assert execution_receipt["status"] == "simulated"
            assert execution_receipt["execution_mode"] == "synthetic"
            assert execution_receipt["effect"] == "none"
            assert execution_receipt["revision"] == 2
            assert client.post(f"{path}/candidates/{candidate_id}/steps/1/execute",
                               headers=execute_headers, json=execute_body).json() == execution_receipt
            assert task_file.read_bytes() == source_bytes_before
            ledger = app.state.planning_candidate_store._read_unlocked()
            assert len(ledger["audit"]) == 2
            assert all("idempotency-key" not in str(event).lower() for event in ledger["audit"])
            assert all("p3-approve-1" not in json.dumps(event) and "p3-execute-1" not in json.dumps(event)
                       for event in ledger["audit"])

            rejected = client.post(f"{path}/candidates", headers=headers, json=base)
            rejected_id = rejected.json()["candidate_id"]
            reject_response = client.post(
                f"{path}/candidates/{rejected_id}/steps/1/decision",
                headers={**headers, "Idempotency-Key": "p3-reject-1"},
                json={"decision": "rejected", "expected_revision": 0},
            )
            assert reject_response.status_code == 200
            blocked_execution = client.post(
                f"{path}/candidates/{rejected_id}/steps/1/execute",
                headers={**headers, "Idempotency-Key": "p3-reject-execute"},
                json={"expected_revision": 1},
            )
            assert blocked_execution.status_code == 409
            assert task_file.read_bytes() == source_bytes_before
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
    assert not thread.is_alive()


def test_preview_source_drift_hides_steps_and_never_approves(tmp_path, monkeypatch):
    app, roots = _configured_app(tmp_path, monkeypatch)
    task_ref, _, _ = _seed_sources(app, roots)
    task_file = roots["tasks"] / "tasks.json"
    with TestClient(app, base_url=ORIGIN) as client:
        _login(client)
        created = client.post("/api/chat/sessions/session-A/planning/candidates", headers={"Origin": ORIGIN},
                             json={"objective": "Review changed source", "source_refs": [task_ref],
                                   "calendar_window": None})
        assert created.status_code == 200
        candidate_id = created.json()["candidate_id"]
        changed = json.loads(task_file.read_text(encoding="utf-8"))
        changed["tasks"][0]["title"] = "Synthetic changed source"
        task_file.write_text(json.dumps(changed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.chmod(task_file, 0o600)
        response = client.get(f"/api/chat/sessions/session-A/planning/candidates/{candidate_id}",
                              headers={"Origin": ORIGIN})
        assert response.status_code == 200
        assert response.json()["status"] == "stale"
        assert response.json()["steps"] == []


def test_workflow_pause_cancel_retry_and_partial_recovery_are_explicit_and_idempotent(tmp_path, monkeypatch):
    app, roots = _configured_app(tmp_path, monkeypatch)
    task_ref, _, _ = _seed_sources(app, roots)
    service = app.state.planning_candidate_service
    with TestClient(app, base_url=ORIGIN) as client:
        _login(client)
        headers = {"Origin": ORIGIN}
        path = "/api/chat/sessions/session-A/planning"
        created = client.post(f"{path}/candidates", headers=headers, json={
            "objective": "Exercise synthetic workflow state", "source_refs": [task_ref],
            "calendar_window": None,
        })
        candidate_id = created.json()["candidate_id"]
        control_url = f"{path}/candidates/{candidate_id}/control"
        paused = client.post(control_url, headers={**headers, "Idempotency-Key": "pause-1"},
                             json={"command": "pause", "expected_revision": 0})
        assert paused.status_code == 200 and paused.json()["workflow_status"] == "paused"
        assert client.post(control_url, headers={**headers, "Idempotency-Key": "pause-1"},
                           json={"command": "pause", "expected_revision": 0}).json() == paused.json()
        assert client.post(f"{path}/candidates/{candidate_id}/steps/1/execute",
                           headers={**headers, "Idempotency-Key": "paused-execute"},
                           json={"expected_revision": 1}).status_code == 409
        resumed = client.post(control_url, headers={**headers, "Idempotency-Key": "resume-1"},
                              json={"command": "resume", "expected_revision": 1})
        assert resumed.status_code == 200 and resumed.json()["workflow_status"] == "active"
        approved = client.post(f"{path}/candidates/{candidate_id}/steps/1/decision",
                               headers={**headers, "Idempotency-Key": "approve-1"},
                               json={"decision": "approved", "expected_revision": 2})
        assert approved.status_code == 200

        def fail_once(_step):
            raise OSError("synthetic injected failure")

        monkeypatch.setattr(service, "_synthetic_execute", fail_once)
        failed = client.post(f"{path}/candidates/{candidate_id}/steps/1/execute",
                             headers={**headers, "Idempotency-Key": "execute-fail"},
                             json={"expected_revision": 3})
        assert failed.status_code == 200 and failed.json()["status"] == "failed"
        assert failed.json()["effect"] == "none"
        assert client.get(f"{path}/candidates/{candidate_id}", headers=headers).json()["workflow_status"] == "partial"
        monkeypatch.setattr(service, "_synthetic_execute", lambda _step: {
            "status": "simulated", "execution_mode": "synthetic", "effect": "none"})
        retried = client.post(control_url, headers={**headers, "Idempotency-Key": "retry-1"},
                              json={"command": "retry", "expected_revision": 4})
        assert retried.status_code == 200 and retried.json()["steps"][0]["execution_status"] == "retry_ready"
        executed = client.post(f"{path}/candidates/{candidate_id}/steps/1/execute",
                               headers={**headers, "Idempotency-Key": "execute-retry"},
                               json={"expected_revision": 5})
        assert executed.status_code == 200 and executed.json()["status"] == "simulated"
        assert client.get(f"{path}/candidates/{candidate_id}", headers=headers).json()["workflow_status"] == "completed"
        assert len(app.state.planning_candidate_store._read_unlocked()["audit"]) == 6

        other = client.post(f"{path}/candidates", headers=headers, json={
            "objective": "Exercise cancellation", "source_refs": [task_ref], "calendar_window": None,
        }).json()["candidate_id"]
        cancelled = client.post(f"{path}/candidates/{other}/control",
                                headers={**headers, "Idempotency-Key": "cancel-1"},
                                json={"command": "cancel", "expected_revision": 0})
        assert cancelled.status_code == 200 and cancelled.json()["workflow_status"] == "cancelled"
        assert client.post(f"{path}/candidates/{other}/steps/1/decision",
                           headers={**headers, "Idempotency-Key": "cancelled-approve"},
                           json={"decision": "approved", "expected_revision": 1}).status_code == 409


def test_retrospective_revalidates_sources_and_feedback_is_explicit_audited_and_idempotent(tmp_path, monkeypatch):
    app, roots = _configured_app(tmp_path, monkeypatch)
    task_ref, _, _ = _seed_sources(app, roots)
    memory_before = sorted(path.name for path in roots["memory"].iterdir())
    with TestClient(app, base_url=ORIGIN) as client:
        _login(client)
        headers = {"Origin": ORIGIN}
        path = "/api/chat/sessions/session-A/planning"
        candidate = client.post(f"{path}/candidates", headers=headers, json={
            "objective": "Review synthetic outcome", "source_refs": [task_ref], "calendar_window": None,
        }).json()
        candidate_id = candidate["candidate_id"]
        review_url = f"{path}/candidates/{candidate_id}/retrospective"
        report = client.get(review_url, headers=headers)
        assert report.status_code == 200, report.text
        body = report.json()
        assert set(body) == {"event", "version", "session_id", "candidate_id", "revision",
                             "workflow_status", "counts", "steps", "feedback"}
        assert body["event"] == "planning.retrospective"
        assert body["counts"] == {"planned": 1, "approved": 0, "rejected": 0,
                                   "completed": 0, "failed": 0, "stale_sources": 0}
        assert body["steps"][0]["source_state"] == "verified"
        assert "SYNTHETIC_PRIVATE_JOURNAL_BODY" not in report.text
        assert str(roots["tasks"]) not in report.text
        feedback_url = f"{review_url}/feedback"
        feedback_headers = {**headers, "Idempotency-Key": "retrospective-rating-1"}
        feedback_body = {"rating": "useful", "expected_revision": 0}
        feedback = client.post(feedback_url, headers=feedback_headers, json=feedback_body)
        assert feedback.status_code == 200 and feedback.json()["rating"] == "useful"
        replay = client.post(feedback_url, headers=feedback_headers, json=feedback_body)
        assert replay.json() == feedback.json()
        rated = client.get(review_url, headers=headers).json()
        assert rated["revision"] == 1 and rated["feedback"] == "useful"
        assert len(app.state.planning_candidate_store._read_unlocked()["audit"]) == 1
        task_file = roots["tasks"] / "tasks.json"
        changed = json.loads(task_file.read_text(encoding="utf-8"))
        changed["tasks"][0]["title"] = "Changed after plan"
        task_file.write_text(json.dumps(changed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.chmod(task_file, 0o600)
        stale = client.get(review_url, headers=headers).json()
        assert stale["counts"]["stale_sources"] == 1
        assert stale["steps"][0]["source_state"] == "stale"
    assert sorted(path.name for path in roots["memory"].iterdir()) == memory_before


def test_stage3_end_to_end_real_localhost_auth_cas_stale_and_restart(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from secondbrain_core.modules.source_reference_authority import SourceReferenceAuthority

    def listener_for(host="127.0.0.1", port=0):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(32)
        return listener

    listener = listener_for()
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    app, roots = _configured_app(tmp_path, monkeypatch, origin, host)
    task_ref, _, _ = _seed_sources(app, roots)
    task_file = roots["tasks"] / "tasks.json"
    source_bytes = task_file.read_bytes()

    async def forbidden_run(self, *args, **kwargs):
        raise AssertionError("Stage 3 must never invoke a Hermes model/run")

    monkeypatch.setattr(HermesAPI, "start_run", forbidden_run)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    candidate_id = None
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            _login(client, origin)
            headers = {"Origin": origin}
            path = "/api/chat/sessions/session-A/planning"

            verify_calls = []
            original_verify = SourceReferenceAuthority.verify
            monkeypatch.setattr(SourceReferenceAuthority, "verify",
                                lambda self, ref: (verify_calls.append(ref), original_verify(self, ref))[1])
            original_require = app.state.app_auth.require_action

            def deny_planning_read(request, action):
                if action == "planning.read":
                    from fastapi import HTTPException
                    raise HTTPException(status_code=403, detail="Action is not enabled")
                return original_require(request, action)

            app.state.app_auth.require_action = deny_planning_read
            denied = client.get(f"{path}/candidates/not-a-real-id/retrospective", headers=headers)
            assert denied.status_code == 403
            assert verify_calls == []
            app.state.app_auth.require_action = original_require
            monkeypatch.setattr(SourceReferenceAuthority, "verify", original_verify)

            created = client.post(f"{path}/candidates", headers=headers, json={
                "objective": "End-to-end synthetic planning", "source_refs": [task_ref],
                "calendar_window": None,
            })
            assert created.status_code == 200, created.text
            candidate_id = created.json()["candidate_id"]
            decision_url = f"{path}/candidates/{candidate_id}/steps/1/decision"

            def approve(key):
                with httpx.Client(base_url=origin, timeout=5, trust_env=False,
                                  cookies=client.cookies) as concurrent_client:
                    return concurrent_client.post(decision_url, headers={**headers, "Idempotency-Key": key},
                                                  json={"decision": "approved", "expected_revision": 0})

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(approve, ("concurrent-approve-a", "concurrent-approve-b")))
            assert sorted(response.status_code for response in responses) == [200, 409]
            executed = client.post(f"{path}/candidates/{candidate_id}/steps/1/execute",
                                   headers={**headers, "Idempotency-Key": "integrated-execute"},
                                   json={"expected_revision": 1})
            assert executed.status_code == 200 and executed.json()["effect"] == "none"
            retrospective = client.get(f"{path}/candidates/{candidate_id}/retrospective", headers=headers)
            assert retrospective.status_code == 200
            assert retrospective.json()["counts"]["completed"] == 1
            assert task_file.read_bytes() == source_bytes

            stale = client.post(f"{path}/candidates", headers=headers, json={
                "objective": "Stale source must stop", "source_refs": [task_ref], "calendar_window": None,
            }).json()["candidate_id"]
            changed = json.loads(task_file.read_text(encoding="utf-8"))
            changed["tasks"][0]["title"] = "Drift after capture"
            task_file.write_text(json.dumps(changed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.chmod(task_file, 0o600)
            denied_decision = client.post(f"{path}/candidates/{stale}/steps/1/decision",
                                          headers={**headers, "Idempotency-Key": "stale-approve"},
                                          json={"decision": "approved", "expected_revision": 0})
            assert denied_decision.status_code == 409
            assert client.get(f"{path}/candidates/{stale}/retrospective", headers=headers).json()[
                "counts"]["stale_sources"] == 1
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
    assert not thread.is_alive()

    # Reconstruct the real Core app over the same synthetic roots and read back durable state.
    listener2 = listener_for(host, port)
    app2, _ = _configured_app(tmp_path, monkeypatch, origin, host)
    server2 = uvicorn.Server(uvicorn.Config(app2, host=host, port=port, log_level="critical",
                                            lifespan="off", access_log=False, proxy_headers=False))
    thread2 = threading.Thread(target=server2.run, kwargs={"sockets": [listener2]}, daemon=True)
    thread2.start()
    try:
        deadline = time.monotonic() + 10
        while not server2.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server2.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            _login(client, origin)
            headers = {"Origin": origin}
            readback = client.get(
                f"/api/chat/sessions/session-A/planning/candidates/{candidate_id}", headers=headers)
            assert readback.status_code == 200
            assert readback.json()["workflow_status"] == "completed"
            report = client.get(
                f"/api/chat/sessions/session-A/planning/candidates/{candidate_id}/retrospective",
                headers=headers)
            assert report.status_code == 200 and report.json()["counts"]["completed"] == 1
    finally:
        server2.should_exit = True
        thread2.join(timeout=10)
        listener2.close()
    assert not thread2.is_alive()
