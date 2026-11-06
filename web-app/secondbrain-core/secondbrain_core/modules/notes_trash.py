"""Bounded Notes Trash candidate; all filesystem changes stay under explicit roots."""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response

from .notes import (MAX_BLOCKSUITE_RESOURCE_BYTES, MAX_BLOCKSUITE_RESOURCES_PER_NOTE,
                    MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE, MAX_MARKDOWN_BYTES,
                    NotesStore, _BLOCKSUITE_RESOURCE_FILENAME)


_TRASH_ID = re.compile(r"^[0-9a-f]{32}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXCLUDED = {"drafts", "inbox", "00-inbox", "00_inbox", "capture", "raw", "review", "knowledge",
             "memory", "personal-memory", "journal", "private", "attachments", ".obsidian", ".trash"}
_MANIFEST_FIELDS = {"schema", "trash_id", "operation_key_sha256", "collection", "relative_path",
                    "sha256", "size_bytes", "trashed_at", "state", "device", "inode",
                    "restored_at", "recovery_reason", "recovery_sha256"}
_RESOURCE_MANIFEST_FIELDS = _MANIFEST_FIELDS | {"resources"}
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


def _rename_noreplace(source_fd, source_name, target_fd, target_name):
    """Atomically move one name without replacing the destination name."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux"):
        function_name, flags = "renameat2", 1  # RENAME_NOREPLACE
    elif sys.platform == "darwin":
        function_name, flags = "renameatx_np", 4  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    function = getattr(libc, function_name, None)
    if function is None:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    result = function(source_fd, os.fsencode(source_name), target_fd,
                      os.fsencode(target_name), flags)
    if result != 0:
        error = ctypes.get_errno() or errno.EIO
        raise OSError(error, os.strerror(error), target_name)


class NotesTrashStore:
    """Synthetic-ready same-filesystem move/restore store; never scans Notes roots."""

    MAX_ITEMS = 500
    MAX_LIST_OFFSET = 5000
    MAX_MANIFEST_BYTES = 32 * 1024

    def __init__(self, notes_store, trash_root):
        self.notes_store = notes_store
        self.trash_root = trash_root if isinstance(trash_root, str) and trash_root else ""
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
        if not isinstance(value, dict) or value.get("schema") not in {1, 2}:
            return False
        expected_fields = _MANIFEST_FIELDS if value["schema"] == 1 else _RESOURCE_MANIFEST_FIELDS
        resources = value.get("resources", [])
        resources_valid = (isinstance(resources, list) and len(resources) <= MAX_BLOCKSUITE_RESOURCES_PER_NOTE
                           and all(isinstance(item, dict) and set(item) == {
                               "resource_id", "sha256", "size_bytes"
                           } and isinstance(item.get("resource_id"), str)
                           and re.fullmatch(r"[0-9a-f]{32}", item["resource_id"]) is not None
                           and isinstance(item.get("sha256"), str)
                           and _SHA256.fullmatch(item["sha256"]) is not None
                           and type(item.get("size_bytes")) is int
                           and 0 <= item["size_bytes"] <= MAX_BLOCKSUITE_RESOURCE_BYTES
                           for item in resources)
                           and sum(item["size_bytes"] for item in resources)
                           <= MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE
                           and len({item["resource_id"] for item in resources}) == len(resources))
        return (set(value) == expected_fields and resources_valid
                and value.get("trash_id") == trash_id
                and value.get("state") in {"pending", "trashed", "restored", "recovery_required"}
                and isinstance(value.get("collection"), str)
                and isinstance(value.get("relative_path"), str)
                and isinstance(value.get("sha256"), str) and _SHA256.fullmatch(value["sha256"])
                and type(value.get("size_bytes")) is int and 0 <= value["size_bytes"] <= MAX_MARKDOWN_BYTES
                and type(value.get("device")) is int and type(value.get("inode")) is int
                and (value.get("recovery_reason") is None
                     or value.get("recovery_reason") in {"move_identity_mismatch", "source_name_conflict",
                                                          "restore_identity_mismatch", "trash_name_missing"})
                and (value.get("recovery_sha256") is None
                     or (isinstance(value.get("recovery_sha256"), str)
                         and _SHA256.fullmatch(value["recovery_sha256"]) is not None)))

    def _load_manifest(self, item_fd, trash_id):
        try:
            payload, _info = _read_at(item_fd, "manifest.json", self.MAX_MANIFEST_BYTES)
            value = json.loads(payload.decode("utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail="Trash record requires recovery") from exc
        if not self._valid_manifest(value, trash_id):
            raise HTTPException(status_code=503, detail="Trash record requires recovery")
        return value

    def _open_resource_trash_directory(self, item_fd, *, create=False):
        if create:
            try:
                os.mkdir("resources", 0o700, dir_fd=item_fd)
                os.fsync(item_fd)
            except FileExistsError:
                pass
        try:
            fd = os.open("resources", _DIRECTORY_FLAGS, dir_fd=item_fd)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Trash resources are unsafe") from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise HTTPException(status_code=503, detail="Trash resources are unsafe")
        return fd

    def _read_resource_at(self, directory_fd, resource_id):
        filename = f"{resource_id}.blocksuite.json"
        if not re.fullmatch(r"[0-9a-f]{32}", resource_id):
            raise HTTPException(status_code=503, detail="Trash resource identity is invalid")
        try:
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Trash resource could not be opened safely") from exc
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_mode & 0o077 or before.st_nlink != 1
                    or before.st_size > MAX_BLOCKSUITE_RESOURCE_BYTES):
                raise HTTPException(status_code=503, detail="Trash resource file is unsafe")
            chunks, remaining = [], MAX_BLOCKSUITE_RESOURCE_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(fd)
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    or len(raw) != before.st_size or len(raw) > MAX_BLOCKSUITE_RESOURCE_BYTES):
                raise HTTPException(status_code=503, detail="Trash resource changed during verification")
        finally:
            os.close(fd)
        try:
            body = json.loads(raw.decode("utf-8"))
            canonical = self.notes_store._validate_blocksuite_resource(resource_id, body)
        except (UnicodeError, ValueError, RecursionError, HTTPException) as exc:
            raise HTTPException(status_code=503, detail="Trash resource failed schema verification") from exc
        if canonical != raw:
            raise HTTPException(status_code=503, detail="Trash resource is not canonical")
        return {"raw": raw, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
                "resource_id": resource_id, "device": before.st_dev, "inode": before.st_ino}

    @staticmethod
    def _resource_matches(observed, expected):
        return (observed is not None and observed["resource_id"] == expected["resource_id"]
                and observed["sha256"] == expected["sha256"]
                and observed["size_bytes"] == expected["size_bytes"])

    def _inventory_blocksuite_resources(self, parent_fd):
        try:
            attachments_fd = self.notes_store._open_attachments_directory(parent_fd)
        except HTTPException as exc:
            if exc.status_code == 404:
                return []
            raise
        try:
            names = os.listdir(attachments_fd)
            resources = []
            for filename in names:
                if not _BLOCKSUITE_RESOURCE_FILENAME.fullmatch(filename):
                    continue
                resource_id = filename.split(".", 1)[0]
                observed = self._read_resource_at(attachments_fd, resource_id)
                if observed is None:
                    raise HTTPException(status_code=503, detail="BlockSuite resource disappeared during inventory")
                resources.append({key: observed[key] for key in
                                  ("resource_id", "sha256", "size_bytes")})
            resources.sort(key=lambda item: item["resource_id"])
            if (len(resources) > MAX_BLOCKSUITE_RESOURCES_PER_NOTE
                    or sum(item["size_bytes"] for item in resources)
                    > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE):
                raise HTTPException(status_code=409, detail="BlockSuite resource inventory exceeds note limits")
            return resources
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite resource inventory is unavailable") from exc
        finally:
            os.close(attachments_fd)

    def _move_resources_to_trash(self, parent_fd, item_fd, manifest):
        resources = manifest.get("resources", [])
        if not resources:
            return
        try:
            attachments_fd = self.notes_store._open_attachments_directory(parent_fd)
        except HTTPException as exc:
            if exc.status_code == 404:
                attachments_fd = None
            else:
                raise
        trash_resources_fd = self._open_resource_trash_directory(item_fd, create=True)
        try:
            for expected in resources:
                resource_id = expected["resource_id"]
                source = self._read_resource_at(attachments_fd, resource_id) if attachments_fd is not None else None
                moved = self._read_resource_at(trash_resources_fd, resource_id)
                if moved is not None:
                    if not self._resource_matches(moved, expected):
                        raise HTTPException(status_code=503, detail="Trashed resource failed integrity verification")
                    if source is not None:
                        raise HTTPException(status_code=503, detail="Duplicate resource names require recovery")
                    continue
                if source is None or not self._resource_matches(source, expected):
                    raise HTTPException(status_code=503, detail="BlockSuite resource is missing or changed")
                _rename_noreplace(attachments_fd, f"{resource_id}.blocksuite.json", trash_resources_fd,
                                  f"{resource_id}.blocksuite.json")
                moved = self._read_resource_at(trash_resources_fd, resource_id)
                if not self._resource_matches(moved, expected):
                    raise HTTPException(status_code=503, detail="Moved resource failed integrity verification")
                os.fsync(attachments_fd)
                os.fsync(trash_resources_fd)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Trash resource target is occupied") from exc
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite resource move requires recovery") from exc
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            os.close(trash_resources_fd)

    def _restore_resources(self, parent_fd, item_fd, manifest):
        resources = manifest.get("resources", [])
        if not resources:
            return
        try:
            trash_resources_fd = self._open_resource_trash_directory(item_fd)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="Trash resource directory is missing") from exc
        attachments_fd = None
        try:
            try:
                attachments_fd = self.notes_store._open_attachments_directory(parent_fd)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                attachments_fd = None
            # Preflight every name before moving any resource. Existing names are
            # accepted only when the recorded resource id, byte count, and hash match.
            observed = []
            for expected in resources:
                resource_id = expected["resource_id"]
                in_trash = self._read_resource_at(trash_resources_fd, resource_id)
                in_source = None
                if attachments_fd is not None:
                    filename = f"{resource_id}.blocksuite.json"
                    try:
                        os.stat(filename, dir_fd=attachments_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        try:
                            in_source = self._read_resource_at(attachments_fd, resource_id)
                        except HTTPException as exc:
                            raise HTTPException(status_code=409,
                                                detail="Restore resource target is occupied") from exc
                if in_trash is None and self._resource_matches(in_source, expected):
                    observed.append((expected, in_trash, in_source))
                    continue
                if not self._resource_matches(in_trash, expected):
                    raise HTTPException(status_code=503, detail="Trash resource is missing or damaged")
                if in_source is not None:
                    raise HTTPException(status_code=409, detail="Restore resource target is occupied")
                observed.append((expected, in_trash, in_source))

            if attachments_fd is None:
                attachments_fd = self.notes_store._open_attachments_directory(parent_fd, create=True)
            for expected, in_trash, in_source in observed:
                if in_source is not None:
                    continue
                resource_id = expected["resource_id"]
                try:
                    _rename_noreplace(trash_resources_fd, f"{resource_id}.blocksuite.json", attachments_fd,
                                      f"{resource_id}.blocksuite.json")
                except FileExistsError as exc:
                    raise HTTPException(status_code=409, detail="Restore resource target is occupied") from exc
                restored = self._read_resource_at(attachments_fd, resource_id)
                if not self._resource_matches(restored, expected):
                    raise HTTPException(status_code=503, detail="Restored resource failed integrity verification")
                os.fsync(attachments_fd)
                os.fsync(trash_resources_fd)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite resource restore requires recovery") from exc
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            os.close(trash_resources_fd)

    def _verify_resources_in_trash(self, item_fd, manifest):
        resources = manifest.get("resources", [])
        if not resources:
            return
        try:
            resource_fd = self._open_resource_trash_directory(item_fd)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="Trash resource directory is missing") from exc
        try:
            for expected in resources:
                if not self._resource_matches(self._read_resource_at(resource_fd, expected["resource_id"]), expected):
                    raise HTTPException(status_code=503, detail="Trashed resource is missing or damaged")
        finally:
            os.close(resource_fd)

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
                "status": status or manifest["state"], "duplicate": duplicate,
                "recovery_reason": manifest["recovery_reason"]}

    def _mark_recovery_required(self, item_fd, manifest, reason, observed_sha256=None):
        manifest.update(state="recovery_required", recovery_reason=reason,
                        recovery_sha256=observed_sha256)
        self._write_manifest(item_fd, manifest)
        self._append_event(item_fd, {"event": "recovery_required", "trash_id": manifest["trash_id"],
                                     "reason": reason, "observed_sha256": observed_sha256,
                                     "recorded_at": _now(), "actor": "owner"})

    def _commit_trashed(self, item_fd, parent_fd, manifest, digest, info, *, duplicate=False):
        self._move_resources_to_trash(parent_fd, item_fd, manifest)
        os.fsync(parent_fd)
        os.fsync(item_fd)
        manifest.update(state="trashed", device=info.st_dev, inode=info.st_ino)
        self._append_event(item_fd, {"event": "trashed", "trash_id": manifest["trash_id"],
                                     "sha256": digest, "recorded_at": _now(), "actor": "owner"})
        self._write_manifest(item_fd, manifest)
        return self._item_result(manifest, status="trashed", duplicate=duplicate)

    def _recover_atomic_move(self, item_fd, parent_fd, filename, manifest, digest):
        """Commit only when the expected inode is in Trash and the source name is absent."""
        moved = None
        info = None
        source_absent = False
        try:
            moved, info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
        except OSError:
            pass
        if info is not None:
            try:
                os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                source_absent = True
            except OSError:
                pass
        if (source_absent and info is not None
                and hashlib.sha256(moved).hexdigest() == digest
                and (info.st_dev, info.st_ino) == (manifest["device"], manifest["inode"])):
            self._move_resources_to_trash(parent_fd, item_fd, manifest)
            return self._commit_trashed(item_fd, parent_fd, manifest, digest, info, duplicate=True)
        observed = hashlib.sha256(moved).hexdigest() if moved is not None else None
        self._mark_recovery_required(item_fd, manifest, "source_name_conflict", observed)
        raise HTTPException(status_code=503, detail="Trash action requires manual recovery")

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
        lock_fd = None
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
                    self._verify_resources_in_trash(item_fd, manifest)
                    return self._item_result(manifest, status="trashed", duplicate=True)
                if manifest["state"] != "pending":
                    raise HTTPException(status_code=409, detail="Trash action is no longer replayable")
            parent_fd, filename = self._source_parent(collection, relative)
            lock_fd = self.notes_store._open_note_lock(parent_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
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
                    if (hashlib.sha256(note_bytes).hexdigest() != expected_sha256
                            or (note_info.st_dev, note_info.st_ino) != (manifest["device"], manifest["inode"])):
                        raise HTTPException(status_code=503, detail="Trash record requires recovery")
                    try:
                        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        current = None
                    if current is not None:
                        self._mark_recovery_required(item_fd, manifest, "source_name_conflict")
                        raise HTTPException(status_code=503, detail="Trash action requires manual recovery")
                    self._move_resources_to_trash(parent_fd, item_fd, manifest)
                    return self._commit_trashed(item_fd, parent_fd, manifest, expected_sha256,
                                                note_info, duplicate=True)
                try:
                    source_bytes, source_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=503, detail="Trash action requires manual recovery") from exc
                created = False
            digest = hashlib.sha256(source_bytes).hexdigest()
            if digest != expected_sha256:
                if manifest is not None and manifest["state"] == "pending":
                    self._mark_recovery_required(item_fd, manifest, "source_name_conflict", digest)
                    raise HTTPException(status_code=503, detail="Trash action requires manual recovery")
                raise HTTPException(status_code=409, detail="Note changed; refresh before moving to Trash")
            if (manifest is not None and manifest["state"] == "pending"
                    and (source_info.st_dev, source_info.st_ino)
                    != (manifest["device"], manifest["inode"])):
                self._mark_recovery_required(item_fd, manifest, "source_name_conflict", digest)
                raise HTTPException(status_code=503, detail="Trash action requires manual recovery")
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
                resources = self._inventory_blocksuite_resources(parent_fd)
                manifest = {"schema": 2, "trash_id": trash_id, "operation_key_sha256": key_hash,
                            "collection": collection, "relative_path": relative, "sha256": digest,
                            "size_bytes": len(source_bytes), "trashed_at": _now(), "state": "pending",
                            "device": source_info.st_dev, "inode": source_info.st_ino,
                            "restored_at": None, "recovery_reason": None, "recovery_sha256": None,
                            "resources": resources}
                self._write_manifest(item_fd, manifest, exclusive=True)
                self._append_event(item_fd, {"event": "trash_intent", "trash_id": trash_id,
                                             "sha256": digest, "recorded_at": _now(), "actor": "owner"})

            try:
                _rename_noreplace(parent_fd, filename, item_fd, "note.md")
            except FileExistsError:
                return self._recover_atomic_move(item_fd, parent_fd, filename, manifest, digest)
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    return self._recover_atomic_move(item_fd, parent_fd, filename, manifest, digest)
                raise HTTPException(status_code=503, detail="Trash cannot move the verified note safely") from exc
            try:
                moved, moved_info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
            except OSError as exc:
                self._mark_recovery_required(item_fd, manifest, "move_identity_mismatch")
                raise HTTPException(status_code=503, detail="Moved note requires manual recovery") from exc
            moved_digest = hashlib.sha256(moved).hexdigest()
            if (moved_digest != digest or (moved_info.st_dev, moved_info.st_ino)
                    != (source_info.st_dev, source_info.st_ino)):
                try:
                    _rename_noreplace(item_fd, "note.md", parent_fd, filename)
                    os.fsync(parent_fd)
                    os.fsync(item_fd)
                    self._mark_recovery_required(item_fd, manifest, "move_identity_mismatch", moved_digest)
                except OSError:
                    self._mark_recovery_required(item_fd, manifest, "move_identity_mismatch", moved_digest)
                raise HTTPException(status_code=409, detail="Note changed during Trash move; recovery required")
            return self._commit_trashed(item_fd, parent_fd, manifest, digest, moved_info)
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Notes Trash operation is unavailable") from exc
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
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
            return {"status": "partial" if any(row["status"] in {"pending", "recovery_required"} for row in items)
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
        lock_fd = None
        try:
            try:
                item_fd = os.open(trash_id, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="Trash item not found") from exc
            manifest = self._load_manifest(item_fd, trash_id)
            if manifest["state"] == "restored":
                parent_fd, filename = self._source_parent(manifest["collection"], manifest["relative_path"])
                lock_fd = self.notes_store._open_note_lock(parent_fd)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                restored, restored_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                if (hashlib.sha256(restored).hexdigest() != manifest["sha256"]
                        or (restored_info.st_dev, restored_info.st_ino) != (manifest["device"], manifest["inode"])):
                    raise HTTPException(status_code=503, detail="Restored note failed integrity verification")
                self._restore_resources(parent_fd, item_fd, manifest)
                return self._item_result(manifest, status="restored", duplicate=True)
            if manifest["state"] != "trashed":
                raise HTTPException(status_code=409, detail="Trash item is not restorable")
            parent_fd, filename = self._source_parent(manifest["collection"], manifest["relative_path"])
            lock_fd = self.notes_store._open_note_lock(parent_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if os.fstat(parent_fd).st_dev != os.fstat(root_fd).st_dev:
                raise HTTPException(status_code=503, detail="Notes and Trash must share a filesystem")

            try:
                trash_bytes, trash_info = _read_at(item_fd, "note.md", MAX_MARKDOWN_BYTES)
            except FileNotFoundError:
                # A prior atomic rename may have completed before its durable
                # manifest update. Complete only if the target is the recorded inode.
                try:
                    restored, restored_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except OSError as exc:
                    self._mark_recovery_required(item_fd, manifest, "trash_name_missing")
                    raise HTTPException(status_code=503, detail="Restore requires manual recovery") from exc
                if ((restored_info.st_dev, restored_info.st_ino) != (manifest["device"], manifest["inode"])
                        or hashlib.sha256(restored).hexdigest() != manifest["sha256"]):
                    raise HTTPException(status_code=409, detail="Restore target is occupied")
                self._restore_resources(parent_fd, item_fd, manifest)
                os.fsync(parent_fd)
                os.fsync(item_fd)
                manifest.update(state="restored", restored_at=_now())
                self._append_event(item_fd, {"event": "restored", "trash_id": trash_id,
                                             "sha256": manifest["sha256"], "recorded_at": manifest["restored_at"],
                                             "actor": "owner"})
                self._write_manifest(item_fd, manifest)
                return self._item_result(manifest, status="restored", duplicate=True)

            if (hashlib.sha256(trash_bytes).hexdigest() != manifest["sha256"]
                    or (trash_info.st_dev, trash_info.st_ino) != (manifest["device"], manifest["inode"])):
                self._mark_recovery_required(item_fd, manifest, "restore_identity_mismatch",
                                             hashlib.sha256(trash_bytes).hexdigest())
                raise HTTPException(status_code=503, detail="Trash item failed integrity verification")

            try:
                os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise HTTPException(status_code=409, detail="Restore target is occupied")

            # Restore resources before note.md becomes visible again. Every
            # resource is preflighted first; note rename is the final commit.
            self._restore_resources(parent_fd, item_fd, manifest)

            try:
                _rename_noreplace(item_fd, "note.md", parent_fd, filename)
            except FileExistsError:
                # A competing restore may have completed. A same-inode target is
                # an idempotent success; any other target remains untouched.
                try:
                    restored, restored_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except OSError as exc:
                    raise HTTPException(status_code=409,
                                        detail="Restore target already exists; nothing was overwritten") from exc
                if ((restored_info.st_dev, restored_info.st_ino) != (trash_info.st_dev, trash_info.st_ino)
                        or hashlib.sha256(restored).hexdigest() != manifest["sha256"]):
                    raise HTTPException(status_code=409,
                                        detail="Restore target already exists; nothing was overwritten")
            except FileNotFoundError as exc:
                # Another process may have won the atomic rename. Prove the final
                # target before treating it as a duplicate; otherwise retain recovery state.
                try:
                    restored, restored_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
                except OSError:
                    self._mark_recovery_required(item_fd, manifest, "trash_name_missing")
                    raise HTTPException(status_code=503, detail="Restore requires manual recovery") from exc
                if ((restored_info.st_dev, restored_info.st_ino) != (trash_info.st_dev, trash_info.st_ino)
                        or hashlib.sha256(restored).hexdigest() != manifest["sha256"]):
                    self._mark_recovery_required(item_fd, manifest, "trash_name_missing",
                                                 hashlib.sha256(restored).hexdigest())
                    raise HTTPException(status_code=503, detail="Restore requires manual recovery") from exc

            restored, restored_info = _read_at(parent_fd, filename, MAX_MARKDOWN_BYTES)
            if ((restored_info.st_dev, restored_info.st_ino) != (trash_info.st_dev, trash_info.st_ino)
                    or hashlib.sha256(restored).hexdigest() != manifest["sha256"]):
                try:
                    _rename_noreplace(parent_fd, filename, item_fd, "note.md")
                    os.fsync(parent_fd)
                    os.fsync(item_fd)
                except OSError:
                    pass
                self._mark_recovery_required(item_fd, manifest, "restore_identity_mismatch",
                                             hashlib.sha256(restored).hexdigest())
                raise HTTPException(status_code=503, detail="Restore identity changed; recovery required")

            os.fsync(parent_fd)
            os.fsync(item_fd)
            manifest.update(state="restored", restored_at=_now())
            self._append_event(item_fd, {"event": "restored", "trash_id": trash_id,
                                         "sha256": manifest["sha256"], "recorded_at": manifest["restored_at"],
                                         "actor": "owner"})
            self._write_manifest(item_fd, manifest)
            return self._item_result(manifest, status="restored")
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Notes Trash operation is unavailable") from exc
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            if parent_fd is not None:
                os.close(parent_fd)
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

    return router
