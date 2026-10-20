from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .knowledge_read import _open_dir_chain


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_MAX_RECORD_BYTES = 128 * 1024
_MAX_SOURCE_REFS = 50
_SOURCE_KINDS = {"project", "task", "journal"}
_RECORD_FIELDS = {"brief_id", "date", "timezone", "generated_at", "generation_status",
                  "categories", "summary", "source_refs"}
_GENERATION_STATUSES = {"generated", "partial", "stale", "failed"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _valid_source_reference(reference):
    return (isinstance(reference, dict) and set(reference) == {"kind", "id", "version"}
            and isinstance(reference.get("kind"), str) and reference["kind"] in _SOURCE_KINDS
            and isinstance(reference.get("id"), str)
            and _OPAQUE_ID.fullmatch(reference["id"]) is not None
            and isinstance(reference.get("version"), str)
            and _SHA256.fullmatch(reference["version"]) is not None)


def _parse_generated_at(value, zone, requested_day):
    if not isinstance(value, str) or len(value) > 64 or not _RFC3339.fullmatch(value):
        return False
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if instant.tzinfo is None or instant.utcoffset() is None:
        return False
    return instant.astimezone(zone).date().isoformat() == requested_day


def _validate_record(record, day, timezone_name, zone, max_source_refs):
    if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
        return False
    if (not isinstance(record.get("brief_id"), str)
            or not _OPAQUE_ID.fullmatch(record["brief_id"])
            or record.get("date") != day or record.get("timezone") != timezone_name
            or not isinstance(record.get("generation_status"), str)
            or record["generation_status"] not in _GENERATION_STATUSES
            or not _parse_generated_at(record.get("generated_at"), zone, day)):
        return False
    summary = record.get("summary")
    if not isinstance(summary, str) or len(summary) > 20000:
        return False
    categories = record.get("categories")
    if (not isinstance(categories, list) or len(categories) > 30
            or any(not isinstance(item, str) or not item.strip() or len(item) > 80
                   for item in categories)):
        return False
    refs = record.get("source_refs")
    if (not isinstance(refs, list) or len(refs) > max_source_refs
            or (not refs and record["generation_status"] != "failed")
            or any(not _valid_source_reference(ref) for ref in refs)):
        return False
    return True


@dataclass(frozen=True)
class DailyBriefRecordSnapshot:
    configured: bool
    available: bool
    found: bool
    record: dict[str, Any] | None
    sha256: str | None
    source_verification: str
    failure_status: str | None = None


class DailyBriefRecordReadStore:
    """Read one exact Core-owned daily record; never enumerates history or writes.

    V1 stores one authoritative timezone per calendar date in ``{date}.json``.
    A query for the same date with a different timezone is unavailable; it never
    probes alternate files or synthesizes a timezone-specific record.
    """

    def __init__(self, root, *, max_record_bytes=_MAX_RECORD_BYTES,
                 max_source_refs=_MAX_SOURCE_REFS):
        self.configured = bool(root)
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
        if not self.configured:
            return DailyBriefRecordSnapshot(False, False, False, None, None, "unverified")
        if not self.root:
            return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified", "unavailable")
        if not isinstance(day, str) or not _DATE.fullmatch(day):
            raise ValueError("invalid day")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid day")
            if (not isinstance(timezone_name, str) or not timezone_name
                    or len(timezone_name) > 64):
                raise ValueError("invalid timezone")
            zone = ZoneInfo(timezone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("invalid query") from exc

        try:
            root_fd = _open_dir_chain(self.root)
        except OSError:
            return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified", "unavailable")
        try:
            root_info = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                    or root_info.st_mode & 0o077):
                return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified", "unavailable")
            try:
                fd = os.open(day + ".json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            except FileNotFoundError:
                return DailyBriefRecordSnapshot(True, True, False, None, None, "unverified")
            except OSError:
                return DailyBriefRecordSnapshot(True, False, False, None, None, "unverified", "unavailable")
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.geteuid() or info.st_mode & 0o077
                        or info.st_size < 0 or info.st_size > self.max_record_bytes):
                    return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified", "unavailable")
                payload = self._read_fd(fd, self.max_record_bytes)
                if len(payload) != info.st_size or len(payload) > self.max_record_bytes:
                    return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified", "unavailable")
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)

        try:
            record = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeError, ValueError, json.JSONDecodeError):
            return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified", "failed")
        if (isinstance(record, dict)
                and (record.get("date") != day or record.get("timezone") != timezone_name)):
            return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified", "unavailable")
        if not _validate_record(record, day, timezone_name, zone, self.max_source_refs):
            return DailyBriefRecordSnapshot(True, False, True, None, None, "unverified", "failed")
        refs = record["source_refs"]
        if source_verifier is None:
            source_status = "unverified"
        else:
            results = []
            verifier_failed = False
            for reference in refs:
                try:
                    result = source_verifier(reference)
                except Exception:
                    verifier_failed = True
                    results.append("failed")
                    continue
                if result is True or result == "verified":
                    results.append("verified")
                elif result is False or result == "missing":
                    results.append("missing")
                elif isinstance(result, str) and result in {"stale", "unavailable", "failed"}:
                    results.append(result)
                elif isinstance(result, str) and result in {"unsupported", "forbidden"}:
                    results.append(result)
                else:
                    verifier_failed = True
                    results.append("failed")
            if not results:
                source_status = "unverified"
            elif "forbidden" in results:
                # Keep this distinction internal; the HTTP mapper withholds
                # content and maps it to the frozen partial envelope.
                source_status = "forbidden"
            elif "stale" in results:
                source_status = "stale"
            elif all(result == "verified" for result in results):
                source_status = "verified"
            elif "unsupported" in results:
                source_status = "unsupported"
            elif all(result != "verified" for result in results):
                if "unavailable" in results:
                    source_status = "unavailable"
                elif verifier_failed or "failed" in results:
                    source_status = "failed"
                else:
                    source_status = "missing"
            else:
                source_status = "partial"
        return DailyBriefRecordSnapshot(
            True, True, True, record, hashlib.sha256(payload).hexdigest(), source_status,
        )
