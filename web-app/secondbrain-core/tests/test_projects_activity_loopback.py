"""Real localhost HTTP coverage for the Core Activity read contract."""
import hashlib
import json
import os
import socket
import stat
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import uvicorn

from secondbrain_core.app import create_app
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.tasks import TaskStore


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _record(day, index):
    entry_id = hashlib.sha256(f"loopback-{day}-{index}".encode()).hexdigest()
    return {
        "id": entry_id, "operation_id": f"op-{index}", "session_id": "s",
        "date": day, "created_at": f"{day}T08:00:00+08:00",
    }


def _write_budget_day(root, day, *, rows=5000, total_bytes=1024 * 1024):
    records = [_record(day, index) for index in range(rows)]
    encoded = [json.dumps(row, separators=(",", ":")).encode() for row in records]
    prefix = b"".join(row + b"\n" for row in encoded[:-1])
    final = encoded[-1] + b"\n"
    if len(prefix) + len(final) > total_bytes:
        raise AssertionError("synthetic rows exceed target file size")
    payload = prefix + encoded[-1] + b" " * (total_bytes - len(prefix) - len(final)) + b"\n"
    path = Path(root) / f"{day}.jsonl"
    path.write_bytes(payload)
    os.chmod(path, 0o600)
    assert path.stat().st_size == total_bytes
    return path


