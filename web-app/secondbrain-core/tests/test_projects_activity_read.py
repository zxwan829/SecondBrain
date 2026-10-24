import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.capture import CaptureService, MAX_ACTIVITY_CAPTURE_BYTES, MAX_ACTIVITY_CAPTURE_STATE_FILES
from secondbrain_core.modules.daily_brief_import import DailyBriefAuditStore
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.personal_memory import PersonalMemoryStore
from secondbrain_core.modules.projects_activity_read import create_projects_activity_router
from secondbrain_core.modules.review_promote.activity_read import ReviewActivityReadStore
from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore
from secondbrain_core.modules.tasks import TaskStore


def make_client(tmp_path, journal=None, tasks=None, projects=None, daily_brief_audit=None, memory=None, capture=None,
                review=None):
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
        capture_service=capture,
        review_store=review,
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


def make_capture(tmp_path):
    raw = tmp_path / "capture-raw"
    review = tmp_path / "capture-review"
    state = tmp_path / "core-state"
    for root in (raw, review, state):
        root.mkdir(mode=0o700)
        os.chmod(root, 0o700)
    return CaptureService(raw, review, state, processors=object())


def make_review(tmp_path):
    root = tmp_path / "review"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return ReviewActivityReadStore(str(root)), root


def capture_state(capture_id, *, status="partial_success", captured_at=None, padding=""):
    return {
        "capture_id": capture_id, "source_type": "text", "input_type": "txt",
        "captured_at": captured_at or f"{date.today().isoformat()}T08:00:00Z",
        "updated_at": "2026-10-24T08:01:00Z", "status": status,
        "raw_path": "PRIVATE-raw.txt", "raw_sha256": "a" * 64,
        "review_path": "PRIVATE-review.md", "review_sha256": "b" * 64,
        "content_preview": "PRIVATE capture content", "capture_context": "PRIVATE context",
        "padding": padding,
    }


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


def test_activity_projects_capture_state_without_recovery_or_sensitive_fields(tmp_path, monkeypatch):
    capture = make_capture(tmp_path)
    capture_id = "a" * 32
    state = capture_state(capture_id)
    capture._write_state(state)
    path = capture._state_path(capture_id)
    before = path.read_bytes()
    monkeypatch.setattr(capture, "_recover_interrupted", lambda _state: (_ for _ in ()).throw(
        AssertionError("Activity must never recover or mutate Capture state")))

    response = make_client(tmp_path, capture=capture).get(
        f"/api/activity?from={date.today().isoformat()}&to={date.today().isoformat()}&timezone=UTC")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == ["capture"]
    assert body["status"] == "partial"  # Capture is a real source, but Activity has other required sources.
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item == {
        "activity_id": item["activity_id"], "kind": "capture", "status": "partial_success",
        "occurred_at": f"{date.today().isoformat()}T08:00:00.000000Z",
    }
    assert len(item["activity_id"]) == 32
    assert capture_id not in response.text
    assert "PRIVATE" not in response.text
    assert str(capture.raw_root) not in response.text
    assert str(capture.review_root) not in response.text
    assert path.read_bytes() == before
    assert sorted(p.name for p in capture.state_root.iterdir()) == [capture_id + ".json"]


def test_activity_capture_permission_is_preflighted_before_state_io(tmp_path, monkeypatch):
    capture = make_capture(tmp_path)
    reads = []
    monkeypatch.setattr(capture, "read_activity_events", lambda: reads.append(True) or ([], True))
    client = make_client(tmp_path, capture=capture)
    auth = client.app.state.test_auth
    original_require_action = auth.require_action

    def deny_capture_before_io(request, action):
        if action == "inbox.read":
            raise __import__("fastapi").HTTPException(status_code=403, detail="denied")
        return original_require_action(request, action)

    monkeypatch.setattr(auth, "require_action", deny_capture_before_io)
    response = client.get("/api/activity")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == []
    assert reads == []


