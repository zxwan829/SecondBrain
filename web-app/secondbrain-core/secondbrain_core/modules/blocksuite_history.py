"""Content-addressed, note-bound BlockSuite recovery points."""
import fcntl
import base64
import hashlib
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import HTTPException


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_ID = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_ID = re.compile(r"^[0-9a-f]{32}$")
_BLOB_ID = re.compile(r"^[A-Za-z0-9_-]{43}=$")
_BLOB_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _blob_id_matches_digest(blob_id, digest):
    try:
        raw = base64.b64decode(blob_id.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeError, ValueError):
        return False
    return len(raw) == 32 and base64.urlsafe_b64encode(raw).decode("ascii") == blob_id and raw.hex() == digest
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
MAX_NOTE_SNAPSHOTS = 3
MAX_NOTE_HISTORY_BYTES = 192 * 1024 * 1024
MAX_GLOBAL_HISTORY_BYTES = 2 * 1024 * 1024 * 1024
MAX_SNAPSHOT_MANIFEST_BYTES = 128 * 1024
MAX_HISTORY_SCAN_ENTRIES = 200_000
MAX_HISTORY_OBJECTS = 200_000


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _secure_directory(fd):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise HTTPException(status_code=503, detail="BlockSuite history directory is unsafe")


class BlockSuiteHistoryStore:
    """History metadata stays with each note; immutable payload blocks are shared by SHA-256."""

    def __init__(self, notes_store):
        self.notes_store = notes_store
        self.global_root = notes_store.roots["drafts"] / ".blocksuite-history"

    @contextmanager
    def _global(self, *, create=False, exclusive=True):
        root_fd = objects_fd = lock_fd = None
        try:
            if create:
                parent_fd = self.notes_store._open_directory(self.global_root.parent)
                try:
                    try:
                        os.mkdir(self.global_root.name, 0o700, dir_fd=parent_fd)
                    except FileExistsError:
                        pass
                    os.fsync(parent_fd)
                except OSError as exc:
                    raise HTTPException(status_code=507, detail="BlockSuite history directory could not be created") from exc
                finally:
                    os.close(parent_fd)
            try:
                root_fd = self.notes_store._open_directory(self.global_root, missing_status=404)
            except HTTPException as exc:
                if not create and exc.status_code == 404:
                    yield None
                    return
                raise
            _secure_directory(root_fd)
            if create:
                try:
                    os.mkdir("objects", 0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
                os.fsync(root_fd)
            try:
                objects_fd = os.open("objects", _DIR_FLAGS, dir_fd=root_fd)
            except FileNotFoundError:
                if not create:
                    yield {"root_fd": root_fd, "objects_fd": None}
                    return
                raise HTTPException(status_code=503, detail="BlockSuite history object store is unavailable")
            _secure_directory(objects_fd)
            lock_fd = os.open(".lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                              0o600, dir_fd=root_fd)
            os.fsync(root_fd)
            lock_info = os.fstat(lock_fd)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                    or lock_info.st_mode & 0o077 or lock_info.st_nlink != 1):
                raise HTTPException(status_code=503, detail="BlockSuite history lock is unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            if exclusive:
                self._cleanup_temps(root_fd)
            self._validate_global_root(root_fd)
            yield {"root_fd": root_fd, "objects_fd": objects_fd, "lock_fd": lock_fd}
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=507, detail="BlockSuite history storage is unavailable") from exc
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            if objects_fd is not None:
                os.close(objects_fd)
            if root_fd is not None:
                os.close(root_fd)

    @staticmethod
    def _validate_global_root(root_fd):
        try:
            names = set(os.listdir(root_fd))
        except OSError as exc:
            raise HTTPException(status_code=507, detail="BlockSuite global history directory is unavailable") from exc
        if names - {"objects", ".lock", "index.json"}:
            raise HTTPException(status_code=507, detail="BlockSuite global history contains an unknown entry")
        if "objects" not in names or ".lock" not in names:
            raise HTTPException(status_code=507, detail="BlockSuite global history is incomplete")
        for name in names - {"objects"}:
            try:
                info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=507, detail="BlockSuite global history entry is unsafe") from exc
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or info.st_nlink != 1 or (name == "index.json" and info.st_size > 16 * 1024 * 1024)):
                raise HTTPException(status_code=507, detail="BlockSuite global history entry is unsafe")

    def _open_snapshot_directory(self, directory_fd, collection, relative, *, create=False):
        namespace = self.notes_store._history_namespace(collection, relative)
        history_fd = (self.notes_store._open_history_directory_for_update(directory_fd, namespace)
                      if create else self.notes_store._open_history_directory_for_read(directory_fd, namespace))
        if history_fd is None:
            return None
        try:
            if create:
                try:
                    os.mkdir("blocksuite", 0o700, dir_fd=history_fd)
                except FileExistsError:
                    pass
                os.fsync(history_fd)
            try:
                suite_fd = os.open("blocksuite", _DIR_FLAGS, dir_fd=history_fd)
            except FileNotFoundError:
                return None
            _secure_directory(suite_fd)
            if create:
                try:
                    os.mkdir("snapshots", 0o700, dir_fd=suite_fd)
                except FileExistsError:
                    pass
                os.fsync(suite_fd)
            try:
                snapshots_fd = os.open("snapshots", _DIR_FLAGS, dir_fd=suite_fd)
            except FileNotFoundError:
                return None
            _secure_directory(snapshots_fd)
            return snapshots_fd
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite snapshot directory is unsafe") from exc
        finally:
            os.close(history_fd)
            if "suite_fd" in locals():
                os.close(suite_fd)

    @staticmethod
    def _read_small(directory_fd, name, max_bytes):
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite history file is unsafe") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > max_bytes):
                raise HTTPException(status_code=503, detail="BlockSuite history file is unsafe")
            raw = bytearray()
            while len(raw) <= max_bytes:
                chunk = os.read(fd, min(65536, max_bytes + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            if (len(raw) != info.st_size or len(raw) > max_bytes
                    or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise HTTPException(status_code=503, detail="BlockSuite history file changed during read")
            return bytes(raw)
        finally:
            os.close(fd)

    @staticmethod
    def _cleanup_temps(directory_fd):
        for name in os.listdir(directory_fd):
            if not re.fullmatch(r"\.blocksuite-tmp-[0-9a-f]{32}", name):
                continue
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=507, detail="BlockSuite temporary file cannot be inspected") from exc
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink not in {1, 2}):
                raise HTTPException(status_code=507, detail="BlockSuite temporary file is unsafe")
            os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)

    @staticmethod
    def _atomic_write(directory_fd, name, raw, *, exclusive=False):
        temp_name = f".blocksuite-tmp-{uuid.uuid4().hex}"
        fd = None
        try:
            fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=directory_fd)
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.close(fd)
            fd = None
            if exclusive:
                try:
                    os.link(temp_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                            follow_symlinks=False)
                except FileExistsError as exc:
                    raise HTTPException(status_code=409, detail="BlockSuite snapshot already exists") from exc
                os.unlink(temp_name, dir_fd=directory_fd)
            else:
                os.replace(temp_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        except Exception:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            if fd is not None:
                os.close(fd)

    @staticmethod
    def _scan_objects(objects_fd):
        objects = {}
        total = 0
        try:
            names = os.listdir(objects_fd)
        except OSError as exc:
            raise HTTPException(status_code=507, detail="BlockSuite object inventory is unavailable") from exc
        if len(names) > MAX_HISTORY_OBJECTS:
            raise HTTPException(status_code=507, detail="BlockSuite global object scan exceeds its budget")
        for name in names:
            if re.fullmatch(r"\.blocksuite-tmp-[0-9a-f]{32}", name):
                try:
                    temp_info = os.stat(name, dir_fd=objects_fd, follow_symlinks=False)
                except OSError as exc:
                    raise HTTPException(status_code=507, detail="BlockSuite temporary object is unsafe") from exc
                if (not stat.S_ISREG(temp_info.st_mode) or temp_info.st_uid != os.geteuid()
                        or temp_info.st_mode & 0o077 or temp_info.st_nlink != 1):
                    raise HTTPException(status_code=507, detail="BlockSuite temporary object is unsafe")
                os.unlink(name, dir_fd=objects_fd)
                continue
            if not _SHA256.fullmatch(name):
                raise HTTPException(status_code=507, detail="BlockSuite object store contains an unknown entry")
            try:
                info = os.stat(name, dir_fd=objects_fd, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=507, detail="BlockSuite object could not be inspected") from exc
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise HTTPException(status_code=507, detail="BlockSuite object file is unsafe")
            objects[name] = info.st_size
            total += info.st_size
        return objects, total

    def _manifest_directory_rows(self, snapshots_fd):
        if snapshots_fd is None:
            return []
        rows = []
        names = os.listdir(snapshots_fd)
        if len(names) > MAX_HISTORY_SCAN_ENTRIES:
            raise HTTPException(status_code=507, detail="BlockSuite manifest scan exceeds its budget")
        for name in names:
            if name == "restore.json":
                self._read_restore_journal(snapshots_fd)
                continue
            if not re.fullmatch(r"[0-9a-f]{64}\.json", name):
                raise HTTPException(status_code=507, detail="BlockSuite snapshot directory has an unknown entry")
            rows.append(self._read_manifest(snapshots_fd, name[:-5]))
        return rows

    @staticmethod
    def _open_child_directory(parent_fd, name):
        try:
            fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HTTPException(status_code=507, detail="BlockSuite history scan encountered an unsafe path") from exc
        try:
            _secure_directory(fd)
        except Exception:
            os.close(fd)
            raise
        return fd

    def _history_manifests_at(self, history_fd, *, drafts_layout):
        """Read only our versioned snapshot manifests; reject ambiguous history layouts."""
        manifests = []

        def read_suite(parent_fd):
            suite_fd = self._open_child_directory(parent_fd, "blocksuite")
            if suite_fd is None:
                return
            try:
                for name in os.listdir(suite_fd):
                    if name != "snapshots":
                        raise HTTPException(status_code=507, detail="BlockSuite history contains an unknown directory")
                snapshots_fd = self._open_child_directory(suite_fd, "snapshots")
                if snapshots_fd is not None:
                    try:
                        manifests.extend(self._manifest_directory_rows(snapshots_fd))
                    finally:
                        os.close(snapshots_fd)
            finally:
                os.close(suite_fd)

        names = os.listdir(history_fd)
        if drafts_layout:
            for name in names:
                if name == "blocksuite":
                    read_suite(history_fd)
                elif re.fullmatch(r"[0-9a-f]{64}\.md", name):
                    continue
                else:
                    info = os.stat(name, dir_fd=history_fd, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise HTTPException(status_code=507, detail="Draft history contains an unsafe entry")
            return manifests

        for name in names:
            if re.fullmatch(r"[0-9a-f]{64}\.md", name):
                info = os.stat(name, dir_fd=history_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise HTTPException(status_code=507, detail="Note history contains an unsafe entry")
                continue
            if not re.fullmatch(r"[0-9a-f]{64}", name):
                raise HTTPException(status_code=507, detail="Note history contains an unknown entry")
            namespace_fd = self._open_child_directory(history_fd, name)
            if namespace_fd is None:
                raise HTTPException(status_code=507, detail="Note history changed during scan")
            try:
                for child in os.listdir(namespace_fd):
                    if child == "blocksuite":
                        read_suite(namespace_fd)
                    elif re.fullmatch(r"[0-9a-f]{64}\.md", child):
                        info = os.stat(child, dir_fd=namespace_fd, follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                            raise HTTPException(status_code=507, detail="Note history contains an unsafe entry")
                    else:
                        info = os.stat(child, dir_fd=namespace_fd, follow_symlinks=False)
                        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                            raise HTTPException(status_code=507, detail="Note history contains an unsafe entry")
                        raise HTTPException(status_code=507, detail="Note history contains an unknown directory")
            finally:
                os.close(namespace_fd)
        return manifests

    def _scan_authorized_manifests(self):
        """Bounded no-follow traversal of each configured Notes root for history references."""
        manifests = []
        seen_entries = 0
        roots = self.notes_store.roots
        for collection, root_path in roots.items():
            try:
                root_fd = self.notes_store._open_directory(root_path, missing_status=404)
            except HTTPException as exc:
                raise HTTPException(status_code=507, detail="An authorized Notes root could not be scanned completely") from exc
            stack = [(root_fd, True)]
            try:
                while stack:
                    directory_fd, is_root = stack.pop()
                    try:
                        names = os.listdir(directory_fd)
                        seen_entries += len(names)
                        if seen_entries > MAX_HISTORY_SCAN_ENTRIES:
                            raise HTTPException(status_code=507, detail="BlockSuite global manifest scan exceeds its budget")
                        for name in names:
                            if is_root and collection == "drafts" and name == ".blocksuite-history":
                                continue
                            try:
                                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                            except OSError as exc:
                                raise HTTPException(status_code=507, detail="Notes root changed during history scan") from exc
                            if stat.S_ISLNK(info.st_mode):
                                raise HTTPException(status_code=507, detail="Notes root contains a symlink; history scan is incomplete")
                            if name == ".history":
                                if not stat.S_ISDIR(info.st_mode):
                                    raise HTTPException(status_code=507, detail="Notes history path is unsafe")
                                history_fd = self._open_child_directory(directory_fd, name)
                                if history_fd is None:
                                    raise HTTPException(status_code=507, detail="Notes history changed during scan")
                                try:
                                    manifests.extend(self._history_manifests_at(history_fd, drafts_layout=collection == "drafts"))
                                finally:
                                    os.close(history_fd)
                                continue
                            if stat.S_ISDIR(info.st_mode):
                                child_fd = self._open_child_directory(directory_fd, name)
                                if child_fd is None:
                                    raise HTTPException(status_code=507, detail="Notes root changed during history scan")
                                stack.append((child_fd, False))
                            elif not stat.S_ISREG(info.st_mode):
                                raise HTTPException(status_code=507, detail="Notes root contains an unsafe entry")
                    finally:
                        os.close(directory_fd)
            except Exception:
                for fd, _ in stack:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                raise
        return manifests

    def _manifest_references(self, manifests):
        references = {}
        for manifest in manifests:
            pairs = [(manifest["note_sha256"], manifest["note_bytes"])]
            pairs.extend((item["sha256"], item["bytes"]) for item in manifest["artifacts"])
            for digest, size in pairs:
                old_size = references.setdefault(digest, size)
                if old_size != size:
                    raise HTTPException(status_code=507, detail="BlockSuite manifests disagree on content size")
        return references

    def _garbage_collect_unreferenced(self, objects_fd, *, enforce_cap=True):
        manifests = self._scan_authorized_manifests()
        references = self._manifest_references(manifests)
        objects, _total = self._scan_objects(objects_fd)
        if set(references) - set(objects):
            raise HTTPException(status_code=507, detail="A referenced BlockSuite history object is missing")
        removed = False
        for digest, size in objects.items():
            if digest in references:
                if references[digest] != size:
                    raise HTTPException(status_code=507, detail="BlockSuite object size disagrees with its manifests")
                self._read_object(objects_fd, digest, size)
                continue
            # A path is collected only after a complete authorized-root scan and
            # after proving its content matches the generated content-addressed name.
            data = self._read_object(objects_fd, digest, size)
            if hashlib.sha256(data).hexdigest() != digest:
                raise HTTPException(status_code=507, detail="Unreferenced BlockSuite object failed verification")
            os.unlink(digest, dir_fd=objects_fd)
            removed = True
        if removed:
            os.fsync(objects_fd)
        objects, total = self._scan_objects(objects_fd)
        if enforce_cap and total > MAX_GLOBAL_HISTORY_BYTES:
            raise HTTPException(status_code=507, detail="Global BlockSuite history capacity is exhausted")
        return objects, total, references

    @staticmethod
    def _retained_prior_rows(prior_rows, preserve_ids=()):
        preserve_ids = set(preserve_ids)
        retained = prior_rows[-(MAX_NOTE_SNAPSHOTS - 1):]
        retained_ids = {item["snapshot_id"] for item in retained} | preserve_ids
        if len(retained_ids) > MAX_NOTE_SNAPSHOTS - 1:
            for item in prior_rows:
                if item["snapshot_id"] in retained_ids and item["snapshot_id"] not in preserve_ids:
                    retained_ids.remove(item["snapshot_id"])
                    if len(retained_ids) <= MAX_NOTE_SNAPSHOTS - 1:
                        break
        return [item for item in prior_rows if item["snapshot_id"] in retained_ids]

    @staticmethod
    def _write_object(objects_fd, digest, data):
        if hashlib.sha256(data).hexdigest() != digest:
            raise HTTPException(status_code=409, detail="BlockSuite object digest mismatch")
        temp_name = f".blocksuite-tmp-{uuid.uuid4().hex}"
        fd = None
        try:
            fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=objects_fd)
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            os.close(fd)
            fd = None
            try:
                os.link(temp_name, digest, src_dir_fd=objects_fd, dst_dir_fd=objects_fd,
                        follow_symlinks=False)
            except FileExistsError:
                existing = BlockSuiteHistoryStore._read_object(objects_fd, digest, len(data))
                if existing != data:
                    raise HTTPException(status_code=503, detail="BlockSuite content object hash conflict")
            os.unlink(temp_name, dir_fd=objects_fd)
            os.fsync(objects_fd)
        except Exception:
            try:
                os.unlink(temp_name, dir_fd=objects_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            if fd is not None:
                os.close(fd)

    @staticmethod
    def _read_object(objects_fd, digest, expected_bytes):
        if not _SHA256.fullmatch(digest):
            raise HTTPException(status_code=503, detail="BlockSuite snapshot contains an invalid object id")
        try:
            fd = os.open(digest, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=objects_fd)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite snapshot object is missing") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1
                    or info.st_size != expected_bytes):
                raise HTTPException(status_code=503, detail="BlockSuite snapshot object is unsafe")
            chunks = []
            remaining = expected_bytes + 1
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
                    or len(data) != expected_bytes or hashlib.sha256(data).hexdigest() != digest):
                raise HTTPException(status_code=503, detail="BlockSuite snapshot object failed verification")
            return data
        finally:
            os.close(fd)

    @staticmethod
    def _validate_manifest(value, snapshot_id):
        if (not isinstance(value, dict) or set(value) != {
                "schema", "snapshot_id", "note_key", "note_sha256", "note_bytes", "artifact_set_etag",
                "created_at", "state", "artifacts"}):
            return False
        if (value.get("schema") != 1 or value.get("snapshot_id") != snapshot_id
                or not _SNAPSHOT_ID.fullmatch(snapshot_id)
                or not isinstance(value.get("note_key"), str) or not _SHA256.fullmatch(value["note_key"])
                or not isinstance(value.get("note_sha256"), str) or not _SHA256.fullmatch(value["note_sha256"])
                or type(value.get("note_bytes")) is not int or not 1 <= value["note_bytes"] <= 1_000_000
                or not isinstance(value.get("artifact_set_etag"), str)
                or not _SHA256.fullmatch(value["artifact_set_etag"])
                or value.get("state") not in {"pending", "complete"}
                or not isinstance(value.get("created_at"), str) or not isinstance(value.get("artifacts"), list)):
            return False
        if len(value["artifacts"]) > 64:
            return False
        total = 0
        seen = set()
        for item in value["artifacts"]:
            if (not isinstance(item, dict) or set(item) != {"kind", "id", "sha256", "bytes", "content_type"}
                    or item.get("kind") not in {"resource", "blob"} or not isinstance(item.get("id"), str)
                    or not isinstance(item.get("sha256"), str) or not _SHA256.fullmatch(item["sha256"])
                    or type(item.get("bytes")) is not int or item["bytes"] <= 0
                    or (item["kind"] == "resource" and (
                        not _RESOURCE_ID.fullmatch(item["id"]) or item["content_type"] != "application/json"
                        or item["bytes"] > 10 * 1024 * 1024))
                    or (item["kind"] == "blob" and (
                        not _BLOB_ID.fullmatch(item["id"]) or item["content_type"] not in _BLOB_TYPES
                        or item["bytes"] > 5 * 1024 * 1024
                        or not _blob_id_matches_digest(item["id"], item["sha256"])))
                    or (item["kind"], item["id"]) in seen):
                return False
            seen.add((item["kind"], item["id"]))
            total += item["bytes"]
        artifacts_etag = hashlib.sha256(_canonical(value["artifacts"])).hexdigest()
        identity = {"note_key": value["note_key"], "note_sha256": value["note_sha256"],
                    "artifacts": value["artifacts"]}
        derived_id = hashlib.sha256(_canonical(identity)).hexdigest()
        return (total <= 64 * 1024 * 1024 and artifacts_etag == value["artifact_set_etag"]
                and derived_id == snapshot_id)

    def _read_manifest(self, snapshots_fd, snapshot_id):
        raw = self._read_small(snapshots_fd, f"{snapshot_id}.json", MAX_SNAPSHOT_MANIFEST_BYTES)
        if raw is None:
            raise HTTPException(status_code=404, detail="BlockSuite recovery point not found")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="BlockSuite recovery point is corrupt") from exc
        if not self._validate_manifest(value, snapshot_id) or _canonical(value) != raw:
            raise HTTPException(status_code=503, detail="BlockSuite recovery point is unsafe")
        return value

    def _list_local(self, snapshots_fd, *, complete_only=True):
        if snapshots_fd is None:
            return []
        entries = []
        try:
            names = os.listdir(snapshots_fd)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite recovery points are unavailable") from exc
        for name in names:
            if name == "restore.json":
                self._read_restore_journal(snapshots_fd)
                continue
            if not re.fullmatch(r"[0-9a-f]{64}\.json", name):
                raise HTTPException(status_code=503, detail="BlockSuite snapshot directory has an unknown entry")
            manifest = self._read_manifest(snapshots_fd, name[:-5])
            if manifest["state"] == "complete" or not complete_only:
                entries.append(manifest)
        return sorted(entries, key=lambda item: (item["created_at"], item["snapshot_id"]))

    def _read_restore_journal(self, snapshots_fd):
        raw = self._read_small(snapshots_fd, "restore.json", 128 * 1024)
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="BlockSuite restore journal is corrupt") from exc
        required = {"schema", "snapshot_id", "source_note_etag", "source_artifact_set_etag",
                    "target_note_sha256", "target_artifact_set_etag", "source_artifacts", "state"}
        if (not isinstance(value, dict) or set(value) != required or value.get("schema") != 1
                or not _SNAPSHOT_ID.fullmatch(str(value.get("snapshot_id", "")))
                or not _SHA256.fullmatch(str(value.get("source_note_etag", "")))
                or not _SHA256.fullmatch(str(value.get("source_artifact_set_etag", "")))
                or not _SHA256.fullmatch(str(value.get("target_note_sha256", "")))
                or not _SHA256.fullmatch(str(value.get("target_artifact_set_etag", "")))
                or value.get("state") not in {"writing", "complete"}
                or not isinstance(value.get("source_artifacts"), list)
                or len(value["source_artifacts"]) > 64 or _canonical(value) != raw):
            raise HTTPException(status_code=503, detail="BlockSuite restore journal is unsafe")
        seen = set()
        for item in value["source_artifacts"]:
            if (not isinstance(item, dict) or set(item) != {"kind", "id", "sha256", "bytes", "content_type"}
                    or item.get("kind") not in {"resource", "blob"}
                    or not _SHA256.fullmatch(str(item.get("sha256", "")))
                    or type(item.get("bytes")) is not int or item["bytes"] <= 0
                    or (item["kind"] == "resource" and (
                        not _RESOURCE_ID.fullmatch(str(item.get("id", "")))
                        or item["content_type"] != "application/json" or item["bytes"] > 10 * 1024 * 1024))
                    or (item["kind"] == "blob" and (
                        not _BLOB_ID.fullmatch(str(item.get("id", "")))
                        or item["content_type"] not in _BLOB_TYPES or item["bytes"] > 5 * 1024 * 1024
                        or not _blob_id_matches_digest(item["id"], item["sha256"])))
                    or (item["kind"], item["id"]) in seen):
                raise HTTPException(status_code=503, detail="BlockSuite restore journal is unsafe")
            seen.add((item["kind"], item["id"]))
        source_inventory = list(value["source_artifacts"])
        source_inventory.sort(key=lambda item: (item["kind"], item["id"]))
        source_etag = hashlib.sha256(_canonical(source_inventory)).hexdigest()
        if source_etag != value["source_artifact_set_etag"]:
            raise HTTPException(status_code=503, detail="BlockSuite restore journal artifact set is invalid")
        return value

    def write_restore_journal(self, snapshots_fd, value):
        raw = _canonical(value)
        self._atomic_write(snapshots_fd, "restore.json", raw)

    def snapshot_locked(self, collection, relative, directory_fd, note_content, artifacts, *, preserve_ids=()):
        """Persist the current Markdown plus all validated BlockSuite resources before a mutation."""
        note_bytes = note_content.encode("utf-8")
        note_sha = hashlib.sha256(note_bytes).hexdigest()
        note_key = hashlib.sha256(f"{collection}\0{relative}".encode("utf-8")).hexdigest()
        artifact_rows = [{"kind": item["kind"], "id": item["id"], "sha256": item["sha256"],
                          "bytes": len(item["data"]), "content_type": item["content_type"]}
                         for item in artifacts]
        artifact_rows.sort(key=lambda item: (item["kind"], item["id"]))
        artifact_set_etag = hashlib.sha256(_canonical(artifact_rows)).hexdigest()
        identity = {"note_key": note_key, "note_sha256": note_sha, "artifacts": artifact_rows}
        snapshot_id = hashlib.sha256(_canonical(identity)).hexdigest()
        snapshots_fd = self._open_snapshot_directory(directory_fd, collection, relative, create=True)
        try:
            with self._global(create=True) as global_fds:
                objects_fd = global_fds["objects_fd"]
                self._cleanup_temps(snapshots_fd)
                current = self._list_local(snapshots_fd, complete_only=False)
                all_manifests = self._scan_authorized_manifests()
                global_rows = self._manifest_references(all_manifests)
                for existing in current:
                    if existing["snapshot_id"] == snapshot_id and existing["state"] == "complete":
                        local_complete = self._list_local(snapshots_fd)
                        prior_rows = [item for item in local_complete if item["snapshot_id"] != snapshot_id]
                        retained = self._retained_prior_rows(prior_rows, preserve_ids)
                        for row in [*retained, existing]:
                            self._verify_manifest_objects(objects_fd, row)
                        self._garbage_collect_unreferenced(objects_fd, enforce_cap=False)
                        self._prune_local(snapshots_fd, existing, preserve_ids=preserve_ids)
                        self._garbage_collect_unreferenced(objects_fd)
                        self._rebuild_index(global_fds)
                        return self._summary(existing)
                prior_rows = [item for item in self._list_local(snapshots_fd) if item["snapshot_id"] != snapshot_id]
                preserve_ids = set(preserve_ids)
                retained_rows = self._retained_prior_rows(prior_rows, preserve_ids)
                retained_ids = {item["snapshot_id"] for item in retained_rows}
                for retained in retained_rows:
                    self._verify_manifest_objects(objects_fd, retained)
                note_history_bytes = self._unique_bytes([*retained_rows, {"artifacts": artifact_rows,
                                                                         "note_sha256": note_sha,
                                                                         "note_bytes": len(note_bytes)}])
                if note_history_bytes > MAX_NOTE_HISTORY_BYTES:
                    raise HTTPException(status_code=507, detail="Per-note BlockSuite history capacity is exhausted")

                incoming = {note_sha: note_bytes}
                for artifact, row in zip(sorted(artifacts, key=lambda item: (item["kind"], item["id"])), artifact_rows):
                    if hashlib.sha256(artifact["data"]).hexdigest() != row["sha256"]:
                        raise HTTPException(status_code=409, detail="BlockSuite artifact changed before snapshot")
                    incoming[row["sha256"]] = artifact["data"]
                objects, _object_bytes = self._scan_objects(objects_fd)
                pruned_ids = {item["snapshot_id"] for item in prior_rows} - retained_ids
                projected_rows = {}
                for row in all_manifests:
                    if row["snapshot_id"] in pruned_ids:
                        continue
                    for digest, size in [(row["note_sha256"], row["note_bytes"]),
                                         *((item["sha256"], item["bytes"]) for item in row["artifacts"])]:
                        existing_size = projected_rows.setdefault(digest, size)
                        if existing_size != size:
                            raise HTTPException(status_code=507, detail="BlockSuite manifests disagree on content size")
                for digest, data in incoming.items():
                    if digest in global_rows:
                        if global_rows[digest] != len(data):
                            raise HTTPException(status_code=507, detail="BlockSuite manifests disagree on content size")
                    if digest in objects:
                        if self._read_object(objects_fd, digest, len(data)) != data:
                            raise HTTPException(status_code=503, detail="BlockSuite history object failed dedup verification")
                    projected_rows[digest] = len(data)
                if sum(projected_rows.values()) > MAX_GLOBAL_HISTORY_BYTES:
                    raise HTTPException(status_code=507, detail="Global BlockSuite history capacity is exhausted")

                manifest = {"schema": 1, "snapshot_id": snapshot_id, "note_key": note_key,
                            "note_sha256": note_sha, "note_bytes": len(note_bytes),
                            "artifact_set_etag": artifact_set_etag, "created_at": _now(),
                            "state": "pending", "artifacts": artifact_rows}
                manifest_name = f"{snapshot_id}.json"
                pending_raw = _canonical(manifest)
                existing_raw = self._read_small(snapshots_fd, manifest_name, MAX_SNAPSHOT_MANIFEST_BYTES)
                if existing_raw is None:
                    self._atomic_write(snapshots_fd, manifest_name, pending_raw, exclusive=True)
                else:
                    existing_manifest = self._read_manifest(snapshots_fd, snapshot_id)
                    immutable = ("schema", "snapshot_id", "note_key", "note_sha256", "note_bytes",
                                 "artifact_set_etag", "artifacts")
                    if (any(existing_manifest[key] != manifest[key] for key in immutable)
                            or existing_manifest["state"] != "pending"):
                        raise HTTPException(status_code=409, detail="BlockSuite recovery point id conflicts")
                    manifest = existing_manifest
                for digest, data in incoming.items():
                    self._write_object(objects_fd, digest, data)
                    if self._read_object(objects_fd, digest, len(data)) != data:
                        raise HTTPException(status_code=503, detail="BlockSuite history object failed verification")
                manifest["state"] = "complete"
                self._atomic_write(snapshots_fd, manifest_name, _canonical(manifest))
                os.fsync(snapshots_fd)
                # Validate the entire authorized history/object graph while old
                # manifests still protect every prior recovery point.
                self._garbage_collect_unreferenced(objects_fd, enforce_cap=False)
                self._prune_local(snapshots_fd, manifest, preserve_ids=preserve_ids)
                self._garbage_collect_unreferenced(objects_fd)
                self._rebuild_index(global_fds)
                return self._summary(manifest)
        finally:
            os.close(snapshots_fd)

    @staticmethod
    def _unique_bytes(rows):
        seen = {}
        for row in rows:
            seen[row["note_sha256"]] = row["note_bytes"]
            for artifact in row["artifacts"]:
                seen[artifact["sha256"]] = artifact["bytes"]
        return sum(seen.values())

    @staticmethod
    def _summary(manifest):
        return {"snapshot_id": manifest["snapshot_id"], "note_sha256": manifest["note_sha256"],
                "artifact_set_etag": manifest["artifact_set_etag"], "created_at": manifest["created_at"],
                "artifact_count": len(manifest["artifacts"]),
                "artifact_bytes": sum(item["bytes"] for item in manifest["artifacts"])}

    def _prune_local(self, snapshots_fd, current_manifest, *, preserve_ids=()):
        complete = self._list_local(snapshots_fd)
        ordered = [item["snapshot_id"] for item in complete]
        keep_ids = set(ordered[-MAX_NOTE_SNAPSHOTS:])
        keep_ids.add(current_manifest["snapshot_id"])
        keep_ids.update(preserve_ids)
        protected = set(preserve_ids) | {current_manifest["snapshot_id"]}
        if len(keep_ids) > MAX_NOTE_SNAPSHOTS:
            for snapshot_id in ordered:
                if snapshot_id in keep_ids and snapshot_id not in protected:
                    keep_ids.remove(snapshot_id)
                    if len(keep_ids) <= MAX_NOTE_SNAPSHOTS:
                        break
        for item in complete:
            if item["snapshot_id"] not in keep_ids:
                os.unlink(f"{item['snapshot_id']}.json", dir_fd=snapshots_fd)
        os.fsync(snapshots_fd)

    def list_snapshots_locked(self, collection, relative, directory_fd):
        snapshots_fd = self._open_snapshot_directory(directory_fd, collection, relative)
        if snapshots_fd is None:
            return []
        try:
            with self._global(create=False, exclusive=False) as global_fds:
                if global_fds is None or global_fds["objects_fd"] is None:
                    return []
                rows = self._list_local(snapshots_fd)
                for row in rows:
                    self._verify_manifest_objects(global_fds["objects_fd"], row)
                return [self._summary(row) for row in rows[-MAX_NOTE_SNAPSHOTS:]]
        finally:
            os.close(snapshots_fd)

    def _verify_manifest_objects(self, objects_fd, manifest):
        self._read_object(objects_fd, manifest["note_sha256"], manifest["note_bytes"])
        for artifact in manifest["artifacts"]:
            self._read_object(objects_fd, artifact["sha256"], artifact["bytes"])

    def read_snapshot_locked(self, collection, relative, directory_fd, snapshot_id):
        if not _SNAPSHOT_ID.fullmatch(snapshot_id or ""):
            raise HTTPException(status_code=404, detail="BlockSuite recovery point not found")
        snapshots_fd = self._open_snapshot_directory(directory_fd, collection, relative)
        if snapshots_fd is None:
            raise HTTPException(status_code=404, detail="BlockSuite recovery point not found")
        try:
            manifest = self._read_manifest(snapshots_fd, snapshot_id)
            if manifest["state"] != "complete":
                raise HTTPException(status_code=409, detail="BlockSuite recovery point is incomplete")
            with self._global(create=False, exclusive=False) as global_fds:
                if global_fds is None or global_fds["objects_fd"] is None:
                    raise HTTPException(status_code=503, detail="BlockSuite recovery objects are unavailable")
                note_bytes = self._read_object(global_fds["objects_fd"], manifest["note_sha256"],
                                               manifest["note_bytes"])
                artifacts = {item["id"]: self._read_object(global_fds["objects_fd"], item["sha256"],
                                                            item["bytes"])
                             for item in manifest["artifacts"]}
                return manifest, note_bytes, artifacts
        finally:
            os.close(snapshots_fd)

    def _rebuild_index(self, global_fds):
        # The index is a cache derived from strict snapshot manifests and verified
        # objects; it is never trusted to authorize deletion or restore.
        objects, total = self._scan_objects(global_fds["objects_fd"])
        index = {"schema": 1, "object_count": len(objects), "object_bytes": total,
                 "objects": dict(sorted(objects.items()))}
        self._atomic_write(global_fds["root_fd"], "index.json", _canonical(index))
