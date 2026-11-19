"""Synthetic localhost coverage for the current read-only Journal GET route."""
import hashlib
import json
import os
import socket
import stat
import threading
import time
from datetime import date
from pathlib import Path

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.journal import JournalStore


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _source_snapshot(root):
    state = {}
    for path in sorted(Path(root).iterdir()):
        info = path.lstat()
        state[path.name] = (
            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_dev,
            info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return state


def test_journal_get_preserves_shape_and_is_read_only_over_localhost(tmp_path, monkeypatch):
    day = date.today().isoformat()
    roots = {name: _private_dir(tmp_path / name) for name in (
        "review", "raw", "knowledge", "state", "projects", "briefs", "tasks", "journal", "notes",
    )}
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-journal-get-password\n")
    os.chmod(password_file, 0o600)

    fixture_store = JournalStore(str(roots["journal"]))
    expected = fixture_store.append(day, "记一下 synthetic Journal GET row", "journal-get-fixture-key")["entry"]
    (roots["journal"] / f".{day}.lock").unlink(missing_ok=True)
    (roots["journal"] / ".operations.lock").unlink(missing_ok=True)

    reads = []
    original_read = JournalStore.read

    def tracked_read(store, requested_day):
        reads.append(requested_day)
        return original_read(store, requested_day)

    monkeypatch.setattr(JournalStore, "read", tracked_read)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]), "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password_file), "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host, "SB_HERMES_API_URL": "", "SB_PROMOTE_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]), "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]), "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    server = thread = None
    try:
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                               lifespan="off", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "localhost Core HTTP server did not start"

        with httpx.Client(base_url=origin, trust_env=False, timeout=5.0) as client:
            anonymous = client.get(f"/api/journal/{day}", headers={"Origin": origin})
            assert anonymous.status_code == 401
            assert reads == []
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-journal-get-password"})
            assert login.status_code == 200

            writable_before = _source_snapshot(roots["journal"])
            response = client.get(f"/api/journal/{day}", headers={"Origin": origin})
            assert response.status_code == 200
            assert response.json() == {"date": day, "entries": [expected]}
            assert _source_snapshot(roots["journal"]) == writable_before
            assert not any(name.endswith(".lock") for name in writable_before)
            assert reads == [day]

            source_path = roots["journal"] / f"{day}.jsonl"
            source_bytes = source_path.read_bytes()
            source_path.write_bytes(b'{"id":"synthetic-malformed"\n')
            malformed = client.get(f"/api/journal/{day}", headers={"Origin": origin})
            assert malformed.status_code == 503

            source_path.write_bytes(b" " * (1024 * 1024 + 1))
            oversized = client.get(f"/api/journal/{day}", headers={"Origin": origin})
            assert oversized.status_code == 503
            source_path.write_bytes(source_bytes)

            os.chmod(roots["journal"] / f"{day}.jsonl", 0o400)
            os.chmod(roots["journal"], 0o500)
            readonly_before = _source_snapshot(roots["journal"])
            assert stat.S_IMODE(roots["journal"].stat().st_mode) == 0o500
            assert stat.S_IMODE((roots["journal"] / f"{day}.jsonl").stat().st_mode) == 0o400
            if os.geteuid() != 0:
                assert not os.access(roots["journal"], os.W_OK)

            readonly = client.get(f"/api/journal/{day}", headers={"Origin": origin})
            assert readonly.status_code == 200
            assert readonly.json() == {"date": day, "entries": [expected]}
            missing_day = "2099-01-01"
            missing = client.get(f"/api/journal/{missing_day}", headers={"Origin": origin})
            assert missing.status_code == 200
            assert missing.json() == {"date": missing_day, "entries": []}

            assert _source_snapshot(roots["journal"]) == readonly_before
            assert not any(name.endswith(".lock") for name in readonly_before)
            assert reads == [day, day, day, day, missing_day]
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        listener.close()
