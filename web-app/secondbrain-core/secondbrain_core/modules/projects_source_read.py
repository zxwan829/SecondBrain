from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .knowledge_read import _open_dir_chain


_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
_PROJECT_FIELDS = {"id", "title", "status", "next_step", "recent_activity",
                   "linked_notes", "updated_at"}
_PROJECT_STATUSES = {"active", "paused", "completed", "archived", "unknown"}
_DEFAULT_MAX_ENTRIES = 200
_DEFAULT_MAX_FILE_BYTES = 64 * 1024
_DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class ProjectSourceDocument:
    project_id: str
    sha256: str
    document: dict[str, Any]


@dataclass(frozen=True)
class ProjectSourceSnapshot:
    configured: bool
    available: bool
    complete: bool
    documents: tuple[ProjectSourceDocument, ...]
    has_more: bool = False

    @property
    def status(self):
        if not self.configured:
            return "not_configured"
        if not self.available:
            return "unavailable"
        if not self.complete:
            return "partial"
        return "complete"


def _valid_timestamp(value):
    if not isinstance(value, str) or len(value) > 64 or not _RFC3339.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _valid_project_document(document):
    if not isinstance(document, dict) or set(document) - _PROJECT_FIELDS:
        return False
    project_id = document.get("id")
    title = document.get("title")
    status = document.get("status")
    if (not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id)
            or not isinstance(title, str) or not title.strip() or len(title) > 300
            or not isinstance(status, str) or status not in _PROJECT_STATUSES):
        return False
    if "next_step" in document and (not isinstance(document["next_step"], str)
                                    or len(document["next_step"]) > 2000):
        return False
    if "updated_at" in document and not _valid_timestamp(document["updated_at"]):
        return False
    activity = document.get("recent_activity")
    if activity is not None:
        if (not isinstance(activity, dict) or set(activity) != {"kind", "occurred_at"}
                or not isinstance(activity["kind"], str) or not activity["kind"].strip()
                or len(activity["kind"]) > 80 or not _valid_timestamp(activity["occurred_at"])):
            return False
    linked_notes = document.get("linked_notes")
    if linked_notes is not None:
        if not isinstance(linked_notes, list) or len(linked_notes) > 100:
            return False
        for reference in linked_notes:
            if (not isinstance(reference, dict) or set(reference) != {"id", "version"}
                    or not isinstance(reference["id"], str)
                    or not _PROJECT_ID.fullmatch(reference["id"])
                    or not isinstance(reference["version"], str)
                    or not _SHA256.fullmatch(reference["version"])):
                return False
    return True


class ProjectsSourceReadStore:
    """Bounded, read-only reader for an explicitly configured project source root.

    This is a source-reading layer, not the public Projects wire mapper. It
    never guesses a source path and never returns a filesystem path.
    """

    def __init__(self, root, *, max_entries=_DEFAULT_MAX_ENTRIES,
                 max_file_bytes=_DEFAULT_MAX_FILE_BYTES,
                 max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES):
        self.configured = bool(root)
        self.root = root if isinstance(root, str) and os.path.isabs(root) else ""
        self.max_entries = max_entries
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    @staticmethod
    def _read_fd(fd, limit):
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read_snapshot(self):
        if not self.configured:
            return ProjectSourceSnapshot(False, False, False, ())
        if not self.root:
            return ProjectSourceSnapshot(True, False, False, ())
        try:
            root_fd = _open_dir_chain(self.root)
        except OSError:
            return ProjectSourceSnapshot(True, False, False, ())
        root_info = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                or root_info.st_mode & 0o077):
            os.close(root_fd)
            return ProjectSourceSnapshot(True, False, False, ())
        complete = True
        bytes_read = 0
        entries_seen = 0
        has_more = False
        by_id = {}
        duplicate_ids = set()
        try:
            try:
                entries = os.scandir(root_fd)
            except OSError:
                return ProjectSourceSnapshot(True, False, False, ())
            with entries:
                for entry in entries:
                    if entries_seen >= self.max_entries:
                        complete = False
                        has_more = True
                        break
                    entries_seen += 1
                    name = entry.name
                    if (not isinstance(name, str) or name in {"", ".", ".."}
                            or "/" in name or "\\" in name or "\x00" in name):
                        complete = False
                        continue
                    if not name.lower().endswith(".json"):
                        continue
                    try:
                        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                    except OSError:
                        complete = False
                        continue
                    try:
                        info = os.fstat(fd)
                        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                                or info.st_uid != os.geteuid() or info.st_mode & 0o077
                                or info.st_size < 0 or info.st_size > self.max_file_bytes
                                or bytes_read + info.st_size > self.max_total_bytes):
                            complete = False
                            continue
                        payload = self._read_fd(fd, min(
                            self.max_file_bytes, self.max_total_bytes - bytes_read,
                        ))
                        if len(payload) != info.st_size:
                            complete = False
                            continue
                        bytes_read += len(payload)
                        try:
                            document = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
                        except (UnicodeError, ValueError, json.JSONDecodeError):
                            complete = False
                            continue
                        if not _valid_project_document(document):
                            complete = False
                            continue
                        project_id = document["id"]
                        if project_id in by_id or project_id in duplicate_ids:
                            by_id.pop(project_id, None)
                            duplicate_ids.add(project_id)
                            complete = False
                            continue
                        by_id[project_id] = ProjectSourceDocument(
                            project_id=project_id,
                            sha256=hashlib.sha256(payload).hexdigest(),
                            document=document,
                        )
                    finally:
                        os.close(fd)
        finally:
            os.close(root_fd)
        rows = tuple(by_id[key] for key in sorted(by_id))
        return ProjectSourceSnapshot(True, True, complete, rows, has_more)