def _snapshot(root):
    snapshot = {}
    for path in sorted(Path(root).iterdir()):
        info = path.lstat()
        snapshot[path.name] = (
            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_dev,
            info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return snapshot


def test_core_activity_real_localhost_http_security_budget_and_read_only(tmp_path, monkeypatch):
    today = date.today()
    day = today.isoformat()
    roots = {name: _private_dir(tmp_path / name) for name in (
        "review", "raw", "knowledge", "state", "projects", "briefs", "tasks", "journal", "notes",
    )}
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-activity-password\n")
    os.chmod(password_file, 0o600)

    journal_seed = JournalStore(str(roots["journal"]))
    journal_seed.append(day, "记一下 synthetic normal Journal row", "loopback-journal-key",
                        session_id="synthetic-session")
    task_seed = TaskStore(str(roots["tasks"]))
    task_seed.create("Synthetic Activity Task", (today + timedelta(days=1)).isoformat(),
                     "loopback-task-key", original_command="PRIVATE synthetic command",
                     session_id="synthetic-session")
    # Two exact per-day limits exhaust the request-wide 2 MiB budget before a
    # third date can be opened. The data is synthetic and never outside tmp_path.
    budget_days = ((today - timedelta(days=2)).isoformat(), (today - timedelta(days=1)).isoformat())
    for budget_day in budget_days:
        _write_budget_day(roots["journal"], budget_day)
    # Remove append-only lock files created during fixture setup, then make the
    # source genuinely read-only. GETs must neither need nor recreate them.
    (roots["journal"] / ".operations.lock").unlink()
    (roots["journal"] / f".{day}.lock").unlink()
    for source_file in roots["journal"].iterdir():
        os.chmod(source_file, 0o400)
    os.chmod(roots["journal"], 0o500)

    calls = []
    direct_task_reads = []
    fail_day = {"value": None}
    original_read = JournalStore.read_source_day
    original_task_list = TaskStore.list

    def tracked_read(store, requested_day, **kwargs):
        calls.append((requested_day, kwargs.get("max_bytes"), kwargs.get("max_entries")))
        if fail_day["value"] == requested_day:
            raise OSError("synthetic private path /private/never-leak")
        return original_read(store, requested_day, **kwargs)

    def tracked_task_list(store, *args, **kwargs):
        direct_task_reads.append((args, kwargs))
        return original_task_list(store, *args, **kwargs)

    monkeypatch.setattr(JournalStore, "read_source_day", tracked_read)
    monkeypatch.setattr(TaskStore, "list", tracked_task_list)
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
    old_env = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
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
        assert server.started, "localhost Core Uvicorn server did not start"

        before = {name: _snapshot(roots[name]) for name in ("journal", "tasks")}
        assert stat.S_IMODE(roots["journal"].stat().st_mode) == 0o500
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o400
                   for path in roots["journal"].iterdir())
        if os.geteuid() != 0:
            assert not os.access(roots["journal"], os.W_OK)
        assert ".operations.lock" not in before["journal"]
        assert f".{day}.lock" not in before["journal"]
        with httpx.Client(base_url=origin, trust_env=False, timeout=5.0) as client:
            denied = client.get(f"/api/activity?from={day}&to={day}", headers={"Origin": origin})
            assert denied.status_code == 401
            assert calls == []  # authorization happens before any source read
            assert client.get(f"/api/journal/{day}", headers={"Origin": origin}).status_code == 401
            assert client.get("/api/tasks?status=all", headers={"Origin": origin}).status_code == 401
            assert direct_task_reads == []

            wrong_origin = client.post("/api/auth/login", headers={"Origin": "http://evil.invalid"},
                                       json={"password": "synthetic-activity-password"})
            assert wrong_origin.status_code == 403
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-activity-password"})
            assert login.status_code == 200

            task_read = client.get("/api/tasks?status=all", headers={"Origin": origin})
            assert task_read.status_code == 200
            assert task_read.json()["tasks"][0]["title"] == "Synthetic Activity Task"
            assert len(direct_task_reads) == 1

            normal = client.get(f"/api/activity?from={day}&to={day}&limit=1",
                                headers={"Origin": origin})
            assert normal.status_code == 200
            body = normal.json()
            assert body["status"] == "ok"
            assert {"journal", "tasks"}.issubset(set(body["source"]))
            assert len(body["items"]) == 1
            assert body["pagination"] == {"limit": 1, "offset": 0, "has_more": True}
            first_id = body["items"][0]["activity_id"]
            page_two = client.get(f"/api/activity?from={day}&to={day}&limit=1&offset=1",
                                  headers={"Origin": origin})
            assert page_two.status_code == 200
            assert page_two.json()["pagination"] == {"limit": 1, "offset": 1, "has_more": False}
            assert page_two.json()["items"][0]["activity_id"] != first_id
            all_kinds = {body["items"][0]["kind"], page_two.json()["items"][0]["kind"]}
            assert all_kinds == {"journal", "task"}
            assert "PRIVATE" not in normal.text and "synthetic-session" not in normal.text
            assert "/private/" not in normal.text and "original_text" not in normal.text

            missing = "2099-01-01"
            empty = client.get(f"/api/activity?from={missing}&to={missing}", headers={"Origin": origin})
            assert empty.status_code == 200
            assert empty.json()["status"] == "empty"
            assert empty.json()["items"] == []
            assert empty.json()["pagination"]["has_more"] is False

            calls.clear()
            start, end = budget_days[0], (today + timedelta(days=1)).isoformat()
            exhausted = client.get(
                f"/api/activity?from={start}&to={end}&limit=1&offset=20000", headers={"Origin": origin})
            assert exhausted.status_code == 200
            exhausted_body = exhausted.json()
            assert exhausted_body["status"] == "partial"
            assert exhausted_body["items"] == []
            assert exhausted_body["pagination"] == {"limit": 1, "offset": 20000, "has_more": False}
            assert calls == [(budget_days[0], 1024 * 1024, 5000),
                             (budget_days[1], 1024 * 1024, 5000)]

            fail_day["value"] = missing
            failed_read = client.get(f"/api/activity?from={missing}&to={missing}", headers={"Origin": origin})
            assert failed_read.status_code == 200
            assert failed_read.json()["status"] == "partial"
            assert failed_read.json()["items"] == []
            assert "/private/never-leak" not in failed_read.text
            assert "synthetic private path" not in failed_read.text

        after = {name: _snapshot(roots[name]) for name in ("journal", "tasks")}
        assert after == before  # GET created no locks/files and changed no source bytes or metadata
        assert ".operations.lock" not in after["journal"]
        assert f".{day}.lock" not in after["journal"]
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        listener.close()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
