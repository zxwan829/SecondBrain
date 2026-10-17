"""Recoverable, private projections of explicit Journal and Task Chat operations."""
import fcntl
import json
import os
import stat
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request


class ChatActivityStore:
    """Store a repairable activity projection under the private Core state root.

    Journal and Task records remain authoritative: they commit the session and
    operation references in the same transaction as the business write. This
    file is rebuilt from those references on reads, so a crash between the
    business commit and projection update cannot lose a successful activity.
    """

    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("Chat activity root must be absolute")
        try:
            os.mkdir(self.root, 0o700)
        except FileExistsError:
            pass
        info = self.root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or not os.access(self.root, os.W_OK)):
            raise ValueError("Chat activity root must be a private writable directory owned by the Core UID")
        self.path = self.root / "activities.json"
        self.lock_path = self.root / ".activities.lock"

    def _lock(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise HTTPException(status_code=500, detail="Chat activity lock is not private")
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _read_unlocked(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Chat activity data could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=500, detail="Chat activity data is not private")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                rows = json.load(stream)
            if not isinstance(rows, dict) or not all(isinstance(key, str) and isinstance(value, dict)
                                                     for key, value in rows.items()):
                raise ValueError("invalid activity data")
            return rows
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Chat activity data is invalid") from exc
        finally:
            os.close(fd)

    def _write_unlocked(self, rows):
        temporary = self.root / f".activities-{uuid.uuid4().hex}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                json.dump(rows, stream, ensure_ascii=False, separators=(",", ":"))
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
            raise HTTPException(status_code=500, detail="Chat activity update failed safely") from exc
        finally:
            os.close(fd)

    def upsert(self, event):
        required = ("event_id", "operation_id", "session_id", "kind", "original_text", "status", "occurred_at")
        if not isinstance(event, dict) or any(not isinstance(event.get(key), str) or not event[key] for key in required):
            raise HTTPException(status_code=400, detail="Chat activity record is invalid")
        if event["status"] not in {"succeeded", "failed"} or event["kind"] not in {"journal", "task"}:
            raise HTTPException(status_code=400, detail="Chat activity state is invalid")
        fd = self._lock()
        try:
            rows = self._read_unlocked()
            prior = rows.get(event["event_id"])
            if prior:
                if any(prior.get(key) != event[key] for key in ("operation_id", "session_id", "kind", "original_text")):
                    raise HTTPException(status_code=409, detail="Chat activity operation reference conflicts")
                # A durable business record is authoritative over a previously
                # recorded validation failure. Never downgrade a success.
                if prior.get("status") == "succeeded" and event["status"] == "failed":
                    return prior
                if prior.get("status") == "failed" and event["status"] == "succeeded":
                    event = {**event, "occurred_at": prior.get("occurred_at", event["occurred_at"])}
            rows[event["event_id"]] = dict(event)
            self._write_unlocked(rows)
            return rows[event["event_id"]]
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def for_session(self, session_id):
        fd = self._lock()
        try:
            rows = self._read_unlocked()
            return [row for row in rows.values() if row.get("session_id") == session_id]
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def journal_activity(record, session_id):
    operation_id = record.get("operation_id")
    if not session_id or not operation_id:
        return None
    return {
        "event_id": f"journal:{operation_id}", "operation_id": operation_id,
        "session_id": session_id, "kind": "journal", "status": "succeeded",
        "original_text": record["original_text"], "occurred_at": record["created_at"],
        "journal_date": record.get("date"),
    }


def task_activity(task, session_id, status="succeeded", detail=None):
    operation_id = task.get("operation_id")
    if not session_id or not operation_id:
        return None
    event = {
        "event_id": f"task:{operation_id}", "operation_id": operation_id,
        "session_id": session_id, "kind": "task", "status": status,
        "original_text": task.get("original_command", ""),
        "occurred_at": task.get("created_at", ""),
        "task_id": task.get("id"), "task_title": task.get("title"),
        "task_due_date": task.get("due_date"), "task_status": task.get("status"),
    }
    if detail:
        event["detail"] = detail
    return event


def create_chat_activity_router(auth, hermes, activity_store, journal_store, task_store):
    router = APIRouter(prefix="/api/chat/sessions")

    @router.get("/{session_id}/activities")
    async def list_session_activities(request: Request, session_id: str):
        auth.require_action(request, "chat.read")
        # A caller cannot enumerate arbitrary activity by supplying an unknown
        # Session ID. Hermes is the source of truth for existence/deletion.
        await hermes.get_session(session_id)
        source_events = []
        if journal_store is not None:
            source_events.extend(journal_store.session_activities(session_id))
        if task_store is not None:
            source_events.extend(task_store.session_activities(session_id))
        try:
            for event in source_events:
                activity_store.upsert(event)
            persisted = activity_store.for_session(session_id)
        except HTTPException:
            # Domain records contain the operation reference in the same
            # atomic write as the business action. They remain a safe recovery
            # source if the projection file is temporarily unavailable.
            persisted = []
        by_id = {event["event_id"]: event for event in persisted}
        for event in source_events:
            by_id[event["event_id"]] = event
        return {"session_id": session_id, "activities": sorted(
            by_id.values(), key=lambda event: (event.get("occurred_at", ""), event["event_id"]))}

    return router
