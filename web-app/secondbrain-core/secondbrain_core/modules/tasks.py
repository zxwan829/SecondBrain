"""Private, durable Task CRUD exposed only through authenticated App APIs."""
import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

from .chat_activity import task_activity


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_TITLE_BYTES = 4096
_MAX_PROJECTION_BYTES = 2 * 1024 * 1024
_MAX_TASK_UPDATE_IDEMPOTENCY_KEYS = 4096
_TASK_SOURCE_VERSION_FIELDS = ("id", "title", "due_date", "status", "created_at", "updated_at", "source")


def task_source_version(task):
    """Hash the stable, public Task projection used by trusted source refs.

    Private command/session/history/idempotency details are deliberately not
    included. Server-issued updated_at changes on every supported edit.
    """
    if not isinstance(task, dict) or any(key not in task for key in _TASK_SOURCE_VERSION_FIELDS):
        return None
    if (not isinstance(task["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", task["id"])
            or not isinstance(task["title"], str) or not task["title"].strip()
            or len(task["title"].encode("utf-8")) > _MAX_TITLE_BYTES
            or not isinstance(task["status"], str) or task["status"] not in {"open", "completed"}
            or task["source"] != "web_app_explicit_task"):
        return None
    due_date = task["due_date"]
    if due_date is not None:
        try:
            if not isinstance(due_date, str) or date.fromisoformat(due_date).isoformat() != due_date:
                return None
        except ValueError:
            return None
    for field in ("created_at", "updated_at"):
        try:
            stamp = datetime.fromisoformat(task[field].replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            return None
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
    canonical = {key: task[key] for key in _TASK_SOURCE_VERSION_FIELDS}
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _valid_date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise HTTPException(status_code=400, detail="due_date must use YYYY-MM-DD or null")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="due_date is invalid") from exc
    return value


class TaskStore:
    """Small JSON store guarded by flock and atomic replacement under one private root."""

    def __init__(self, root):
        path = Path(root)
        if not path.is_absolute():
            raise ValueError("Task root must be absolute")
        try:
            info = path.lstat()
        except OSError as exc:
            raise ValueError("Task root must already exist") from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or not os.access(path, os.W_OK)):
            raise ValueError("Task root must be a private writable directory owned by the Core UID")
        self.root = path
        self.root_identity = (info.st_dev, info.st_ino)
        self.path = path / "tasks.json"
        self.lock_path = path / ".tasks.lock"

    def _open_root(self):
        try:
            fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Task storage is unavailable") from exc
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
                or (info.st_dev, info.st_ino) != self.root_identity):
            os.close(fd)
            raise HTTPException(status_code=503, detail="Task storage is unavailable")
        return fd

    def _lock(self):
        root_fd = self._open_root()
        try:
            try:
                fd = os.open(self.lock_path.name, os.O_CREAT | os.O_EXCL | os.O_RDWR
                             | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            except FileExistsError:
                fd = os.open(self.lock_path.name, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                             dir_fd=root_fd)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Task lock file could not be opened safely") from exc
        finally:
            os.close(root_fd)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            os.close(fd)
            raise HTTPException(status_code=500, detail="Task lock file is not private")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as exc:
            os.close(fd)
            raise HTTPException(status_code=500, detail="Task lock could not be acquired safely") from exc
        return fd

    def _read_unlocked(self, max_bytes=None):
        root_fd = self._open_root()
        fd = None
        try:
            try:
                fd = os.open(self.path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0), dir_fd=root_fd)
            except FileNotFoundError:
                return {"tasks": [], "idempotency": {}}
            except OSError as exc:
                raise HTTPException(status_code=500, detail="Task data file could not be opened safely") from exc
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise HTTPException(status_code=500, detail="Task data file is not private")
            if max_bytes is not None and info.st_size > max_bytes:
                raise HTTPException(status_code=503, detail="Task projection exceeds read budget")
            read_limit = max_bytes if max_bytes is not None else info.st_size
            chunks, total = [], 0
            while True:
                chunk = os.read(fd, min(65536, read_limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > read_limit:
                    if max_bytes is not None:
                        raise HTTPException(status_code=503, detail="Task projection exceeds read budget")
                    raise HTTPException(status_code=503, detail="Task data changed while being read")
            if total != info.st_size:
                raise HTTPException(status_code=503, detail="Task data changed while being read")
            try:
                data = json.loads(b"".join(chunks).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
                raise HTTPException(status_code=500, detail="Task data is invalid") from exc
            if not isinstance(data, dict) or not isinstance(data.get("tasks"), list) or not isinstance(data.get("idempotency"), dict):
                raise ValueError("invalid Task store")
            return data
        except HTTPException:
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Task data is invalid") from exc
        finally:
            if fd is not None:
                os.close(fd)
            os.close(root_fd)

    def _restore_unlocked(self, root_fd, data):
        """Restore the pre-commit snapshot in the already-pinned Task root."""
        temporary = f".tasks-restore-{uuid.uuid4().hex}.tmp"
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(fd)
            os.replace(temporary, self.path.name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=root_fd)
            except FileNotFoundError:
                pass

    def _write_unlocked(self, data, rollback):
        temporary = f".tasks-{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        root_fd = self._open_root()
        fd = None
        committed = False
        try:
            fd = os.open(temporary, flags, 0o600, dir_fd=root_fd)
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(fd)
            check_fd = self._open_root()
            os.close(check_fd)
            os.replace(temporary, self.path.name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            committed = True
            os.fsync(root_fd)
            # The pinned FD can now refer to a displaced directory. If the
            # configured path changed during the replace, roll back there before
            # reporting failure so the replacement root never misses a success.
            check_fd = self._open_root()
            os.close(check_fd)
        except HTTPException as exc:
            if committed:
                try:
                    rollback()
                    self._restore_unlocked(root_fd, data)
                except OSError as rollback_exc:
                    raise HTTPException(
                        status_code=503,
                        detail="Task write outcome requires recovery; restore the initialized Task root and retry",
                    ) from rollback_exc
                raise HTTPException(status_code=503, detail="Task write was rolled back because storage changed") from exc
            try:
                os.unlink(temporary, dir_fd=root_fd)
            except OSError:
                pass
            raise
        except OSError as exc:
            if committed:
                try:
                    rollback()
                    self._restore_unlocked(root_fd, data)
                except OSError as rollback_exc:
                    raise HTTPException(
                        status_code=503,
                        detail="Task write outcome requires recovery; reload Task state before retrying",
                    ) from rollback_exc
                raise HTTPException(status_code=503, detail="Task write was rolled back after storage sync failure") from exc
            try:
                os.unlink(temporary, dir_fd=root_fd)
            except OSError:
                pass
            raise HTTPException(status_code=500, detail="Task update failed safely") from exc
        finally:
            if fd is not None:
                os.close(fd)
            os.close(root_fd)

    def _with_lock(self, operation):
        fd = self._lock()
        try:
            data = self._read_unlocked()
            outcome = operation(data)
            result, changed = outcome[:2]
            rollback = outcome[2] if len(outcome) == 3 else None
            if changed:
                if rollback is None:
                    raise RuntimeError("Task mutation must define rollback state")
                self._write_unlocked(data, rollback)
            return result
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _key_hash(key):
        if (not isinstance(key, str) or not 1 <= len(key) <= 255
                or any(ord(char) < 33 or ord(char) > 126 for char in key)):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        return hashlib.sha256(key.encode("ascii")).hexdigest()

    def create(self, title, due_date, idempotency_key, original_command="", session_id=None):
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(status_code=400, detail="Task title is required")
        if len(title.encode("utf-8")) > _MAX_TITLE_BYTES:
            raise HTTPException(status_code=413, detail="Task title is too long")
        due_date = _valid_date(due_date)
        if not isinstance(original_command, str) or len(original_command.encode("utf-8")) > 16_384:
            raise HTTPException(status_code=400, detail="Original command is invalid")
        key_hash = self._key_hash(idempotency_key)
        fingerprint = hashlib.sha256(json.dumps({"title": title, "due_date": due_date,
                                                "original_command": original_command}, sort_keys=True,
                                               ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

        def operation(data):
            prior = data["idempotency"].get(key_hash)
            if prior:
                if (prior.get("operation") not in {None, "task.create"}
                        or prior["fingerprint"] != fingerprint):
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used with different Task content")
                task = next((item for item in data["tasks"] if item["id"] == prior["task_id"]), None)
                if task is None:
                    raise HTTPException(status_code=500, detail="Task idempotency record is inconsistent")
                if task.get("session_id") != session_id:
                    raise HTTPException(status_code=409, detail="Idempotency-Key belongs to a different Chat Session")
                return {"status": "duplicate", "task": task}, False
            stamp = _now()
            task = {"id": uuid.uuid4().hex, "title": title.strip(), "due_date": due_date,
                    "status": "open", "created_at": stamp, "updated_at": stamp,
                    "source": "web_app_explicit_task", "original_command": original_command,
                    "operation_id": idempotency_key, "session_id": session_id,
                    "history": [{"at": stamp, "event": "created", "changes": {"title": title.strip(), "due_date": due_date, "status": "open"}}]}
            data["tasks"].append(task)
            data["idempotency"][key_hash] = {
                "operation": "task.create", "fingerprint": fingerprint, "task_id": task["id"],
            }
            def rollback():
                data["tasks"].remove(task)
                data["idempotency"].pop(key_hash, None)
            return {"status": "created", "task": task}, True, rollback

        return self._with_lock(operation)

    def session_activities(self, session_id):
        def operation(data):
            items = [task_activity(task, session_id) for task in data["tasks"]
                     if task.get("session_id") == session_id and task.get("operation_id")]
            return [item for item in items if item], False
        return self._with_lock(operation)

    def list_for_projection(self):
        """Read metadata for Core read projections only within a fixed byte budget."""
        fd = self._lock()
        try:
            data = self._read_unlocked(max_bytes=_MAX_PROJECTION_BYTES)
            items = list(data["tasks"])
            items.sort(key=lambda item: (item.get("due_date") or "9999-12-31",
                                         item.get("created_at", ""), item.get("id", "")))
            return {"tasks": items}
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def list_for_projection_read_only(self):
        """Read a stable projection without creating or opening the Task lock file."""
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {"tasks": []}
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Task projection unavailable") from exc
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_mode & 0o077 or before.st_size < 0
                    or before.st_size > _MAX_PROJECTION_BYTES):
                raise HTTPException(status_code=503, detail="Task projection unavailable")
            payload = bytearray()
            while len(payload) <= _MAX_PROJECTION_BYTES:
                chunk = os.read(fd, min(65536, _MAX_PROJECTION_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            after = os.fstat(fd)
            try:
                current = os.stat(self.path, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Task projection unavailable") from exc
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                     info.st_mtime_ns, info.st_ctime_ns)
            if (len(payload) != before.st_size or len(payload) > _MAX_PROJECTION_BYTES
                    or identity(after) != identity(before) or identity(current) != identity(before)):
                raise HTTPException(status_code=503, detail="Task projection changed during read")
            try:
                data = json.loads(payload.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=503, detail="Task projection unavailable") from exc
            if (not isinstance(data, dict) or not isinstance(data.get("tasks"), list)
                    or not isinstance(data.get("idempotency"), dict)):
                raise HTTPException(status_code=503, detail="Task projection unavailable")
            items = list(data["tasks"])
            items.sort(key=lambda item: (item.get("due_date") or "9999-12-31",
                                         item.get("created_at", ""), item.get("id", "")))
            return {"tasks": items}
        finally:
            os.close(fd)

    def list(self, status="open", due_date=None):
        if status not in {"open", "completed", "all"}:
            raise HTTPException(status_code=400, detail="status must be open, completed, or all")
        due_date = _valid_date(due_date)

        def operation(data):
            items = [item for item in data["tasks"]
                     if (status == "all" or item.get("status") == status)
                     and (due_date is None or item.get("due_date") == due_date)]
            items.sort(key=lambda item: (item.get("due_date") or "9999-12-31", item.get("created_at", ""), item.get("id", "")))
            return {"tasks": items}, False

        return self._with_lock(operation)

    def update(self, task_id, body, idempotency_key=None):
        if not isinstance(body, dict) or not body:
            raise HTTPException(status_code=400, detail="Task changes are required")
        expected = body.get("expected_updated_at")
        if not isinstance(expected, str) or not expected:
            raise HTTPException(status_code=400, detail="expected_updated_at is required")
        changes = {key: body[key] for key in ("title", "due_date", "status") if key in body}
        if not changes:
            raise HTTPException(status_code=400, detail="No supported Task fields were provided")
        if "title" in changes:
            title = changes["title"]
            if not isinstance(title, str) or not title.strip():
                raise HTTPException(status_code=400, detail="Task title is required")
            if len(title.encode("utf-8")) > _MAX_TITLE_BYTES:
                raise HTTPException(status_code=413, detail="Task title is too long")
            changes["title"] = title.strip()
        if "due_date" in changes:
            changes["due_date"] = _valid_date(changes["due_date"])
        if "status" in changes and changes["status"] not in {"open", "completed"}:
            raise HTTPException(status_code=400, detail="Task status must be open or completed")
        key_hash = self._key_hash(idempotency_key) if idempotency_key is not None else None
        fingerprint = None
        if key_hash is not None:
            fingerprint = hashlib.sha256(json.dumps({
                "operation": "task.update", "task_id": task_id,
                "expected_updated_at": expected, "changes": changes,
            }, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

        def operation(data):
            if key_hash is not None:
                prior = data["idempotency"].get(key_hash)
                if prior is not None:
                    if (prior.get("operation") != "task.update"
                            or prior.get("fingerprint") != fingerprint
                            or prior.get("task_id") != task_id):
                        raise HTTPException(status_code=409, detail="Idempotency-Key was already used differently")
                    replay_task = next((item for item in data["tasks"] if item["id"] == task_id), None)
                    if (replay_task is None
                            or replay_task.get("updated_at") != prior.get("result_updated_at")):
                        raise HTTPException(status_code=409, detail="Task changed after the keyed update; reload before retrying")
                    return {"task": replay_task}, False

            task = next((item for item in data["tasks"] if item["id"] == task_id), None)
            if task is None:
                raise HTTPException(status_code=404, detail="Task not found")
            if task["updated_at"] != expected:
                raise HTTPException(status_code=409, detail="Task changed since it was loaded; reload before editing")
            if key_hash is not None:
                update_key_count = sum(
                    1 for item in data["idempotency"].values()
                    if isinstance(item, dict) and item.get("operation") == "task.update"
                )
                if update_key_count >= _MAX_TASK_UPDATE_IDEMPOTENCY_KEYS:
                    raise HTTPException(status_code=503, detail="Task retry ledger is full")
            previous = {key: task.get(key) for key in changes}
            previous_updated_at = task["updated_at"]
            previous_history_length = len(task.get("history", []))
            had_history = "history" in task
            task.update(changes)
            stamp = _now()
            prior_stamp = datetime.fromisoformat(task["updated_at"])
            if datetime.fromisoformat(stamp) <= prior_stamp:
                stamp = (prior_stamp + timedelta(microseconds=1)).isoformat()
            task["updated_at"] = stamp
            task.setdefault("history", []).append({"at": stamp, "event": "updated", "changes": {
                key: {"from": previous[key], "to": task[key]} for key in changes if previous[key] != task[key]
            }})
            if key_hash is not None:
                data["idempotency"][key_hash] = {
                    "operation": "task.update", "fingerprint": fingerprint,
                    "task_id": task_id, "result_updated_at": stamp,
                }
            previous_values = {key: previous[key] for key in changes}

            def rollback():
                task.update(previous_values)
                task["updated_at"] = previous_updated_at
                if had_history:
                    del task["history"][previous_history_length:]
                else:
                    task.pop("history", None)
                if key_hash is not None:
                    data["idempotency"].pop(key_hash, None)

            return {"task": task}, True, rollback

        return self._with_lock(operation)


def create_task_router(auth, store, hermes=None, activity_store=None):
    router = APIRouter(prefix="/api/tasks")

    def configured():
        if store is None:
            raise HTTPException(status_code=503, detail="Task is not enabled")

    @router.get("")
    def list_tasks(request: Request, status: str = "open", due_date: str | None = None):
        auth.require_action(request, "task.read")
        configured()
        result = store.list(status, due_date)
        for task in result["tasks"]:
            version = task_source_version(task)
            if version is not None:
                task["source_ref"] = {"id": task["id"], "version": version}
        return result

    @router.post("")
    async def create_task(request: Request, body: dict):
        auth.require_action(request, "task.write")
        configured()
        session_id = body.get("session_id")
        if session_id is not None:
            if not isinstance(session_id, str) or not session_id or hermes is None:
                raise HTTPException(status_code=400, detail="A valid Chat Session is required")
            await hermes.get_session(session_id)
        key = request.headers.get("idempotency-key", "")
        try:
            result = store.create(body.get("title"), body.get("due_date"), key,
                                  body.get("original_command", ""), session_id)
        except HTTPException as exc:
            command = body.get("original_command", "")
            if (session_id and activity_store is not None and exc.status_code in {400, 413}
                    and isinstance(command, str) and command and key and 1 <= len(key) <= 255):
                failed_task = {"operation_id": key, "original_command": command, "created_at": _now()}
                failed = task_activity(failed_task, session_id, status="failed", detail=exc.detail)
                # There is no Task row to repair a failed-create activity
                # from, so persist it before returning it to the caller.
                activity_store.upsert(failed)
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "activity": failed})
            raise
        event = task_activity(result["task"], session_id)
        if event and activity_store is not None:
            try:
                activity_store.upsert(event)
            except HTTPException:
                # The Task record owns the operation reference and repairs the
                # projection after a crash or temporary activity-root failure.
                pass
            result["activity"] = event
        return result

    @router.patch("/{task_id}")
    def update_task(request: Request, task_id: str, body: dict):
        auth.require_action(request, "task.write")
        configured()
        if not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        return store.update(task_id, body, idempotency_key=request.headers.get("idempotency-key"))

    return router
