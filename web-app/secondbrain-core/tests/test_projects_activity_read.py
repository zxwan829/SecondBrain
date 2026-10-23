import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.daily_brief_import import DailyBriefAuditStore
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.personal_memory import PersonalMemoryStore
from secondbrain_core.modules.projects_activity_read import create_projects_activity_router
from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore
from secondbrain_core.modules.tasks import TaskStore


def make_client(tmp_path, journal=None, tasks=None, projects=None, daily_brief_audit=None, memory=None):
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-password-value\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    token = "synthetic-app-session"
    session_id = hashlib.sha256(token.encode()).hexdigest()
    auth._sessions[session_id] = time.time() + 600
    auth._session_actions[session_id] = set(auth.SUPPORTED_ACTIONS)
    app = FastAPI()
    app.state.test_auth = auth
    app.include_router(create_projects_activity_router(
        auth, journal, tasks, projects_store=projects,
        daily_brief_audit_store=daily_brief_audit,
        memory_store=memory,
    ))
    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    return client


def make_journal(tmp_path):
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return JournalStore(str(root))


def make_tasks(tmp_path):
    root = tmp_path / "tasks"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return TaskStore(str(root))


def make_memory(tmp_path):
    root = tmp_path / "memory"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return PersonalMemoryStore(root)


def test_projects_is_authenticated_truthful_empty_contract(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/projects?limit=7&offset=2")
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_configured",
        "items": [],
        "pagination": {"limit": 7, "offset": 2, "has_more": False},
        "source": None,
        "freshness": {"checked_at": response.json()["freshness"]["checked_at"]},
    }
    assert response.json()["freshness"]["checked_at"].endswith("Z")

    client.cookies.clear()
    assert client.get("/api/projects").status_code == 401


