"""Real localhost HTTP exercise for the authenticated Core source readers."""
import hashlib
import json
import os
import socket
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.notes import NotesStore
from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore
from secondbrain_core.modules.tasks import TaskStore, task_source_version


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_core_real_loopback_verifies_task_project_journal_and_project_note(tmp_path):
    roots = {name: _private_dir(tmp_path / name) for name in (
        "review", "raw", "knowledge", "state", "projects", "briefs", "tasks",
        "journal", "notes",
    )}
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-loopback-password\n")
    os.chmod(password_file, 0o600)

    task_store = TaskStore(str(roots["tasks"]))
    task = task_store.create("Synthetic Task", "2026-10-21", "loopback-task-key")["task"]
    journal_store = JournalStore(str(roots["journal"]))
    journal = journal_store.append("2026-10-20", "记一下 synthetic Journal row",
                                   "loopback-journal-key")["entry"]
    journal_version = journal_store.read_source_day("2026-10-20")["entries"][journal["id"]]["version"]
    notes_store = NotesStore(str(roots["notes"]))
    note = notes_store.create("# Synthetic Project Note\n")

    project_path = roots["projects"] / "project-loopback.json"
    project = {"id": "project-loopback", "title": "Synthetic Project", "status": "active",
               "linked_notes": [{"id": note["path"], "version": note["etag"]}]}
    project_bytes = json.dumps(project, separators=(",", ":")).encode("utf-8")
    project_path.write_bytes(project_bytes)
    os.chmod(project_path, 0o600)
    project_version = ProjectsSourceReadStore(str(roots["projects"])).read_snapshot().documents[0].sha256

    brief_path = roots["briefs"] / "2026-10-20.json"
    brief = {
        "brief_id": "brief-loopback", "date": "2026-10-20", "timezone": "Asia/Shanghai",
        "generated_at": "2026-10-20T08:00:00+08:00", "generation_status": "generated",
        "categories": ["synthetic"], "summary": "Synthetic verified-source summary",
        "source_refs": [
            {"kind": "project", "id": project["id"], "version": project_version},
            {"kind": "task", "id": task["id"], "version": task_source_version(task)},
            {"kind": "journal", "id": f"2026-10-20:{journal['id']}", "version": journal_version},
        ],
    }
    brief_path.write_text(json.dumps(brief, separators=(",", ":")), encoding="utf-8")
    os.chmod(brief_path, 0o600)

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
    old_env = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    app = None
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

        with httpx.Client(base_url=origin, trust_env=False, timeout=3.0) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-loopback-password"})
            assert login.status_code == 200

            projects = client.get("/api/projects", headers={"Origin": origin})
            assert projects.status_code == 200
            assert projects.json()["status"] == "real"
            assert "linked_notes" not in projects.json()["items"][0]
            assert note["path"] not in projects.text
            assert "Synthetic Project Note" not in projects.text

            daily = client.get("/api/daily-brief?date=2026-10-20&timezone=Asia%2FShanghai",
                               headers={"Origin": origin})
            assert daily.status_code == 200
            assert daily.json()["status"] == "real"
            assert daily.json()["items"][0]["source_refs"] == brief["source_refs"]
            assert "Synthetic Task" not in daily.text
            assert "synthetic Journal row" not in daily.text

            brief["source_refs"][1]["version"] = "0" * 64
            brief_path.write_text(json.dumps(brief, separators=(",", ":")), encoding="utf-8")
            os.chmod(brief_path, 0o600)
            stale = client.get("/api/daily-brief?date=2026-10-20&timezone=Asia%2FShanghai",
                               headers={"Origin": origin})
            assert stale.status_code == 200
            assert stale.json()["status"] == "stale" and stale.json()["items"] == []
            assert "Synthetic verified-source summary" not in stale.text

            denied_origin = client.get("/api/daily-brief?date=2026-10-20&timezone=Asia%2FShanghai",
                                       headers={"Origin": "http://evil.test"})
            assert denied_origin.status_code == 403
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        if thread is None or not thread.is_alive():
            listener.close()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
