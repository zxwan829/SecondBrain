"""Core-owned type/tag vocabulary; deliberately independent of Vault Markdown."""
import fcntl
import json
import os
import re
import stat
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

INITIAL_TYPES = ("日记", "笔记", "头脑风暴", "摘要", "会议纪要")
MAX_TYPES = 10
FRONTMATTER_TYPE_KEY = "类型"
FRONTMATTER_TAGS_KEY = "tags"
SYSTEM_METADATA_KEYS = frozenset({"状态", "创建日期", "修改日期"})
_RESERVED_NAMES = SYSTEM_METADATA_KEYS | {"待整理", "整理中", "已整理"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_name(value, field):
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"Invalid {field}")
    name = unicodedata.normalize("NFC", value).strip()
    if (not name or len(name) > 40 or name.startswith("#")
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or name in _RESERVED_NAMES):
        raise HTTPException(status_code=422, detail=f"Invalid {field}")
    return name


def _initial_state():
    return {
        "schema_version": 1,
        "revision": 0,
        "types": [{"id": f"builtin-{index + 1}", "name": name, "enabled": True, "built_in": True}
                  for index, name in enumerate(INITIAL_TYPES)],
        "tags": [],
        "synonyms": [],
        "audit": [],
    }


class VocabularyStore:
    """Atomic Core-private catalog with revision checks and co-located audit."""

    def __init__(self, state_root):
        self.state_root = Path(state_root)
        self.directory = self.state_root / "vocabulary"
        self.path = self.directory / "catalog.json"
        self.lock_path = self.directory / ".lock"

    def _ensure_directory(self):
        try:
            info = self.state_root.lstat()
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Core state unavailable") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise HTTPException(status_code=503, detail="Core state unavailable")
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise HTTPException(status_code=503, detail="Core state permissions are unsafe")
        self.directory.mkdir(mode=0o700, exist_ok=True)
        child = self.directory.lstat()
        if (not stat.S_ISDIR(child.st_mode) or stat.S_ISLNK(child.st_mode)
                or child.st_uid != os.geteuid() or child.st_mode & 0o077):
            raise HTTPException(status_code=503, detail="Vocabulary state permissions are unsafe")

    def _read(self):
        if not self.path.exists():
            return _initial_state()
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077 or info.st_size > 2_000_000):
                    raise HTTPException(status_code=503, detail="Vocabulary state file is unsafe")
                with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                    state = json.load(stream)
            finally:
                os.close(fd)
        except HTTPException:
            raise
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail="Vocabulary state could not be read safely") from exc
        if (not isinstance(state, dict) or state.get("schema_version") != 1
                or not isinstance(state.get("revision"), int)
                or any(not isinstance(state.get(key), list) for key in ("types", "tags", "synonyms", "audit"))):
            raise HTTPException(status_code=503, detail="Unsupported vocabulary state")
        return state

    def read(self):
        self._ensure_directory()
        return self._read()

    def _write_atomic(self, state):
        data = (json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        fd, temporary = tempfile.mkstemp(prefix=".catalog-", dir=self.directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _mutate(self, expected_revision, confirmed, operation, mutate):
        if confirmed is not True:
            raise HTTPException(status_code=400, detail="Explicit user confirmation is required")
        self._ensure_directory()
        try:
            lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.fchmod(lock_fd, 0o600)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Vocabulary lock unavailable") from exc
        try:
            lock_info = os.fstat(lock_fd)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                    or lock_info.st_mode & 0o077):
                raise HTTPException(status_code=503, detail="Vocabulary lock permissions are unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            state = self._read()
            if expected_revision != state["revision"]:
                raise HTTPException(status_code=412, detail="Vocabulary revision changed; reload before retrying")
            target = mutate(state)
            state["revision"] += 1
            state["audit"].append({"revision": state["revision"], "operation": operation,
                                   "actor": "owner", "target": target, "at": _now()})
            self._write_atomic(state)
            return state
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)

    @staticmethod
    def _unique(rows, name):
        return any(row.get("name", row.get("alias", "")).casefold() == name.casefold() for row in rows)

    def add_type(self, name, expected_revision, confirmed):
        name = _clean_name(name, "type")

        def mutate(state):
            if self._unique(state["types"], name):
                raise HTTPException(status_code=409, detail="Type already exists")
            if len(state["types"]) >= MAX_TYPES:
                raise HTTPException(status_code=409, detail="Type library limit reached")
            row = {"id": str(uuid.uuid4()), "name": name, "enabled": True, "built_in": False}
            state["types"].append(row)
            return {"kind": "type", "id": row["id"], "name": name}

        return self._mutate(expected_revision, confirmed, "type.add", mutate)

    def set_type_enabled(self, item_id, enabled, expected_revision, confirmed):
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=422, detail="Invalid enabled value")

        def mutate(state):
            row = next((item for item in state["types"] if item["id"] == item_id), None)
            if row is None:
                raise HTTPException(status_code=404, detail="Type not found")
            row["enabled"] = enabled
            return {"kind": "type", "id": item_id, "enabled": enabled}

        return self._mutate(expected_revision, confirmed, "type.set_enabled", mutate)

    def add_tag(self, name, expected_revision, confirmed):
        name = _clean_name(name, "tag")

        def mutate(state):
            if self._unique(state["tags"], name):
                raise HTTPException(status_code=409, detail="Tag already exists")
            row = {"id": str(uuid.uuid4()), "name": name, "enabled": True}
            state["tags"].append(row)
            return {"kind": "tag", "id": row["id"], "name": name}

        return self._mutate(expected_revision, confirmed, "tag.add", mutate)

    def set_tag_enabled(self, item_id, enabled, expected_revision, confirmed):
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=422, detail="Invalid enabled value")

        def mutate(state):
            row = next((item for item in state["tags"] if item["id"] == item_id), None)
            if row is None:
                raise HTTPException(status_code=404, detail="Tag not found")
            row["enabled"] = enabled
            return {"kind": "tag", "id": item_id, "enabled": enabled}

        return self._mutate(expected_revision, confirmed, "tag.set_enabled", mutate)

    def add_synonym(self, alias, tag_id, expected_revision, confirmed):
        alias = _clean_name(alias, "synonym")

        def mutate(state):
            tag = next((item for item in state["tags"] if item["id"] == tag_id), None)
            if tag is None or not tag["enabled"]:
                raise HTTPException(status_code=404, detail="Active target tag not found")
            if alias.casefold() == tag["name"].casefold() or self._unique(state["synonyms"], alias):
                raise HTTPException(status_code=409, detail="Synonym already exists or matches its target")
            row = {"id": str(uuid.uuid4()), "alias": alias, "tag_id": tag_id, "enabled": True}
            state["synonyms"].append(row)
            return {"kind": "synonym", "id": row["id"], "tag_id": tag_id, "alias": alias}

        return self._mutate(expected_revision, confirmed, "synonym.add", mutate)


