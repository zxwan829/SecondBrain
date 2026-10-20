"""Real localhost Core HTTP regression for bounded Capture state reads."""
import json
import os
import socket
import threading
import time

import httpx
import uvicorn

from secondbrain_core.app import create_app


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_capture_summary_loopback_skips_unsafe_state_without_writes(tmp_path, monkeypatch):
    roots = {name: _private_dir(tmp_path / name) for name in (
        "raw", "review", "knowledge", "state", "journal", "projects", "briefs", "tasks", "notes",
    )}
    state_root = _private_dir(roots["state"] / "captures")
    password = tmp_path / "synthetic-app-password"
    password.write_text("synthetic-capture-password\n", encoding="utf-8")
    os.chmod(password, 0o600)
    unlock_secret = tmp_path / "synthetic-promote-secret"
    unlock_secret.write_text("synthetic-unused-promote-secret-0000000000000000", encoding="utf-8")
    os.chmod(unlock_secret, 0o600)

    valid_id = "a" * 32
    valid_path = state_root / f"{valid_id}.json"
    valid_bytes = json.dumps({
        "capture_id": valid_id, "source_type": "text", "input_type": "text",
        "captured_at": "2026-10-20T00:00:00Z", "display_filename": "synthetic.txt",
        "status": "processing", "content_preview": "SYNTHETIC SECRET BODY",
        "capture_context": "SYNTHETIC SECRET CONTEXT", "raw_path": "synthetic.txt",
        "review_path": None, "error": None,
    }).encode("utf-8")
    valid_path.write_bytes(valid_bytes)
    os.chmod(valid_path, 0o600)
    unsafe_id = "b" * 32
    unsafe_target = tmp_path / "outside-state.json"
    unsafe_target.write_text(json.dumps({
        "capture_id": unsafe_id, "source_type": "text", "input_type": "text",
        "captured_at": "2026-10-20T00:00:01Z", "status": "completed",
        "content_preview": "MUST NOT LEAK", "raw_path": "outside.txt",
    }), encoding="utf-8")
    os.chmod(unsafe_target, 0o600)
    (state_root / f"{unsafe_id}.json").symlink_to(unsafe_target)
    before_files = sorted(path.name for path in state_root.iterdir())
    before_stat = valid_path.stat()

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
            anonymous = client.get("/api/inbox/summary?limit=100")
            assert anonymous.status_code == 401
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-capture-password"})
            assert login.status_code == 200, login.text
            response = client.get("/api/inbox/summary?limit=100", headers={"Origin": origin})
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["status"] == "real"
            assert [item["capture_id"] for item in payload["items"]] == [valid_id]
            assert "SYNTHETIC SECRET BODY" not in response.text
            assert "MUST NOT LEAK" not in response.text
            assert str(tmp_path) not in response.text
        assert valid_path.read_bytes() == valid_bytes
        assert valid_path.stat().st_mtime_ns == before_stat.st_mtime_ns
        assert sorted(path.name for path in state_root.iterdir()) == before_files
        assert list(roots["raw"].iterdir()) == []
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if not thread.is_alive():
            listener.close()
