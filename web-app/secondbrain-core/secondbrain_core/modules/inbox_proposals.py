"""Core-owned, source-versioned Inbox suggestion and decision records.

The store contains proposal metadata and audit state only. Notes and Capture
remain the source of truth; no proposal endpoint executes a target action.
"""
import fcntl
import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from .vocabulary import INITIAL_TYPES


_KINDS = {"type", "tags", "journal", "review", "project"}
_DECISIONS = {"approved_recorded", "rejected"}
_EXECUTION_STATES = {"not_executed", "executing", "executed", "failed_retryable",
                     "blocked", "stale", "not_implemented"}
_SYSTEM_TAGS = {"待整理", "整理中", "已整理"}
_IDEMPOTENCY_KEY = re.compile(r"^[\x21-\x7e]{1,255}$")
_CAPTURE_ID = re.compile(r"^[0-9a-f]{32}$")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_key(source):
    return _canonical_hash({key: source[key] for key in ("source_kind", "source_id", "collection", "path")
                            if key in source})


def _mock_suggestions(content, title, preferences, vocabulary):
    text = f"{title}\n{content}"
    journal_intent = bool(re.match(r"^\s*(?:记一下|记下来|写日记|记录一下)(?:[：:,，\s]+|$)", content))
    detected = ("日记" if journal_intent else "会议纪要" if re.search(r"会议|纪要|参会|议程", text)
                else "头脑风暴" if re.search(r"头脑风暴|brainstorm|发散", text, re.I)
                else "摘要" if re.search(r"摘要|总结|summary", text, re.I) else "笔记")
    enabled_types = [row["name"] for row in vocabulary.get("types", [])
                     if isinstance(row, dict) and row.get("enabled") is True and isinstance(row.get("name"), str)]
    enabled_tags = [row["name"] for row in vocabulary.get("tags", [])
                    if isinstance(row, dict) and row.get("enabled") is True and isinstance(row.get("name"), str)]
    tag_by_id = {row["id"]: row["name"] for row in vocabulary.get("tags", [])
                 if isinstance(row, dict) and row.get("enabled") is True and isinstance(row.get("id"), str)
                 and isinstance(row.get("name"), str)}
    alias_map = {unicodedata.normalize("NFC", row["alias"]).casefold(): tag_by_id[row["tag_id"]]
                 for row in vocabulary.get("synonyms", []) if isinstance(row, dict) and row.get("enabled") is True
                 and row.get("tag_id") in tag_by_id and isinstance(row.get("alias"), str)}
    manual_type = preferences.get("manual_type")
    if manual_type not in enabled_types:
        manual_type = None
    raw_tags = list(dict.fromkeys(re.findall(r"(?:^|\s)#([\w\u0080-\uffff-]{1,40})", text)))[:5]
    normalize_tag = lambda item: unicodedata.normalize("NFC", item).casefold()
    removed = {normalize_tag(item) for item in preferences.get("removed_tags", []) if isinstance(item, str)}
    system_tags = {unicodedata.normalize("NFC", item).casefold() for item in _SYSTEM_TAGS}
    canonical_tags = {unicodedata.normalize("NFC", value).casefold(): value for value in enabled_tags}
    canonicalized = [(item, canonical_tags.get(normalize_tag(item)) or alias_map.get(normalize_tag(item)))
                     for item in raw_tags]
    tags = [canonical for _, canonical in canonicalized
            if canonical and normalize_tag(canonical) not in removed]
    tags = list(dict.fromkeys(tag for tag in tags if tag))
    recognized_inputs = set(canonical_tags) | set(alias_map)
    candidates = [item for item, canonical in canonicalized
                  if normalize_tag(item) not in system_tags and normalize_tag(item) not in recognized_inputs
                  and normalize_tag(item) not in removed
                  and (canonical is None or normalize_tag(canonical) not in removed)]
    project = re.search(r"项目\s*[：:]\s*([^\n，,。]+)", text)
    return {
        "type": {"value": manual_type or (detected if detected in enabled_types else (enabled_types[0] if enabled_types else "")),
                 "reason": "保留用户手动修正的类型。" if manual_type else "由确定性本地 Mock 规则推导。",
                 "vocabulary_values": enabled_types},
        "tags": {"values": tags, "unknown_candidates": candidates,
                 "removed_by_user": sorted(preferences.get("removed_tags", [])),
                 "vocabulary_values": enabled_tags},
        "journal": {"value": "检测到明确日记意图；请在来源中复核原文。" if journal_intent else "未检测到明确日记意图。",
                    "reason": "仅记录来源内意图提示，不复制正文或写入 Journal。"},
        "review": {"value": "建议在来源内复核是否需要提交 Review。",
                   "reason": "仅生成流程提示，不复制正文或创建 Review。"},
        "project": {"value": project.group(1).strip() if project else "", "reason": "仅采用显式项目字段。"},
    }


