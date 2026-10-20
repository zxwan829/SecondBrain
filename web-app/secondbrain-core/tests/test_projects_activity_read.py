import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.projects_activity_read import create_projects_activity_router
from secondbrain_core.modules.tasks import TaskStore


def make_client(tmp_path, journal=None, tasks=None):
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-password-value\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    token = "synthetic-app-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 600
    app = FastAPI()
    app.include_router(create_projects_activity_router(auth, journal, tasks))
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


def test_projects_is_authenticated_truthful_empty_contract(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/projects?limit=7&offset=2")
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_configured",
        "items": [],
        "pagination": {"limit": 7, "offset": 2, "has_more": False},
        "source": None,
    }

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
