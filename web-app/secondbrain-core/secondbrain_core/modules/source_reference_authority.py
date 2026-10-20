"""Fail-closed source adapters for authenticated Core read projections."""
import re
import uuid
from datetime import date

from fastapi import HTTPException

from .tasks import task_source_version


_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_JOURNAL_ID = re.compile(r"^(\d{4}-\d{2}-\d{2}):([a-f0-9]{64})$")
_MAX_JOURNAL_BYTES_PER_REQUEST = 2 * 1024 * 1024
_MAX_JOURNAL_BYTES_PER_DAY = 1024 * 1024
_MAX_NOTES_BYTES_PER_REQUEST = 2 * 1024 * 1024
_MAX_NOTE_BYTES = 1024 * 1024
_MAX_NOTES_PER_REQUEST = 100


class SourceReferenceAuthority:
    """Resolve only server-issued IDs against bounded authoritative stores.

    Instances are request-scoped. Store snapshots are cached only for the life
    of one HTTP request and versions are recomputed from Core-owned records.
    """

    def __init__(self, projects_store=None, task_store=None, journal_store=None,
                 notes_store=None, permission_checks=None):
        self.projects_store = projects_store
        self.task_store = task_store
        self.journal_store = journal_store
        self.notes_store = notes_store
        self.permission_checks = permission_checks or {}
        self._project_snapshot = None
        self._task_rows = None
        self._journal_days = {}
        self._journal_bytes = 0
        self._notes_bytes = 0
        self._note_versions = {}

    def _authorized(self, kind):
        check = self.permission_checks.get(kind)
        if check is None:
            return False
        try:
            check()
        except Exception:
            return False
        return True

    def verify(self, reference):
        if not isinstance(reference, dict):
            return "unsupported"
        kind = reference.get("kind")
        if kind == "project":
            return self._verify_project(reference)
        if kind == "task":
            return self._verify_task(reference)
        if kind == "journal":
            return self._verify_journal(reference)
        # Notes may be a Projects association, but are not a Brief source kind.
        return "unsupported"

    def _verify_project(self, reference):
        if self.projects_store is None:
            return "unavailable"
        if not self._authorized("project"):
            return "forbidden"
        if self._project_snapshot is None:
            try:
                self._project_snapshot = self.projects_store.read_snapshot()
            except Exception:
                return "unavailable"
        snapshot = self._project_snapshot
        if not snapshot.configured or not snapshot.available or not snapshot.complete:
            # An incomplete bounded scan cannot prove a missing or unique ID.
            return "unavailable"
        matches = [row for row in snapshot.documents if row.project_id == reference["id"]]
        if not matches:
            return "missing"
        if len(matches) != 1:
            return "unavailable"
        return "verified" if matches[0].sha256 == reference["version"] else "stale"

    def _verify_task(self, reference):
        if self.task_store is None:
            return "unavailable"
        if not self._authorized("task"):
            return "forbidden"
        if self._task_rows is None:
            try:
                self._task_rows = self.task_store.list_for_projection()["tasks"]
            except Exception:
                return "unavailable"
        matches = [row for row in self._task_rows if row.get("id") == reference["id"]]
        if not matches:
            return "missing"
        if len(matches) != 1:
            return "unavailable"
        version = task_source_version(matches[0])
        if version is None:
            return "unsupported"
        return "verified" if version == reference["version"] else "stale"

    def _journal_day(self, day):
        if day in self._journal_days:
            return self._journal_days[day]
        if self.journal_store is None:
            return None
        try:
            snapshot = self.journal_store.read_source_day(
                day, max_bytes=_MAX_JOURNAL_BYTES_PER_DAY,
            )
        except Exception:
            self._journal_days[day] = None
            return None
        consumed = snapshot.get("bytes_read", 0)
        if self._journal_bytes + consumed > _MAX_JOURNAL_BYTES_PER_REQUEST:
            self._journal_days[day] = None
            return None
        self._journal_bytes += consumed
        self._journal_days[day] = snapshot
        return snapshot

    def _verify_journal(self, reference):
        if self.journal_store is None:
            return "unavailable"
        if not self._authorized("journal"):
            return "forbidden"
        match = _JOURNAL_ID.fullmatch(reference["id"])
        if not match:
            return "unsupported"
        day, entry_id = match.groups()
        try:
            if date.fromisoformat(day).isoformat() != day:
                return "unsupported"
        except ValueError:
            return "unsupported"
        snapshot = self._journal_day(day)
        if snapshot is None or not snapshot.get("available"):
            return "unavailable"
        row = snapshot["entries"].get(entry_id)
        if row is None:
            return "missing"
        record = row["record"]
        if (record.get("id") != entry_id
                or record.get("source") not in {"web_app_explicit_intent", "inbox_approved_proposal"}):
            return "unsupported"
        return "verified" if row["version"] == reference["version"] else "stale"

    def verify_project_note(self, reference):
        """Verify an explicit project link only for NotesStore-issued Draft IDs."""
        if self.notes_store is None:
            return "unavailable"
        if not self._authorized("notes"):
            return "forbidden"
        note_id = reference.get("id") if isinstance(reference, dict) else None
        version = reference.get("version") if isinstance(reference, dict) else None
        if (not isinstance(note_id, str) or not isinstance(version, str)
                or not _SHA256.fullmatch(version)):
            return "unsupported"
        try:
            canonical_id = str(uuid.UUID(note_id))
        except (ValueError, AttributeError, TypeError):
            return "unsupported"
        if canonical_id != note_id:
            return "unsupported"
        if note_id not in self._note_versions and len(self._note_versions) >= _MAX_NOTES_PER_REQUEST:
            return "unavailable"
        if note_id not in self._note_versions:
            remaining = _MAX_NOTES_BYTES_PER_REQUEST - self._notes_bytes
            if remaining <= 0:
                return "unavailable"
            try:
                result = self.notes_store.read_source_draft(
                    note_id, max_bytes=min(_MAX_NOTE_BYTES, remaining),
                )
            except HTTPException as exc:
                status = "missing" if exc.status_code == 404 else "unavailable"
                self._note_versions[note_id] = status
            except Exception:
                self._note_versions[note_id] = "unavailable"
            else:
                self._notes_bytes += result["size_bytes"]
                self._note_versions[note_id] = {
                    "version": result.get("etag"), "size_bytes": result["size_bytes"],
                }
        actual = self._note_versions[note_id]
        if isinstance(actual, str):
            return actual
        return "verified" if actual["version"] == version else "stale"
