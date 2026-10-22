"""Bounded, session-scoped deterministic planning candidates.

This module deliberately does not call a model or execute suggested actions.
Candidates contain only server-verified source references and review reasons.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request

from .calendar_read import _opaque_id
from .source_reference_authority import SourceReferenceAuthority
from .tasks import task_source_version


_MAX_BODY_BYTES = 16 * 1024
_MAX_OBJECTIVE_BYTES = 500
_MAX_SOURCE_REFS = 20
_MAX_STEPS = 20
_MAX_RESPONSE_BYTES = 16 * 1024
_MAX_CANDIDATES = 64
_MAX_LEDGER_BYTES = 2 * 1024 * 1024
_MAX_CALENDAR_DAYS = 31
_SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TASK_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_JOURNAL_ID = re.compile(r"^(\d{4}-\d{2}-\d{2}):([a-f0-9]{64})$")
_ALLOWED_JOURNAL_SOURCES = {"web_app_explicit_intent", "inbox_approved_proposal"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _now():
    return datetime.now(timezone.utc)


def _stamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise HTTPException(status_code=400, detail="Invalid planning date window")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid planning date window") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=400, detail="Invalid planning date window")
    return parsed


def _validate_ref(reference):
    if not isinstance(reference, dict) or set(reference) != {"kind", "id", "version"}:
        raise HTTPException(status_code=400, detail="Invalid planning source reference")
    kind, source_id, version = reference["kind"], reference["id"], reference["version"]
    if not isinstance(kind, str):
        raise HTTPException(status_code=400, detail="Unsupported planning source kind")
    if kind not in {"task", "project", "journal"}:
        raise HTTPException(status_code=400, detail="Unsupported planning source kind")
    if not isinstance(source_id, str) or len(source_id) > 160 or not isinstance(version, str):
        raise HTTPException(status_code=400, detail="Invalid planning source reference")
    if kind == "task" and (not _TASK_ID.fullmatch(source_id) or not _SHA256.fullmatch(version)):
        raise HTTPException(status_code=400, detail="Invalid planning source reference")
    if kind == "project" and (not _PROJECT_ID.fullmatch(source_id) or not _SHA256.fullmatch(version)):
        raise HTTPException(status_code=400, detail="Invalid planning source reference")
    if kind == "journal":
        match = _JOURNAL_ID.fullmatch(source_id)
        if not match or not _SHA256.fullmatch(version):
            raise HTTPException(status_code=400, detail="Invalid planning source reference")
        _parse_day(match.group(1))
    return {"kind": kind, "id": source_id, "version": version}


def _validate_request(value):
    if not isinstance(value, dict) or set(value) != {"objective", "source_refs", "calendar_window"}:
        raise HTTPException(status_code=400, detail="Invalid planning candidate request")
    objective = value["objective"]
    if not isinstance(objective, str) or not objective.strip() or len(objective.encode("utf-8")) > _MAX_OBJECTIVE_BYTES:
        raise HTTPException(status_code=400, detail="Invalid planning objective")
    refs = value["source_refs"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= _MAX_SOURCE_REFS:
        raise HTTPException(status_code=400, detail="Invalid planning source selection")
    normalized = [_validate_ref(item) for item in refs]
    keys = [(item["kind"], item["id"]) for item in normalized]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=400, detail="Duplicate planning source reference")
    window = value["calendar_window"]
    if window is not None:
        if not isinstance(window, dict) or set(window) != {"from", "to", "timezone"}:
            raise HTTPException(status_code=400, detail="Invalid planning date window")
        start, end = _parse_day(window["from"]), _parse_day(window["to"])
        zone_name = window["timezone"]
        if not isinstance(zone_name, str) or not zone_name or len(zone_name) > 64:
            raise HTTPException(status_code=400, detail="Invalid planning timezone")
        try:
            zone = ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid planning timezone") from exc
        if (end < start or (end - start).days >= _MAX_CALENDAR_DAYS
                or (start.year, start.month) != (end.year, end.month)):
            raise HTTPException(status_code=400, detail="Invalid planning date window")
        window = {"from": start.isoformat(), "to": end.isoformat(), "timezone": zone_name}
    else:
        zone = None
    return objective.strip(), normalized, window, zone


class PlanningCandidateStore:
    """Private bounded ledger; initialization and reads do not create files."""

    def __init__(self, root):
        self.root = Path(root)
        try:
            info = self.root.lstat()
        except OSError as exc:
            raise ValueError("Planning state root must already exist") from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise ValueError("Planning state root must be private and owned by Core")
        self.path = self.root / ".planning-candidates.json"
        self.lock_path = self.root / ".planning-candidates.lock"

    def _lock(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            os.close(fd)
            raise HTTPException(status_code=503, detail="Planning state is unavailable")
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _read_unlocked(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {"candidates": {}}
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Planning state is unavailable") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or info.st_size > _MAX_LEDGER_BYTES):
                raise HTTPException(status_code=503, detail="Planning state is unavailable")
            chunks, remaining = [], _MAX_LEDGER_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(fd)
            if (len(payload) != info.st_size or len(payload) > _MAX_LEDGER_BYTES
                    or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise HTTPException(status_code=503, detail="Planning state changed during read")
            data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
            if (not isinstance(data, dict) or set(data) != {"candidates"}
                    or not isinstance(data["candidates"], dict)):
                raise ValueError("invalid planning state")
            return data
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(status_code=503, detail="Planning state is invalid") from exc
        finally:
            os.close(fd)

    def _write_unlocked(self, data):
        temporary = self.root / f".planning-candidates-{uuid.uuid4().hex}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            payload = _canonical_bytes(data) + b"\n"
            if len(payload) > _MAX_LEDGER_BYTES:
                raise HTTPException(status_code=503, detail="Planning state limit reached")
            remaining = memoryview(payload)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError("incomplete planning state write")
                remaining = remaining[written:]
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(temporary, self.path)
            root_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                              | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(root_fd)
            finally:
                os.close(root_fd)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            if fd >= 0:
                os.close(fd)

    def create(self, *, session_id, objective, source_refs, steps, status, expires_at):
        candidate_id = uuid.uuid4().hex
        record = {
            "candidate_id": candidate_id,
            "session_id": session_id,
            "revision": 0,
            "status": status,
            "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
            "source_refs": source_refs,
            "steps": steps,
            "expires_at": expires_at,
            "created_at": _stamp(_now()),
        }
        fd = self._lock()
        try:
            data = self._read_unlocked()
            now = _now()
            # Expired rows are this ledger's own bounded ephemeral records; prune
            # them only during an explicit create, never in a background task.
            candidates = {key: value for key, value in data["candidates"].items()
                          if isinstance(value, dict)
                          and datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00")) > now}
            if len(candidates) >= _MAX_CANDIDATES:
                raise HTTPException(status_code=503, detail="Planning candidate limit reached")
            candidates[candidate_id] = record
            data["candidates"] = candidates
            self._write_unlocked(data)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Planning state is unavailable") from exc
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return candidate_id


class PlanningCandidateService:
    def __init__(self, auth, hermes, task_store, projects_store, journal_store, ledger):
        self.auth = auth
        self.hermes = hermes
        self.task_store = task_store
        self.projects_store = projects_store
        self.journal_store = journal_store
        self.ledger = ledger

    def _authorize(self, request, refs, calendar_window):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.write")
        actions = {"task": "task.read", "project": "projects.read", "journal": "journal.read"}
        kinds = {ref["kind"] for ref in refs}
        if calendar_window is not None:
            kinds.update({"task", "journal"})
            self.auth.require_action(request, "calendar.read")
        for kind in sorted(kinds):
            self.auth.require_action(request, actions[kind])

    async def create(self, request, session_id):
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=404, detail="Planning session not found")
        # Common permissions precede body parsing and every external/source read.
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.write")
        chunks, total = [], 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > _MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Planning request is too large")
            chunks.append(chunk)
        payload = b"".join(chunks)
        try:
            body = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid planning candidate request") from exc
        objective, refs, window, zone = _validate_request(body)
        actions = {"task": "task.read", "project": "projects.read", "journal": "journal.read"}
        kinds = {ref["kind"] for ref in refs}
        if window is not None:
            kinds.update({"task", "journal"})
            self.auth.require_action(request, "calendar.read")
        for kind in sorted(kinds):
            self.auth.require_action(request, actions[kind])
        if self.hermes is None:
            raise HTTPException(status_code=503, detail="Planning session authority is unavailable")
        try:
            session = await self.hermes.get_session(session_id)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(status_code=404, detail="Planning session not found") from exc
            raise HTTPException(status_code=503, detail="Planning session authority is unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Planning session authority is unavailable") from exc
        if not isinstance(session, dict) or session.get("session_id", session.get("id")) != session_id:
            raise HTTPException(status_code=404, detail="Planning session not found")
        self._authorize(request, refs, window)

        authority = SourceReferenceAuthority(
            projects_store=self.projects_store,
            task_store=self.task_store,
            journal_store=self.journal_store,
            permission_checks={
                "project": lambda: self.auth.require_action(request, "projects.read"),
                "task": lambda: self.auth.require_action(request, "task.read"),
                "journal": lambda: self.auth.require_action(request, "journal.read"),
            },
        )
        states = [authority.verify(ref) for ref in refs]
        if "forbidden" in states:
            raise HTTPException(status_code=403, detail="Planning source access denied")
        if any(state in {"unavailable"} for state in states):
            status, steps = "unavailable", []
        elif any(state != "verified" for state in states):
            status, steps = "stale", []
        else:
            steps = [self._step(ref, self._reason(ref["kind"])) for ref in refs]
            status = self._review_status(authority, refs)

        calendar_refs = []
        if window is not None and status not in {"stale", "unavailable"}:
            calendar_refs, calendar_available = self._calendar_refs(authority, window, zone)
            if not calendar_available:
                status, steps = "unavailable", []
            else:
                known = {(ref["kind"], ref["id"], ref["version"]) for ref in refs}
                for ref in calendar_refs:
                    key = (ref["kind"], ref["id"], ref["version"])
                    if key not in known:
                        steps.append(self._step(ref, "review_calendar"))
                        known.add(key)
                if len(steps) > _MAX_STEPS:
                    raise HTTPException(status_code=413, detail="Planning source selection is too large")
        if status in {"ready", "needs_review"}:
            status = self._review_status(authority, [step["source_ref"] for step in steps])

        # Use a fresh request-scoped authority for a second version check after
        # all projections have been read. Any drift removes every step.
        if status in {"ready", "needs_review"}:
            final_authority = SourceReferenceAuthority(
                projects_store=self.projects_store, task_store=self.task_store,
                journal_store=self.journal_store,
                permission_checks={
                    "project": lambda: self.auth.require_action(request, "projects.read"),
                    "task": lambda: self.auth.require_action(request, "task.read"),
                    "journal": lambda: self.auth.require_action(request, "journal.read"),
                },
            )
            all_refs = list(refs) + [ref for ref in calendar_refs if ref not in refs]
            final_states = [final_authority.verify(ref) for ref in all_refs]
            if any(state != "verified" for state in final_states):
                status, steps = "stale", []
        self._authorize(request, refs, window)
        steps = [{**step, "position": index + 1} for index, step in enumerate(steps)]
        stored_refs = [step["source_ref"] for step in steps]
        expires_at = _stamp(_now() + timedelta(minutes=30))

        candidate_id = self.ledger.create(
            session_id=session_id,
            objective=objective,
            source_refs=stored_refs,
            steps=steps,
            status=status,
            expires_at=expires_at,
        )
        response = {
            "event": "planning.candidate", "version": 1,
            "session_id": session_id, "candidate_id": candidate_id,
            "revision": 0, "expires_at": expires_at,
            "status": status, "objective": objective, "steps": steps,
        }
        if len(_canonical_bytes(response)) > _MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=413, detail="Planning response is too large")
        return response

    @staticmethod
    def _reason(kind):
        return {"task": "review_task", "project": "review_project",
                "journal": "review_journal"}[kind]

    @staticmethod
    def _step(reference, reason):
        return {"position": 0, "kind": "review_source", "source_ref": dict(reference),
                "reason": reason, "priority": "unspecified", "depends_on": []}

    @staticmethod
    def _review_status(authority, refs):
        """Completed Tasks and non-active Projects need an explicit human review."""
        for ref in refs:
            if ref["kind"] == "task" and authority._task_rows is not None:
                row = next((item for item in authority._task_rows if item.get("id") == ref["id"]), None)
                if row is not None and row.get("status") != "open":
                    return "needs_review"
            if ref["kind"] == "project" and authority._project_snapshot is not None:
                row = next((item.document for item in authority._project_snapshot.documents
                            if item.project_id == ref["id"]), None)
                if row is not None and row.get("status") != "active":
                    return "needs_review"
        return "ready"

    def _calendar_refs(self, authority, window, zone):
        start, end = _parse_day(window["from"]), _parse_day(window["to"])
        events = []
        try:
            if self.task_store is None or self.journal_store is None:
                return [], False
            if authority._task_rows is None:
                authority._task_rows = self.task_store.list_for_projection()["tasks"]
            task_rows = authority._task_rows
            for task in task_rows:
                due = task.get("due_date")
                task_id = task.get("id")
                if not isinstance(due, str) or not start.isoformat() <= due <= end.isoformat():
                    continue
                version = task_source_version(task)
                if version is None or not isinstance(task_id, str):
                    return [], False
                ref = {"kind": "task", "id": task_id, "version": version}
                if authority.verify(ref) != "verified":
                    return [], False
                events.append((due, "task", _opaque_id("task", due, task_id), ref))
            day_count = (end - start).days + 1
            for offset in range(day_count):
                day = date.fromordinal(start.toordinal() + offset).isoformat()
                snapshot = authority._journal_day(day)
                if snapshot is None or snapshot.get("available") is not True:
                    return [], False
                for entry_id, row in snapshot.get("entries", {}).items():
                    record = row.get("record") if isinstance(row, dict) else None
                    if not isinstance(record, dict) or record.get("source") not in _ALLOWED_JOURNAL_SOURCES:
                        continue
                    version = row.get("version")
                    ref = {"kind": "journal", "id": f"{day}:{entry_id}", "version": version}
                    if authority.verify(ref) != "verified":
                        return [], False
                    events.append((day, "journal", _opaque_id("journal", day, entry_id), ref))
        except Exception:
            return [], False
        events.sort(key=lambda item: (item[0], item[1], item[2]))
        if len(events) > _MAX_STEPS:
            return [], False
        return [item[3] for item in events], True


def create_planning_router(service):
    router = APIRouter(prefix="/api/chat/sessions/{session_id}/planning")

    @router.post("/candidates")
    async def create_candidate(request: Request, session_id: str):
        return await service.create(request, session_id)

    return router