@dataclass(frozen=True)
class NoteVocabularyOverrides:
    """Per-note policy metadata supplied by a future authorized integration."""
    type_value: Optional[str] = None
    type_manually_locked: bool = False
    manually_removed_tags: tuple[str, ...] = ()


def apply_automatic_metadata(overrides, suggested_type, suggested_tags, enabled_types, enabled_tags):
    """Pure contract for future note integrations; performs no Markdown writes."""
    selected_type = overrides.type_value if overrides.type_manually_locked else (
        suggested_type if suggested_type in set(enabled_types) else overrides.type_value
    )
    allowed_tags = {unicodedata.normalize("NFC", tag).casefold() for tag in enabled_tags}
    removed = {unicodedata.normalize("NFC", tag).casefold() for tag in overrides.manually_removed_tags}
    selected_tags = []
    for tag in suggested_tags:
        clean = _clean_name(tag, "tag")
        if (clean.casefold() in allowed_tags and clean.casefold() not in removed
                and all(existing.casefold() != clean.casefold() for existing in selected_tags)):
            selected_tags.append(clean)
    return {FRONTMATTER_TYPE_KEY: selected_type, FRONTMATTER_TAGS_KEY: selected_tags}


def preview_inventory_candidates(candidates, state):
    """Classify caller-supplied candidates only; never reads Vault paths or mutates state."""
    active = {row["name"].casefold() for row in state["tags"] if row["enabled"]}
    known = []
    new = []
    for candidate in candidates:
        name = _clean_name(candidate, "candidate")
        (known if name.casefold() in active else new).append(name)
    return {"known": sorted(set(known), key=str.casefold),
            "new_pending_review": sorted(set(new), key=str.casefold),
            "source_read": False, "persisted": False}


def create_vocabulary_router(auth, store):
    router = APIRouter(prefix="/api/vocabulary")

    def require(request, action):
        auth.require_action(request, f"vocabulary.{action}")

    def revision(request):
        raw = request.headers.get("if-match", "").strip().strip('"')
        if not re.fullmatch(r"\d+", raw):
            raise HTTPException(status_code=428, detail="If-Match vocabulary revision is required")
        return int(raw)

    def result(response, state):
        response.headers["ETag"] = f'"{state["revision"]}"'
        return state

    @router.get("")
    def read(request: Request, response: Response):
        require(request, "read")
        return result(response, store.read())

    @router.post("/types")
    def add_type(request: Request, response: Response, body: dict):
        require(request, "write")
        return result(response, store.add_type(body.get("name"), revision(request), body.get("confirmed")))

    @router.patch("/types/{item_id}")
    def set_type(request: Request, response: Response, item_id: str, body: dict):
        require(request, "write")
        return result(response, store.set_type_enabled(item_id, body.get("enabled"), revision(request), body.get("confirmed")))

    @router.post("/tags")
    def add_tag(request: Request, response: Response, body: dict):
        require(request, "write")
        return result(response, store.add_tag(body.get("name"), revision(request), body.get("confirmed")))

    @router.patch("/tags/{item_id}")
    def set_tag(request: Request, response: Response, item_id: str, body: dict):
        require(request, "write")
        return result(response, store.set_tag_enabled(item_id, body.get("enabled"), revision(request), body.get("confirmed")))

    @router.post("/synonyms")
    def add_synonym(request: Request, response: Response, body: dict):
        require(request, "write")
        return result(response, store.add_synonym(body.get("alias"), body.get("tag_id"), revision(request), body.get("confirmed")))

    return router