class InboxProposalStore:
    """Private JSON state using Core's existing lock/atomic-replace pattern."""

    def __init__(self, directory):
        self.root = Path(directory)
        if not self.root.is_absolute():
            raise ValueError("Inbox proposal directory must be absolute")
        self.root.mkdir(mode=0o700, parents=False, exist_ok=True)
        self.path = self.root / "proposals.json"
        self.lock_path = self.root / ".proposals.lock"
        self._check_private(self.root, directory=True)

    @staticmethod
    def _check_private(path, directory=False):
        try:
            info = path.lstat()
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Inbox proposal storage is unavailable") from exc
        expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not expected or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise HTTPException(status_code=500, detail="Inbox proposal storage is not private")

    def _lock(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=500, detail="Inbox proposal lock is unsafe")
            fcntl.flock(fd, fcntl.LOCK_EX)
            return fd
        except Exception:
            os.close(fd)
            raise

    def _read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {"records": {}, "idempotency": {}, "source_preferences": {}}
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Inbox proposal file could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=500, detail="Inbox proposal file is unsafe")
            if info.st_size > 10 * 1024 * 1024:
                raise HTTPException(status_code=500, detail="Inbox proposal state exceeds its size limit")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                data = json.load(stream)
            if (not isinstance(data, dict) or not all(isinstance(data.get(key), dict)
                                                      for key in ("records", "idempotency", "source_preferences"))):
                raise ValueError("invalid proposal state")
            for proposal_id, record in data["records"].items():
                if (not isinstance(proposal_id, str) or not isinstance(record, dict)
                        or record.get("proposal_id") != proposal_id or record.get("kind") not in _KINDS
                        or record.get("status") not in (_DECISIONS | {"suggested", "stale"})
                        or not isinstance(record.get("source_key"), str)
                        or not isinstance(record.get("source_version"), str)
                        or not isinstance(record.get("vocabulary_version"), (int, str))
                        or not isinstance(record.get("version"), int)
                        or not isinstance(record.get("suggestion"), dict)
                        or not isinstance(record.get("history"), list)):
                    raise ValueError("invalid proposal record")
                legacy_execution_status = record.get("target_execution_status", "not_executed")
                if legacy_execution_status == "not_supported":
                    # PR #59's approved_recorded rows predate C2c execution.
                    # Normalize them as history only; never infer execution.
                    legacy_execution_status = "not_implemented" if record.get("kind") == "project" else "not_executed"
                    record["target_execution_status"] = legacy_execution_status
                execution = record.setdefault("execution", {"status": legacy_execution_status})
                if (not isinstance(execution, dict) or execution.get("status") not in _EXECUTION_STATES
                        or (execution.get("attempt_id") is not None and not isinstance(execution.get("attempt_id"), str))
                        or ("attempts" in execution and not isinstance(execution.get("attempts"), list))):
                    raise ValueError("invalid proposal execution record")
            if any(not isinstance(value, dict) for value in data["idempotency"].values()):
                raise ValueError("invalid proposal idempotency state")
            if any(not isinstance(value, dict) for value in data["source_preferences"].values()):
                raise ValueError("invalid proposal preference state")
            return data
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Inbox proposal state is corrupt") from exc
        finally:
            os.close(fd)

    def _write(self, data):
        temporary = self.root / f".proposals-{uuid.uuid4().hex}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
                json.dump(data, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
            temporary.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Inbox proposal update failed safely") from exc
        finally:
            os.close(fd)

    def _transaction(self, callback):
        fd = self._lock()
        try:
            data = self._read()
            result, changed = callback(data)
            if changed:
                self._write(data)
            return result
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _idem_key(key):
        if not isinstance(key, str) or not _IDEMPOTENCY_KEY.fullmatch(key):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        return hashlib.sha256(key.encode("ascii")).hexdigest()

    @staticmethod
    def _event(record, event, actor, at, request_id=None):
        row = {"event": event, "actor": actor, "at": at, "version": record["version"]}
        if request_id:
            row["request_id"] = request_id
        record.setdefault("history", []).append(row)

    def create(self, source, source_version, suggestions, actor, idempotency_key, vocabulary_version=0):
        key_hash = self._idem_key(idempotency_key)
        source_key = _source_key(source)
        fingerprint = _canonical_hash({"source_key": source_key, "source_version": source_version,
                                       "suggestions": suggestions})

        def operation(data):
            prior = data["idempotency"].get(key_hash)
            if prior:
                if prior.get("fingerprint") != fingerprint or prior.get("actor") != actor:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used for another request")
                return {"status": "duplicate", "proposals": [data["records"][pid] for pid in prior["proposal_ids"]]}, False
            now = _now()
            records = []
            for kind, value in suggestions.items():
                if kind not in _KINDS:
                    raise HTTPException(status_code=400, detail="Unsupported proposal kind")
                for existing in data["records"].values():
                    if existing["source_key"] == source_key and existing["kind"] == kind and existing["status"] == "suggested":
                        existing["status"] = "stale"
                        existing["updated_at"] = now
                        existing["version"] += 1
                        existing["stale_reason"] = "superseded_by_new_suggestion"
                        self._event(existing, "stale", actor, now, idempotency_key)
                proposal_id = uuid.uuid4().hex
                record = {"proposal_id": proposal_id, **source, "source_key": source_key,
                          "source_version": source_version, "kind": kind,
                          "suggestion": {"original": value, "current": value},
                          "vocabulary_version": vocabulary_version, "status": "suggested",
                          "actor": actor, "created_at": now, "updated_at": now, "decision_at": None,
                          "version": 1, "request_id": idempotency_key,
                          "target_execution_status": "not_executed",
                          "execution": {"status": "not_executed"}, "history": []}
                self._event(record, "suggested", actor, now, idempotency_key)
                data["records"][proposal_id] = record
                records.append(record)
            data["idempotency"][key_hash] = {"fingerprint": fingerprint, "actor": actor,
                                             "proposal_ids": [record["proposal_id"] for record in records]}
            return {"status": "created", "proposals": records}, True

        return self._transaction(operation)

    def preferences(self, source):
        return self._transaction(lambda data: (dict(data["source_preferences"].get(_source_key(source), {})), False))

    def for_source(self, source, source_version, actor, vocabulary_version=None):
        source_key = _source_key(source)

        def operation(data):
            now = _now()
            changed = False
            records = [item for item in data["records"].values() if item["source_key"] == source_key]
            for record in records:
                if ((record["source_version"] != source_version
                     or (vocabulary_version is not None and record["vocabulary_version"] != vocabulary_version))
                        and record["status"] != "stale"):
                    record["status"] = "stale"
                    record["stale_reason"] = "source_or_vocabulary_version_changed"
                    record["updated_at"] = now
                    record["version"] += 1
                    self._event(record, "stale", actor, now)
                    changed = True
            records.sort(key=lambda item: (item["created_at"], item["proposal_id"]))
            return {"proposals": records}, changed

        return self._transaction(operation)

    def get(self, proposal_id):
        def operation(data):
            record = data["records"].get(proposal_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            return dict(record), False
        return self._transaction(operation)

    def idempotent_result(self, proposal_id, operation, value, expected_version, actor, key):
        key_hash = self._idem_key(key)
        fingerprint = _canonical_hash({"proposal_id": proposal_id, operation: value, "version": expected_version})
        def lookup(data):
            prior = data["idempotency"].get(key_hash)
            if not prior:
                return None, False
            if prior.get("fingerprint") != fingerprint or prior.get("actor") != actor:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for another request")
            return data["records"].get(prior.get("proposal_id") or (prior.get("proposal_ids") or [None])[0]), False
        return self._transaction(lookup)

    def mark_stale(self, proposal_id, reason, actor):
        def operation(data):
            record = data["records"].get(proposal_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            if record["status"] != "stale":
                record["status"] = "stale"
                record["stale_reason"] = reason
                execution = record.setdefault("execution", {"status": record.get("target_execution_status", "not_executed")})
                if execution.get("status") not in {"executed", "not_implemented"}:
                    execution.update({"status": "stale", "error_code": reason})
                    record["target_execution_status"] = "stale"
                record["updated_at"] = _now()
                record["version"] += 1
                self._event(record, "stale", actor, record["updated_at"])
                return dict(record), True
            return dict(record), False
        return self._transaction(operation)

    def _idempotent_mutation(self, record, data, key, actor, fingerprint, operation):
        key_hash = self._idem_key(key)
        prior = data["idempotency"].get(key_hash)
        if prior:
            if prior.get("fingerprint") != fingerprint or prior.get("actor") != actor:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for another request")
            return data["records"][prior["proposal_id"]], False
        result = operation(record, data)
        data["idempotency"][key_hash] = {"fingerprint": fingerprint, "actor": actor,
                                         "proposal_id": record["proposal_id"]}
        return result, True

    def edit(self, proposal_id, value, expected_version, actor, key, current_source_version):
        fingerprint = _canonical_hash({"proposal_id": proposal_id, "value": value, "version": expected_version})

        def transaction(data):
            record = data["records"].get(proposal_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            def apply(item, state):
                if item["source_version"] != current_source_version:
                    raise HTTPException(status_code=409, detail="Source changed; regenerate this suggestion")
                if item["version"] != expected_version:
                    raise HTTPException(status_code=412, detail="Proposal changed; reload before editing")
                if item["status"] != "suggested":
                    raise HTTPException(status_code=409, detail="Only pending suggestions can be edited")
                normalized_value = self._validate_suggestion_value(item["kind"], value, item["suggestion"]["original"])
                item["suggestion"]["current"] = normalized_value
                item["version"] += 1
                item["updated_at"] = _now()
                self._event(item, "edited", actor, item["updated_at"], key)
                if item["kind"] == "type":
                    state["source_preferences"].setdefault(item["source_key"], {})["manual_type"] = value["value"]
                elif item["kind"] == "tags":
                    original = set(item["suggestion"]["original"].get("values", []))
                    current = set(normalized_value.get("values", []))
                    prefs = state["source_preferences"].setdefault(item["source_key"], {})
                    removed = set(prefs.get("removed_tags", [])) | (original - current)
                    removed -= current
                    prefs["removed_tags"] = sorted(removed)
                return item
            return self._idempotent_mutation(record, data, key, actor, fingerprint, apply)

        return self._transaction(transaction)

    @staticmethod
    def _validate_suggestion_value(kind, value, original):
        if kind == "type":
            allowed = original.get("vocabulary_values", []) if isinstance(original, dict) else []
            if (not isinstance(value, dict) or not isinstance(value.get("value"), str)
                    or value.get("value") not in allowed):
                raise HTTPException(status_code=400, detail="Type must use the current centralized vocabulary")
            return {"value": value["value"], "vocabulary_values": allowed}
        elif kind == "tags":
            values = value.get("values") if isinstance(value, dict) else None
            candidates = value.get("unknown_candidates") if isinstance(value, dict) else None
            allowed = original.get("vocabulary_values", []) if isinstance(original, dict) else []
            if (not isinstance(values, list) or not isinstance(allowed, list) or any(item not in allowed for item in values)
                    or not isinstance(candidates, list) or len(values) > 10 or len(candidates) > 10
                    or any(not isinstance(item, str) or len(item) > 40 or item in _SYSTEM_TAGS for item in candidates)):
                raise HTTPException(status_code=400, detail="Tags must use known demo values and separate unknown candidates")
            return {"values": list(dict.fromkeys(values)), "unknown_candidates": list(dict.fromkeys(candidates)),
                    "removed_by_user": original.get("removed_by_user", []), "vocabulary_values": allowed}
        elif not isinstance(value, dict) or not isinstance(value.get("value"), str) or len(value["value"]) > 4096:
            raise HTTPException(status_code=400, detail="Invalid proposal edit")
        return {"value": value["value"]}

    def decide(self, proposal_id, decision, expected_version, actor, key, current_source_version):
        if decision not in _DECISIONS:
            raise HTTPException(status_code=400, detail="Unsupported proposal decision")
        fingerprint = _canonical_hash({"proposal_id": proposal_id, "decision": decision,
                                       "version": expected_version})

        def transaction(data):
            record = data["records"].get(proposal_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            def apply(item, state):
                if item["kind"] in {"type", "tags"}:
                    raise HTTPException(status_code=400, detail="Existing type and tag metadata do not require per-note approval")
                if item["source_version"] != current_source_version:
                    raise HTTPException(status_code=409, detail="Source changed; regenerate and review this suggestion")
                if item["version"] != expected_version:
                    raise HTTPException(status_code=412, detail="Proposal changed; reload before deciding")
                if item["status"] != "suggested":
                    raise HTTPException(status_code=409, detail="Proposal already has a recorded decision")
                item["status"] = decision
                item["decision_at"] = _now()
                item["updated_at"] = item["decision_at"]
                item["version"] += 1
                item["target_execution_status"] = "not_implemented" if item["kind"] == "project" else "not_executed"
                item["execution"] = {"status": item["target_execution_status"]}
                self._event(item, decision, actor, item["decision_at"], key)
                return item
            return self._idempotent_mutation(record, data, key, actor, fingerprint, apply)

        return self._transaction(transaction)

    def begin_execution(self, proposal_id, expected_version, actor, preview_sha256,
                        source_version, vocabulary_version, target_action, target, source_summary):
        """Durably reserve the one confirmed target execution for a proposal."""
        if not isinstance(preview_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", preview_sha256):
            raise HTTPException(status_code=400, detail="A verified execution preview is required")
        operation_key = "execution:" + proposal_id
        key_hash = self._idem_key(operation_key)
        fingerprint = _canonical_hash({"proposal_id": proposal_id, "preview_sha256": preview_sha256,
                                       "expected_version": expected_version, "target_action": target_action})

        def operation(data):
            record = data["records"].get(proposal_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            prior = data["idempotency"].get(key_hash)
            if prior:
                if prior.get("fingerprint") != fingerprint or prior.get("actor") != actor:
                    raise HTTPException(status_code=409, detail="This proposal already has a different execution preview")
                execution = record.get("execution", {})
                if execution.get("status") == "failed_retryable":
                    now = _now()
                    attempt_id = uuid.uuid4().hex
                    execution.update({"status": "executing", "attempt_id": attempt_id,
                                      "started_at": now, "updated_at": now})
                    execution.pop("error_code", None)
                    execution.setdefault("attempts", []).append({"attempt_id": attempt_id,
                        "actor": actor, "started_at": now, "status": "executing"})
                    record["target_execution_status"] = "executing"
                    record["updated_at"] = now
                    self._event(record, "execution_retry_started", actor, now, operation_key)
                    return dict(record), True
                return dict(record), False
            if record.get("kind") not in {"journal", "review"}:
                raise HTTPException(status_code=501, detail="This proposal target is not implemented")
            if record.get("status") != "approved_recorded":
                raise HTTPException(status_code=409, detail="Only an explicitly approved proposal can be executed")
            if record.get("version") != expected_version:
                raise HTTPException(status_code=412, detail="Proposal changed; reload and confirm the current preview")
            if record.get("source_version") != source_version or record.get("vocabulary_version") != vocabulary_version:
                raise HTTPException(status_code=409, detail="Source or vocabulary changed; proposal is stale")
            if any(candidate_id != proposal_id and candidate.get("source_key") == record.get("source_key")
                   and candidate.get("kind") == record.get("kind")
                   and candidate.get("source_version") == source_version
                   and candidate.get("vocabulary_version") == vocabulary_version
                   and candidate.get("status") == "approved_recorded"
                   and candidate.get("execution", {}).get("status") in {
                       "executing", "executed", "failed_retryable", "blocked"}
                   for candidate_id, candidate in data["records"].items()):
                raise HTTPException(status_code=409, detail="A proposal for this source and target already has an execution attempt")
            execution = record.setdefault("execution", {"status": "not_executed"})
            if execution.get("status") != "not_executed":
                raise HTTPException(status_code=409, detail="This proposal already has an execution attempt")
            now = _now()
            execution.update({"status": "executing", "attempt_id": uuid.uuid4().hex,
                              "actor": actor, "target_action": target_action,
                              "preview_sha256": preview_sha256, "source_version": source_version,
                              "vocabulary_version": vocabulary_version, "started_at": now,
                              "updated_at": now, "target": target, "source_summary": source_summary})
            execution.setdefault("attempts", []).append({"attempt_id": execution["attempt_id"],
                "actor": actor, "started_at": now, "status": "executing"})
            record["target_execution_status"] = "executing"
            record["updated_at"] = now
            self._event(record, "execution_started", actor, now, operation_key)
            data["idempotency"][key_hash] = {"fingerprint": fingerprint, "actor": actor,
                                             "proposal_id": proposal_id}
            return dict(record), True

        return self._transaction(operation)

    def finish_execution(self, proposal_id, actor, *, status, result=None, error_code=None):
        if status not in {"executed", "failed_retryable", "blocked"}:
            raise HTTPException(status_code=400, detail="Invalid execution outcome")

        def operation(data):
            record = data["records"].get(proposal_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Proposal not found")
            execution = record.setdefault("execution", {"status": "not_executed"})
            if execution.get("status") == "executed":
                return dict(record), False
            if execution.get("status") not in {"executing", "failed_retryable"}:
                raise HTTPException(status_code=409, detail="Proposal has no resumable execution attempt")
            now = _now()
            execution.update({"status": status, "updated_at": now})
            record["target_execution_status"] = status
            if error_code:
                execution["error_code"] = str(error_code)[:80]
            else:
                execution.pop("error_code", None)
            attempts = execution.get("attempts", [])
            if attempts and isinstance(attempts[-1], dict):
                attempts[-1].update({"status": status, "completed_at": now,
                                     **({"error_code": str(error_code)[:80]} if error_code else {})})
            if isinstance(result, dict):
                for field in ("target_id", "target_uri", "target_status", "target_sha256", "output_sha256"):
                    value = result.get(field)
                    if isinstance(value, str):
                        execution[field] = value[:1024]
                execution["completed_at"] = now if status == "executed" else None
            record["updated_at"] = now
            event = "execution_succeeded" if status == "executed" else "execution_failed" if status == "failed_retryable" else "execution_blocked"
            self._event(record, event, actor, now, execution.get("attempt_id"))
            return dict(record), True

        return self._transaction(operation)


class InboxProposalSources:
    def __init__(self, capture, notes_store):
        self.capture = capture
        self.notes_store = notes_store

    def resolve(self, source):
        kind = source.get("source_kind")
        if kind == "capture":
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not _CAPTURE_ID.fullmatch(source_id):
                raise HTTPException(status_code=404, detail="Capture source not found")
            state = self.capture.get(source_id)
            raw_name = state.get("raw_path")
            if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in {".", ".."}:
                raise HTTPException(status_code=404, detail="Capture source is invalid")
            try:
                root_fd = os.open(self.capture.raw_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                  getattr(os, "O_NOFOLLOW", 0))
                try:
                    raw_fd = os.open(raw_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                finally:
                    os.close(root_fd)
                digest = hashlib.sha256()
                with os.fdopen(raw_fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 50 * 1024 * 1024:
                        raise HTTPException(status_code=404, detail="Capture source is unsafe")
                    for chunk in iter(lambda: stream.read(65536), b""):
                        digest.update(chunk)
            except HTTPException:
                raise
            except OSError as exc:
                raise HTTPException(status_code=404, detail="Capture source is unavailable") from exc
            raw_hash = digest.hexdigest()
            if state.get("raw_sha256") != raw_hash:
                raise HTTPException(status_code=409, detail="Capture source changed or failed integrity verification")
            canonical = {"source_kind": "capture", "source_id": source_id}
            source_data = {**canonical, "raw_sha256": raw_hash, "source_type": state.get("source_type", ""),
                           "input_type": state.get("input_type", ""), "title": state.get("title", ""),
                           "content_preview": state.get("content_preview", "")}
            return canonical, _canonical_hash(source_data), state.get("content_preview", ""), state.get("title", "")
        if kind == "notes":
            collection, path = source.get("collection"), source.get("path")
            if not isinstance(collection, str) or not isinstance(path, str):
                raise HTTPException(status_code=404, detail="Notes source not found")
            result = self.notes_store.read(collection, path)
            canonical = {"source_kind": "notes", "source_id": f"{collection}:{path}",
                         "collection": collection, "path": path}
            title = next((line[2:].strip() for line in result["content"].splitlines() if line.startswith("# ")), Path(path).stem)
            return canonical, result["etag"], result["content"], title
        raise HTTPException(status_code=400, detail="Unsupported Inbox source kind")

    def execution_content(self, source):
        """Read bounded textual source bytes again for an explicit target preview."""
        canonical, version, _, _ = self.resolve(source)
        if canonical["source_kind"] == "notes":
            result = self.notes_store.read(canonical["collection"], canonical["path"])
            content = result.get("content")
            version = result.get("etag")
            title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), Path(canonical["path"]).stem)
        else:
            state = self.capture.get(canonical["source_id"])
            if state.get("input_type") not in {"txt", "text", "markdown", "md", "capture_context"}:
                raise HTTPException(status_code=415, detail="Only textual Capture sources can be executed in C2c-1")
            raw_name = state.get("raw_path")
            if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in {".", ".."}:
                raise HTTPException(status_code=404, detail="Capture source is invalid")
            try:
                root_fd = os.open(self.capture.raw_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                  getattr(os, "O_NOFOLLOW", 0))
                try:
                    raw_fd = os.open(raw_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                finally:
                    os.close(root_fd)
                with os.fdopen(raw_fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 200_000:
                        raise HTTPException(status_code=413, detail="Capture text exceeds the C2c execution limit")
                    raw = stream.read(200_001)
            except HTTPException:
                raise
            except OSError as exc:
                raise HTTPException(status_code=409, detail="Capture source is unavailable") from exc
            raw_hash = hashlib.sha256(raw).hexdigest()
            if state.get("raw_sha256") != raw_hash:
                raise HTTPException(status_code=409, detail="Capture source changed or failed integrity verification")
            try:
                content = raw.decode("utf-8-sig", errors="strict")
            except UnicodeError as exc:
                raise HTTPException(status_code=415, detail="Capture source is not valid UTF-8 text") from exc
            title = state.get("title") or Path(raw_name).stem
        if not isinstance(content, str) or len(content.encode("utf-8")) > 200_000:
            raise HTTPException(status_code=413, detail="Source text exceeds the C2c execution limit")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return canonical, version, content, title, content_hash


def _source_from_record(record):
    return {key: record[key] for key in ("source_kind", "source_id", "collection", "path") if key in record}


def create_inbox_proposal_router(auth, store, sources, vocabulary_store=None,
                                 journal_store=None, capture_service=None):
    router = APIRouter(prefix="/api/inbox/proposals")

    def actor(request, action):
        return auth.require_action(request, f"inbox.proposals.{action}")

    def authorize_source(request, source):
        kind = source.get("source_kind")
        if kind == "notes":
            collection, path = source.get("collection"), source.get("path")
            if (not isinstance(collection, str) or collection not in getattr(sources.notes_store, "roots", {})
                    or not isinstance(path, str) or source.get("source_id") != f"{collection}:{path}"):
                raise HTTPException(status_code=404, detail="Notes source not found")
            auth.require_action(request, "notes.read")
            return
        if kind == "capture":
            if not isinstance(source.get("source_id"), str) or not _CAPTURE_ID.fullmatch(source["source_id"]):
                raise HTTPException(status_code=404, detail="Capture source not found")
            # Capture originals are exposed by the existing Inbox read gate.
            auth.require_action(request, "inbox.read")
            return
        raise HTTPException(status_code=404, detail="Inbox source not found")

    def current(record, user):
        if vocabulary_store is not None and record["vocabulary_version"] != vocabulary_store.read().get("revision"):
            raise HTTPException(status_code=409, detail="Vocabulary changed; regenerate this suggestion")
        source = _source_from_record(record)
        canonical, version, _, _ = sources.resolve(source)
        if _source_key(canonical) != record["source_key"]:
            raise HTTPException(status_code=409, detail="Proposal source identity mismatch")
        return version

    def execution_preview(record, user, body):
        if record.get("status") != "approved_recorded":
            raise HTTPException(status_code=409, detail="Record a human approval before preparing execution")
        if record.get("kind") == "project":
            return {"status": "not_implemented", "proposal_id": record["proposal_id"],
                    "message": "Project association execution is not implemented in C2c-1"}
        if record.get("kind") not in {"journal", "review"}:
            raise HTTPException(status_code=409, detail="This proposal has no executable target")
        try:
            version = current(record, user)
            require_current_source_version(record["proposal_id"], record, version, user)
            canonical, source_version, source_text, source_title, source_content_sha = sources.execution_content(
                _source_from_record(record))
        except HTTPException as exc:
            if exc.status_code in {404, 409, 415, 422}:
                store.mark_stale(record["proposal_id"], "source_or_vocabulary_changed", user)
            raise
        if source_version != record["source_version"]:
            store.mark_stale(record["proposal_id"], "source_version_changed", user)
            raise HTTPException(status_code=409, detail="Source changed; proposal is stale")
        vocabulary_version = vocabulary_store.read().get("revision") if vocabulary_store is not None else record["vocabulary_version"]
        if vocabulary_version != record["vocabulary_version"]:
            store.mark_stale(record["proposal_id"], "vocabulary_version_changed", user)
            raise HTTPException(status_code=409, detail="Vocabulary changed; proposal is stale")
        saved_target = record.get("execution", {}).get("target") if record.get("execution", {}).get("status") in {"failed_retryable", "executing"} else None
        target_text = body.get("target_text", (saved_target or {}).get("text", source_text))
        target_title = body.get("target_title", (saved_target or {}).get("title", source_title))
        target_date = body.get("target_date", (saved_target or {}).get("date", journal_store.today() if journal_store is not None else JournalStore.today()))
        if not isinstance(target_text, str) or not target_text.strip():
            raise HTTPException(status_code=400, detail="Execution preview text is required")
        if record["kind"] == "journal":
            if journal_store is None:
                raise HTTPException(status_code=503, detail="Journal execution is not enabled")
            if len(target_text.encode("utf-8")) > 16_384:
                raise HTTPException(status_code=413, detail="Journal entry is too long")
            if not isinstance(target_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
                raise HTTPException(status_code=400, detail="Journal date must use YYYY-MM-DD")
            target_action = "journal.append"
            target = {"date": target_date, "text": target_text}
        else:
            if capture_service is None:
                raise HTTPException(status_code=503, detail="Review submission is not enabled")
            if not isinstance(target_title, str) or not target_title.strip() or len(target_title) > 160:
                raise HTTPException(status_code=400, detail="Review title must contain 1-160 characters")
            target_action = "capture.write"
            target = {"title": target_title, "text": target_text}
        source_ref = canonical.get("path") or canonical.get("source_id")
        source_summary = {"source_kind": canonical["source_kind"], "source_ref": source_ref,
                          "source_version": source_version, "source_content_sha256": source_content_sha}
        digest = _canonical_hash({"proposal_id": record["proposal_id"], "kind": record["kind"],
                                  "source_summary": source_summary, "vocabulary_version": vocabulary_version,
                                  "target_action": target_action, "target": target})
        return {"status": "ready", "proposal_id": record["proposal_id"], "kind": record["kind"],
                "proposal_version": record["version"], "vocabulary_version": vocabulary_version,
                "source_summary": source_summary, "target_action": target_action,
                "target": target, "preview_sha256": digest}

    def require_current_source_version(proposal_id, record, version, user):
        if version != record["source_version"]:
            store.mark_stale(proposal_id, "source_version_changed", user)
            raise HTTPException(status_code=409, detail="Source changed; proposal is stale and must be regenerated")

    @router.get("")
    def list_source(request: Request, source_kind: str, source_id: str,
                    collection: Optional[str] = None, path: Optional[str] = None):
        user = actor(request, "read")
        source = {"source_kind": source_kind, "source_id": source_id}
        if collection is not None:
            source["collection"] = collection
        if path is not None:
            source["path"] = path
        authorize_source(request, source)
        canonical, version, _, _ = sources.resolve(source)
        vocabulary_version = vocabulary_store.read().get("revision") if vocabulary_store is not None else None
        return store.for_source(canonical, version, user, vocabulary_version)

    @router.post("")
    def create_suggestions(request: Request, body: dict):
        user = actor(request, "write")
        source = {key: body.get(key) for key in ("source_kind", "source_id", "collection", "path") if body.get(key) is not None}
        authorize_source(request, source)
        canonical, version, content, title = sources.resolve(source)
        preferences = store.preferences(canonical)
        vocabulary = vocabulary_store.read() if vocabulary_store is not None else {
            "revision": 0, "types": [{"name": name, "enabled": True} for name in INITIAL_TYPES], "tags": [], "synonyms": []}
        generated = _mock_suggestions(content, title, preferences, vocabulary)
        result = store.create(canonical, version, generated, user, request.headers.get("idempotency-key", ""),
                              vocabulary_version=vocabulary.get("revision", 0))
        return result

    @router.get("/{proposal_id}/history")
    def history(request: Request, proposal_id: str):
        user = actor(request, "read")
        record = store.get(proposal_id)
        authorize_source(request, _source_from_record(record))
        try:
            version = current(record, user)
            if version != record["source_version"]:
                record = store.mark_stale(proposal_id, "source_version_changed", user)
        except HTTPException as exc:
            if exc.status_code not in {404, 409, 415, 422}:
                raise
            if isinstance(exc.detail, str) and exc.detail.startswith("Vocabulary changed"):
                record = store.mark_stale(proposal_id, "vocabulary_version_changed", user)
                return {"proposal": record, "history": record["history"]}
            store.mark_stale(proposal_id, "source_unavailable", user)
            raise HTTPException(status_code=409, detail="Source is unavailable; proposal history is unavailable") from exc
        return {"proposal": record, "history": record["history"]}

    @router.put("/{proposal_id}")
    def edit_suggestion(request: Request, proposal_id: str, body: dict):
        user = actor(request, "write")
        key = request.headers.get("idempotency-key", "")
        record = store.get(proposal_id)
        authorize_source(request, _source_from_record(record))
        try:
            version = current(record, user)
        except HTTPException as exc:
            if exc.status_code in {404, 409, 415, 422}:
                vocabulary_changed = isinstance(exc.detail, str) and exc.detail.startswith("Vocabulary changed")
                reason = "vocabulary_version_changed" if vocabulary_changed else "source_unavailable"
                store.mark_stale(proposal_id, reason, user)
                raise HTTPException(status_code=409, detail=f"{exc.detail}; proposal is stale") from exc
            raise
        require_current_source_version(proposal_id, record, version, user)
        replay = store.idempotent_result(proposal_id, "value", body.get("suggestion"), body.get("expected_version"), user, key)
        if replay is not None:
            return {"proposal": replay, "duplicate": True}
        return {"proposal": store.edit(proposal_id, body.get("suggestion"), body.get("expected_version"), user,
                                        key, version), "duplicate": False}

    @router.post("/{proposal_id}/decision")
    def decide(request: Request, proposal_id: str, body: dict):
        user = actor(request, "write")
        key = request.headers.get("idempotency-key", "")
        record = store.get(proposal_id)
        authorize_source(request, _source_from_record(record))
        try:
            version = current(record, user)
        except HTTPException as exc:
            if exc.status_code in {404, 409, 415, 422}:
                vocabulary_changed = isinstance(exc.detail, str) and exc.detail.startswith("Vocabulary changed")
                reason = "vocabulary_version_changed" if vocabulary_changed else "source_unavailable"
                store.mark_stale(proposal_id, reason, user)
                raise HTTPException(status_code=409, detail=f"{exc.detail}; proposal is stale") from exc
            raise
        require_current_source_version(proposal_id, record, version, user)
        replay = store.idempotent_result(proposal_id, "decision", body.get("decision"), body.get("expected_version"), user, key)
        if replay is not None:
            return {"proposal": replay, "duplicate": True}
        return {"proposal": store.decide(proposal_id, body.get("decision"), body.get("expected_version"), user,
                                         key, version), "duplicate": False}

    @router.post("/{proposal_id}/execution-preview")
    def preview_execution(request: Request, proposal_id: str, body: dict):
        user = actor(request, "read")
        record = store.get(proposal_id)
        authorize_source(request, _source_from_record(record))
        return execution_preview(record, user, body)

    @router.post("/{proposal_id}/execute")
    def execute(request: Request, proposal_id: str, body: dict):
        # Preserve the existing human approval write gate and require the
        # target domain gate below; no new ambient execution capability.
        user = actor(request, "write")
        record = store.get(proposal_id)
        authorize_source(request, _source_from_record(record))
        if record.get("kind") == "project":
            raise HTTPException(status_code=501, detail="Project association execution is not implemented in C2c-1")
        preview = execution_preview(record, user, body)
        if preview.get("status") != "ready" or body.get("confirmed") is not True:
            raise HTTPException(status_code=400, detail="Explicit confirmation of a ready execution preview is required")
        if body.get("preview_sha256") != preview["preview_sha256"]:
            raise HTTPException(status_code=409, detail="Execution preview changed; review the current preview again")
        target_action = preview["target_action"]
        auth.require_action(request, target_action)
        # Re-read the source immediately before reserving and invoking its dedicated target store.
        latest = execution_preview(record, user, body)
        if latest["preview_sha256"] != preview["preview_sha256"]:
            store.mark_stale(proposal_id, "source_changed_before_execution", user)
            raise HTTPException(status_code=409, detail="Source or preview changed; execution was not started")
        started = store.begin_execution(
            proposal_id, preview["proposal_version"], user, preview["preview_sha256"],
            preview["source_summary"]["source_version"], preview["vocabulary_version"], target_action,
            preview["target"], preview["source_summary"])
        if started.get("execution", {}).get("status") == "executed":
            return {"proposal": started, "duplicate": True}
        if started.get("execution", {}).get("status") in {"blocked", "stale", "not_implemented"}:
            raise HTTPException(status_code=409, detail="This execution is blocked and cannot be retried")
        if started.get("execution", {}).get("status") not in {"executing", "failed_retryable"}:
            raise HTTPException(status_code=409, detail="No resumable execution attempt is available")
        execution_key = "c2c-" + proposal_id
        try:
            # Last source check before side effect. The stable downstream operation key
            # recovers the same Journal/Review target after a lost response or restart.
            latest = execution_preview(record, user, body)
            if latest["preview_sha256"] != preview["preview_sha256"]:
                store.mark_stale(proposal_id, "source_changed_before_target_write", user)
                raise HTTPException(status_code=409, detail="Source changed; target write was not started")
            target_replayed = False
            if record["kind"] == "journal":
                result = journal_store.append_approved_proposal(
                    preview["target"]["date"], preview["target"]["text"], execution_key,
                    proposal_id, str(preview["source_summary"]["source_ref"]),
                    preview["source_summary"]["source_content_sha256"])
                entry = result["entry"]
                target = {"target_id": entry["id"], "target_uri": "journal:" + result["date"],
                          "target_status": result["status"],
                          "target_sha256": preview["source_summary"]["source_content_sha256"],
                          "output_sha256": hashlib.sha256(entry["original_text"].encode("utf-8")).hexdigest()}
            else:
                state = capture_service.create_approved_review(
                    text=preview["target"]["text"], title=preview["target"]["title"],
                    execution_key=execution_key, proposal_id=proposal_id,
                    source_ref=str(preview["source_summary"]["source_ref"]),
                    source_version_sha256=preview["source_summary"]["source_content_sha256"],
                    captured_at=started["execution"]["started_at"])
                target_replayed = bool(state.pop("_idempotent_replay", False))
                target = {"target_id": state["capture_id"], "target_uri": state["review_path"],
                          "target_status": state["status"], "target_sha256": state["raw_sha256"],
                          "output_sha256": state["review_sha256"]}
            completed = store.finish_execution(proposal_id, user, status="executed", result=target)
            duplicate = (result.get("status") == "duplicate" if record["kind"] == "journal"
                         else target_replayed)
            return {"proposal": completed, "duplicate": duplicate}
        except HTTPException as exc:
            if exc.status_code == 409:
                try:
                    current_record = store.get(proposal_id)
                    if current_record.get("execution", {}).get("status") == "executing":
                        store.finish_execution(proposal_id, user, status="blocked", error_code="target_conflict")
                except HTTPException:
                    pass
                raise
            outcome = "failed_retryable" if exc.status_code >= 500 else "blocked"
            store.finish_execution(proposal_id, user, status=outcome, error_code=f"http_{exc.status_code}")
            raise
        except Exception as exc:
            store.finish_execution(proposal_id, user, status="failed_retryable", error_code="target_execution_error")
            raise HTTPException(status_code=503, detail="Target execution failed safely; retry the same confirmed preview") from exc

    return router
