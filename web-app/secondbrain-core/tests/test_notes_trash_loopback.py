"""Real Core localhost Trash move, restore, explicit purge, and boundary checks."""
import hashlib
import json
import os
import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from secondbrain_core.app import create_app
import secondbrain_core.modules.notes_trash as notes_trash_module


def _private(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _run_core(tmp_path, monkeypatch):
    vault = _private(tmp_path / "synthetic-vault")
    projects = _private(vault / "Projects")
    inbox = _private(vault / "00-Inbox")
    _private(vault / ".trash")
    knowledge = _private(vault / "Knowledge")
    roots = {name: _private(tmp_path / name) for name in (
        "raw", "review", "state", "journal", "briefs", "tasks", "drafts",
    )}
    password = tmp_path / "synthetic-app-password"
    password.write_text("synthetic-notes-trash-password\n", encoding="utf-8")
    os.chmod(password, 0o600)
    secret = tmp_path / "synthetic-unused-promote-secret"
    secret.write_text("synthetic-unused-promote-secret-value-0000000000000000", encoding="utf-8")
    os.chmod(secret, 0o600)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(knowledge), "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_PROMOTE_UNLOCK_SECRET_FILE": str(secret), "SB_APP_PASSWORD_FILE": str(password),
        "SB_DASHBOARD_ORIGINS": origin, "SB_CORE_ALLOWED_HOSTS": host,
        "SB_HERMES_API_URL": "", "SB_HERMES_API_KEY": "", "SB_PROMOTE_ENABLED": "false",
        "SB_JOURNAL_ROOT": str(roots["journal"]), "SB_PROJECTS_INDEX_ROOT": "",
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]), "SB_TASK_ROOT": str(roots["tasks"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["drafts"]),
        "SB_NOTES_AUTHORIZED_ROOTS": json.dumps({"projects": str(projects), "inbox": str(inbox)}),
        "SB_NOTES_TRASH_ROOT": str(vault / ".trash" / "secondbrain"),
        "SB_PERSONAL_MEMORY_ENABLED": "false", "SB_PERSONAL_LEARNING_ENABLED": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app(), listener, host, port, origin, projects, vault


def test_real_core_trash_roundtrip_no_overwrite_idempotency_and_explicit_purge(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "synthetic-note.md"
    original = b"---\ntags: [keep-me]\n---\n\n# Synthetic\n\n[[unmodified wiki link]]\n"
    note.write_bytes(original)
    os.chmod(note, 0o600)
    attachment_dir = _private(projects / "attachments")
    attachment = attachment_dir / "shared.bin"
    attachment.write_bytes(b"synthetic-shared-attachment")
    os.chmod(attachment, 0o600)

    inbox_note = vault / "00-Inbox" / "should-stay.md"
    inbox_note.write_bytes(b"synthetic inbox must remain excluded")
    os.chmod(inbox_note, 0o600)
    sha = hashlib.sha256(original).hexdigest()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="error",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            assert client.get("/api/notes/trash", headers={"Origin": origin}).json()["status"] == "empty"

            stale = client.delete("/api/notes/trash/projects/synthetic-note.md",
                                  headers={"Origin": origin, "If-Match": '"' + "0" * 64 + '"',
                                           "Idempotency-Key": "synthetic-trash-stale"})
            assert stale.status_code == 409
            assert note.read_bytes() == original
            assert not (vault / ".trash" / "secondbrain").exists()

            denied_collection = client.delete("/api/notes/trash/inbox/should-stay.md",
                                              headers={"Origin": origin, "If-Match": '"' + hashlib.sha256(inbox_note.read_bytes()).hexdigest() + '"',
                                                       "Idempotency-Key": "synthetic-trash-inbox"})
            assert denied_collection.status_code == 403
            assert inbox_note.exists()

            protected = _private(projects / "Knowledge") / "protected.md"
            protected.write_bytes(b"Synthetic nested Knowledge must remain excluded")
            os.chmod(protected, 0o600)
            protected_result = client.delete("/api/notes/trash/projects/Knowledge/protected.md", headers={
                "Origin": origin, "If-Match": f'"{hashlib.sha256(protected.read_bytes()).hexdigest()}"',
                "Idempotency-Key": "synthetic-trash-nested-knowledge",
            })
            assert protected_result.status_code == 403
            assert protected.exists()

            moved = client.delete("/api/notes/trash/projects/synthetic-note.md", headers={
                "Origin": origin, "If-Match": f'"{sha}"', "Idempotency-Key": "synthetic-trash-1",
            })
            assert moved.status_code == 201, moved.text
            entry = moved.json()
            assert entry["status"] == "trashed" and not entry["duplicate"]
            assert not note.exists()
            trash_item = vault / ".trash" / "secondbrain" / entry["trash_id"]
            assert (trash_item / "note.md").read_bytes() == original
            assert attachment.read_bytes() == b"synthetic-shared-attachment"

            replay = client.delete("/api/notes/trash/projects/synthetic-note.md", headers={
                "Origin": origin, "If-Match": f'"{sha}"', "Idempotency-Key": "synthetic-trash-1",
            })
            assert replay.status_code == 200 and replay.json()["duplicate"] is True
            reused_key = client.delete("/api/notes/trash/projects/other.md", headers={
                "Origin": origin, "If-Match": f'"{sha}"', "Idempotency-Key": "synthetic-trash-1",
            })
            assert reused_key.status_code == 409

            listing = client.get("/api/notes/trash?limit=10&offset=0", headers={"Origin": origin})
            assert listing.status_code == 200
            assert listing.headers["cache-control"] == "private, no-store"
            assert listing.json()["items"][0]["sha256"] == sha
            assert listing.json()["items"][0]["path"] == "synthetic-note.md"

            note.write_bytes(b"different preexisting content")
            os.chmod(note, 0o600)
            conflict = client.post(f"/api/notes/trash/{entry['trash_id']}/restore",
                                   headers={"Origin": origin})
            assert conflict.status_code == 409
            assert note.read_bytes() == b"different preexisting content"
            note.unlink()
            restored = client.post(f"/api/notes/trash/{entry['trash_id']}/restore",
                                   headers={"Origin": origin})
            assert restored.status_code == 201, restored.text
            assert note.read_bytes() == original
            assert attachment.read_bytes() == b"synthetic-shared-attachment"
            replay_restore = client.post(f"/api/notes/trash/{entry['trash_id']}/restore",
                                         headers={"Origin": origin})
            assert replay_restore.status_code == 200 and replay_restore.json()["duplicate"] is True

            # Simulate process death immediately after the no-overwrite hard
            # link, before the Trash name and durable manifest are finalized.
            interrupted_note = projects / "restore-recovery.md"
            interrupted_bytes = b"Synthetic interrupted restore"
            interrupted_note.write_bytes(interrupted_bytes)
            os.chmod(interrupted_note, 0o600)
            interrupted_sha = hashlib.sha256(interrupted_bytes).hexdigest()
            interrupted_move = client.delete("/api/notes/trash/projects/restore-recovery.md", headers={
                "Origin": origin, "If-Match": f'"{interrupted_sha}"',
                "Idempotency-Key": "synthetic-restore-interrupted",
            })
            assert interrupted_move.status_code == 201
            interrupted_id = interrupted_move.json()["trash_id"]
            interrupted_trash_note = (vault / ".trash" / "secondbrain" / interrupted_id / "note.md")
            os.link(interrupted_trash_note, interrupted_note)
            recovered_restore = client.post(f"/api/notes/trash/{interrupted_id}/restore",
                                            headers={"Origin": origin})
            assert recovered_restore.status_code == 200
            assert recovered_restore.json()["duplicate"] is True
            assert interrupted_note.read_bytes() == interrupted_bytes
            assert not interrupted_trash_note.exists()
            assert recovered_restore.json()["status"] == "restored"

            purge_note = projects / "purge-me.md"
            purge_bytes = b"Synthetic explicit purge candidate"
            purge_note.write_bytes(purge_bytes)
            os.chmod(purge_note, 0o600)
            purge_sha = hashlib.sha256(purge_bytes).hexdigest()
            purge_move = client.delete("/api/notes/trash/projects/purge-me.md", headers={
                "Origin": origin, "If-Match": f'"{purge_sha}"', "Idempotency-Key": "synthetic-trash-purge",
            })
            assert purge_move.status_code == 201
            purge_id = purge_move.json()["trash_id"]
            preview = client.post(f"/api/notes/trash/{purge_id}/purge/preview",
                                  headers={"Origin": origin})
            assert preview.status_code == 200 and preview.headers["cache-control"] == "private, no-store"
            challenge = preview.json()
            wrong = client.post(f"/api/notes/trash/{purge_id}/purge/confirm", headers={"Origin": origin},
                                json={"confirmation": "wrong", "confirm": "permanently_delete", "sha256": purge_sha})
            assert wrong.status_code == 409
            assert (vault / ".trash" / "secondbrain" / purge_id / "note.md").read_bytes() == purge_bytes
            confirmed = client.post(f"/api/notes/trash/{purge_id}/purge/confirm", headers={"Origin": origin},
                                    json={"confirmation": challenge["confirmation"],
                                          "confirm": "permanently_delete", "sha256": purge_sha})
            assert confirmed.status_code == 204
            assert not (vault / ".trash" / "secondbrain" / purge_id / "note.md").exists()
            assert (vault / ".trash" / "secondbrain" / purge_id / "manifest.json").exists()
            audit = (vault / ".trash" / "secondbrain" / purge_id / "events.jsonl").read_text(encoding="utf-8")
            assert "permanent_delete_intent" in audit and "permanently_deleted" in audit
            assert "Synthetic explicit purge candidate" not in audit
            replay_purge = client.post(f"/api/notes/trash/{purge_id}/purge/confirm", headers={"Origin": origin},
                                       json={"confirmation": challenge["confirmation"],
                                             "confirm": "permanently_delete", "sha256": purge_sha})
            assert replay_purge.status_code == 200 and replay_purge.json()["duplicate"] is True
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_core_rebuild_recovers_persisted_trash_without_auto_purge(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "restart-note.md"
    original = b"Synthetic restart recovery note"
    note.write_bytes(original)
    os.chmod(note, 0o600)
    sha = hashlib.sha256(original).hexdigest()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    moved_id = None
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            moved = client.delete("/api/notes/trash/projects/restart-note.md", headers={
                "Origin": origin, "If-Match": f'"{sha}"', "Idempotency-Key": "synthetic-trash-restart",
            })
            assert moved.status_code == 201
            moved_id = moved.json()["trash_id"]
            assert not note.exists()
            assert (vault / ".trash" / "secondbrain" / moved_id / "note.md").read_bytes() == original
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()

    # A fresh create_app instance loses its session/challenge state but recovers
    # the durable Trash manifest and bytes from the same synthetic roots.
    second_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    second_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    second_listener.bind(("127.0.0.1", 0))
    second_listener.listen(32)
    second_host, second_port = second_listener.getsockname()
    second_origin = f"http://{second_host}:{second_port}"
    monkeypatch.setenv("SB_DASHBOARD_ORIGINS", second_origin)
    monkeypatch.setenv("SB_CORE_ALLOWED_HOSTS", second_host)
    app2 = create_app()
    server2 = uvicorn.Server(uvicorn.Config(app2, host=second_host, port=second_port, log_level="critical",
                                            lifespan="off", access_log=False, proxy_headers=False))
    thread2 = threading.Thread(target=server2.run, kwargs={"sockets": [second_listener]}, daemon=True)
    thread2.start()
    try:
        deadline = time.monotonic() + 10
        while not server2.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server2.started
        with httpx.Client(base_url=second_origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": second_origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            listing = client.get("/api/notes/trash", headers={"Origin": second_origin})
            assert listing.status_code == 200
            item = next(row for row in listing.json()["items"] if row["trash_id"] == moved_id)
            assert item["status"] == "trashed" and item["sha256"] == sha
            restored = client.post(f"/api/notes/trash/{moved_id}/restore", headers={"Origin": second_origin})
            assert restored.status_code == 201
            assert note.read_bytes() == original
            # No startup scan, purge, or cleanup occurred while reconstructing Core.
            assert (vault / ".trash" / "secondbrain" / moved_id / "manifest.json").exists()
    finally:
        server2.should_exit = True
        thread2.join(timeout=10)
        second_listener.close()
        assert not thread2.is_alive()


def test_trash_routes_fail_closed_when_trash_root_is_unconfigured(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    monkeypatch.setenv("SB_NOTES_TRASH_ROOT", "")
    app = create_app()
    note = projects / "must-remain.md"
    payload = b"Synthetic disabled Trash remains untouched"
    note.write_bytes(payload)
    os.chmod(note, 0o600)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="error",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            response = client.delete("/api/notes/trash/projects/must-remain.md", headers={
                "Origin": origin,
                "If-Match": f'"{hashlib.sha256(payload).hexdigest()}"',
                "Idempotency-Key": "synthetic-trash-disabled",
            })
            assert response.status_code == 501
            assert note.read_bytes() == payload
            assert not (vault / ".trash" / "secondbrain").exists()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_trash_source_replacement_after_inode_anchor_fails_closed(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "race.md"
    original = b"Synthetic original inode"
    replacement = b"Synthetic replacement must remain at source"
    note.write_bytes(original)
    os.chmod(note, 0o600)
    sha = hashlib.sha256(original).hexdigest()
    real_link = os.link
    replaced = False

    def link_then_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None, follow_symlinks=True):
        nonlocal replaced
        result = real_link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
                           follow_symlinks=follow_symlinks)
        if src == "race.md" and not replaced:
            replacement_fd = os.open("race-replacement.tmp", os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                                     0o600, dir_fd=src_dir_fd)
            try:
                os.write(replacement_fd, replacement)
                os.fsync(replacement_fd)
            finally:
                os.close(replacement_fd)
            os.replace("race-replacement.tmp", "race.md", src_dir_fd=src_dir_fd,
                       dst_dir_fd=src_dir_fd)
            replaced = True
        return result

    monkeypatch.setattr(notes_trash_module.os, "link", link_then_replace)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="error",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            result = client.delete("/api/notes/trash/projects/race.md", headers={
                "Origin": origin, "If-Match": f'"{sha}"', "Idempotency-Key": "synthetic-trash-race",
            })
            assert result.status_code == 409
            assert note.read_bytes() == replacement
            trash_items = list((vault / ".trash" / "secondbrain").iterdir())
            assert len(trash_items) == 1
            assert (trash_items[0] / "note.md").read_bytes() == original
            assert json.loads((trash_items[0] / "manifest.json").read_text(encoding="utf-8"))["state"] == "pending"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_trash_capacity_limit_prevents_unbounded_new_records(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "capacity.md"
    payload = b"Synthetic capacity note"
    note.write_bytes(payload)
    os.chmod(note, 0o600)
    trash_root = vault / ".trash" / "secondbrain"
    _private(trash_root)
    for index in range(500):
        (trash_root / f"occupied-{index:03d}").write_bytes(b"synthetic")
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="error",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            result = client.delete("/api/notes/trash/projects/capacity.md", headers={
                "Origin": origin, "If-Match": f'"{hashlib.sha256(payload).hexdigest()}"',
                "Idempotency-Key": "synthetic-trash-capacity",
            })
            assert result.status_code == 503
            assert note.read_bytes() == payload
            assert len(list(trash_root.iterdir())) == 500
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
