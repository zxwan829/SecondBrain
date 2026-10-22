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
                                   "expires_at", "status", "objective", "steps"}
            assert result["event"] == "planning.candidate" and result["version"] == 1
            assert result["session_id"] == "session-A" and result["revision"] == 0
            assert result["status"] == "ready"
            assert 0 < len(result["steps"]) <= 20
            assert [item["position"] for item in result["steps"]] == list(range(1, len(result["steps"]) + 1))
            assert {item["reason"] for item in result["steps"]} == {
                "review_task", "review_project", "review_journal",
            }
            assert all(set(item) == {"position", "kind", "source_ref", "reason", "priority", "depends_on"}
                       for item in result["steps"])
            assert all(item["kind"] == "review_source" and item["priority"] == "unspecified"
                       and item["depends_on"] == [] for item in result["steps"])
            assert "SYNTHETIC_PRIVATE_JOURNAL_BODY" not in response.text
            assert str(roots["journal"]) not in response.text
            assert "next_step" not in response.text and "Review synthetic plan" not in response.text
            assert len(response.content) <= 16 * 1024
            stored = app.state.planning_candidate_store._read_unlocked()["candidates"][result["candidate_id"]]
            assert stored["session_id"] == "session-A"
            assert stored["objective_sha256"] == hashlib.sha256(body["objective"].encode()).hexdigest()
            assert body["objective"] not in json.dumps(stored)
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

