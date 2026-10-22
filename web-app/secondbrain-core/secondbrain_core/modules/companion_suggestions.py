"""Explicitly triggered, source-versioned Companion suggestion candidates.

This module never schedules, sends messages, starts Hermes Runs, or mutates a
Task/Project/Journal/Knowledge source. Its private ledger stores only suggestion
control state and idempotency receipts; source records remain authoritative.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response

from .tasks import task_source_version


_MAX_STATE_BYTES = 1024 * 1024
_MAX_RECORDS = 500
_MAX_IDEMPOTENCY = 1000
_MAX_TASKS = 50
_MAX_PROJECTS = 50
_TTL = timedelta(hours=24)
_SUGGESTION_ZONE = ZoneInfo("Asia/Shanghai")
_CATEGORIES = {"task_due", "project_next_step"}
_IDEM_KEY = re.compile(r"^[\x21-\x7e]{1,255}$")
_RFC3339 = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _utc_now():
    return datetime.now(timezone.utc)


def _stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


async def _bounded_body(request, limit=4096):
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > limit:
            raise HTTPException(status_code=400, detail="Invalid Companion request")
        chunks.extend(chunk)
    return bytes(chunks)


def _parse_stamp(value):
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _valid_settings(value):
    if not isinstance(value, dict) or set(value) != {"enabled", "categories"}:
        return False
    categories = value["categories"]
    return (isinstance(value["enabled"], bool) and isinstance(categories, list)
            and all(isinstance(item, str) for item in categories)
            and len(categories) <= len(_CATEGORIES)
            and len(categories) == len(set(categories))
            and set(categories) <= _CATEGORIES)


class CompanionSuggestionStore:
    """Private single-owner CAS ledger; reads do not create locks or files."""

    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("Companion state root must be absolute")

    @staticmethod
    def _error():
        raise HTTPException(status_code=503, detail="Companion state unavailable")

    def _root_fd(self, *, create=False):
        try:
            if create:
                os.makedirs(self.root, mode=0o700, exist_ok=True)
            info = self.root.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077):
                self._error()
            fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
            opened = os.fstat(fd)
            current = self.root.lstat()
            if ((opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                    or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)):
                os.close(fd)
                self._error()
            return fd
        except FileNotFoundError:
            return None
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Companion state unavailable") from exc

    @staticmethod
    def _check_file(fd, *, writable=False):
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o077
                or (writable and not info.st_mode & stat.S_IWUSR)):
            raise HTTPException(status_code=503, detail="Companion state unavailable")
        return info

    def _read_at(self, root_fd):
        try:
            fd = os.open("companion-suggestions.json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                         dir_fd=root_fd)
        except FileNotFoundError:
            return self._empty()
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Companion state unavailable") from exc
        try:
            info = self._check_file(fd)
            if info.st_size < 0 or info.st_size > _MAX_STATE_BYTES:
                self._error()
            chunks, remaining = [], _MAX_STATE_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(fd)
            if (len(raw) != info.st_size or after.st_ino != info.st_ino
                    or after.st_size != info.st_size or after.st_mtime_ns != info.st_mtime_ns):
                self._error()
            current = os.stat("companion-suggestions.json", dir_fd=root_fd, follow_symlinks=False)
            if (not stat.S_ISREG(current.st_mode) or current.st_dev != after.st_dev
                    or current.st_ino != after.st_ino):
                self._error()
            try:
                state = json.loads(raw.decode("utf-8"), object_pairs_hook=self._unique_object)
            except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=503, detail="Companion state unavailable") from exc
            if not self._valid_state(state):
                self._error()
            return state
        finally:
            os.close(fd)

    @staticmethod
    def _unique_object(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate key")
            out[key] = value
        return out

    @staticmethod
    def _empty():
        return {"schema": 1, "revision": 0,
                "settings": {"enabled": False, "categories": []},
                "suggestions": [], "idempotency": {}}

    @staticmethod
    def _valid_state(state):
        if (not isinstance(state, dict) or set(state) != {"schema", "revision", "settings", "suggestions", "idempotency"}
                or state.get("schema") != 1 or not isinstance(state.get("revision"), int)
                or isinstance(state.get("revision"), bool) or state["revision"] < 0
                or not _valid_settings(state.get("settings"))
                or not isinstance(state.get("suggestions"), list)
                or len(state["suggestions"]) > _MAX_RECORDS
                or not isinstance(state.get("idempotency"), dict)
                or len(state["idempotency"]) > _MAX_IDEMPOTENCY):
            return False
        seen = set()
        for row in state["suggestions"]:
            if (not isinstance(row, dict) or set(row) != {"id", "category", "title", "reason", "source_ref",
                    "state", "created_at", "expires_at", "revision", "feedback"}
                    or not isinstance(row["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", row["id"])
                    or row["id"] in seen or not isinstance(row["category"], str)
                    or row["category"] not in _CATEGORIES
                    or not isinstance(row["title"], str) or len(row["title"].encode("utf-8")) > 4096
                    or not isinstance(row["reason"], str) or len(row["reason"].encode("utf-8")) > 256
                    or not isinstance(row["state"], str)
                    or row["state"] not in {"shown", "accepted", "dismissed"}
                    or (row["feedback"] is not None and not isinstance(row["feedback"], str))
                    or row["feedback"] not in {None, "accepted", "dismissed"}
                    or not isinstance(row["revision"], int) or isinstance(row["revision"], bool)
                    or row["revision"] < 1 or _parse_stamp(row["created_at"]) is None
                    or _parse_stamp(row["expires_at"]) is None):
                return False
            ref = row["source_ref"]
            if (not isinstance(ref, dict) or set(ref) != {"kind", "id", "version"}
                    or not isinstance(ref["kind"], str) or ref["kind"] not in {"task", "project"}
                    or not isinstance(ref["id"], str) or not ref["id"] or len(ref["id"]) > 256
                    or not isinstance(ref["version"], str) or not re.fullmatch(r"[a-f0-9]{64}", ref["version"])):
                return False
            seen.add(row["id"])
        for key, value in state["idempotency"].items():
            if (not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key)
                    or not isinstance(value, dict) or set(value) != {"fingerprint", "receipt"}
                    or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("fingerprint", "")))
                    or not isinstance(value.get("receipt"), dict)):
                return False
        return True

    def read(self):
        root_fd = self._root_fd()
        if root_fd is None:
            return self._empty()
        try:
            return self._read_at(root_fd)
        finally:
            os.close(root_fd)

    def _lock_at(self, root_fd):
        try:
            try:
                fd = os.open(".companion-suggestions.lock", os.O_CREAT | os.O_RDWR
                             | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            except FileNotFoundError:
                opened = os.fstat(root_fd)
                current = self.root.lstat()
                if ((opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
                        or not stat.S_ISDIR(current.st_mode)):
                    self._error()
                fd = os.open(".companion-suggestions.lock", os.O_CREAT | os.O_RDWR
                             | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            self._check_file(fd, writable=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
            return fd
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Companion state unavailable") from exc

    @staticmethod
    def _key_hash(key):
        if not isinstance(key, str) or not _IDEM_KEY.fullmatch(key):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        return hashlib.sha256(key.encode("ascii")).hexdigest()

    def _write_at(self, root_fd, state):
        payload = _canonical(state) + b"\n"
        if len(payload) > _MAX_STATE_BYTES:
            self._error()
        temp = ".companion-suggestions-" + uuid.uuid4().hex + ".tmp"
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=root_fd)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Companion state unavailable") from exc
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(fd)
            os.replace(temp, "companion-suggestions.json", src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError as exc:
            try:
                os.unlink(temp, dir_fd=root_fd)
            except OSError:
                pass
            raise HTTPException(status_code=503, detail="Companion state unavailable") from exc
        finally:
            os.close(fd)

    def _mutate(self, key, fingerprint, operation):
        root_fd = self._root_fd(create=True)
        lock_fd = None
        try:
            if root_fd is None:
                self._error()
            lock_fd = self._lock_at(root_fd)
            state = self._read_at(root_fd)
            prior = state["idempotency"].get(key)
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="Idempotency-Key conflict")
                return prior["receipt"]
            result, _changed = operation(state)
            state["idempotency"][key] = {"fingerprint": fingerprint, "receipt": result}
            if len(state["idempotency"]) > _MAX_IDEMPOTENCY:
                state["idempotency"].pop(next(iter(state["idempotency"])))
            self._write_at(root_fd, state)
            return result
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            if root_fd is not None:
                os.close(root_fd)

    def set_preferences(self, *, enabled, categories, expected_revision, idempotency_key):
        fingerprint = hashlib.sha256(_canonical({"enabled": enabled, "categories": categories,
                                                  "expected_revision": expected_revision})).hexdigest()
        key = self._key_hash(idempotency_key)

        def operation(state):
            if expected_revision != state["revision"]:
                raise HTTPException(status_code=409, detail="Companion preferences changed")
            state["revision"] += 1
            state["settings"] = {"enabled": enabled, "categories": categories}
            receipt = {"status": "saved", "revision": state["revision"], "settings": state["settings"]}
            return receipt, True
        return self._mutate(key, fingerprint, operation)

    def replace_suggestions(self, candidates, *, expected_revision, now=None):
        now = now or _utc_now()
        fingerprint = hashlib.sha256(_canonical({"at": _stamp(now), "candidates": candidates})).hexdigest()
        key = self._key_hash("evaluate-" + uuid.uuid4().hex)

        def operation(state):
            if state["revision"] != expected_revision:
                raise HTTPException(status_code=409, detail="Companion preferences changed")
            if not state["settings"]["enabled"]:
                return {"status": "disabled", "revision": state["revision"], "items": []}, False
            if any(item["category"] not in state["settings"]["categories"] for item in candidates):
                raise HTTPException(status_code=409, detail="Companion preferences changed")
            existing = state["suggestions"]
            visible = []
            for candidate in candidates:
                ref = candidate["source_ref"]
                identity = (candidate["category"], ref["kind"], ref["id"], ref["version"])
                recent = next((row for row in reversed(existing)
                               if (row["category"], row["source_ref"]["kind"], row["source_ref"]["id"],
                                   row["source_ref"]["version"]) == identity
                               and now - (_parse_stamp(row["created_at"]) or now) < _TTL), None)
                if recent is not None:
                    if recent["state"] == "shown" and _parse_stamp(recent["expires_at"]) > now:
                        visible.append(recent)
                    continue
                created = _stamp(now)
                row = {"id": uuid.uuid4().hex, "category": candidate["category"],
                       "title": candidate["title"], "reason": candidate["reason"],
                       "source_ref": ref, "state": "shown", "created_at": created,
                       "expires_at": _stamp(now + _TTL), "revision": 1, "feedback": None}
                existing.append(row)
                visible.append(row)
            state["suggestions"] = existing[-_MAX_RECORDS:]
            state["revision"] += 1
            result = {"status": "available" if visible else "none",
                      "revision": state["revision"], "items": [self._public(row) for row in visible]}
            return result, True
        return self._mutate(key, fingerprint, operation)

    def lookup_idempotent(self, idempotency_key, intent):
        key = self._key_hash(idempotency_key)
        fingerprint = hashlib.sha256(_canonical(intent)).hexdigest()
        prior = self.read()["idempotency"].get(key)
        if prior is None:
            return None
        if prior["fingerprint"] != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key conflict")
        return prior["receipt"]

    @staticmethod
    def _public(row):
        return {key: row[key] for key in ("id", "category", "title", "reason", "source_ref", "state", "expires_at")}

    def feedback(self, suggestion_id, *, decision, expected_revision, idempotency_key, now=None):
        now = now or _utc_now()
        fingerprint = hashlib.sha256(_canonical({"id": suggestion_id, "decision": decision,
                                                  "expected_revision": expected_revision})).hexdigest()
        key = self._key_hash(idempotency_key)

        def operation(state):
            row = next((item for item in state["suggestions"] if item["id"] == suggestion_id), None)
            if row is None:
                raise HTTPException(status_code=404, detail="Suggestion not found")
            if expected_revision != row["revision"] or row["state"] != "shown":
                raise HTTPException(status_code=409, detail="Suggestion changed")
            if _parse_stamp(row["expires_at"]) <= now:
                raise HTTPException(status_code=409, detail="Suggestion expired")
            row["state"] = decision
            row["feedback"] = decision
            row["revision"] += 1
            state["revision"] += 1
            return {"status": "accepted" if decision == "accepted" else "dismissed",
                    "id": row["id"], "revision": row["revision"], "state": row["state"]}, True
        return self._mutate(key, fingerprint, operation)

    def active(self, *, now=None):
        now = now or _utc_now()
        state = self.read()
        if not state["settings"]["enabled"]:
            return state, []
        rows = [self._public(row) for row in state["suggestions"]
                if row["state"] == "shown" and row["category"] in state["settings"]["categories"]
                and _parse_stamp(row["expires_at"]) > now]
        return state, rows


def create_companion_suggestions_router(auth, store, task_store, projects_store):
    router = APIRouter(prefix="/api/companion", tags=["companion-suggestions"])

    def set_no_store(response):
        response.headers["Cache-Control"] = "private, no-store"

    def verify_sources(rows, categories, *, task_rows=None, project_snapshot=None):
        valid = []
        task_by_id = {row.get("id"): row for row in (task_rows or []) if isinstance(row, dict)}
        projects_by_id = {row.project_id: row for row in
                          (project_snapshot.documents if project_snapshot and project_snapshot.available
                           and project_snapshot.complete else ())}
        for row in rows:
            if row["category"] not in categories:
                continue
            ref = row["source_ref"]
            if ref["kind"] == "task":
                current = task_by_id.get(ref["id"])
                if current is None or current.get("status") != "open":
                    continue
                version = task_source_version(current)
            elif ref["kind"] == "project":
                current = projects_by_id.get(ref["id"])
                if current is None:
                    continue
                version = current.sha256
            else:
                continue
            if version == ref["version"]:
                valid.append(row)
        return valid

    @router.get("/preferences")
    def get_preferences(request: Request, response: Response):
        auth.require_action(request, "companion.read")
        set_no_store(response)
        state = store.read()
        return {"event": "companion.preferences", "version": 1,
                "revision": state["revision"], **state["settings"]}

    @router.put("/preferences")
    async def put_preferences(request: Request, response: Response):
        auth.require_action(request, "companion.write")
        set_no_store(response)
        raw = await _bounded_body(request)
        try:
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=CompanionSuggestionStore._unique_object)
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid Companion preferences") from exc
        if (not isinstance(body, dict) or set(body) != {"enabled", "categories", "expected_revision"}
                or not isinstance(body["enabled"], bool) or not isinstance(body["categories"], list)
                or not all(isinstance(item, str) for item in body["categories"])
                or len(body["categories"]) > 2 or len(body["categories"]) != len(set(body["categories"]))
                or set(body["categories"]) - _CATEGORIES or not isinstance(body["expected_revision"], int)
                or isinstance(body["expected_revision"], bool) or body["expected_revision"] < 0
                or (body["enabled"] and not body["categories"])):
            raise HTTPException(status_code=400, detail="Invalid Companion preferences")
        result = store.set_preferences(enabled=body["enabled"], categories=body["categories"],
                                       expected_revision=body["expected_revision"],
                                       idempotency_key=request.headers.get("idempotency-key", ""))
        return {"event": "companion.preferences.receipt", "version": 1, **result}

    @router.post("/suggestions/evaluate")
    async def evaluate(request: Request, response: Response):
        auth.require_action(request, "companion.read")
        set_no_store(response)
        raw = await _bounded_body(request, 16)
        if raw not in (b"", b"{}"):
            raise HTTPException(status_code=400, detail="Invalid suggestion evaluation request")
        state = store.read()
        categories = state["settings"]["categories"] if state["settings"]["enabled"] else []
        if not categories:
            return {"event": "companion.suggestions", "version": 1,
                    "status": "disabled", "revision": state["revision"], "items": []}
        allowed = {}
        for category, action in (("task_due", "task.read"), ("project_next_step", "projects.read")):
            if category in categories:
                try:
                    auth.require_action(request, action)
                    allowed[category] = True
                except HTTPException as exc:
                    if exc.status_code != 403:
                        raise
                    allowed[category] = False
        now = _utc_now()
        local_day = now.astimezone(_SUGGESTION_ZONE).date()
        candidates = []
        failed = False
        if allowed.get("task_due"):
            try:
                auth.require_action(request, "task.read")
                if task_store is None:
                    raise ValueError("Task source unavailable")
                data = task_store.list_for_projection_read_only()["tasks"]
                if len(data) > _MAX_TASKS:
                    failed = True
                for task in data[:_MAX_TASKS]:
                    if task.get("status") != "open" or not isinstance(task.get("due_date"), str):
                        continue
                    try:
                        due = date.fromisoformat(task["due_date"])
                        if due.isoformat() != task["due_date"] or due > local_day + timedelta(days=7):
                            continue
                    except ValueError:
                        continue
                    version = task_source_version(task)
                    if version is None:
                        continue
                    candidates.append({"category": "task_due", "title": task["title"],
                                       "reason": "Due on " + task["due_date"],
                                       "source_ref": {"kind": "task", "id": task["id"], "version": version}})
            except Exception:
                failed = True
        if allowed.get("project_next_step"):
            try:
                auth.require_action(request, "projects.read")
                snapshot = projects_store.read_snapshot() if projects_store is not None else None
                if snapshot is None or not snapshot.configured or not snapshot.available or not snapshot.complete:
                    failed = True
                else:
                    for project in snapshot.documents[:_MAX_PROJECTS]:
                        doc = project.document
                        if doc.get("status") != "active" or not isinstance(doc.get("next_step"), str) or not doc["next_step"].strip():
                            continue
                        candidates.append({"category": "project_next_step", "title": doc["title"],
                                           "reason": "A next step is recorded for this project",
                                           "source_ref": {"kind": "project", "id": project.project_id,
                                                          "version": project.sha256}})
            except Exception:
                failed = True
        for category, action in (("task_due", "task.read"), ("project_next_step", "projects.read")):
            if category in categories and allowed.get(category):
                auth.require_action(request, action)
        auth.require_action(request, "companion.read")
        result = store.replace_suggestions(candidates, expected_revision=state["revision"])
        status = "partial" if failed or any(not value for value in allowed.values()) else result["status"]
        return {"event": "companion.suggestions", "version": 1,
                "status": status, "revision": result["revision"], "items": result["items"]}

    @router.get("/suggestions")
    def get_suggestions(request: Request, response: Response):
        auth.require_action(request, "companion.read")
        set_no_store(response)
        state, rows = store.active()
        if not rows:
            return {"event": "companion.suggestions", "version": 1,
                    "status": "disabled" if not state["settings"]["enabled"] else "none",
                    "revision": state["revision"], "items": []}
        categories = {row["category"] for row in rows}
        for category, action in (("task_due", "task.read"), ("project_next_step", "projects.read")):
            if any(row["category"] == category for row in rows):
                auth.require_action(request, action)
        try:
            task_rows = task_store.list_for_projection_read_only()["tasks"] if "task_due" in categories and task_store else []
            project_snapshot = projects_store.read_snapshot() if "project_next_step" in categories and projects_store else None
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Companion sources unavailable") from exc
        valid = verify_sources(rows, categories, task_rows=task_rows, project_snapshot=project_snapshot)
        for category, action in (("task_due", "task.read"), ("project_next_step", "projects.read")):
            if category in categories:
                auth.require_action(request, action)
        auth.require_action(request, "companion.read")
        latest = store.read()
        if latest["revision"] != state["revision"] or not latest["settings"]["enabled"]:
            return {"event": "companion.suggestions", "version": 1,
                    "status": "disabled" if not latest["settings"]["enabled"] else "partial",
                    "revision": latest["revision"], "items": []}
        return {"event": "companion.suggestions", "version": 1,
                "status": "available" if valid else "none", "revision": state["revision"], "items": valid}

    @router.post("/suggestions/{suggestion_id}/feedback")
    async def feedback(suggestion_id: str, request: Request, response: Response):
        auth.require_action(request, "companion.write")
        set_no_store(response)
        raw = await _bounded_body(request)
        try:
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=CompanionSuggestionStore._unique_object)
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid suggestion feedback") from exc
        if (len(raw) > 4096 or not isinstance(body, dict) or set(body) != {"decision", "expected_revision"}
                or not isinstance(body["decision"], str) or body["decision"] not in {"accepted", "dismissed"}
                or not isinstance(body["expected_revision"], int) or isinstance(body["expected_revision"], bool)
                or body["expected_revision"] < 1 or not re.fullmatch(r"[a-f0-9]{32}", suggestion_id)):
            raise HTTPException(status_code=400, detail="Invalid suggestion feedback")
        state = store.read()
        row = next((item for item in state["suggestions"] if item["id"] == suggestion_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        idem_key = request.headers.get("idempotency-key", "")
        intent = {"id": suggestion_id, "decision": body["decision"],
                  "expected_revision": body["expected_revision"]}
        replay = store.lookup_idempotent(idem_key, intent)
        if replay is not None:
            return {"event": "companion.suggestion.feedback", "version": 1, **replay}
        category = row["category"]
        if not state["settings"]["enabled"] or category not in state["settings"]["categories"]:
            raise HTTPException(status_code=409, detail="Suggestion is no longer enabled")
        action = "task.read" if category == "task_due" else "projects.read"
        auth.require_action(request, action)
        try:
            if category == "task_due":
                tasks = task_store.list_for_projection()["tasks"] if task_store else []
                current = next((item for item in tasks if item.get("id") == row["source_ref"]["id"]), None)
                current_version = task_source_version(current) if current and current.get("status") == "open" else None
            else:
                snapshot = projects_store.read_snapshot() if projects_store else None
                current = next((item for item in snapshot.documents if item.project_id == row["source_ref"]["id"]), None) if snapshot and snapshot.available and snapshot.complete else None
                current_version = current.sha256 if current else None
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Companion sources unavailable") from exc
        if current_version != row["source_ref"]["version"]:
            raise HTTPException(status_code=409, detail="Suggestion source changed")
        auth.require_action(request, "companion.write")
        auth.require_action(request, action)
        result = store.feedback(suggestion_id, decision=body["decision"],
                                expected_revision=body["expected_revision"],
                                idempotency_key=idem_key)
        return {"event": "companion.suggestion.feedback", "version": 1, **result}

    return router
