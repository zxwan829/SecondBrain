"""Real localhost HTTP exercise for the authenticated Core source readers."""
import hashlib
import json
import os
import stat
import socket
import threading
import time
from pathlib import Path
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


def _tree_snapshot(root):
    result = {}
    for path in sorted(Path(root).iterdir()):
        info = path.lstat()
        result[path.name] = {
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
            "dev": info.st_dev, "ino": info.st_ino, "nlink": info.st_nlink,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns, "atime_ns": info.st_atime_ns,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        }
    return result


def _directory_state(path):
    info = Path(path).lstat()
    return (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_dev,
            info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def test_core_real_loopback_verifies_task_project_journal_and_project_note(tmp_path, monkeypatch):
    brief_day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
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
    journal = journal_store.append(brief_day, "记一下 synthetic Journal row",
                                   "loopback-journal-key")["entry"]
    journal_version = journal_store.read_source_day(brief_day)["entries"][journal["id"]]["version"]
    # The source reader must work without a pre-existing daily lock and without
    # write permission. The regular Journal write path above created it, so
    # remove it as fixture setup before freezing the synthetic root read-only.
    (roots["journal"] / f".{brief_day}.lock").unlink()
    (roots["journal"] / ".operations.lock").unlink()
    os.chmod(roots["journal"] / f"{brief_day}.jsonl", 0o400)
    os.chmod(roots["journal"], 0o500)
    assert os.geteuid() != 0 and not os.access(roots["journal"], os.W_OK)
    denied_create = roots["journal"] / ".permission-probe"
    try:
        fd = os.open(denied_create, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except PermissionError:
        pass
    else:
        os.close(fd)
        denied_create.unlink(missing_ok=True)
        raise AssertionError("synthetic Journal fixture unexpectedly permits file creation")
    journal_tree_before = _tree_snapshot(roots["journal"])
    journal_dir_before = _directory_state(roots["journal"])
    notes_store = NotesStore(str(roots["notes"]))
    note = notes_store.create("# Synthetic Project Note\n")

    project_path = roots["projects"] / "project-loopback.json"
    project = {"id": "project-loopback", "title": "Synthetic Project", "status": "active",
               "linked_notes": [{"id": note["path"], "version": note["etag"]}]}
    project_bytes = json.dumps(project, separators=(",", ":")).encode("utf-8")
    project_path.write_bytes(project_bytes)
    os.chmod(project_path, 0o600)
    project_version = ProjectsSourceReadStore(str(roots["projects"])).read_snapshot().documents[0].sha256

    brief_refs = [
        {"kind": "project", "id": project["id"], "version": project_version},
        {"kind": "task", "id": task["id"], "version": task_source_version(task)},
        {"kind": "journal", "id": f"{brief_day}:{journal['id']}", "version": journal_version},
    ]

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

            import_body = {
                "mode": "manual_generate", "date": brief_day, "timezone": "Asia/Shanghai",
                "idempotency_key": "loopback-brief-key-20261020-123456",
                "categories": ["synthetic"],
                "summary": "Synthetic verified-source summary",
                "source_refs": brief_refs, "approved": True,
            }
            imported = client.post("/api/daily-brief", headers={"Origin": origin}, json=import_body)
            assert imported.status_code == 201
            assert set(imported.json()) == {"status", "brief_id", "date", "timezone"}
            assert "Synthetic verified-source summary" not in imported.text
            daily = client.get(f"/api/daily-brief?date={brief_day}&timezone=Asia%2FShanghai",
                               headers={"Origin": origin})
            assert daily.status_code == 200
            assert daily.json()["status"] == "real"
            assert daily.json()["items"][0]["source_refs"] == brief_refs
            assert daily.json()["items"][0]["summary"] == import_body["summary"]
            assert "Synthetic Task" not in daily.text
            assert "synthetic Journal row" not in daily.text
            journal_tree_after = _tree_snapshot(roots["journal"])
            # A read may update atime on platforms without O_NOATIME; all other
            # metadata, bytes, modes, identities, and directory entries must
            # remain identical.
            assert set(journal_tree_after) == set(journal_tree_before)
            assert _directory_state(roots["journal"]) == journal_dir_before
            for name in journal_tree_before:
                before = dict(journal_tree_before[name])
                after = dict(journal_tree_after[name])
                before.pop("atime_ns")
                after.pop("atime_ns")
                assert after == before
            assert f".{brief_day}.lock" not in journal_tree_after
            assert ".operations.lock" not in journal_tree_after
            assert ".permission-probe" not in journal_tree_after

            denied_text = "记一下：SYNTHETIC-PRIVATE-HTTP-WRITE-4c2e"
            before_denied_tree = _tree_snapshot(roots["journal"])
            before_denied_dir = _directory_state(roots["journal"])
            denied_append = client.post("/api/journal/entries",
                                        headers={"Origin": origin, "Idempotency-Key": "readonly-http-denied"},
                                        json={"date": brief_day, "text": denied_text})
            assert denied_append.status_code == 503
            assert denied_append.json() == {"detail": "Journal storage is temporarily unavailable"}
            for private_value in (str(roots["journal"]), denied_text, "synthetic-loopback-password",
                                  "session_id", "session-1"):
                assert private_value not in denied_append.text
            after_denied_tree = _tree_snapshot(roots["journal"])
            assert _directory_state(roots["journal"]) == before_denied_dir
            assert set(after_denied_tree) == set(before_denied_tree)
            for name in before_denied_tree:
                before = dict(before_denied_tree[name])
                after = dict(after_denied_tree[name])
                before.pop("atime_ns")
                after.pop("atime_ns")
                assert after == before

            # Force an atomic path replacement after the exact Journal fd has
            # yielded bytes but before its post-read path identity check. The
            # real HTTP Brief route must fail closed and hide the summary.
            journal_path = roots["journal"] / f"{brief_day}.jsonl"
            journal_path_info = journal_path.stat()
            journal_bytes = journal_path.read_bytes()
            original_read = os.read
            replaced = False

            def replace_journal_during_read(fd, size):
                nonlocal replaced
                before_read = os.fstat(fd)
                chunk = original_read(fd, size)
                if (chunk and not replaced
                        and (before_read.st_dev, before_read.st_ino)
                        == (journal_path_info.st_dev, journal_path_info.st_ino)):
                    os.chmod(roots["journal"], 0o700)
                    replacement = roots["journal"] / ".journal-replacement"
                    replacement.write_bytes(journal_bytes)
                    os.chmod(replacement, 0o400)
                    os.replace(replacement, journal_path)
                    os.chmod(roots["journal"], 0o500)
                    replaced = True
                return chunk

            with monkeypatch.context() as patch:
                patch.setattr(os, "read", replace_journal_during_read)
                raced = client.get(f"/api/daily-brief?date={brief_day}&timezone=Asia%2FShanghai",
                                   headers={"Origin": origin})
            assert replaced is True
            assert raced.status_code == 200
            assert raced.json()["status"] in {"unavailable", "partial"}
            assert raced.json()["items"] == []
            assert "Synthetic verified-source summary" not in raced.text
            assert str(roots["journal"]) not in raced.text
            assert "synthetic Journal row" not in raced.text

            task_store.update(task["id"], {"expected_updated_at": task["updated_at"],
                                            "title": "Synthetic Task changed after import"})
            stale = client.get(f"/api/daily-brief?date={brief_day}&timezone=Asia%2FShanghai",
                               headers={"Origin": origin})
            assert stale.status_code == 200
            assert stale.json()["status"] == "stale" and stale.json()["items"] == []
            assert "Synthetic verified-source summary" not in stale.text

            denied_origin = client.get(f"/api/daily-brief?date={brief_day}&timezone=Asia%2FShanghai",
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
