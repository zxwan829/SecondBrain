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
    removed = {unicodedata.normalize("NFC", item).casefold()
               for item in preferences.get("removed_tags", []) if isinstance(item, str)}
    system_tags = {unicodedata.normalize("NFC", item).casefold() for item in _SYSTEM_TAGS}
    canonical_tags = {unicodedata.normalize("NFC", value).casefold(): value for value in enabled_tags}
    tags = [canonical_tags.get(unicodedata.normalize("NFC", item).casefold()) or alias_map.get(unicodedata.normalize("NFC", item).casefold())
            for item in raw_tags if unicodedata.normalize("NFC", item).casefold() not in removed]
    tags = list(dict.fromkeys(tag for tag in tags if tag))
    recognized_inputs = set(canonical_tags) | set(alias_map)
    candidates = [item for item in raw_tags if unicodedata.normalize("NFC", item).casefold() not in removed
                  and unicodedata.normalize("NFC", item).casefold() not in system_tags
                  and unicodedata.normalize("NFC", item).casefold() not in recognized_inputs]
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
                          "target_execution_status": "not_executed", "history": []}
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
                item["target_execution_status"] = "not_supported" if item["kind"] in {"journal", "review", "project"} else "not_executed"
                self._event(item, decision, actor, item["decision_at"], key)
                return item
            return self._idempotent_mutation(record, data, key, actor, fingerprint, apply)

        return self._transaction(transaction)


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


def _source_from_record(record):
    return {key: record[key] for key in ("source_kind", "source_id", "collection", "path") if key in record}


def create_inbox_proposal_router(auth, store, sources, vocabulary_store=None):
    router = APIRouter(prefix="/api/inbox/proposals")

    def actor(request, action):
        return auth.require_action(request, f"inbox.proposals.{action}")

    def current(record, user):
        if vocabulary_store is not None and record["vocabulary_version"] != vocabulary_store.read().get("revision"):
            raise HTTPException(status_code=409, detail="Vocabulary changed; regenerate this suggestion")
        source = _source_from_record(record)
        canonical, version, _, _ = sources.resolve(source)
        if _source_key(canonical) != record["source_key"]:
            raise HTTPException(status_code=409, detail="Proposal source identity mismatch")
        return version

    @router.get("")
    def list_source(request: Request, source_kind: str, source_id: str,
                    collection: Optional[str] = None, path: Optional[str] = None):
        user = actor(request, "read")
        source = {"source_kind": source_kind, "source_id": source_id}
        if collection is not None:
            source["collection"] = collection
        if path is not None:
            source["path"] = path
        canonical, version, _, _ = sources.resolve(source)
        vocabulary_version = vocabulary_store.read().get("revision") if vocabulary_store is not None else None
        return store.for_source(canonical, version, user, vocabulary_version)

    @router.post("")
    def create_suggestions(request: Request, body: dict):
        user = actor(request, "write")
        source = {key: body.get(key) for key in ("source_kind", "source_id", "collection", "path") if body.get(key) is not None}
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
        try:
            version = current(record, user)
            if version != record["source_version"]:
                record = store.mark_stale(proposal_id, "source_version_changed", user)
        except HTTPException as exc:
            if exc.status_code not in {404, 409, 415, 422}:
                raise
            record = store.mark_stale(proposal_id, "source_unavailable", user)
        return {"proposal": record, "history": record["history"]}

    @router.put("/{proposal_id}")
    def edit_suggestion(request: Request, proposal_id: str, body: dict):
        user = actor(request, "write")
        key = request.headers.get("idempotency-key", "")
        replay = store.idempotent_result(proposal_id, "value", body.get("suggestion"), body.get("expected_version"), user, key)
        if replay is not None:
            return {"proposal": replay, "duplicate": True}
        record = store.get(proposal_id)
        try:
            version = current(record, user)
        except HTTPException as exc:
            if exc.status_code in {404, 409, 415, 422}:
                store.mark_stale(proposal_id, "source_unavailable", user)
                raise HTTPException(status_code=409, detail="Source is unavailable; suggestion is stale") from exc
            raise
        return {"proposal": store.edit(proposal_id, body.get("suggestion"), body.get("expected_version"), user,
                                        key, version), "duplicate": False}

    @router.post("/{proposal_id}/decision")
    def decide(request: Request, proposal_id: str, body: dict):
        user = actor(request, "write")
        key = request.headers.get("idempotency-key", "")
        replay = store.idempotent_result(proposal_id, "decision", body.get("decision"), body.get("expected_version"), user, key)
        if replay is not None:
            return {"proposal": replay, "duplicate": True}
        record = store.get(proposal_id)
        try:
            version = current(record, user)
        except HTTPException as exc:
            if exc.status_code in {404, 409, 415, 422}:
                store.mark_stale(proposal_id, "source_unavailable", user)
                raise HTTPException(status_code=409, detail="Source is unavailable; suggestion is stale") from exc
            raise
        return {"proposal": store.decide(proposal_id, body.get("decision"), body.get("expected_version"), user,
                                         key, version), "duplicate": False}

    return router
