"""Real Core localhost Trash move/restore, atomic rename races, and boundaries."""
import hashlib
import base64
from io import BytesIO
import json
import errno
import multiprocessing
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import HTTPException
from PIL import Image

from secondbrain_core.app import create_app
import secondbrain_core.modules.notes_trash as notes_trash_module
from secondbrain_core.modules.notes import NotesStore
from secondbrain_core.modules.notes_trash import NotesTrashStore


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


def _rename_race_worker(source_root, target_root, target_name, barrier, results):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    source_fd = os.open(source_root, flags)
    target_fd = os.open(target_root, flags)
    try:
        barrier.wait(timeout=10)
        try:
            notes_trash_module._rename_noreplace(source_fd, "source.md", target_fd, target_name)
            results.put((target_name, 0))
        except OSError as exc:
            results.put((target_name, exc.errno))
    finally:
        os.close(source_fd)
        os.close(target_fd)


def test_real_core_trash_roundtrip_no_overwrite_idempotency_and_purge_is_not_exposed(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "synthetic-note.md"
    original = b"---\ntags: [keep-me]\n---\n\n# Synthetic\n\nUnmodified Markdown body.\n"
    note.write_bytes(original)
    os.chmod(note, 0o600)
    note_store = NotesStore(tmp_path / "drafts", {"projects": projects})
    initial_note_etag = hashlib.sha256(original).hexdigest()
    resource_body = {"schemaVersion": 1, "resourceKind": "database", "docId": "trash_test_doc",
                     "updateB64": "eWpzLXRyYXNoLXRlc3Q=", "snapshot": {"blocks": ["synthetic"]}}
    created_resource = note_store.create_blocksuite_resource("projects", note.name, resource_body,
                                                             initial_note_etag)
    note_with_reference = original.decode("utf-8") + "\n" + created_resource["reference"] + "\n"
    note_store.update("projects", note.name, note_with_reference, initial_note_etag,
                      expected_artifacts=created_resource["artifact_set_etag"])
    original = note_with_reference.encode("utf-8")
    resource_id = created_resource["resource_id"]
    resource_source = projects / "attachments" / created_resource["filename"]
    resource_raw = resource_source.read_bytes()
    resource_sha = hashlib.sha256(resource_raw).hexdigest()
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
            anonymous_list = client.get("/api/notes/trash", headers={"Origin": origin})
            assert anonymous_list.status_code == 401
            anonymous_delete = client.delete("/api/notes/trash/projects/synthetic-note.md", headers={
                "Origin": origin, "If-Match": f'"{sha}"', "Idempotency-Key": "synthetic-trash-anonymous",
            })
            assert anonymous_delete.status_code == 401
            assert note.read_bytes() == original
            assert not (vault / ".trash" / "secondbrain").exists()

            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            assert client.get("/api/notes/trash", headers={"Origin": origin}).json()["status"] == "empty"

            auth = app.state.app_auth
            require_action = auth.require_action

            def deny_notes_delete(request, action):
                if action == "notes.delete":
                    raise HTTPException(status_code=403, detail="Action is not enabled")
                return require_action(request, action)

            monkeypatch.setattr(auth, "require_action", deny_notes_delete)
            authenticated_but_unauthorized = client.delete(
                "/api/notes/trash/projects/synthetic-note.md", headers={
                    "Origin": origin, "If-Match": f'"{sha}"',
                    "Idempotency-Key": "synthetic-trash-no-delete-grant",
                })
            assert authenticated_but_unauthorized.status_code == 403
            assert note.read_bytes() == original
            assert not (vault / ".trash" / "secondbrain").exists()
            monkeypatch.setattr(auth, "require_action", require_action)

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
            assert client.post(f"/api/notes/trash/{entry['trash_id']}/purge/preview",
                               headers={"Origin": origin}).status_code == 405
            assert not note.exists()
            trash_item = vault / ".trash" / "secondbrain" / entry["trash_id"]
            assert (trash_item / "note.md").read_bytes() == original
            assert (trash_item / "resources" / created_resource["filename"]).read_bytes() == resource_raw
            assert not resource_source.exists()
            assert attachment.read_bytes() == b"synthetic-shared-attachment"
            with pytest.raises(HTTPException) as trashed_resource_unreadable:
                note_store.read_blocksuite_resource("projects", note.name, resource_id)
            assert trashed_resource_unreadable.value.status_code == 404

            def deny_notes_restore(request, action):
                if action == "notes.restore":
                    raise HTTPException(status_code=403, detail="Action is not enabled")
                return require_action(request, action)

            monkeypatch.setattr(auth, "require_action", deny_notes_restore)
            unauthorized_restore = client.post(f"/api/notes/trash/{entry['trash_id']}/restore",
                                               headers={"Origin": origin})
            assert unauthorized_restore.status_code == 403
            assert not note.exists()
            assert (trash_item / "note.md").read_bytes() == original
            monkeypatch.setattr(auth, "require_action", require_action)

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
            assert (trash_item / "resources" / created_resource["filename"]).read_bytes() == resource_raw
            note.unlink()

            # Damaged and missing closure files fail closed without publishing
            # note.md or altering an unrelated attachment.
            trash_resource = trash_item / "resources" / created_resource["filename"]
            trash_resource.write_bytes(resource_raw + b"damaged")
            os.chmod(trash_resource, 0o600)
            damaged = client.post(f"/api/notes/trash/{entry['trash_id']}/restore", headers={"Origin": origin})
            assert damaged.status_code == 503
            assert not note.exists() and not resource_source.exists()
            trash_resource.write_bytes(resource_raw)
            os.chmod(trash_resource, 0o600)
            trash_resource.unlink()
            missing = client.post(f"/api/notes/trash/{entry['trash_id']}/restore", headers={"Origin": origin})
            assert missing.status_code == 503
            assert not note.exists() and not resource_source.exists()
            trash_resource.write_bytes(resource_raw)
            os.chmod(trash_resource, 0o600)

            # A conflicting resource destination is not overwritten and leaves
            # both the note reference and original resource safely in Trash.
            _private(resource_source.parent)
            resource_source.write_bytes(b"synthetic conflicting resource")
            os.chmod(resource_source, 0o600)
            resource_conflict = client.post(f"/api/notes/trash/{entry['trash_id']}/restore",
                                            headers={"Origin": origin})
            assert resource_conflict.status_code == 409
            assert not note.exists()
            assert resource_source.read_bytes() == b"synthetic conflicting resource"
            assert trash_resource.read_bytes() == resource_raw
            resource_source.unlink()

            restored = client.post(f"/api/notes/trash/{entry['trash_id']}/restore",
                                   headers={"Origin": origin})
            assert restored.status_code == 201, restored.text
            assert note.read_bytes() == original
            restored_resource = note_store.read_blocksuite_resource("projects", note.name, resource_id)
            assert restored_resource["etag"] == created_resource["etag"]
            assert hashlib.sha256(resource_source.read_bytes()).hexdigest() == resource_sha
            assert restored_resource["updateB64"] == resource_body["updateB64"]
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
            item_fd = os.open(interrupted_trash_note.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            source_fd = os.open(projects, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                notes_trash_module._rename_noreplace(item_fd, "note.md", source_fd, interrupted_note.name)
            finally:
                os.close(item_fd)
                os.close(source_fd)
            recovered_restore = client.post(f"/api/notes/trash/{interrupted_id}/restore",
                                            headers={"Origin": origin})
            assert recovered_restore.status_code == 200
            assert recovered_restore.json()["duplicate"] is True
            assert interrupted_note.read_bytes() == interrupted_bytes
            assert not interrupted_trash_note.exists()
            assert recovered_restore.json()["status"] == "restored"

    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_resource_closure_recovers_after_interrupted_trash_move(tmp_path, monkeypatch):
    vault = _private(tmp_path / "vault")
    projects = _private(vault / "Projects")
    _private(vault / ".trash")
    drafts = _private(tmp_path / "drafts")
    store = NotesStore(drafts, {"projects": projects})
    note = projects / "closure-retry.md"
    note_bytes = b"# Resource closure retry\n\nStable resource reference follows.\n"
    note.write_bytes(note_bytes)
    os.chmod(note, 0o600)
    note_etag = hashlib.sha256(note_bytes).hexdigest()
    resource_body = {"schemaVersion": 1, "resourceKind": "database", "docId": "retry_doc",
                     "updateB64": "c2FtcGxlLXlqcw==", "snapshot": {"blocks": ["retry"]}}
    created = store.create_blocksuite_resource("projects", note.name, resource_body, note_etag)
    image_buffer = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(image_buffer, format="PNG")
    blob_bytes = image_buffer.getvalue()
    blob_id = base64.urlsafe_b64encode(hashlib.sha256(blob_bytes).digest()).decode("ascii")
    created_blob = store.put_blocksuite_blob("projects", note.name, blob_id, blob_bytes, "image/png",
                                              note_etag, created["artifact_set_etag"])
    note_with_reference = note_bytes.decode() + "\n" + created["reference"] + "\n"
    store.update("projects", note.name, note_with_reference, note_etag,
                 expected_artifacts=created_blob["artifact_set_etag"])
    final_note_etag = hashlib.sha256(note_with_reference.encode()).hexdigest()
    resource_path = projects / "attachments" / created["filename"]
    resource_bytes = resource_path.read_bytes()
    blob_path = projects / "attachments" / f"{hashlib.sha256(blob_bytes).hexdigest()}.blocksuite-blob"
    trash_root = vault / ".trash" / "secondbrain"
    trash = NotesTrashStore(store, str(trash_root))

    real_rename = notes_trash_module._rename_noreplace
    move_calls = 0

    def fail_second_move(source_fd, source_name, target_fd, target_name):
        nonlocal move_calls
        move_calls += 1
        if move_calls == 3:
            raise OSError(errno.EIO, "synthetic interruption after note move")
        return real_rename(source_fd, source_name, target_fd, target_name)

    monkeypatch.setattr(notes_trash_module, "_rename_noreplace", fail_second_move)
    with pytest.raises(HTTPException) as interrupted:
        trash.trash("projects", note.name, final_note_etag, "closure-retry-key")
    assert interrupted.value.status_code == 503
    trash_id = hashlib.sha256(b"closure-retry-key").hexdigest()[:32]
    item_dir = trash_root / trash_id
    manifest = json.loads((item_dir / "manifest.json").read_text())
    assert manifest["state"] == "pending"
    assert manifest["schema"] == 3
    assert len(manifest["resources"]) == len(manifest["blobs"]) == 1
    assert manifest["resources"][0]["resource_id"] == created["resource_id"]
    assert manifest["resources"][0]["sha256"] == hashlib.sha256(resource_bytes).hexdigest()
    assert manifest["blobs"][0]["blob_id"] == blob_id
    assert manifest["blobs"][0]["sha256"] == hashlib.sha256(blob_bytes).hexdigest()
    assert not note.exists() and not resource_path.exists() and blob_path.exists()
    assert (item_dir / "resources" / created["filename"]).read_bytes() == resource_bytes
    with pytest.raises(HTTPException) as hidden:
        store.read_blocksuite_resource("projects", note.name, created["resource_id"])
    assert hidden.value.status_code == 404

    monkeypatch.setattr(notes_trash_module, "_rename_noreplace", real_rename)
    retried = trash.trash("projects", note.name, final_note_etag, "closure-retry-key")
    assert retried["status"] == "trashed" and retried["duplicate"] is True
    assert not resource_path.exists() and not blob_path.exists()
    assert (item_dir / "resources" / created["filename"]).read_bytes() == resource_bytes
    assert (item_dir / "resources" / blob_path.name).read_bytes() == blob_bytes
    restored = trash.restore(trash_id)
    assert restored["status"] == "restored"
    assert note.read_bytes() == note_with_reference.encode()
    assert store.read_blocksuite_resource("projects", note.name, created["resource_id"])["etag"] == created["etag"]
    assert store.read_blocksuite_blob("projects", note.name, blob_id)["data"] == blob_bytes


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


def test_trash_source_replacement_after_atomic_move_is_restored_or_recovery_required(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "race.md"
    original = b"Synthetic original inode"
    replacement = b"Synthetic replacement must remain at source"
    note.write_bytes(original)
    os.chmod(note, 0o600)
    sha = hashlib.sha256(original).hexdigest()
    real_rename = notes_trash_module._rename_noreplace
    replaced = False

    def replace_source_then_rename(src_fd, src, dst_fd, dst):
        nonlocal replaced
        if src == "race.md" and not replaced:
            replacement_fd = os.open("race-replacement.tmp", os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                                     0o600, dir_fd=src_fd)
            try:
                os.write(replacement_fd, replacement)
                os.fsync(replacement_fd)
            finally:
                os.close(replacement_fd)
            os.replace("race-replacement.tmp", "race.md", src_dir_fd=src_fd, dst_dir_fd=src_fd)
            replaced = True
        return real_rename(src_fd, src, dst_fd, dst)

    monkeypatch.setattr(notes_trash_module, "_rename_noreplace", replace_source_then_rename)
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
            manifest = json.loads((trash_items[0] / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["state"] == "recovery_required"
            assert manifest["recovery_reason"] == "move_identity_mismatch"
            assert manifest["recovery_sha256"] == hashlib.sha256(replacement).hexdigest()
            assert not (trash_items[0] / "note.md").exists()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_trash_pending_record_recovers_after_move_before_manifest_commit(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "crash.md"
    payload = b"Synthetic move committed before process interruption"
    note.write_bytes(payload)
    os.chmod(note, 0o600)
    digest = hashlib.sha256(payload).hexdigest()
    actual_rename = notes_trash_module._rename_noreplace
    interrupted = False

    def rename_then_interrupt(src_fd, src, dst_fd, dst):
        nonlocal interrupted
        actual_rename(src_fd, src, dst_fd, dst)
        if src == "crash.md" and not interrupted:
            interrupted = True
            raise OSError(errno.EIO, "synthetic interruption after atomic move")

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
            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", rename_then_interrupt)
            headers = {"Origin": origin, "If-Match": f'"{digest}"',
                       "Idempotency-Key": "synthetic-trash-crash-recovery"}
            first = client.delete("/api/notes/trash/projects/crash.md", headers=headers)
            assert first.status_code == 503
            assert not note.exists()
            items = list((vault / ".trash" / "secondbrain").iterdir())
            assert len(items) == 1
            assert json.loads((items[0] / "manifest.json").read_text(encoding="utf-8"))["state"] == "pending"
            assert (items[0] / "note.md").read_bytes() == payload

            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", actual_rename)
            replay = client.delete("/api/notes/trash/projects/crash.md", headers=headers)
            assert replay.status_code == 200 and replay.json()["duplicate"] is True
            assert replay.json()["status"] == "trashed"
            assert json.loads((items[0] / "manifest.json").read_text(encoding="utf-8"))["state"] == "trashed"
            assert (items[0] / "note.md").read_bytes() == payload
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_pending_retry_refuses_same_bytes_from_replaced_source_inode(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "pending-replaced.md"
    payload = b"Synthetic identical bytes on a different source inode"
    note.write_bytes(payload)
    os.chmod(note, 0o600)
    digest = hashlib.sha256(payload).hexdigest()
    original_inode = note.stat().st_ino
    real_rename = notes_trash_module._rename_noreplace

    def interrupt_before_move(_src_fd, _src, _dst_fd, _dst):
        raise OSError(errno.EIO, "synthetic interruption before atomic move")

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
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
            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", interrupt_before_move)
            headers = {"Origin": origin, "If-Match": f'"{digest}"',
                       "Idempotency-Key": "synthetic-pending-inode-binding"}
            first = client.delete("/api/notes/trash/projects/pending-replaced.md", headers=headers)
            assert first.status_code == 503
            assert note.read_bytes() == payload

            replacement_tmp = projects / "pending-replaced.tmp"
            replacement_tmp.write_bytes(payload)
            os.chmod(replacement_tmp, 0o600)
            os.replace(replacement_tmp, note)
            assert note.stat().st_ino != original_inode

            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", real_rename)
            retry = client.delete("/api/notes/trash/projects/pending-replaced.md", headers=headers)
            assert retry.status_code == 503
            assert note.read_bytes() == payload
            item_dir = vault / ".trash" / "secondbrain" / hashlib.sha256(
                b"synthetic-pending-inode-binding").hexdigest()[:32]
            manifest = json.loads((item_dir / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["state"] == "recovery_required"
            assert manifest["recovery_reason"] == "source_name_conflict"
            assert manifest["recovery_sha256"] == digest
            assert not (item_dir / "note.md").exists()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_concurrent_pending_replays_converge_on_one_atomic_move(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "pending-concurrent.md"
    payload = b"Synthetic concurrent pending replay"
    note.write_bytes(payload)
    os.chmod(note, 0o600)
    digest = hashlib.sha256(payload).hexdigest()
    real_rename = notes_trash_module._rename_noreplace

    def interrupt_before_move(_src_fd, _src, _dst_fd, _dst):
        raise OSError(errno.EIO, "synthetic pending interruption")

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        headers = {"Origin": origin, "If-Match": f'"{digest}"',
                   "Idempotency-Key": "synthetic-pending-concurrent"}
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as login_client:
            login = login_client.post("/api/auth/login", headers={"Origin": origin},
                                      json={"password": "synthetic-notes-trash-password"})
            assert login.status_code == 200
            cookies = dict(login_client.cookies)
            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", interrupt_before_move)
            interrupted = login_client.delete("/api/notes/trash/projects/pending-concurrent.md",
                                              headers=headers)
            assert interrupted.status_code == 503
            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", real_rename)

        # The same per-parent Notes lock serializes Trash/resource closure with
        # Notes writes and concurrent replays. Both requests must converge on
        # one move without requiring two simultaneous rename attempts.
        monkeypatch.setattr(notes_trash_module, "_rename_noreplace", real_rename)
        def replay():
            with httpx.Client(base_url=origin, timeout=8, trust_env=False, cookies=cookies) as client:
                return client.delete("/api/notes/trash/projects/pending-concurrent.md",
                                     headers=headers)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: replay(), range(2)))
        assert sorted(response.status_code for response in results) == [200, 201]
        assert sum(response.json()["duplicate"] for response in results) == 1
        item_id = results[0].json()["trash_id"]
        item_dir = vault / ".trash" / "secondbrain" / item_id
        manifest = json.loads((item_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["state"] == "trashed"
        assert (item_dir / "note.md").read_bytes() == payload
        assert not note.exists()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_cross_process_atomic_rename_has_one_winner_without_overwrite(tmp_path):
    source = _private(tmp_path / "race-source")
    destination_one = _private(tmp_path / "race-destination-one")
    destination_two = _private(tmp_path / "race-destination-two")
    payload = b"Synthetic cross-process rename race"
    source_file = source / "source.md"
    source_file.write_bytes(payload)
    os.chmod(source_file, 0o600)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    workers = [
        context.Process(target=_rename_race_worker,
                        args=(str(source), str(destination_one), "one.md", barrier, results)),
        context.Process(target=_rename_race_worker,
                        args=(str(source), str(destination_two), "two.md", barrier, results)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)
    assert all(worker.exitcode == 0 for worker in workers)
    results_seen = [results.get(timeout=2) for _ in workers]
    assert sorted(code for _, code in results_seen) == sorted([0, errno.ENOENT])
    moved = [path for path in (destination_one / "one.md", destination_two / "two.md") if path.exists()]
    assert len(moved) == 1 and moved[0].read_bytes() == payload
    assert not source_file.exists()


def test_restore_trash_name_replacement_rolls_back_without_overwrite(tmp_path, monkeypatch):
    app, listener, host, port, origin, projects, vault = _run_core(tmp_path, monkeypatch)
    note = projects / "restore-race.md"
    original = b"Synthetic expected restore inode"
    replacement = b"Synthetic replaced Trash entry"
    note.write_bytes(original)
    os.chmod(note, 0o600)
    original_sha = hashlib.sha256(original).hexdigest()
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
            moved = client.delete("/api/notes/trash/projects/restore-race.md", headers={
                "Origin": origin, "If-Match": f'"{original_sha}"',
                "Idempotency-Key": "synthetic-restore-race",
            })
            assert moved.status_code == 201
            item_id = moved.json()["trash_id"]
            trash_note = vault / ".trash" / "secondbrain" / item_id / "note.md"
            real_rename = notes_trash_module._rename_noreplace
            replaced = False

            def replace_trash_name_then_rename(src_fd, src, dst_fd, dst):
                nonlocal replaced
                if src == "note.md" and dst == "restore-race.md" and not replaced:
                    replacement_fd = os.open("replacement.tmp", os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                                             0o600, dir_fd=src_fd)
                    try:
                        os.write(replacement_fd, replacement)
                        os.fsync(replacement_fd)
                    finally:
                        os.close(replacement_fd)
                    os.replace("replacement.tmp", "note.md", src_dir_fd=src_fd, dst_dir_fd=src_fd)
                    replaced = True
                return real_rename(src_fd, src, dst_fd, dst)

            monkeypatch.setattr(notes_trash_module, "_rename_noreplace", replace_trash_name_then_rename)
            restored = client.post(f"/api/notes/trash/{item_id}/restore", headers={"Origin": origin})
            assert restored.status_code == 503
            assert not note.exists()
            assert trash_note.read_bytes() == replacement
            manifest = json.loads(trash_note.parent.joinpath("manifest.json").read_text(encoding="utf-8"))
            assert manifest["state"] == "recovery_required"
            assert manifest["recovery_reason"] == "restore_identity_mismatch"
            assert manifest["recovery_sha256"] == hashlib.sha256(replacement).hexdigest()
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
