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


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_TITLE_BYTES = 4096


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
        self.path = path / "tasks.json"
        self.lock_path = path / ".tasks.lock"

    def _lock(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise HTTPException(status_code=500, detail="Task lock file is not private")
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _read_unlocked(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {"tasks": [], "idempotency": {}}
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Task data file could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=500, detail="Task data file is not private")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                data = json.load(stream)
            if not isinstance(data, dict) or not isinstance(data.get("tasks"), list) or not isinstance(data.get("idempotency"), dict):
                raise ValueError("invalid Task store")
            return data
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Task data is invalid") from exc
        finally:
            os.close(fd)

    def _write_unlocked(self, data):
        temporary = self.root / f".tasks-{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(fd)
            os.replace(temporary, self.path)
            root_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(root_fd)
            finally:
                os.close(root_fd)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(status_code=500, detail="Task update failed safely") from exc
        finally:
            os.close(fd)

    def _with_lock(self, operation):
        fd = self._lock()
        try:
            data = self._read_unlocked()
            result, changed = operation(data)
            if changed:
                self._write_unlocked(data)
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

    def create(self, title, due_date, idempotency_key, original_command=""):
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
                if prior["fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used with different Task content")
                task = next((item for item in data["tasks"] if item["id"] == prior["task_id"]), None)
                if task is None:
                    raise HTTPException(status_code=500, detail="Task idempotency record is inconsistent")
                return {"status": "duplicate", "task": task}, False
            stamp = _now()
            task = {"id": uuid.uuid4().hex, "title": title.strip(), "due_date": due_date,
                    "status": "open", "created_at": stamp, "updated_at": stamp,
                    "source": "web_app_explicit_task", "original_command": original_command,
                    "history": [{"at": stamp, "event": "created", "changes": {"title": title.strip(), "due_date": due_date, "status": "open"}}]}
            data["tasks"].append(task)
            data["idempotency"][key_hash] = {"fingerprint": fingerprint, "task_id": task["id"]}
            return {"status": "created", "task": task}, True

        return self._with_lock(operation)

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

    def update(self, task_id, body):
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

        def operation(data):
            task = next((item for item in data["tasks"] if item["id"] == task_id), None)
            if task is None:
                raise HTTPException(status_code=404, detail="Task not found")
            if task["updated_at"] != expected:
                raise HTTPException(status_code=409, detail="Task changed since it was loaded; reload before editing")
            previous = {key: task.get(key) for key in changes}
            task.update(changes)
            stamp = _now()
            prior_stamp = datetime.fromisoformat(task["updated_at"])
            if datetime.fromisoformat(stamp) <= prior_stamp:
                stamp = (prior_stamp + timedelta(microseconds=1)).isoformat()
            task["updated_at"] = stamp
            task.setdefault("history", []).append({"at": stamp, "event": "updated", "changes": {
                key: {"from": previous[key], "to": task[key]} for key in changes if previous[key] != task[key]
            }})
            return {"task": task}, True

        return self._with_lock(operation)


def create_task_router(auth, store):
    router = APIRouter(prefix="/api/tasks")

    def configured():
        if store is None:
            raise HTTPException(status_code=503, detail="Task is not enabled")

    @router.get("")
    def list_tasks(request: Request, status: str = "open", due_date: str | None = None):
        auth.require_action(request, "task.read")
        configured()
        return store.list(status, due_date)

    @router.post("")
    def create_task(request: Request, body: dict):
        auth.require_action(request, "task.write")
        configured()
        return store.create(body.get("title"), body.get("due_date"),
                            request.headers.get("idempotency-key", ""), body.get("original_command", ""))

    @router.patch("/{task_id}")
    def update_task(request: Request, task_id: str, body: dict):
        auth.require_action(request, "task.write")
        configured()
        if not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        return store.update(task_id, body)

    return router
