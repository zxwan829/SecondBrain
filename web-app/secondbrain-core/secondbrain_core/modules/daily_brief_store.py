from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .knowledge_read import _open_dir_chain


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_RECORD_BYTES = 128 * 1024
_MAX_SOURCE_REFS = 50


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class DailyBriefRecordSnapshot:
    configured: bool
    available: bool
    found: bool
    record: dict[str, Any] | None
    sha256: str | None
    source_verification: str


class DailyBriefRecordReadStore:
    """Read one exact Core-owned daily record; never enumerates history or writes."""

    def __init__(self, root, *, max_record_bytes=_MAX_RECORD_BYTES,
                 max_source_refs=_MAX_SOURCE_REFS):
        self.root = root if isinstance(root, str) and os.path.isabs(root) else ""
        self.max_record_bytes = max_record_bytes
        self.max_source_refs = max_source_refs

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

    def read(self, day, timezone_name, source_verifier: Callable[[dict], bool] | None = None):
        if not self.root:
            return DailyBriefRecordSnapshot(False, False, False, None, None, "unverified")
        if not isinstance(day, str) or not _DATE.fullmatch(day):
            raise ValueError("invalid day")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid day")
            if (not isinstance(timezone_name, str) or not timezone_name
                    or len(timezone_name) > 64):
                raise ValueError("invalid timezone")
            ZoneInfo(timezone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("invalid query") from exc

        try:
            root_fd = _open_dir_chain(self.root)
        except OSError:
            return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified")
        try:
            root_info = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                    or root_info.st_mode & 0o077):
                return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified")
            try:
                fd = os.open(day + ".json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            except FileNotFoundError:
                return DailyBriefRecordSnapshot(True, True, False, None, None, "unverified")
            except OSError:
                return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified")
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.geteuid() or info.st_mode & 0o077
                        or info.st_size < 0 or info.st_size > self.max_record_bytes):
                    return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified")
                payload = self._read_fd(fd, self.max_record_bytes)
                if len(payload) != info.st_size or len(payload) > self.max_record_bytes:
                    return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified")
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)

        try:
            record = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeError, ValueError, json.JSONDecodeError):
            return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified")
        if (not isinstance(record, dict) or record.get("date") != day
                or record.get("timezone") != timezone_name):
            return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified")
        refs = record.get("source_refs")
        if not isinstance(refs, list) or len(refs) > self.max_source_refs:
            return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified")
        if source_verifier is None:
            source_status = "unverified"
        else:
            try:
                verified = [source_verifier(ref) is True for ref in refs]
            except Exception:
                verified = []
            source_status = ("verified" if verified and all(verified)
                             else "partial" if verified else "unverified")
        return DailyBriefRecordSnapshot(
            True, True, True, record, hashlib.sha256(payload).hexdigest(), source_status,
        )
