"""Bounded Notes Trash candidate; all filesystem changes stay under explicit roots."""
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response

from .notes import MAX_MARKDOWN_BYTES, NotesStore


_TRASH_ID = re.compile(r"^[0-9a-f]{32}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXCLUDED = {"drafts", "inbox", "00-inbox", "00_inbox", "capture", "raw", "review", "knowledge",
             "memory", "personal-memory", "journal", "private", "attachments", ".obsidian", ".trash"}
_MANIFEST_FIELDS = {"schema", "trash_id", "operation_key_sha256", "collection", "relative_path",
                    "sha256", "size_bytes", "trashed_at", "state", "device", "inode",
                    "restored_at", "purged_at", "purge_challenge_sha256", "purge_session_sha256"}
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _open_chain(path):
    """Open every path component without following symlinks."""
    if not isinstance(path, str) or not os.path.isabs(path):
        raise OSError("absolute directory required")
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        components = Path(path).parts[1:]
        for index, component in enumerate(components):
            if component in {"", ".", ".."}:
                raise OSError("invalid path component")
            next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = next_fd
            info = os.fstat(current)
            if not stat.S_ISDIR(info.st_mode):
                raise OSError("path component is not a directory")
            if index < len(components) - 1 and info.st_mode & 0o022:
                if not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
                    raise OSError("unsafe writable path component")
        info = os.fstat(current)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise OSError("directory is not private and Core-owned")
        return current
    except Exception:
        os.close(current)
        raise