def test_projects_rejects_invalid_pagination(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/projects?limit=101").status_code == 400
    assert client.get("/api/projects?offset=-1").status_code == 400


def test_activity_unconfigured_and_empty_sources_are_distinct(tmp_path):
    unavailable = make_client(tmp_path).get("/api/activity")
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["source"] == []
    assert unavailable.json()["items"] == []

    journal = make_journal(tmp_path)
    empty = make_client(tmp_path, journal=journal).get("/api/activity")
    assert empty.status_code == 200
    assert empty.json()["status"] == "partial"
    assert empty.json()["source"] == ["journal"]
    assert empty.json()["items"] == []


def test_activity_projects_only_minimal_journal_and_task_metadata(tmp_path):
    journal = make_journal(tmp_path)
    tasks = make_tasks(tmp_path)
    day = date.today().isoformat()
    journal.append(day, "记一下 synthetic PRIVATE journal body", "synthetic-journal-operation",
                   session_id="private-session-id")
    tasks.create("Synthetic task title", (date.today() + timedelta(days=1)).isoformat(),
                 "synthetic-task-operation", original_command="PRIVATE task command",
                 session_id="private-session-id")
    client = make_client(tmp_path, journal=journal, tasks=tasks)

    response = client.get(f"/api/activity?from={day}&to={day}&timezone=Asia%2FShanghai&limit=1")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["source"] == ["journal", "tasks"]
    assert body["pagination"] == {"limit": 1, "offset": 0, "has_more": True}
    assert len(body["items"]) == 1
    assert set(body["items"][0]) <= {
        "activity_id", "kind", "status", "occurred_at", "journal_date",
        "task_due_date", "task_status",
    }
    assert "original_text" not in body["items"][0]
    assert "original_command" not in body["items"][0]
    assert "session_id" not in body["items"][0]
    assert "operation_id" not in body["items"][0]
    assert "PRIVATE" not in response.text
    assert "private-session-id" not in response.text
    assert "synthetic-journal-operation" not in response.text

    next_page = client.get(f"/api/activity?from={day}&to={day}&timezone=Asia%2FShanghai&limit=1&offset=1")
    assert next_page.status_code == 200
    assert next_page.json()["pagination"]["has_more"] is False
    assert next_page.json()["items"][0]["activity_id"] != body["items"][0]["activity_id"]


def test_activity_projects_task_updates_from_authoritative_history_without_private_fields(tmp_path):
    tasks = make_tasks(tmp_path)
    due_day = date.today().isoformat()
    created = tasks.create("Synthetic task title", due_day, "synthetic-task-operation",
                           original_command="PRIVATE task command", session_id="private-session-id")
    task = created["task"]
    tasks.update(task["id"], {"expected_updated_at": task["updated_at"], "status": "completed"})
    activity_day = datetime.fromisoformat(task["created_at"]).date().isoformat()

    response = make_client(tmp_path, tasks=tasks).get(
        f"/api/activity?from={activity_day}&to={activity_day}&timezone=UTC&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"  # only one of the required minimum sources is configured
    assert body["source"] == ["tasks"]
    assert [item["status"] for item in body["items"]] == ["updated", "succeeded"]
    assert body["items"][0]["occurred_at"] > body["items"][1]["occurred_at"]
    assert body["items"][0]["activity_id"] != body["items"][1]["activity_id"]
    assert all(set(item) <= {"activity_id", "kind", "status", "occurred_at",
                             "task_due_date", "task_status"} for item in body["items"])
    assert "PRIVATE" not in response.text
    assert "private-session-id" not in response.text
    assert "synthetic-task-operation" not in response.text


def test_activity_task_snapshot_is_read_only_and_does_not_create_lock_file(tmp_path):
    tasks = make_tasks(tmp_path)
    assert not tasks.lock_path.exists()

    response = make_client(tmp_path, tasks=tasks).get("/api/activity")

    assert response.status_code == 200
    assert response.json()["source"] == ["tasks"]
    assert response.json()["items"] == []
    assert not tasks.lock_path.exists()


def test_activity_includes_explicit_tasks_without_chat_session_id(tmp_path):
    tasks = make_tasks(tmp_path)
    created = tasks.create("Synthetic standalone task", None, "synthetic-task-no-session",
                           original_command="PRIVATE standalone command")
    day = datetime.fromisoformat(created["task"]["created_at"]).date().isoformat()

    response = make_client(tmp_path, tasks=tasks).get(
        f"/api/activity?from={day}&to={day}&timezone=UTC")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["kind"] == "task"
    assert response.json()["items"][0]["status"] == "succeeded"
    assert "PRIVATE" not in response.text
    assert "synthetic-task-no-session" not in response.text


def test_activity_projects_personal_memory_operation_metadata_only_without_creating_lock(tmp_path):
    memory = make_memory(tmp_path)
    created = memory.create(content={"text": "PRIVATE synthetic memory content"},
                            category="preference", fact_kind="user_stated",
                            source_type="user_message", source_ref="session/synthetic",
                            idempotency_key="synthetic-memory-create")
    memory.correct(created["memory_id"], content={"text": "PRIVATE corrected memory"},
                   source_type="user_confirmed", source_ref="session/synthetic",
                   expected_revision=1, idempotency_key="synthetic-memory-correct")
    memory.lock_path.unlink()

    response = make_client(tmp_path, memory=memory).get("/api/activity")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == ["personal_memory"]
    assert {item["status"] for item in body["items"]} == {"created", "corrected"}
    assert all(set(item) == {"activity_id", "kind", "status", "occurred_at"}
               and item["kind"] == "personal_memory" for item in body["items"])
    assert "PRIVATE" not in response.text
    assert "synthetic-memory" not in response.text
    assert created["memory_id"] not in response.text
    assert not memory.lock_path.exists()


def test_activity_personal_memory_permission_is_preflighted_before_read(tmp_path, monkeypatch):
    memory = make_memory(tmp_path)
    reads = []
    monkeypatch.setattr(memory, "read_activity_events", lambda: reads.append(True) or [])
    client = make_client(tmp_path, memory=memory)
    auth = client.app.state.test_auth
    original_require_action = auth.require_action

    def deny_memory_before_io(request, action):
        if action == "personal_memory.read":
            raise __import__("fastapi").HTTPException(status_code=403, detail="denied")
        return original_require_action(request, action)

    monkeypatch.setattr(auth, "require_action", deny_memory_before_io)
    response = client.get("/api/activity")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == []
    assert reads == []


def test_activity_window_timezone_and_query_errors(tmp_path):
    client = make_client(tmp_path, journal=make_journal(tmp_path))
    assert client.get("/api/activity?from=2026-10-01").status_code == 400
    assert client.get("/api/activity?timezone=NoSuch/Timezone").status_code == 400
    assert client.get("/api/activity?from=2026-10-01&to=2026-11-02").status_code == 400
    assert client.get("/api/activity?from=2026-10-02&to=2026-10-01").status_code == 400
    assert client.get("/api/activity?limit=0").status_code == 400


def test_activity_default_journal_read_uses_fixed_365_day_window_and_marks_partial(tmp_path, monkeypatch):
    journal = make_journal(tmp_path)
    calls = []
    original_read = journal.read

    def tracked_read(day):
        calls.append(day)
        return original_read(day)

    monkeypatch.setattr(journal, "read", tracked_read)
    response = make_client(tmp_path, journal=journal).get("/api/activity")
    assert response.status_code == 200
    assert len(calls) == 365
    assert len(set(calls)) == 365
    assert response.json()["status"] == "partial"


def test_activity_ids_distinguish_same_operation_on_separate_journal_days(tmp_path):
    journal = make_journal(tmp_path)
    today = date.today()
    operation_id = "synthetic-reused-operation"
    for index, day in enumerate((today, today - timedelta(days=1))):
        record = {
            "id": f"synthetic-record-{index}", "operation_id": operation_id,
            "session_id": "synthetic-session", "date": day.isoformat(),
            "created_at": datetime.now().astimezone().isoformat(),
            "original_text": f"synthetic body {index}",
        }
        path = journal._path(day.isoformat())
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    response = make_client(tmp_path, journal=journal).get("/api/activity")
    assert response.status_code == 200
    ids = [row["activity_id"] for row in response.json()["items"]]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_activity_requires_owner_session(tmp_path):
    client = make_client(tmp_path, journal=make_journal(tmp_path))
    client.cookies.clear()
    assert client.get("/api/activity").status_code == 401


def test_activity_task_projection_refuses_store_over_fixed_read_budget(tmp_path, monkeypatch):
    tasks = make_tasks(tmp_path)
    tasks.path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    os.chmod(tasks.path, 0o600)
    monkeypatch.setattr(tasks, "list", lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("unbounded Task list must not be used by Activity")))

    response = make_client(tmp_path, tasks=tasks).get("/api/activity")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["source"] == ["tasks"]
    assert body["items"] == []


def test_activity_project_source_uses_explicit_index_revision_and_minimal_fields(tmp_path):
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    day = date.today().isoformat()
    document = {
        "id": "synthetic-project-1", "title": "PRIVATE synthetic title",
        "status": "active", "updated_at": f"{day}T08:00:00Z",
        "next_step": "PRIVATE synthetic body",
    }
    path = root / "project.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(path, 0o600)
    projects = ProjectsSourceReadStore(str(root))

    response = make_client(tmp_path, projects=projects).get(
        f"/api/activity?from={day}&to={day}&timezone=UTC")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["source"] == ["projects"]
    assert len(body["items"]) == 1
    event = body["items"][0]
    assert event["kind"] == "project" and event["status"] == "updated"
    assert event["project_id"] == "synthetic-project-1"
    assert event["project_status"] == "active"
    assert set(event) == {"activity_id", "kind", "status", "occurred_at", "project_id", "project_status"}
    assert "PRIVATE" not in response.text
    assert str(root) not in response.text


def test_activity_source_actions_are_checked_before_reading_each_source(tmp_path, monkeypatch):
    journal = make_journal(tmp_path)
    tasks = make_tasks(tmp_path)
    day = date.today().isoformat()
    journal_reads, task_reads = [], []
    monkeypatch.setattr(journal, "read", lambda value: journal_reads.append(value) or {"entries": []})
    monkeypatch.setattr(tasks, "list_for_projection_read_only",
                        lambda: task_reads.append(True) or {"tasks": []})
    client = make_client(tmp_path, journal=journal, tasks=tasks)
    auth = client.app.state.test_auth
    original_require_action = auth.require_action

    def deny_task_before_io(request, action):
        if action == "task.read":
            raise __import__("fastapi").HTTPException(status_code=403, detail="denied")
        return original_require_action(request, action)

    monkeypatch.setattr(auth, "require_action", deny_task_before_io)
    response = client.get(f"/api/activity?from={day}&to={day}&timezone=UTC")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == ["journal"]
    assert journal_reads == [day]
    assert task_reads == []


def test_activity_projects_denied_before_project_index_io(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    projects = ProjectsSourceReadStore(str(root))
    reads = []
    monkeypatch.setattr(projects, "read_snapshot", lambda: reads.append(True))
    client = make_client(tmp_path, projects=projects)
    auth = client.app.state.test_auth
    original_require_action = auth.require_action

    def deny_projects_before_io(request, action):
        if action == "projects.read":
            raise __import__("fastapi").HTTPException(status_code=403, detail="denied")
        return original_require_action(request, action)

    monkeypatch.setattr(auth, "require_action", deny_projects_before_io)
    day = date.today().isoformat()
    response = client.get(f"/api/activity?from={day}&to={day}&timezone=UTC")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == []
    assert reads == []


def test_activity_reads_only_minimal_successful_daily_brief_audit_events(tmp_path):
    audit_root = tmp_path / "approval"
    audit_root.mkdir(mode=0o700)
    os.chmod(audit_root, 0o700)
    audit_path = audit_root / "daily-brief-audit.jsonl"
    fixture = json.loads((Path(__file__).parent / "fixtures" /
                          "activity_daily_brief_created.json").read_text(encoding="utf-8"))
    day = fixture["audit_event"]["date"]
    event = fixture["audit_event"]
    audit_path.write_bytes(json.dumps(event, separators=(",", ":")).encode() + b"\n")
    os.chmod(audit_path, 0o600)
    store = DailyBriefAuditStore(str(audit_path))

    response = make_client(tmp_path, daily_brief_audit=store).get(
        f"/api/activity?from={day}&to={day}&timezone=UTC")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == ["daily_brief"]
    assert body["status"] == "partial"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["kind"] == "daily_brief" and item["status"] == "created"
    assert item["daily_brief_date"] == day
    assert item == fixture["activity_item"]
    assert "synthetic-request-id" not in response.text
    assert "synthetic-brief-id" not in response.text
    assert "synthetic-actor-hash" not in response.text
    assert "source_kind_counts" not in response.text
    assert not (audit_root / ".daily-brief-audit.lock").exists()


def test_activity_daily_brief_permission_is_preflighted_before_audit_read(tmp_path, monkeypatch):
    audit_root = tmp_path / "approval"
    audit_root.mkdir(mode=0o700)
    os.chmod(audit_root, 0o700)
    store = DailyBriefAuditStore(str(audit_root / "daily-brief-audit.jsonl"))
    reads = []
    monkeypatch.setattr(store, "read_activity_events", lambda: reads.append(True))
    client = make_client(tmp_path, daily_brief_audit=store)
    auth = client.app.state.test_auth
    original_require_action = auth.require_action

    def deny_brief_before_io(request, action):
        if action == "daily_brief.read":
            raise __import__("fastapi").HTTPException(status_code=403, detail="denied")
        return original_require_action(request, action)

    monkeypatch.setattr(auth, "require_action", deny_brief_before_io)
    response = client.get("/api/activity")

    assert response.status_code == 200
    assert response.json()["source"] == []
    assert response.json()["status"] == "partial"
    assert reads == []


def test_activity_daily_brief_audit_budget_exhaustion_is_partial_and_redacted(tmp_path):
    audit_root = tmp_path / "approval"
    audit_root.mkdir(mode=0o700)
    os.chmod(audit_root, 0o700)
    audit_path = audit_root / "daily-brief-audit.jsonl"
    audit_path.write_bytes(b"SYNTHETIC-PRIVATE\n" * (DailyBriefAuditStore.MAX_ACTIVITY_BYTES // 17 + 1))
    os.chmod(audit_path, 0o600)
    store = DailyBriefAuditStore(str(audit_path))

    response = make_client(tmp_path, daily_brief_audit=store).get("/api/activity")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["items"] == []
    assert "SYNTHETIC-PRIVATE" not in response.text


def test_daily_brief_activity_rejects_audit_replacement_during_snapshot_read(tmp_path, monkeypatch):
    import secondbrain_core.modules.daily_brief_import as brief_import

    audit_root = tmp_path / "approval"
    audit_root.mkdir(mode=0o700)
    os.chmod(audit_root, 0o700)
    audit_path = audit_root / "daily-brief-audit.jsonl"
    event = {
        "event_type": "daily_brief_import", "request_id": "synthetic-request-id",
        "brief_id": "synthetic-brief-id", "date": date.today().isoformat(),
        "timezone": "Asia/Shanghai", "source_kind_counts": {}, "outcome": "created",
        "recorded_at": f"{date.today().isoformat()}T08:00:00Z", "actor": "synthetic-actor-hash",
    }
    audit_path.write_bytes(json.dumps(event, separators=(",", ":")).encode() + b"\n")
    os.chmod(audit_path, 0o600)
    replacement = audit_root / "replacement.tmp"
    replacement.write_bytes(audit_path.read_bytes())
    os.chmod(replacement, 0o600)
    store = DailyBriefAuditStore(str(audit_path))
    original_read = os.read
    replaced = False

    def replace_after_first_read(fd, size):
        nonlocal replaced
        payload = original_read(fd, size)
        if not replaced:
            replaced = True
            os.replace(replacement, audit_path)
        return payload

    monkeypatch.setattr(brief_import.os, "read", replace_after_first_read)
    events, complete = store.read_activity_events()

    assert replaced is True
    assert events == []
    assert complete is False
