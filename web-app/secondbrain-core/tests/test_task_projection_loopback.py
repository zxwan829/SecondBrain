"""Real Core localhost HTTP regression for the bounded Task projection."""
import os
import socket
import threading
import time

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.tasks import TaskStore


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_task_projection_loopback_reads_only_synthetic_private_store(tmp_path, monkeypatch):
    roots = {name: _private_dir(tmp_path / name) for name in (
        "raw", "review", "knowledge", "state", "journal", "projects", "briefs", "tasks", "notes",
    )}
    task_store = TaskStore(roots["tasks"])
    task = task_store.create("Synthetic loopback task", "2026-10-21", "loopback-task-key")["task"]
    task_bytes = task_store.path.read_bytes()
    password = tmp_path / "synthetic-app-password"
    password.write_text("synthetic-task-password\n", encoding="utf-8")
    os.chmod(password, 0o600)
    unlock_secret = tmp_path / "synthetic-promote-secret"
    unlock_secret.write_text("synthetic-unused-promote-secret-0000000000000000", encoding="utf-8")
    os.chmod(unlock_secret, 0o600)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
        "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_PROMOTE_UNLOCK_SECRET_FILE": str(unlock_secret),
        "SB_APP_PASSWORD_FILE": str(password),
        "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host,
        "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_HERMES_API_URL": "",
        "SB_HERMES_API_KEY": "",
        "SB_PROMOTE_ENABLED": "false",
        "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]),
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, trust_env=False, timeout=10) as client:
            denied = client.get("/api/tasks?status=all")
            assert denied.status_code == 401
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-task-password"})
            assert login.status_code == 200, login.text
            response = client.get("/api/tasks?status=all", headers={"Origin": origin})
            assert response.status_code == 200, response.text
            assert response.json() == {"tasks": [task]}
            calendar = client.get("/api/calendar?from=2026-10-21&to=2026-10-21",
                                  headers={"Origin": origin})
            assert calendar.status_code == 200, calendar.text
            assert calendar.json()["status"] == "ok"
            assert any(item["kind"] == "task" for item in calendar.json()["items"])
            assert str(tmp_path) not in response.text + calendar.text
        assert task_store.path.read_bytes() == task_bytes
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if not thread.is_alive():
            listener.close()