def _read_at(directory_fd, name, limit, *, max_links=1):
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or not 1 <= info.st_nlink <= max_links or info.st_size > limit):
            raise OSError("unsafe file")
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(fd)
        if ((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                or len(data) != info.st_size or len(data) > limit):
            raise OSError("file changed during read")
        return data, info
    finally:
        os.close(fd)


class NotesTrashStore:
    """Synthetic-ready same-filesystem move/restore store; never scans Notes roots."""

    MAX_ITEMS = 500
    MAX_LIST_OFFSET = 5000
    MAX_MANIFEST_BYTES = 8192

    def __init__(self, notes_store, trash_root):
        self.notes_store = notes_store
        self.trash_root = trash_root if isinstance(trash_root, str) and trash_root else ""
        self._challenges = {}
        self._lock = threading.RLock()
        if self.trash_root:
            path = Path(self.trash_root)
            if (not path.is_absolute() or path.name != "secondbrain"
                    or path.parent.name != ".trash" or path.resolve(strict=False) != path.absolute()):
                raise ValueError("Notes Trash root must be an explicit Vault .trash/secondbrain path")
            for name, root in (notes_store.roots.items() if notes_store else ()):
                candidate = root.absolute()
                if path == candidate or path in candidate.parents or candidate in path.parents:
                    raise ValueError(f"Trash root overlaps Notes root {name}")

    @property
    def configured(self):
        return bool(self.notes_store and self.trash_root)

    def _require_configured(self):
        if not self.configured:
            raise HTTPException(status_code=501, detail="Notes Trash is not configured")

    def _root_fd(self, *, create=False):
        self._require_configured()
        try:
            parent_fd = _open_chain(str(Path(self.trash_root).parent))
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Notes Trash storage is unavailable") from exc
        try:
            if create:
                try:
                    os.mkdir("secondbrain", 0o700, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except FileExistsError:
                    pass
            try:
                fd = os.open("secondbrain", _DIRECTORY_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                if not create:
                    return None
                raise HTTPException(status_code=503, detail="Notes Trash storage is unavailable")
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Notes Trash storage is unavailable") from exc
            info = os.fstat(fd)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077):
                os.close(fd)
                raise HTTPException(status_code=503, detail="Notes Trash storage is unavailable")
            return fd
        finally:
            os.close(parent_fd)

    def _source_parent(self, collection, relative):
        if (not isinstance(collection, str) or collection not in self.notes_store.roots
                or collection.lower() in _EXCLUDED):
            raise HTTPException(status_code=403, detail="Notes collection is not eligible for Trash")
        parsed = NotesStore._relative(relative)
        if (len(parsed.parts) < 1 or any(part.startswith(".") or part.lower() in _EXCLUDED
                                         for part in parsed.parts[:-1])):
            raise HTTPException(status_code=403, detail="Notes path is not eligible for Trash")
        root = self.notes_store.roots[collection]
        vault_root = Path(self.trash_root).parents[1]
        try:
            root_parts = Path(root).relative_to(vault_root).parts
        except ValueError:
            root_parts = (Path(root).name,)
        if any(part.lower() in _EXCLUDED for part in root_parts):
            raise HTTPException(status_code=403, detail="Notes root is excluded from Trash")
        current = None
        try:
            current = _open_chain(str(root))
            for part in parsed.parts[:-1]:
                next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
                os.close(current)
                current = next_fd
                info = os.fstat(current)
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o022):
                    raise OSError("unsafe Notes subdirectory")
            parent_fd = current
            current = None
            return parent_fd, parsed.name
        except FileNotFoundError as exc:
            if current is not None:
                os.close(current)
            raise HTTPException(status_code=404, detail="Note not found") from exc
        except HTTPException:
            if current is not None:
                os.close(current)
            raise
        except OSError as exc:
            if current is not None:
                os.close(current)
            raise HTTPException(status_code=403, detail="Notes path could not be opened safely") from exc

    @staticmethod
    def _valid_manifest(value, trash_id):
        return (isinstance(value, dict) and set(value) == _MANIFEST_FIELDS
                and value.get("schema") == 1 and value.get("trash_id") == trash_id
                and value.get("state") in {"pending", "trashed", "restored", "purge_pending", "purged"}
                and isinstance(value.get("collection"), str)
                and isinstance(value.get("relative_path"), str)
                and isinstance(value.get("sha256"), str) and _SHA256.fullmatch(value["sha256"])
                and type(value.get("size_bytes")) is int and 0 <= value["size_bytes"] <= MAX_MARKDOWN_BYTES
                and type(value.get("device")) is int and type(value.get("inode")) is int
                and (value.get("purge_challenge_sha256") is None
                     or (isinstance(value.get("purge_challenge_sha256"), str)
                         and _SHA256.fullmatch(value["purge_challenge_sha256"]) is not None))
                and (value.get("purge_session_sha256") is None
                     or (isinstance(value.get("purge_session_sha256"), str)
                         and _SHA256.fullmatch(value["purge_session_sha256"]) is not None)))

    def _load_manifest(self, item_fd, trash_id):
        try:
            payload, _info = _read_at(item_fd, "manifest.json", self.MAX_MANIFEST_BYTES)
            value = json.loads(payload.decode("utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail="Trash record requires recovery") from exc
        if not self._valid_manifest(value, trash_id):
            raise HTTPException(status_code=503, detail="Trash record requires recovery")
        return value

    @staticmethod
    def _write_manifest(item_fd, value, *, exclusive=False):
        name = ".manifest-" + uuid.uuid4().hex + ".tmp"
        fd = None
        try:
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=item_fd)
            data = _canonical(value)
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.close(fd)
            fd = None
            if exclusive:
                try:
                    os.stat("manifest.json", dir_fd=item_fd, follow_symlinks=False)
                    raise FileExistsError("manifest exists")
                except FileNotFoundError:
                    pass
            os.replace(name, "manifest.json", src_dir_fd=item_fd, dst_dir_fd=item_fd)
            os.fsync(item_fd)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(name, dir_fd=item_fd)
            except FileNotFoundError:
                pass

    @staticmethod
    def _append_event(item_fd, event):
        payload = _canonical(event) + b"\n"
        fd = os.open("events.jsonl", os.O_CREAT | os.O_APPEND | os.O_WRONLY
                     | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=item_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise OSError("unsafe Trash event log")
            fcntl.flock(fd, fcntl.LOCK_EX)
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    @staticmethod
    def _item_result(manifest, *, status=None, duplicate=False):
        return {"trash_id": manifest["trash_id"], "collection": manifest["collection"],
                "path": manifest["relative_path"], "sha256": manifest["sha256"],
                "size_bytes": manifest["size_bytes"], "trashed_at": manifest["trashed_at"],
                "status": status or manifest["state"], "duplicate": duplicate}

    def trash(self, collection, relative, expected_sha256, idempotency_key):
        self._require_configured()
        if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
            raise HTTPException(status_code=428, detail="If-Match with the current note SHA-256 is required")
        if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        trash_id = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()[:32]
        key_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        root_fd = self._root_fd()
        item_fd = None
        parent_fd = None
        try:
            manifest = None
            if root_fd is not None:
                try:
                    item_fd = os.open(trash_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
                except FileNotFoundError:
                    item_fd = None
            if item_fd is not None:
                manifest = self._load_manifest(item_fd, trash_id)
                if (manifest["operation_key_sha256"] != key_hash or manifest["collection"] != collection
                        or manifest["relative_path"] != relative or manifest["sha256"] != expected_sha256):
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with an earlier Trash action")
                if manifest["state"] == "trashed":
                    existing, info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
                    if hashlib.sha256(existing).hexdigest() != expected_sha256:
                        raise HTTPException(status_code=503, detail="Trash record requires recovery")
                    return self._item_result(manifest, status="trashed", duplicate=True)
                if manifest["state"] != "pending":
                    raise HTTPException(status_code=409, detail="Trash action is no longer replayable")
            parent_fd, filename = self._source_parent(collection, relative)
            if root_fd is None:
                try:
                    source_bytes, source_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=404, detail="Note not found") from exc
                created = True
            elif item_fd is None:
                try:
                    source_bytes, source_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=404, detail="Note not found") from exc
                created = True
            else:
                try:
                    note_bytes, note_info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
                except FileNotFoundError:
                    note_bytes = None
                    note_info = None
                if note_bytes is not None:
                    if hashlib.sha256(note_bytes).hexdigest() != expected_sha256:
                        raise HTTPException(status_code=503, detail="Trash record requires recovery")
                    try:
                        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        current = None
                    if current is not None:
                        if (current.st_dev, current.st_ino) != (note_info.st_dev, note_info.st_ino):
                            raise HTTPException(status_code=409, detail="Source path changed during Trash recovery")
                        os.unlink(filename, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                    manifest.update(state="trashed", device=note_info.st_dev, inode=note_info.st_ino)
                    self._write_manifest(item_fd, manifest)
                    self._append_event(item_fd, {"event": "trashed", "trash_id": trash_id,
                                                 "sha256": expected_sha256, "recorded_at": _now(), "actor": "owner"})
                    return self._item_result(manifest, status="trashed", duplicate=True)
                try:
                    source_bytes, source_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=503, detail="Trash action requires manual recovery") from exc
                created = False
            digest = hashlib.sha256(source_bytes).hexdigest()
            if digest != expected_sha256:
                raise HTTPException(status_code=409, detail="Note changed; refresh before moving to Trash")
            if root_fd is None:
                root_fd = self._root_fd(create=True)
            if os.fstat(parent_fd).st_dev != os.fstat(root_fd).st_dev:
                raise HTTPException(status_code=503, detail="Notes and Trash must share a filesystem")
            if item_fd is None:
                try:
                    with os.scandir(root_fd) as entries:
                        count = 0
                        for _entry in entries:
                            count += 1
                            if count >= self.MAX_ITEMS:
                                raise HTTPException(status_code=503, detail="Trash capacity is exhausted")
                except HTTPException:
                    raise
                except OSError as exc:
                    raise HTTPException(status_code=503, detail="Trash capacity cannot be verified") from exc
                try:
                    os.mkdir(trash_id, 0o700, dir_fd=root_fd)
                    os.fsync(root_fd)
                except FileExistsError:
                    if created:
                        raise HTTPException(status_code=409, detail="Trash operation collided; retry with a new key")
                item_fd = os.open(trash_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            item_info = os.fstat(item_fd)
            if item_info.st_uid != os.geteuid() or item_info.st_mode & 0o077:
                raise HTTPException(status_code=503, detail="Trash record requires recovery")
            if manifest is None:
                manifest = {"schema": 1, "trash_id": trash_id, "operation_key_sha256": key_hash,
                            "collection": collection, "relative_path": relative, "sha256": digest,
                            "size_bytes": len(source_bytes), "trashed_at": _now(), "state": "pending",
                            "device": source_info.st_dev, "inode": source_info.st_ino,
                            "restored_at": None, "purged_at": None, "purge_challenge_sha256": None,
                            "purge_session_sha256": None}
                self._write_manifest(item_fd, manifest, exclusive=True)
                self._append_event(item_fd, {"event": "trash_intent", "trash_id": trash_id,
                                             "sha256": digest, "recorded_at": _now(), "actor": "owner"})

            # Anchor the exact checked inode before removing its source name.
            # A hard link is same-filesystem and no-overwrite; a restart between
            # link and unlink is detected by the pending manifest on replay.
            try:
                current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=409, detail="Note changed before Trash commit") from exc
            if ((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns)
                    != (source_info.st_dev, source_info.st_ino, source_info.st_size,
                        source_info.st_mtime_ns, source_info.st_ctime_ns)):
                raise HTTPException(status_code=409, detail="Note changed before Trash commit")
            try:
                os.link(filename, "note.md", src_dir_fd=parent_fd, dst_dir_fd=item_fd,
                        follow_symlinks=False)
            except FileExistsError as exc:
                raise HTTPException(status_code=503, detail="Trash action requires manual recovery") from exc
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Trash cannot anchor the verified note safely") from exc
            moved, moved_info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES, max_links=2)
            if (hashlib.sha256(moved).hexdigest() != digest
                    or (moved_info.st_dev, moved_info.st_ino) != (source_info.st_dev, source_info.st_ino)):
                raise HTTPException(status_code=503, detail="Trash action requires manual recovery")
            try:
                current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Trash action requires manual recovery") from exc
            if (current.st_dev, current.st_ino) != (source_info.st_dev, source_info.st_ino):
                raise HTTPException(status_code=409, detail="Note changed before Trash commit; recovery required")
            os.unlink(filename, dir_fd=parent_fd)
            os.fsync(parent_fd)
            os.fsync(item_fd)
            manifest.update(state="trashed", device=moved_info.st_dev, inode=moved_info.st_ino)
            self._write_manifest(item_fd, manifest)
            self._append_event(item_fd, {"event": "trashed", "trash_id": trash_id,
                                         "sha256": digest, "recorded_at": _now(), "actor": "owner"})
            return self._item_result(manifest, status="trashed")
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Notes Trash operation is unavailable") from exc
        finally:
            if item_fd is not None:
                os.close(item_fd)
            if root_fd is not None:
                os.close(root_fd)
            if parent_fd is not None:
                os.close(parent_fd)

    def list(self, *, limit=50, offset=0):
        self._require_configured()
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= self.MAX_LIST_OFFSET:
            raise HTTPException(status_code=400, detail="Invalid Trash pagination")
        try:
            root_fd = self._root_fd()
        except HTTPException as exc:
            if exc.status_code == 503 and not Path(self.trash_root).exists():
                return {"status": "empty", "items": [], "pagination": {"limit": limit, "offset": offset, "has_more": False}}
            raise
        if root_fd is None:
            return {"status": "empty", "items": [],
                    "pagination": {"limit": limit, "offset": offset, "has_more": False}}
        try:
            names = []
            try:
                with os.scandir(root_fd) as entries:
                    for entry in entries:
                        names.append(entry.name)
                        if len(names) > self.MAX_ITEMS:
                            raise HTTPException(status_code=503, detail="Trash listing exceeds the read budget")
            except HTTPException:
                raise
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Trash listing is unavailable") from exc
            names.sort()
            items = []
            for name in names:
                if not _TRASH_ID.fullmatch(name):
                    raise HTTPException(status_code=503, detail="Trash listing requires manual recovery")
                try:
                    item_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
                except OSError as exc:
                    raise HTTPException(status_code=503, detail="Trash listing requires manual recovery") from exc
                try:
                    manifest = self._load_manifest(item_fd, name)
                    items.append(self._item_result(manifest))
                finally:
                    os.close(item_fd)
            page = items[offset:offset + limit]
            return {"status": "partial" if any(row["status"] in {"pending", "purge_pending"} for row in items)
                    else ("empty" if not items else "real"), "items": page,
                    "pagination": {"limit": limit, "offset": offset, "has_more": offset + len(page) < len(items)}}
        finally:
            os.close(root_fd)

    def restore(self, trash_id):
        self._require_configured()
        if not isinstance(trash_id, str) or not _TRASH_ID.fullmatch(trash_id):
            raise HTTPException(status_code=404, detail="Trash item not found")
        root_fd = self._root_fd()
        if root_fd is None:
            raise HTTPException(status_code=404, detail="Trash item not found")
        item_fd = None
        parent_fd = None
        try:
            try:
                item_fd = os.open(trash_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="Trash item not found") from exc
            manifest = self._load_manifest(item_fd, trash_id)
            if manifest["state"] == "restored":
                return self._item_result(manifest, status="restored", duplicate=True)
            if manifest["state"] != "trashed":
                raise HTTPException(status_code=409, detail="Trash item is not restorable")
            parent_fd, filename = self._source_parent(manifest["collection"], manifest["relative_path"])
            if os.fstat(parent_fd).st_dev != os.fstat(root_fd).st_dev:
                raise HTTPException(status_code=503, detail="Notes and Trash must share a filesystem")
            try:
                trash_bytes, trash_info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES, max_links=2)
            except FileNotFoundError:
                # A prior restore may have linked the destination and crashed
                # before updating the manifest. Only the recorded inode proves it.
                try:
                    current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
                    restored, restored_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES, max_links=2)
                except OSError as exc:
                    raise HTTPException(status_code=503, detail="Restore requires manual recovery") from exc
                if ((current.st_dev, current.st_ino) != (manifest["device"], manifest["inode"])
                        or (restored_info.st_dev, restored_info.st_ino) != (manifest["device"], manifest["inode"])
                        or hashlib.sha256(restored).hexdigest() != manifest["sha256"]):
                    raise HTTPException(status_code=409, detail="Restore target is occupied")
                manifest.update(state="restored", restored_at=_now())
                self._write_manifest(item_fd, manifest)
                self._append_event(item_fd, {"event": "restored", "trash_id": trash_id,
                                             "sha256": manifest["sha256"], "recorded_at": manifest["restored_at"],
                                             "actor": "owner"})
                return self._item_result(manifest, status="restored", duplicate=True)
            if (hashlib.sha256(trash_bytes).hexdigest() != manifest["sha256"]
                    or (trash_info.st_dev, trash_info.st_ino) != (manifest["device"], manifest["inode"])):
                raise HTTPException(status_code=503, detail="Trash item failed integrity verification")
            try:
                os.link("note.md", filename, src_dir_fd=item_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            except FileExistsError:
                # Recover only the precise interrupted no-overwrite link from a
                # prior restore attempt; different content or inode is a conflict.
                try:
                    current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
                    current_bytes, current_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES,
                                                           max_links=2)
                except OSError as exc:
                    raise HTTPException(status_code=409,
                                        detail="Restore target already exists; nothing was overwritten") from exc
                if ((current.st_dev, current.st_ino) != (trash_info.st_dev, trash_info.st_ino)
                        or (current_info.st_dev, current_info.st_ino) != (trash_info.st_dev, trash_info.st_ino)
                        or hashlib.sha256(current_bytes).hexdigest() != manifest["sha256"]):
                    raise HTTPException(status_code=409,
                                        detail="Restore target already exists; nothing was overwritten")
                os.unlink("note.md", dir_fd=item_fd)
                os.fsync(item_fd)
                manifest.update(state="restored", restored_at=_now())
                self._write_manifest(item_fd, manifest)
                self._append_event(item_fd, {"event": "restored", "trash_id": trash_id,
                                             "sha256": manifest["sha256"], "recorded_at": manifest["restored_at"],
                                             "actor": "owner"})
                return self._item_result(manifest, status="restored", duplicate=True)
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Restore cannot be completed safely") from exc
            os.fsync(parent_fd)
            try:
                os.unlink("note.md", dir_fd=item_fd)
                os.fsync(item_fd)
            except OSError as exc:
                # The original and restored names remain hard links to the same
                # verified inode; a retry recognizes it and finishes safely.
                raise HTTPException(status_code=503, detail="Restore requires safe retry") from exc
            manifest.update(state="restored", restored_at=_now())
            self._write_manifest(item_fd, manifest)
            self._append_event(item_fd, {"event": "restored", "trash_id": trash_id,
                                         "sha256": manifest["sha256"], "recorded_at": manifest["restored_at"],
                                         "actor": "owner"})
            return self._item_result(manifest, status="restored")
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Notes Trash operation is unavailable") from exc
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
            if item_fd is not None:
                os.close(item_fd)
            os.close(root_fd)

    def preview_purge(self, trash_id, session_id):
        self._require_configured()
        if not isinstance(trash_id, str) or not _TRASH_ID.fullmatch(trash_id):
            raise HTTPException(status_code=404, detail="Trash item not found")
        root_fd = self._root_fd()
        if root_fd is None:
            raise HTTPException(status_code=404, detail="Trash item not found")
        item_fd = None
        try:
            try:
                item_fd = os.open(trash_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="Trash item not found") from exc
            manifest = self._load_manifest(item_fd, trash_id)
            if manifest["state"] != "trashed":
                raise HTTPException(status_code=409, detail="Trash item is not eligible for permanent deletion")
            payload, info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
            if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
                raise HTTPException(status_code=503, detail="Trash item failed integrity verification")
            challenge = secrets.token_urlsafe(32)
            expires = time.time() + 300
            with self._lock:
                self._challenges[hashlib.sha256(challenge.encode()).hexdigest()] = (session_id, trash_id,
                                                                                    manifest["sha256"], expires)
            return {"trash_id": trash_id, "sha256": manifest["sha256"],
                    "size_bytes": len(payload), "confirmation": challenge,
                    "expires_in_seconds": 300, "requires_exact_confirmation": "permanently_delete"}
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Permanent deletion preview is unavailable") from exc
        finally:
            if item_fd is not None:
                os.close(item_fd)
            os.close(root_fd)

    def confirm_purge(self, trash_id, session_id, body):
        self._require_configured()
        if not isinstance(trash_id, str) or not _TRASH_ID.fullmatch(trash_id):
            raise HTTPException(status_code=404, detail="Trash item not found")
        if (not isinstance(body, dict) or set(body) != {"confirmation", "confirm", "sha256"}
                or body.get("confirm") != "permanently_delete"
                or not isinstance(body.get("confirmation"), str)
                or not isinstance(body.get("sha256"), str) or not _SHA256.fullmatch(body["sha256"])):
            raise HTTPException(status_code=400, detail="Exact permanent deletion confirmation is required")
        challenge_hash = hashlib.sha256(body["confirmation"].encode()).hexdigest()
        root_fd = self._root_fd()
        if root_fd is None:
            raise HTTPException(status_code=404, detail="Trash item not found")
        item_fd = None
        try:
            try:
                item_fd = os.open(trash_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="Trash item not found") from exc
            manifest = self._load_manifest(item_fd, trash_id)
            if manifest["state"] == "purged":
                if (manifest.get("purge_challenge_sha256") != challenge_hash
                        or manifest.get("purge_session_sha256") != hashlib.sha256(session_id.encode()).hexdigest()):
                    raise HTTPException(status_code=409, detail="Permanent deletion confirmation expired or mismatched")
                return self._item_result(manifest, status="purged", duplicate=True)
            with self._lock:
                challenge = self._challenges.pop(challenge_hash, None)
            if (challenge is None or challenge[0] != session_id or challenge[1] != trash_id
                    or challenge[2] != body["sha256"] or challenge[3] <= time.time()):
                raise HTTPException(status_code=409, detail="Permanent deletion confirmation expired or mismatched")
            if manifest["state"] != "trashed" or manifest["sha256"] != body["sha256"]:
                raise HTTPException(status_code=409, detail="Trash item changed after confirmation preview")
            payload, info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
            if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
                raise HTTPException(status_code=503, detail="Trash item failed integrity verification")
            manifest.update(state="purge_pending")
            self._append_event(item_fd, {"event": "permanent_delete_intent", "trash_id": trash_id,
                                         "sha256": manifest["sha256"], "recorded_at": _now(), "actor": "owner"})
            self._write_manifest(item_fd, manifest)
            current = os.stat("note.md", dir_fd=item_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise HTTPException(status_code=503, detail="Trash item changed during permanent deletion")
            os.unlink("note.md", dir_fd=item_fd)
            os.fsync(item_fd)
            purged_at = _now()
            self._append_event(item_fd, {"event": "permanently_deleted", "trash_id": trash_id,
                                         "sha256": manifest["sha256"], "recorded_at": purged_at,
                                         "actor": "owner"})
            manifest.update(state="purged", purged_at=purged_at,
                            purge_challenge_sha256=challenge_hash,
                            purge_session_sha256=hashlib.sha256(session_id.encode()).hexdigest())
            self._write_manifest(item_fd, manifest)
            return self._item_result(manifest, status="purged")
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Permanent deletion requires manual recovery") from exc
        finally:
            if item_fd is not None:
                os.close(item_fd)
            os.close(root_fd)


def create_notes_trash_router(auth, notes_store, trash_store):
    router = APIRouter(prefix="/api/notes/trash")

    def require(request, action):
        auth.require_action(request, f"notes.{action}")
        if trash_store is None:
            raise HTTPException(status_code=501, detail="Notes Trash is not configured")

    @router.get("")
    def listing(request: Request, response: Response, limit: int = 50, offset: int = 0):
        require(request, "read")
        result = trash_store.list(limit=limit, offset=offset)
        response.headers["Cache-Control"] = "private, no-store"
        return result

    @router.delete("/{collection}/{relative:path}")
    def trash_note(request: Request, response: Response, collection: str, relative: str):
        require(request, "delete")
        raw_match = request.headers.get("if-match", "")
        if len(raw_match) != 66 or raw_match[0] != '"' or raw_match[-1] != '"':
            raise HTTPException(status_code=428, detail="If-Match with the current note SHA-256 is required")
        result = trash_store.trash(collection, relative, raw_match[1:-1],
                                   request.headers.get("idempotency-key", ""))
        response.headers["Cache-Control"] = "private, no-store"
        response.status_code = 200 if result.get("duplicate") else 201
        return result

    @router.post("/{trash_id}/restore")
    def restore(request: Request, response: Response, trash_id: str):
        require(request, "restore")
        result = trash_store.restore(trash_id)
        response.headers["Cache-Control"] = "private, no-store"
        response.status_code = 200 if result.get("duplicate") else 201
        return result

    @router.post("/{trash_id}/purge/preview")
    def preview_purge(request: Request, response: Response, trash_id: str):
        require(request, "purge")
        token = request.cookies.get(auth.COOKIE_NAME, "")
        session_id = hashlib.sha256(token.encode()).hexdigest()
        result = trash_store.preview_purge(trash_id, session_id)
        response.headers["Cache-Control"] = "private, no-store"
        return result

    @router.post("/{trash_id}/purge/confirm")
    def confirm_purge(request: Request, response: Response, trash_id: str, body: dict):
        require(request, "purge")
        token = request.cookies.get(auth.COOKIE_NAME, "")
        session_id = hashlib.sha256(token.encode()).hexdigest()
        result = trash_store.confirm_purge(trash_id, session_id, body)
        response.headers["Cache-Control"] = "private, no-store"
        response.status_code = 200 if result.get("duplicate") else 204
        return result if response.status_code == 200 else Response(status_code=204, headers={"Cache-Control": "private, no-store"})

    return router
