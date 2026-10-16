"""Small, append-only and source-aware Personal Memory Core.

This module is deliberately independent of Hermes and formal Knowledge. The root is
injected by the caller and must already exist as a private directory (for example,
an isolated ``40-Memory`` test root); importing or constructing the app never guesses
or creates a production data location.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SAFE_REF = re.compile(r"^[A-Za-z0-9_.:/#@+ -]{1,512}$")
MAX_CONTENT_BYTES = 8_192
EVENTS_FILE = "personal-memory.jsonl"
LOCK_FILE = "personal-memory.lock"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


class MemoryStoreError(RuntimeError):
    pass


class PersonalMemoryStore:
    """Append-only JSONL event store; malformed data fails closed without repair."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._thread_lock = threading.RLock()
        self._validate_root()
        self.path = self.root / EVENTS_FILE
        self.lock_path = self.root / LOCK_FILE

    def _validate_root(self) -> None:
        try:
            info = os.stat(self.root, follow_symlinks=False)
            resolved = self.root.resolve(strict=True)
        except OSError as exc:
            raise MemoryStoreError("Personal memory root must already exist") from exc
        if (not stat.S_ISDIR(info.st_mode) or self.root.is_symlink() or resolved != self.root.absolute()
                or info.st_uid != os.geteuid() or info.st_mode & 0o077
                or not os.access(self.root, os.W_OK)):
            raise MemoryStoreError("Personal memory root must be a private writable directory owned by Core")

    def _open_lock(self) -> int:
        self._validate_root()
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as exc:
            raise MemoryStoreError("Personal memory lock is unavailable") from exc
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise MemoryStoreError("Personal memory lock must be a private regular file owned by Core")
        os.fchmod(fd, 0o600)
        return fd

    def _read_events_unlocked(self) -> list[dict[str, Any]]:
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise MemoryStoreError("Personal memory data file is unavailable") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise MemoryStoreError("Personal memory data must be a private regular file owned by Core")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read()
        finally:
            os.close(fd)
        events: list[dict[str, Any]] = []
        if not raw:
            return events
        if not raw.endswith(b"\n"):
            raise MemoryStoreError("Personal memory has an incomplete final record; manual recovery required")
        try:
            latest_revisions: dict[str, int] = {}
            event_ids: set[str] = set()
            for line in raw.splitlines():
                event = json.loads(line)
                required = {"schema", "event_id", "memory_id", "revision", "operation", "content",
                            "category", "fact_kind", "source_type", "source_ref", "recorded_at", "status"}
                if (not isinstance(event, dict) or not required.issubset(event)
                        or event.get("schema") != 1 or type(event.get("revision")) is not int
                        or event["revision"] < 1 or not SAFE_ID.fullmatch(event.get("memory_id", ""))
                        or event.get("operation") not in {"create", "correct", "revoked", "expired"}
                        or event.get("status") not in {"active", "pending_verification", "revoked", "expired"}
                        or event.get("category") not in {"preference", "experience", "project_context", "fact"}
                        or event.get("fact_kind") not in {"user_stated", "user_confirmed", "inference"}
                        or event.get("source_type") not in {"user_message", "user_confirmed", "original_file", "session_note"}
                        or not isinstance(event.get("source_ref"), str)
                        or not isinstance(event.get("event_id"), str)
                        or event.get("event_id") in event_ids or not isinstance(event.get("content"), dict)):
                    raise ValueError("invalid event")
                memory_id = event["memory_id"]
                previous_revision = latest_revisions.get(memory_id)
                if ((event["operation"] == "create" and (previous_revision is not None or event["revision"] != 1))
                        or (event["operation"] != "create" and
                            (previous_revision is None or event["revision"] != previous_revision + 1))):
                    raise ValueError("invalid revision sequence")
                event_ids.add(event["event_id"])
                latest_revisions[memory_id] = event["revision"]
                events.append(event)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise MemoryStoreError("Personal memory contains a malformed record; manual recovery required") from exc
        return events

    def _read_events(self) -> list[dict[str, Any]]:
        with self._thread_lock:
            fd = self._open_lock()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                return self._read_events_unlocked()
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._thread_lock:
            lock_fd = self._open_lock()
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                events = self._read_events_unlocked()
                key = event.get("idempotency_key")
                if key and (prior := next((row for row in events if row.get("idempotency_key") == key), None)):
                    if any(prior.get(name) != event.get(name)
                           for name in ("operation", "source_ref", "content", "category", "fact_kind")):
                        raise ValueError("Idempotency key was already used for a different memory")
                    return prior
                if event.get("operation") in {"correct", "revoked", "expired"}:
                    current = next((row for row in reversed(events)
                                    if row.get("memory_id") == event.get("memory_id")), None)
                    if (current is None or current.get("revision") != event.get("expected_revision")
                            or event.get("revision") != event.get("expected_revision") + 1):
                        raise ValueError("Memory changed concurrently; reload before retrying")
                stored_event = {name: value for name, value in event.items() if name != "expected_revision"}
                line = _json_bytes(stored_event) + b"\n"
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                                 getattr(os, "O_NOFOLLOW", 0), 0o600)
                except OSError as exc:
                    raise MemoryStoreError("Personal memory data file cannot be opened safely") from exc
                created = not events and os.fstat(fd).st_size == 0
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise MemoryStoreError("Personal memory data must be a private regular file owned by Core")
                    os.fchmod(fd, 0o600)
                    view = memoryview(line)
                    while view:
                        written = os.write(fd, view)
                        if written <= 0:
                            raise MemoryStoreError("Personal memory append made no progress")
                        view = view[written:]
                    os.fsync(fd)
                finally:
                    os.close(fd)
                if created:
                    dir_fd = os.open(self.root, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                return stored_event
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    @staticmethod
    def _validate_content(content: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(content, dict) or not content:
            raise ValueError("Memory content must be a non-empty object")
        try:
            encoded = _json_bytes(content)
        except (TypeError, ValueError) as exc:
            raise ValueError("Memory content must be JSON serializable") from exc
        if len(encoded) > MAX_CONTENT_BYTES:
            raise ValueError("Memory content exceeds the size limit")
        if not isinstance(content.get("text"), str) or not content["text"].strip():
            raise ValueError("Memory content requires non-empty text")
        return json.loads(encoded)

    @staticmethod
    def _validate_source(source_type: str, source_ref: str, exact: bool) -> None:
        if source_type not in {"user_message", "user_confirmed", "original_file", "session_note"}:
            raise ValueError("Unsupported memory source type")
        if not isinstance(source_ref, str) or not SAFE_REF.fullmatch(source_ref.strip()):
            raise ValueError("A valid source reference is required")
        normalized = source_ref.strip()
        if normalized.startswith(("/", "\\")) or "\\" in normalized or ".." in normalized.split("/"):
            raise ValueError("Source references cannot contain absolute or traversal paths")
        if exact and not source_ref.strip():
            raise ValueError("Exact facts require a source reference")

    def create(self, *, content: dict[str, Any], category: str, fact_kind: str,
               source_type: str, source_ref: str, exact: bool = False,
               expires_at: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        content = self._validate_content(content)
        self._validate_source(source_type, source_ref, exact)
        if category not in {"preference", "experience", "project_context", "fact"}:
            raise ValueError("Unsupported memory category")
        if fact_kind not in {"user_stated", "user_confirmed", "inference"}:
            raise ValueError("Unsupported memory fact kind")
        if fact_kind == "inference":
            status = "pending_verification"
        else:
            status = "active"
        if idempotency_key is not None and not SAFE_ID.fullmatch(idempotency_key):
            raise ValueError("Invalid idempotency key")
        if expires_at is not None:
            try:
                parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if parsed_expiry.tzinfo is None:
                    raise ValueError
            except (ValueError, AttributeError) as exc:
                raise ValueError("Expiry must be an ISO-8601 timestamp with timezone") from exc
        # A source message may yield multiple independent memory candidates. Derive
        # a stable key from each candidate's identity so replay is exactly-once per
        # fact, without treating the whole source message as a single memory.
        candidate_key = idempotency_key or "candidate-" + hashlib.sha256(_json_bytes({
            "source_type": source_type, "source_ref": source_ref.strip(), "content": content,
            "category": category, "fact_kind": fact_kind,
        })).hexdigest()
        event = {"schema": 1, "event_id": str(uuid.uuid4()), "memory_id": str(uuid.uuid4()),
                 "revision": 1, "operation": "create", "content": content, "category": category,
                 "fact_kind": fact_kind, "source_type": source_type, "source_ref": source_ref.strip(),
                 "exact": bool(exact),
                 "verification_status": "source_required" if exact or category == "fact" else "not_required",
                 "recorded_at": _now(), "status": status, "expires_at": expires_at,
                 "idempotency_key": candidate_key}
        return self._append(event)

    def _current(self, memory_id: str) -> dict[str, Any]:
        if not SAFE_ID.fullmatch(memory_id):
            raise ValueError("Invalid memory identifier")
        rows = self._read_events()
        item = None
        for row in rows:
            if row.get("memory_id") == memory_id:
                if item is not None and row.get("revision") != item.get("revision", 0) + 1:
                    raise MemoryStoreError("Personal memory revision sequence is invalid")
                item = row
        if item is None:
            raise KeyError(memory_id)
        return item

    def correct(self, memory_id: str, *, content: dict[str, Any], source_type: str,
                source_ref: str, fact_kind: str | None = None) -> dict[str, Any]:
        current = self._current(memory_id)
        if current["status"] in {"revoked", "expired", "superseded"}:
            raise ValueError("Inactive memories cannot be corrected")
        content = self._validate_content(content)
        self._validate_source(source_type, source_ref, current["exact"])
        if fact_kind is not None and fact_kind not in {"user_stated", "user_confirmed", "inference"}:
            raise ValueError("Unsupported memory fact kind")
        return self._append({**current, "event_id": str(uuid.uuid4()), "revision": current["revision"] + 1,
                             "expected_revision": current["revision"],
                             "operation": "correct", "content": content, "source_type": source_type,
                             "source_ref": source_ref.strip(), "recorded_at": _now(),
                             "fact_kind": fact_kind or current["fact_kind"], "status": "active",
                             "idempotency_key": None})

    def _change_status(self, memory_id: str, status: str, source_type: str, source_ref: str) -> dict[str, Any]:
        current = self._current(memory_id)
        if current["status"] in {"revoked", "expired", "superseded"}:
            raise ValueError("Memory is already inactive")
        self._validate_source(source_type, source_ref, False)
        return self._append({**current, "event_id": str(uuid.uuid4()), "revision": current["revision"] + 1,
                             "expected_revision": current["revision"],
                             "operation": status, "source_type": source_type, "source_ref": source_ref.strip(),
                             "recorded_at": _now(), "status": status, "idempotency_key": None})

    def revoke(self, memory_id: str, *, source_type: str, source_ref: str) -> dict[str, Any]:
        return self._change_status(memory_id, "revoked", source_type, source_ref)

    def expire(self, memory_id: str, *, source_type: str, source_ref: str) -> dict[str, Any]:
        return self._change_status(memory_id, "expired", source_type, source_ref)

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        if not SAFE_ID.fullmatch(memory_id):
            raise ValueError("Invalid memory identifier")
        rows = [row for row in self._read_events() if row.get("memory_id") == memory_id]
        return [{**row, "revision_status": row["status"] if index == len(rows) - 1 else "superseded"}
                for index, row in enumerate(rows)]

    def active_view(self, *, query: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Limit must be from 1 to 20")
        if query is not None and (not isinstance(query, str) or len(query) > 256):
            raise ValueError("Query must be at most 256 characters")
        latest: dict[str, dict[str, Any]] = {}
        for row in self._read_events():
            latest[row["memory_id"]] = row
        now = datetime.now(timezone.utc)
        needle = query.casefold().strip() if query else None
        result = []
        for row in latest.values():
            if row["status"] != "active" or row.get("fact_kind") == "inference":
                continue
            if row.get("expires_at"):
                try:
                    if datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) <= now:
                        continue
                except (ValueError, AttributeError):
                    raise MemoryStoreError("Personal memory expiry timestamp is invalid")
            text = row["content"].get("text", "")
            if needle and needle not in text.casefold() and needle not in row["category"].casefold():
                continue
            recalled = dict(row)
            if row.get("verification_status") == "source_required":
                # This is the model-facing context view. Keep the provenance and
                # verification requirement, but never pass the unsupported claim
                # itself as usable truth. The authenticated history endpoint keeps
                # the original text for audit and correction.
                recalled["content"] = {"text": "Source verification required before using this fact."}
                recalled["recall_status"] = "source_required"
            result.append({**recalled, "source": {"type": row["source_type"], "ref": row["source_ref"]}})
        result.sort(key=lambda row: (row["recorded_at"], row["memory_id"]), reverse=True)
        return result[:limit]


class CreateMemory(BaseModel):
    content: dict[str, Any]
    category: str
    fact_kind: str
    source_type: str
    source_ref: str
    exact: bool = False
    expires_at: str | None = None
    idempotency_key: str | None = None


class CorrectMemory(BaseModel):
    content: dict[str, Any]
    source_type: str
    source_ref: str
    fact_kind: str | None = None


class StatusMemory(BaseModel):
    source_type: str
    source_ref: str


def create_personal_memory_router(auth, store: PersonalMemoryStore) -> APIRouter:
    router = APIRouter(prefix="/api/personal-memory", tags=["personal-memory"])

    def payload(body: BaseModel) -> dict[str, Any]:
        # FastAPI 0.100 supported both Pydantic v1 and v2 during the project's
        # compatibility window; keep the endpoint serialization compatible.
        dump = getattr(body, "model_dump", None)
        return dump() if dump else body.dict()

    def guard(request: Request, action: str) -> None:
        auth.require_action(request, action)

    @router.get("")
    def recall(request: Request, query: str | None = None, limit: int = 10):
        guard(request, "personal_memory.read")
        try:
            return {"items": store.active_view(query=query, limit=limit)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MemoryStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("", status_code=201)
    def create(request: Request, body: CreateMemory):
        guard(request, "personal_memory.write")
        try:
            return store.create(**payload(body))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MemoryStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/{memory_id}/history")
    def history(request: Request, memory_id: str):
        guard(request, "personal_memory.read")
        try:
            rows = store.history(memory_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MemoryStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not rows:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"memory_id": memory_id, "revisions": rows}

    @router.post("/{memory_id}/correct")
    def correct(request: Request, memory_id: str, body: CorrectMemory):
        guard(request, "personal_memory.write")
        try:
            return store.correct(memory_id, **payload(body))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MemoryStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/{memory_id}/revoke")
    def revoke(request: Request, memory_id: str, body: StatusMemory):
        guard(request, "personal_memory.write")
        try:
            return store.revoke(memory_id, **payload(body))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MemoryStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/{memory_id}/expire")
    def expire(request: Request, memory_id: str, body: StatusMemory):
        guard(request, "personal_memory.write")
        try:
            return store.expire(memory_id, **payload(body))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except MemoryStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router
