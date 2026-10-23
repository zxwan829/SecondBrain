"""Real localhost HTTP regression for the authenticated Core Calendar projection."""
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.tasks import TaskStore


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_calendar_real_core_http_auth_projection_and_redaction(tmp_path, monkeypatch):
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    roots = {name: _private_dir(tmp_path / name) for name in (
        "review", "raw", "knowledge", "state", "projects", "briefs", "tasks", "journal", "notes",
    )}
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-calendar-password\n")
    os.chmod(password_file, 0o600)

    journal_store = JournalStore(str(roots["journal"]))
    journal_store.append(day, "记一下：PRIVATE synthetic calendar journal body", "synthetic-calendar-journal-key",
                         session_id="synthetic-private-session")
    task_store = TaskStore(str(roots["tasks"]))
    task_store.create("PRIVATE synthetic calendar task body", day, "synthetic-calendar-task-key",
                      session_id="synthetic-private-session")

    journal_reads, task_reads = [], []
    original_journal_read = JournalStore.read
    original_task_projection = TaskStore.list_for_projection

    def counted_journal_read(store, target_day):
        journal_reads.append(target_day)
        return original_journal_read(store, target_day)

    def counted_task_projection(store):
        task_reads.append(True)
        return original_task_projection(store)

    monkeypatch.setattr(JournalStore, "read", counted_journal_read)
    monkeypatch.setattr(TaskStore, "list_for_projection", counted_task_projection)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]),
        "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
        "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password_file),
        "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host,
        "SB_HERMES_API_URL": "",
        "SB_PROMOTE_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]),
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]),
        "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    server = None
    thread = None
    try:
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                               lifespan="off", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "local Core HTTP server did not start"

        url = f"/api/calendar?from={day}&to={day}&timezone=Asia%2FShanghai"
        with httpx.Client(base_url=origin, trust_env=False, timeout=3.0) as client:
            anonymous = client.get(url, headers={"Origin": origin})
            assert anonymous.status_code == 401
            assert journal_reads == [] and task_reads == []

            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-calendar-password"})
            assert login.status_code == 200

            hostile_origin = client.get(url, headers={"Origin": "http://evil.test"})
            assert hostile_origin.status_code == 403
            assert journal_reads == [] and task_reads == []

            response = client.get(url, headers={"Origin": origin})
            assert response.status_code == 200
            body = response.json()
            assert set(body) == {"status", "items", "source", "freshness"}
            assert body["status"] == "ok"
            assert body["source"] == ["journal", "tasks"]
            assert set(body["freshness"]) == {"checked_at"}
            assert {item["kind"] for item in body["items"]} == {"journal", "task"}
            assert all(set(item) <= {"id", "kind", "date", "occurred_at", "status"}
                       for item in body["items"])
            assert all(item["date"] == day for item in body["items"])
            assert len(journal_reads) == 1 and task_reads == [True]
            for private_value in (
                    str(roots["journal"]), str(roots["tasks"]), "PRIVATE",
                    "synthetic-calendar-journal-key", "synthetic-calendar-task-key",
                    "synthetic-private-session", "synthetic-calendar-password"):
                assert private_value not in response.text

            ids = [item["id"] for item in body["items"]]
            repeated = client.get(url, headers={"Origin": origin})
            assert repeated.status_code == 200
            assert [item["id"] for item in repeated.json()["items"]] == ids

            before_reads = (len(journal_reads), len(task_reads))
            oversized = client.get(
                "/api/calendar?from=2026-10-01&to=2026-11-01&timezone=Asia%2FShanghai",
                headers={"Origin": origin},
            )
            assert oversized.status_code == 400
            assert (len(journal_reads), len(task_reads)) == before_reads
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        listener.close()
