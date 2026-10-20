from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from typing import Any

from .knowledge_read import _open_dir_chain


_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
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
    complete: bool
    documents: tuple[ProjectSourceDocument, ...]


class ProjectsSourceReadStore:
    """Bounded, read-only reader for an explicitly configured project source root.

    This is a source-reading layer, not the public Projects wire mapper. It
    never guesses a source path and never returns a filesystem path.
    """

    def __init__(self, root, *, max_entries=_DEFAULT_MAX_ENTRIES,
                 max_file_bytes=_DEFAULT_MAX_FILE_BYTES,
                 max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES):
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
        if not self.root:
            return ProjectSourceSnapshot(False, False, ())
        try:
            root_fd = _open_dir_chain(self.root)
        except OSError:
            return ProjectSourceSnapshot(True, False, ())
        complete = True
        bytes_read = 0
        entries_seen = 0
        by_id = {}
        duplicate_ids = set()
        try:
            try:
                entries = os.scandir(root_fd)
            except OSError:
                return ProjectSourceSnapshot(True, False, ())
            with entries:
                for entry in entries:
                    if entries_seen >= self.max_entries:
                        complete = False
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
                        if not isinstance(document, dict):
                            complete = False
                            continue
                        project_id = document.get("id")
                        if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
                            complete = False
                            continue
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
        return ProjectSourceSnapshot(True, complete, rows)
