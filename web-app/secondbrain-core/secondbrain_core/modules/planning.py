"""Bounded, session-scoped deterministic planning candidates and approved actions.

No model is called. Any task action is explicitly supplied by the user, stored
in the private candidate ledger, approved, source-revalidated, then executed
through TaskStore's idempotent create operation.
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
_MAX_PROPOSED_TASKS = 10
_MAX_TASK_TITLE_BYTES = 200
_MAX_SOURCE_REFS = 20
_MAX_STEPS = 20
_MAX_RESPONSE_BYTES = 16 * 1024
_MAX_CANDIDATES = 64
_MAX_LEDGER_BYTES = 2 * 1024 * 1024
_MAX_AUDIT_EVENTS = 1000
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
    if (not isinstance(value, dict)
            or set(value) not in (
                {"objective", "source_refs", "calendar_window"},
                {"objective", "source_refs", "calendar_window", "proposed_tasks"},
            )):
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
    proposed_tasks = value.get("proposed_tasks", [])
    if not isinstance(proposed_tasks, list) or len(proposed_tasks) > _MAX_PROPOSED_TASKS:
        raise HTTPException(status_code=400, detail="Invalid proposed Task actions")
    task_actions = []
    for action in proposed_tasks:
        if not isinstance(action, dict) or set(action) != {"title", "due_date"}:
            raise HTTPException(status_code=400, detail="Invalid proposed Task action")
        title = action["title"]
        if (not isinstance(title, str) or not title.strip()
                or len(title.strip().encode("utf-8")) > _MAX_TASK_TITLE_BYTES):
            raise HTTPException(status_code=400, detail="Invalid proposed Task title")
        due_date = action["due_date"]
        if due_date is not None:
            due_date = _parse_day(due_date).isoformat()
        task_actions.append({"title": title.strip(), "due_date": due_date})
    return objective.strip(), normalized, window, zone, task_actions


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
            try:
                current = os.stat(self.path, follow_symlinks=False)
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Planning state changed during read") from exc
            identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
                                     item.st_uid, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if identity(info) != identity(current):
                raise HTTPException(status_code=503, detail="Planning state changed during read")
            data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
            if (not isinstance(data, dict) or set(data) not in ({"candidates"}, {"candidates", "audit"})
                    or not isinstance(data["candidates"], dict)):
                raise ValueError("invalid planning state")
            if "audit" not in data:
                data["audit"] = []
            if not isinstance(data["audit"], list) or len(data["audit"]) > _MAX_AUDIT_EVENTS:
                raise ValueError("invalid planning audit")
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

    def create(self, *, session_id, objective, source_refs, calendar_window, steps, status, expires_at):
        candidate_id = uuid.uuid4().hex
        record = {
            "candidate_id": candidate_id,
            "session_id": session_id,
            "revision": 0,
            "status": status,
            "workflow_status": "active",
            "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
            "objective": objective,
            "source_refs": source_refs,
            "calendar_window": calendar_window,
            "steps": steps,
            "step_states": [{"position": step["position"], "decision": "pending",
                             "execution_status": "not_started"} for step in steps],
            "idempotency": {},
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

    def get(self, candidate_id, session_id):
        data = self._read_unlocked()
        candidate = data["candidates"].get(candidate_id)
        if not isinstance(candidate, dict) or candidate.get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="Planning candidate not found")
        return candidate

    @staticmethod
    def key_hash(value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 255
                or any(ord(char) < 33 or ord(char) > 126 for char in value)):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    def replay(self, candidate_id, session_id, key_hash, fingerprint):
        candidate = self.get(candidate_id, session_id)
        replay = candidate.get("idempotency", {}).get(key_hash)
        if replay is None:
            return None
        if replay.get("fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key was already used differently")
        return replay["response"]

    def mutate(self, *, candidate_id, session_id, key_hash, fingerprint,
               expected_revision, position, transition):
        if (not isinstance(expected_revision, int) or isinstance(expected_revision, bool)
                or expected_revision < 0):
            raise HTTPException(status_code=400, detail="Invalid planning revision")
        fd = self._lock()
        try:
            data = self._read_unlocked()
            record = data["candidates"].get(candidate_id)
            if not isinstance(record, dict) or record.get("session_id") != session_id:
                raise HTTPException(status_code=404, detail="Planning candidate not found")
            if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
                raise HTTPException(status_code=410, detail="Planning candidate expired")
            idempotency = record.setdefault("idempotency", {})
            prior = idempotency.get(key_hash)
            if prior is not None:
                if prior.get("fingerprint") != fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used differently")
                return prior["response"]
            if record.get("revision") != expected_revision:
                raise HTTPException(status_code=409, detail="Planning candidate revision changed")
            if record.get("status") not in {"ready", "needs_review"}:
                raise HTTPException(status_code=409, detail="Planning candidate is not actionable")
            if record.get("workflow_status", "active") != "active":
                raise HTTPException(status_code=409, detail="Planning workflow is not active")
            states = record.get("step_states")
            if not isinstance(states, list) or len(states) != len(record.get("steps", [])):
                states = [{"position": step["position"], "decision": "pending",
                           "execution_status": "not_started"} for step in record.get("steps", [])]
                record["step_states"] = states
            if not isinstance(position, int) or not 1 <= position <= len(states):
                raise HTTPException(status_code=404, detail="Planning step not found")
            if len(data["audit"]) >= _MAX_AUDIT_EVENTS:
                raise HTTPException(status_code=503, detail="Planning audit limit reached")
            step = record["steps"][position - 1]
            state = states[position - 1]
            revision = expected_revision + 1
            response, event_type = transition(record, step, state, revision)
            if not isinstance(response, dict):
                raise HTTPException(status_code=503, detail="Planning operation failed safely")
            record["revision"] = revision
            idempotency[key_hash] = {"fingerprint": fingerprint, "response": response}
            data["audit"].append({
                "candidate_id": candidate_id, "session_id": session_id,
                "revision": revision, "position": position, "event": event_type,
                "idempotency_key_sha256": key_hash,
                "source_ref_sha256": hashlib.sha256(_canonical_bytes(
                    step.get("source_ref") or {"kind": step.get("kind"), "task": step.get("task")}
                )).hexdigest(),
                "recorded_at": _stamp(_now()),
            })
            self._write_unlocked(data)
            return response
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Planning operation failed safely") from exc
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def control(self, *, candidate_id, session_id, key_hash, fingerprint, expected_revision, command):
        if (not isinstance(expected_revision, int) or isinstance(expected_revision, bool)
                or expected_revision < 0):
            raise HTTPException(status_code=400, detail="Invalid planning revision")
        fd = self._lock()
        try:
            data = self._read_unlocked()
            record = data["candidates"].get(candidate_id)
            if not isinstance(record, dict) or record.get("session_id") != session_id:
                raise HTTPException(status_code=404, detail="Planning candidate not found")
            if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
                raise HTTPException(status_code=410, detail="Planning candidate expired")
            idempotency = record.setdefault("idempotency", {})
            prior = idempotency.get(key_hash)
            if prior is not None:
                if prior.get("fingerprint") != fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used differently")
                return prior["response"]
            if record.get("revision") != expected_revision:
                raise HTTPException(status_code=409, detail="Planning candidate revision changed")
            if record.get("status") not in {"ready", "needs_review"}:
                raise HTTPException(status_code=409, detail="Planning candidate is not actionable")
            states = record.get("step_states", [])
            workflow = record.get("workflow_status", "active")
            if command == "pause" and workflow == "active":
                workflow = "paused"
            elif command == "resume" and workflow == "paused":
                workflow = "active"
            elif command == "cancel" and workflow in {"active", "paused", "partial"}:
                workflow = "cancelled"
            elif command == "retry":
                failed = next((state for state in states if state.get("execution_status") == "failed"), None)
                if workflow != "partial" or failed is None:
                    raise HTTPException(status_code=409, detail="No failed planning step can be retried")
                failed["execution_status"] = "retry_ready"
                workflow = "active"
            else:
                raise HTTPException(status_code=409, detail="Planning workflow transition is invalid")
            revision = expected_revision + 1
            record["revision"] = revision
            record["workflow_status"] = workflow
            response = {
                "event": "planning.workflow-control", "version": 1,
                "session_id": session_id, "candidate_id": candidate_id,
                "revision": revision, "command": command, "workflow_status": workflow,
                "steps": [{"position": state["position"], "decision": state["decision"],
                           "execution_status": state["execution_status"]} for state in states],
            }
            if len(data["audit"]) >= _MAX_AUDIT_EVENTS:
                raise HTTPException(status_code=503, detail="Planning audit limit reached")
            idempotency[key_hash] = {"fingerprint": fingerprint, "response": response}
            data["audit"].append({
                "candidate_id": candidate_id, "session_id": session_id, "revision": revision,
                "position": 0, "event": f"workflow_{command}",
                "idempotency_key_sha256": key_hash,
                "source_ref_sha256": hashlib.sha256(_canonical_bytes(record["source_refs"])).hexdigest(),
                "recorded_at": _stamp(_now()),
            })
            self._write_unlocked(data)
            return response
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Planning operation failed safely") from exc
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def record_feedback(self, *, candidate_id, session_id, key_hash, fingerprint,
                        expected_revision, rating):
        fd = self._lock()
        try:
            data = self._read_unlocked()
            record = data["candidates"].get(candidate_id)
            if not isinstance(record, dict) or record.get("session_id") != session_id:
                raise HTTPException(status_code=404, detail="Planning candidate not found")
            idempotency = record.setdefault("idempotency", {})
            prior = idempotency.get(key_hash)
            if prior is not None:
                if prior.get("fingerprint") != fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used differently")
                return prior["response"]
            if record.get("revision") != expected_revision:
                raise HTTPException(status_code=409, detail="Planning candidate revision changed")
            if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
                raise HTTPException(status_code=410, detail="Planning candidate expired")
            if record.get("feedback") is not None:
                raise HTTPException(status_code=409, detail="Planning feedback is already recorded")
            if len(data["audit"]) >= _MAX_AUDIT_EVENTS:
                raise HTTPException(status_code=503, detail="Planning audit limit reached")
            revision = expected_revision + 1
            record["revision"] = revision
            record["feedback"] = {"rating": rating, "recorded_at": _stamp(_now())}
            response = {"event": "planning.feedback", "version": 1,
                        "session_id": session_id, "candidate_id": candidate_id,
                        "revision": revision, "rating": rating}
            idempotency[key_hash] = {"fingerprint": fingerprint, "response": response}
            data["audit"].append({
                "candidate_id": candidate_id, "session_id": session_id, "revision": revision,
                "position": 0, "event": "retrospective_feedback",
                "idempotency_key_sha256": key_hash,
                "source_ref_sha256": hashlib.sha256(_canonical_bytes(record["source_refs"])).hexdigest(),
                "recorded_at": _stamp(_now()),
            })
            self._write_unlocked(data)
            return response
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Planning operation failed safely") from exc
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


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

    @staticmethod
    def _source_actions(refs):
        actions = {"task": "task.read", "project": "projects.read", "journal": "journal.read"}
        return {actions[ref["kind"]] for ref in refs}

    @classmethod
    def _candidate_actions(cls, record):
        actions = cls._source_actions(record.get("source_refs", []))
        if record.get("calendar_window") is not None:
            actions.add("calendar.read")
        return actions

    async def _require_session(self, session_id):
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id) or self.hermes is None:
            raise HTTPException(status_code=404, detail="Planning session not found")
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

    def _verify_refs(self, request, refs):
        if not isinstance(refs, list) or not refs:
            raise HTTPException(status_code=409, detail="Planning candidate has no verifiable sources")
        for action in sorted(self._source_actions(refs)):
            self.auth.require_action(request, action)
        authority = SourceReferenceAuthority(
            projects_store=self.projects_store, task_store=self.task_store,
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
        if "unavailable" in states:
            return "unavailable"
        return "verified" if all(state == "verified" for state in states) else "stale"

    def _execute_step(self, step, *, candidate_id, position, session_id):
        """Execute only explicit, approved Core actions; review steps persist locally."""
        if step.get("kind") == "create_task":
            if self.task_store is None:
                raise HTTPException(status_code=503, detail="Task service is unavailable")
            operation_id = f"planning:{candidate_id}:{position}"
            result = self.task_store.create(
                step["task"]["title"], step["task"]["due_date"], operation_id,
                original_command="", session_id=session_id,
            )
            task = result["task"]
            version = task_source_version(task)
            if version is None:
                # The Task may already be committed. Keep the candidate retryable;
                # deterministic TaskStore idempotency will recover its receipt.
                raise HTTPException(status_code=503, detail="Task result could not be verified")
            return {
                "status": "completed", "execution_mode": "core",
                "effect": "task_created", "task_id": task["id"],
                "task_version": version,
            }
        if step.get("kind") == "review_source":
            return {"status": "completed", "execution_mode": "core",
                    "effect": "planning_ledger"}
        raise HTTPException(status_code=409, detail="Unsupported planning action")

    @staticmethod
    async def _read_body(request):
        chunks, total = [], 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > _MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Planning request is too large")
            chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks).decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid planning request") from exc

    @staticmethod
    def _require_revision(value):
        if not isinstance(value, dict) or set(value) != {"expected_revision"}:
            raise HTTPException(status_code=400, detail="Invalid planning revision")
        revision = value["expected_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise HTTPException(status_code=400, detail="Invalid planning revision")
        return revision

    async def preview(self, request, session_id, candidate_id):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.read")
        if not isinstance(candidate_id, str) or not _TASK_ID.fullmatch(candidate_id):
            raise HTTPException(status_code=404, detail="Planning candidate not found")
        record = self.ledger.get(candidate_id, session_id)
        if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
            raise HTTPException(status_code=410, detail="Planning candidate expired")
        if not isinstance(record.get("objective"), str):
            raise HTTPException(status_code=410, detail="Planning candidate is no longer reviewable")
        await self._require_session(session_id)
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.read")
        status = record.get("status")
        steps = record.get("steps", [])
        if status in {"ready", "needs_review"}:
            source_status = self._verify_refs(request, record.get("source_refs"))
            if source_status != "verified":
                status = "unavailable" if source_status == "unavailable" else "stale"
                steps = []
        for action in sorted(self._candidate_actions(record)):
            self.auth.require_action(request, action)
        states = record.get("step_states") or [
            {"position": step["position"], "decision": "pending", "execution_status": "not_started"}
            for step in steps
        ]
        state_by_position = {item["position"]: item for item in states if isinstance(item, dict)}
        projected_steps = []
        if status in {"ready", "needs_review"}:
            for step in steps:
                state = state_by_position.get(step["position"], {})
                projected_steps.append({
                    **step,
                    "decision": state.get("decision", "pending"),
                    "execution_status": state.get("execution_status", "not_started"),
                })
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.read")
        return {
            "event": "planning.preview", "version": 1, "session_id": session_id,
            "candidate_id": candidate_id, "revision": record.get("revision", 0),
            "expires_at": record["expires_at"], "status": status,
            "workflow_status": record.get("workflow_status", "active"),
            "objective": record["objective"], "steps": projected_steps,
        }

    async def decide(self, request, session_id, candidate_id, position):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        body = await self._read_body(request)
        if not isinstance(body, dict) or set(body) != {"decision", "expected_revision"}:
            raise HTTPException(status_code=400, detail="Invalid planning decision")
        decision = body["decision"]
        if not isinstance(decision, str) or decision not in {"approved", "rejected"}:
            raise HTTPException(status_code=400, detail="Invalid planning decision")
        expected_revision = self._require_revision({"expected_revision": body["expected_revision"]})
        key_hash = self.ledger.key_hash(request.headers.get("idempotency-key", ""))
        record = self.ledger.get(candidate_id, session_id)
        if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
            raise HTTPException(status_code=410, detail="Planning candidate expired")
        if not isinstance(record.get("objective"), str):
            raise HTTPException(status_code=410, detail="Planning candidate is no longer reviewable")
        fingerprint = hashlib.sha256(_canonical_bytes({
            "operation": "decision", "session_id": session_id, "candidate_id": candidate_id,
            "position": position, "body": body,
        })).hexdigest()
        await self._require_session(session_id)
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        for action in sorted(self._candidate_actions(record)):
            self.auth.require_action(request, action)
        replay = self.ledger.replay(candidate_id, session_id, key_hash, fingerprint)
        if replay is not None:
            return replay
        if record.get("revision") != expected_revision:
            raise HTTPException(status_code=409, detail="Planning candidate revision changed")
        states = record.get("step_states", [])
        if not isinstance(position, int) or isinstance(position, bool) or not 1 <= position <= len(states):
            raise HTTPException(status_code=404, detail="Planning step not found")
        if states[position - 1].get("decision") != "pending":
            raise HTTPException(status_code=409, detail="Planning step already has a decision")
        if record.get("status") not in {"ready", "needs_review"}:
            raise HTTPException(status_code=409, detail="Planning candidate is not actionable")
        if self._verify_refs(request, record.get("source_refs")) != "verified":
            raise HTTPException(status_code=409, detail="Planning sources changed or became unavailable")
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")

        def transition(candidate, step, state, revision):
            state["decision"] = decision
            response = {
                "event": "planning.step-decision", "version": 1,
                "session_id": session_id, "candidate_id": candidate_id,
                "revision": revision, "position": position, "decision": decision,
                "execution_status": "not_started",
            }
            return response, "step_approved" if decision == "approved" else "step_rejected"

        return self.ledger.mutate(
            candidate_id=candidate_id, session_id=session_id, key_hash=key_hash,
            fingerprint=fingerprint, expected_revision=expected_revision,
            position=position, transition=transition,
        )

    async def execute(self, request, session_id, candidate_id, position):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.execute")
        body = await self._read_body(request)
        expected_revision = self._require_revision(body)
        key_hash = self.ledger.key_hash(request.headers.get("idempotency-key", ""))
        record = self.ledger.get(candidate_id, session_id)
        if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
            raise HTTPException(status_code=410, detail="Planning candidate expired")
        if not isinstance(record.get("objective"), str):
            raise HTTPException(status_code=410, detail="Planning candidate is no longer executable")
        fingerprint = hashlib.sha256(_canonical_bytes({
            "operation": "execute", "session_id": session_id, "candidate_id": candidate_id,
            "position": position, "body": body,
        })).hexdigest()
        await self._require_session(session_id)
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.execute")
        for action in sorted(self._candidate_actions(record)):
            self.auth.require_action(request, action)
        states = record.get("step_states", [])
        if not isinstance(position, int) or isinstance(position, bool) or not 1 <= position <= len(states):
            raise HTTPException(status_code=404, detail="Planning step not found")
        step = record.get("steps", [])[position - 1]
        if step.get("kind") == "create_task":
            self.auth.require_action(request, "task.write")
        replay = self.ledger.replay(candidate_id, session_id, key_hash, fingerprint)
        if replay is not None:
            return replay
        if record.get("revision") != expected_revision:
            raise HTTPException(status_code=409, detail="Planning candidate revision changed")
        if states[position - 1].get("decision") != "approved":
            raise HTTPException(status_code=409, detail="Planning step requires explicit approval")
        if states[position - 1].get("execution_status") not in {"not_started", "retry_ready"}:
            raise HTTPException(status_code=409, detail="Planning step is already completed")
        if record.get("status") not in {"ready", "needs_review"}:
            raise HTTPException(status_code=409, detail="Planning candidate is not actionable")
        if self._verify_refs(request, record.get("source_refs")) != "verified":
            raise HTTPException(status_code=409, detail="Planning sources changed or became unavailable")
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.execute")
        if step.get("kind") == "create_task":
            # Recheck the write action after the second source verification.
            self.auth.require_action(request, "task.write")

        def transition(candidate, step, state, revision):
            try:
                result = self._execute_step(
                    step, candidate_id=candidate_id, position=position, session_id=session_id,
                )
                state["execution_status"] = result["status"]
            except HTTPException:
                # A Task write can have committed before the Planning ledger
                # update fails. Leave the candidate unchanged; retry uses the
                # deterministic TaskStore operation key to recover exactly once.
                if step.get("kind") == "create_task":
                    raise
                result = {"status": "failed", "execution_mode": "core", "effect": "planning_ledger"}
                state["execution_status"] = "failed"
                candidate["workflow_status"] = "partial"
            except Exception:
                result = {"status": "failed", "execution_mode": "core", "effect": "planning_ledger"}
                state["execution_status"] = "failed"
                candidate["workflow_status"] = "partial"
            else:
                states_now = candidate.get("step_states", [])
                if states_now and all(item.get("decision") == "rejected"
                                      or item.get("execution_status") == "completed"
                                      for item in states_now):
                    candidate["workflow_status"] = "completed"
                elif any(item.get("execution_status") == "failed" for item in states_now):
                    candidate["workflow_status"] = "partial"
                else:
                    candidate["workflow_status"] = "active"
            response = {
                "event": "planning.step-execution", "version": 1,
                "session_id": session_id, "candidate_id": candidate_id,
                "revision": revision, "position": position,
                **result,
            }
            return response, "planning_step_failed" if result["status"] == "failed" else "planning_step_completed"

        return self.ledger.mutate(
            candidate_id=candidate_id, session_id=session_id, key_hash=key_hash,
            fingerprint=fingerprint, expected_revision=expected_revision,
            position=position, transition=transition,
        )

    async def control(self, request, session_id, candidate_id):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        body = await self._read_body(request)
        if not isinstance(body, dict) or set(body) != {"command", "expected_revision"}:
            raise HTTPException(status_code=400, detail="Invalid planning workflow command")
        command = body["command"]
        if not isinstance(command, str) or command not in {"pause", "resume", "cancel", "retry"}:
            raise HTTPException(status_code=400, detail="Invalid planning workflow command")
        revision = self._require_revision({"expected_revision": body["expected_revision"]})
        key_hash = self.ledger.key_hash(request.headers.get("idempotency-key", ""))
        record = self.ledger.get(candidate_id, session_id)
        if not isinstance(record.get("objective"), str):
            raise HTTPException(status_code=410, detail="Planning candidate is no longer reviewable")
        fingerprint = hashlib.sha256(_canonical_bytes({
            "operation": "control", "session_id": session_id, "candidate_id": candidate_id, "body": body,
        })).hexdigest()
        await self._require_session(session_id)
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        for action in sorted(self._candidate_actions(record)):
            self.auth.require_action(request, action)
        replay = self.ledger.replay(candidate_id, session_id, key_hash, fingerprint)
        if replay is not None:
            return replay
        if record.get("revision") != revision:
            raise HTTPException(status_code=409, detail="Planning candidate revision changed")
        if record.get("status") not in {"ready", "needs_review"}:
            raise HTTPException(status_code=409, detail="Planning candidate is not actionable")
        if self._verify_refs(request, record.get("source_refs")) != "verified":
            raise HTTPException(status_code=409, detail="Planning sources changed or became unavailable")
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        return self.ledger.control(candidate_id=candidate_id, session_id=session_id,
                                   key_hash=key_hash, fingerprint=fingerprint,
                                   expected_revision=revision, command=command)

    async def retrospective(self, request, session_id, candidate_id):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.read")
        record = self.ledger.get(candidate_id, session_id)
        if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= _now():
            raise HTTPException(status_code=410, detail="Planning candidate expired")
        if not isinstance(record.get("objective"), str):
            raise HTTPException(status_code=410, detail="Planning candidate is no longer reviewable")
        await self._require_session(session_id)
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.read")
        refs = record.get("source_refs", [])
        for action in sorted(self._candidate_actions(record)):
            self.auth.require_action(request, action)
        source_states = {}
        if refs:
            authority = SourceReferenceAuthority(
                projects_store=self.projects_store, task_store=self.task_store,
                journal_store=self.journal_store,
                permission_checks={
                    "project": lambda: self.auth.require_action(request, "projects.read"),
                    "task": lambda: self.auth.require_action(request, "task.read"),
                    "journal": lambda: self.auth.require_action(request, "journal.read"),
                },
            )
            for ref in refs:
                result = authority.verify(ref)
                if result == "forbidden":
                    raise HTTPException(status_code=403, detail="Planning source access denied")
                source_states[(ref["kind"], ref["id"], ref["version"])] = (
                    result if result in {"verified", "stale"} else "unavailable")
        states = record.get("step_states", [])
        state_by_position = {item["position"]: item for item in states if isinstance(item, dict)}
        steps = []
        for step in record.get("steps", []):
            state = state_by_position.get(step["position"], {})
            ref = step.get("source_ref")
            source_state = ("verified" if source_states
                            and all(value == "verified" for value in source_states.values())
                            else "not_applicable")
            if isinstance(ref, dict):
                key = (ref["kind"], ref["id"], ref["version"])
                source_state = source_states.get(key, "unavailable")
            steps.append({
                "position": step["position"], "kind": step["kind"], "source_ref": ref,
                "decision": state.get("decision", "pending"),
                "execution_status": state.get("execution_status", "not_started"),
                "source_state": source_state,
                **({"task": step["task"]} if step.get("kind") == "create_task" else {}),
            })
        decisions = [item["decision"] for item in steps]
        executions = [item["execution_status"] for item in steps]
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.read")
        return {
            "event": "planning.retrospective", "version": 1,
            "session_id": session_id, "candidate_id": candidate_id,
            "revision": record.get("revision", 0),
            "workflow_status": record.get("workflow_status", "active"),
            "counts": {
                "planned": len(steps), "approved": decisions.count("approved"),
                "rejected": decisions.count("rejected"),
                "completed": sum(value in {"simulated", "completed"} for value in executions),
                "failed": executions.count("failed"),
                "stale_sources": sum(1 for item in steps if item["source_state"] != "verified"),
            },
            "steps": steps,
            "feedback": record.get("feedback", {}).get("rating") if record.get("feedback") else None,
        }

    async def submit_feedback(self, request, session_id, candidate_id):
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        body = await self._read_body(request)
        if not isinstance(body, dict) or set(body) != {"rating", "expected_revision"}:
            raise HTTPException(status_code=400, detail="Invalid planning feedback")
        rating = body["rating"]
        if not isinstance(rating, str) or rating not in {"useful", "not_useful"}:
            raise HTTPException(status_code=400, detail="Invalid planning feedback")
        revision = self._require_revision({"expected_revision": body["expected_revision"]})
        key_hash = self.ledger.key_hash(request.headers.get("idempotency-key", ""))
        record = self.ledger.get(candidate_id, session_id)
        fingerprint = hashlib.sha256(_canonical_bytes({
            "operation": "feedback", "session_id": session_id, "candidate_id": candidate_id, "body": body,
        })).hexdigest()
        await self._require_session(session_id)
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        for action in sorted(self._candidate_actions(record)):
            self.auth.require_action(request, action)
        replay = self.ledger.replay(candidate_id, session_id, key_hash, fingerprint)
        if replay is not None:
            return replay
        if self._verify_refs(request, record.get("source_refs", [])) != "verified":
            raise HTTPException(status_code=409, detail="Planning sources changed or became unavailable")
        self.auth.require_action(request, "chat.read")
        self.auth.require_action(request, "planning.approve")
        return self.ledger.record_feedback(candidate_id=candidate_id, session_id=session_id,
                                           key_hash=key_hash, fingerprint=fingerprint,
                                           expected_revision=revision, rating=rating)

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
        objective, refs, window, zone, task_actions = _validate_request(body)
        if task_actions:
            # Permission is checked before Hermes or any source-store IO.
            self.auth.require_action(request, "task.write")
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
            steps.extend({
                "position": 0, "kind": "create_task", "task": action,
                "reason": "user_submitted_task_action", "priority": "user_selected",
                "depends_on": [],
            } for action in task_actions)
            if len(steps) > _MAX_STEPS:
                raise HTTPException(status_code=413, detail="Planning action selection is too large")

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
        stored_refs = [step["source_ref"] for step in steps if "source_ref" in step]
        expires_at = _stamp(_now() + timedelta(minutes=30))

        # Bound the response before persisting a candidate, so oversized
        # requests cannot leave an unreachable durable record behind.
        response_steps = [{**step, "decision": "pending", "execution_status": "not_started"}
                          for step in steps]
        response = {
            "event": "planning.candidate", "version": 1,
            "session_id": session_id, "candidate_id": "0" * 32,
            "revision": 0, "expires_at": expires_at,
            "status": status, "objective": objective, "steps": response_steps,
            "workflow_status": "active",
        }
        if len(_canonical_bytes(response)) > _MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=413, detail="Planning response is too large")
        candidate_id = self.ledger.create(
            session_id=session_id,
            objective=objective,
            source_refs=stored_refs,
            calendar_window=window,
            steps=steps,
            status=status,
            expires_at=expires_at,
        )
        response["candidate_id"] = candidate_id
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

    @router.get("/candidates/{candidate_id}")
    async def preview_candidate(request: Request, session_id: str, candidate_id: str):
        return await service.preview(request, session_id, candidate_id)

    @router.post("/candidates/{candidate_id}/steps/{position}/decision")
    async def decide_step(request: Request, session_id: str, candidate_id: str, position: int):
        return await service.decide(request, session_id, candidate_id, position)

    @router.post("/candidates/{candidate_id}/steps/{position}/execute")
    async def execute_step(request: Request, session_id: str, candidate_id: str, position: int):
        return await service.execute(request, session_id, candidate_id, position)

    @router.post("/candidates/{candidate_id}/control")
    async def control_candidate(request: Request, session_id: str, candidate_id: str):
        return await service.control(request, session_id, candidate_id)

    @router.get("/candidates/{candidate_id}/retrospective")
    async def retrospective_candidate(request: Request, session_id: str, candidate_id: str):
        return await service.retrospective(request, session_id, candidate_id)

    @router.post("/candidates/{candidate_id}/retrospective/feedback")
    async def feedback_candidate(request: Request, session_id: str, candidate_id: str):
        return await service.submit_feedback(request, session_id, candidate_id)

    return router