def test_activity_capture_file_count_budget_fails_closed_as_partial(tmp_path):
    capture = make_capture(tmp_path)
    for index in range(MAX_ACTIVITY_CAPTURE_STATE_FILES + 1):
        (capture.state_root / (f"{index:032x}.json")).write_text("{}", encoding="utf-8")
        os.chmod(capture.state_root / (f"{index:032x}.json"), 0o600)

    response = make_client(tmp_path, capture=capture).get("/api/activity")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == ["capture"]
    assert response.json()["items"] == []


def test_activity_capture_aggregate_byte_budget_fails_closed_as_partial(tmp_path):
    capture = make_capture(tmp_path)
    per_record = (MAX_ACTIVITY_CAPTURE_BYTES // 3) + 100_000
    for index in range(3):
        capture._write_state(capture_state(f"{index + 1:032x}", padding="x" * per_record))

    response = make_client(tmp_path, capture=capture).get("/api/activity")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == ["capture"]
    assert response.json()["items"] == []


def test_activity_capture_state_replacement_during_read_fails_closed(tmp_path, monkeypatch):
    import secondbrain_core.modules.capture as capture_module

    capture = make_capture(tmp_path)
    capture_id = "c" * 32
    capture._write_state(capture_state(capture_id))
    state_path = capture._state_path(capture_id)
    replacement = capture.state_root / "replacement.tmp"
    replacement.write_bytes(state_path.read_bytes().replace(b"partial_success", b"completed"))
    os.chmod(replacement, 0o600)
    original_read = os.read
    replaced = False

    def replace_after_read(fd, size):
        nonlocal replaced
        payload = original_read(fd, size)
        if not replaced and payload:
            replaced = True
            os.replace(replacement, state_path)
        return payload

    monkeypatch.setattr(capture_module.os, "read", replace_after_read)
    events, complete = capture.read_activity_events()

    assert replaced is True
    assert events == []
    assert complete is False


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
    original_read = journal.read_source_day

    def tracked_read(day, **kwargs):
        calls.append(day)
        return original_read(day, **kwargs)

    monkeypatch.setattr(journal, "read_source_day", tracked_read)
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
            "id": hashlib.sha256(f"synthetic-record-{index}".encode()).hexdigest(), "operation_id": operation_id,
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
    def track_journal_read(value, **_kwargs):
        journal_reads.append(value)
        return {"available": True, "entries": {}, "bytes_read": 0}

    monkeypatch.setattr(journal, "read_source_day", track_journal_read)
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


def test_activity_projects_review_status_only_with_review_permission(tmp_path):
    review, root = make_review(tmp_path)
    private_marker = "PRIVATE_REVIEW_BODY_MARKER"
    (root / "synthetic-review.md").write_text(
        "---\ntype: review\ncaptured_at: 2026-10-24T08:15:00Z\nreview_status: pending\n---\n"
        f"# Synthetic\n\n{private_marker}\n", encoding="utf-8")
    os.chmod(root / "synthetic-review.md", 0o600)

    response = make_client(tmp_path, review=review).get(
        "/api/activity?from=2026-10-24&to=2026-10-24&timezone=UTC")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"  # Other configured activity sources are absent.
    assert body["source"] == ["review"]
    assert len(body["items"]) == 1
    assert set(body["items"][0]) == {"activity_id", "kind", "status", "occurred_at"}
    assert body["items"][0]["kind"] == "review"
    assert body["items"][0]["status"] == "pending"
    assert private_marker not in response.text
    assert str(root) not in response.text


def test_activity_review_permission_is_preflighted_before_filesystem_reads(tmp_path, monkeypatch):
    review, _root = make_review(tmp_path)
    reads = []
    monkeypatch.setattr(review, "read", lambda *_args: reads.append(True) or ([], True))
    client = make_client(tmp_path, review=review)
    auth = client.app.state.test_auth
    original_require_action = auth.require_action

    def deny_review_before_io(request, action):
        if action == "review.read":
            raise __import__("fastapi").HTTPException(status_code=403, detail="denied")
        return original_require_action(request, action)

    monkeypatch.setattr(auth, "require_action", deny_review_before_io)
    day = date.today().isoformat()
    response = client.get(f"/api/activity?from={day}&to={day}&timezone=UTC")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["source"] == []
    assert reads == []


def test_review_activity_skips_symlink_and_reports_partial_without_reading_target(tmp_path):
    review, root = make_review(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(
        "---\ncaptured_at: 2026-10-24T08:15:00Z\nreview_status: pending\n---\nPRIVATE\n",
        encoding="utf-8")
    os.chmod(outside, 0o600)
    (root / "linked.md").symlink_to(outside)

    rows, complete = review.read(date(2026, 10, 24), date(2026, 10, 24), ZoneInfo("UTC"))

    assert rows == []
    assert complete is False


def test_review_activity_malformed_frontmatter_is_partial(tmp_path):
    review, root = make_review(tmp_path)
    malformed = root / "truncated.md"
    malformed.write_text(
        "---\ncaptured_at: 2026-10-24T08:15:00Z\nreview_status: pending\n",
        encoding="utf-8")
    os.chmod(malformed, 0o600)

    rows, complete = review.read(date(2026, 10, 24), date(2026, 10, 24), ZoneInfo("UTC"))

    assert rows == []
    assert complete is False


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


def test_activity_journal_reads_obey_aggregate_byte_budget_and_mark_partial(tmp_path):
    class BudgetedJournal:
        def __init__(self):
            self.calls = []

        def read_source_day(self, day, *, max_bytes, max_entries):
            self.calls.append((day, max_bytes, max_entries))
            return {"available": True, "entries": {}, "bytes_read": max_bytes}

    journal = BudgetedJournal()
    tasks = make_tasks(tmp_path)
    response = make_client(tmp_path, journal=journal, tasks=tasks).get(
        "/api/activity?from=2026-10-01&to=2026-10-04")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["items"] == []
    assert [call[1] for call in journal.calls] == [1024 * 1024, 1024 * 1024]
    assert all(call[2] == 5000 for call in journal.calls)
    assert len(journal.calls) == 2

def test_activity_journal_reads_obey_aggregate_row_budget(tmp_path):
    class BudgetedJournal:
        def __init__(self):
            self.calls = []

        def read_source_day(self, day, *, max_bytes, max_entries):
            self.calls.append((day, max_bytes, max_entries))
            entries = {}
            for index in range(max_entries):
                entry_id = hashlib.sha256(f"{day}-{index}".encode()).hexdigest()
                entries[entry_id] = {"record": {
                    "id": entry_id, "operation_id": f"op-{day}-{index}",
                    "session_id": "synthetic-session", "date": day,
                    "created_at": f"{day}T08:00:00+00:00",
                }}
            return {"available": True, "entries": entries, "bytes_read": 0}

    journal = BudgetedJournal()
    tasks = make_tasks(tmp_path)
    response = make_client(tmp_path, journal=journal, tasks=tasks).get(
        "/api/activity?from=2026-10-01&to=2026-10-03&limit=1")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert len(response.json()["items"]) == 1
    assert [call[2] for call in journal.calls] == [5000, 5000]
    assert len(journal.calls) == 2

def test_activity_journal_snapshot_failure_is_redacted_and_partial(tmp_path):
    class UnavailableJournal:
        def read_source_day(self, _day, *, max_bytes, max_entries):
            raise OSError("synthetic private path /never-return-this")

    tasks = make_tasks(tmp_path)
    response = make_client(tmp_path, journal=UnavailableJournal(), tasks=tasks).get(
        "/api/activity?from=2026-10-01&to=2026-10-01")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["items"] == []
    assert "/never-return-this" not in response.text
