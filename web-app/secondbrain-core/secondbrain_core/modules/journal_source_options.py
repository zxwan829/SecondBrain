"""Internal, read-only Journal candidates for the Daily Brief source picker.

This module intentionally registers no router. The public wire remains blocked
until the A-side D087 contract is frozen.
"""
from datetime import date, datetime, timezone

from fastapi import HTTPException, Request

from .source_reference_authority import SourceReferenceAuthority


_ALLOWED_SOURCES = frozenset({"web_app_explicit_intent", "inbox_approved_proposal"})
_MAX_DAY_BYTES = 1024 * 1024
_MAX_DAY_ENTRIES = 5000
_MAX_REQUEST_BYTES = 2 * 1024 * 1024
_MAX_LIMIT = 50


def _freshness():
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {"checked_at": checked_at}


class JournalSourceOptionsService:
    """Build a bounded, metadata-only candidate list from one Journal day."""

    def __init__(self, journal_store, auth):
        self.journal_store = journal_store
        self.auth = auth

    def select(self, request: Request, day: str, limit: int = 20):
        # Authorize before looking at the date or touching the Journal store so
        # unauthorized callers cannot distinguish an existing day from an empty one.
        self.auth.check_origin(request)
        self.auth.require_action(request, "daily_brief.read")
        self.auth.require_action(request, "journal.read")

        if (not isinstance(day, str) or len(day) != 10):
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("non-canonical date")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid source selection request") from exc
        if (not isinstance(limit, int) or isinstance(limit, bool)
                or limit < 1 or limit > _MAX_LIMIT):
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        if self.journal_store is None:
            return self._unavailable()

        try:
            snapshot = self.journal_store.read_source_day(
                day, max_bytes=_MAX_DAY_BYTES, max_entries=_MAX_DAY_ENTRIES,
            )
            if not snapshot.get("available"):
                return self._unavailable()

            candidates = []
            authority = SourceReferenceAuthority(
                journal_store=self.journal_store,
                permission_checks={
                    "journal": lambda: self.auth.require_action(request, "journal.read"),
                },
            )
            for entry_id, row in sorted(snapshot["entries"].items()):
                record = row["record"]
                if record.get("source") not in _ALLOWED_SOURCES:
                    continue
                version = row["version"]
                reference = {"kind": "journal", "id": f"{day}:{entry_id}", "version": version}
                # Reuse the authoritative Brief verifier and its request budget.
                # Any drift or ambiguity invalidates the whole candidate snapshot.
                if authority._verify_journal(reference) != "verified":
                    return self._unavailable()
                candidates.append({"kind": "journal", "id": reference["id"],
                                   "date": day, "version": version})
                if snapshot.get("bytes_read", 0) + authority._journal_bytes > _MAX_REQUEST_BYTES:
                    return self._unavailable()
            return {
                "status": "real" if candidates else "empty",
                "items": candidates[:limit],
                "freshness": _freshness(),
            }
        except Exception:
            # Store/verifier failures are deliberately indistinguishable from
            # unavailable storage; never return paths, bytes, or exception text.
            return self._unavailable()

    @staticmethod
    def _unavailable():
        return {"status": "unavailable", "items": [],
                "freshness": _freshness()}
