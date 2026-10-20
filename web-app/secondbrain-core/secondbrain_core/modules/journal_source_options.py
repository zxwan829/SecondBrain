"""Authenticated, read-only D087 Daily Brief Journal source options."""
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from .source_reference_authority import SourceReferenceAuthority


_ALLOWED_SOURCES = frozenset({"web_app_explicit_intent", "inbox_approved_proposal"})
_MAX_DAY_BYTES = 1024 * 1024
_MAX_DAY_ENTRIES = 5000
_MAX_REQUEST_BYTES = 2 * 1024 * 1024
_MAX_LIMIT = 50
_ROW_ID = re.compile(r"^[a-f0-9]{64}$")
_DECIMAL = re.compile(r"^[0-9]+$")
_ALLOWED_QUERY = frozenset({"date", "limit"})


def _freshness():
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {"checked_at": checked_at}


class JournalSourceOptionsService:
    """Build a bounded, metadata-only candidate list from one Journal day."""

    def __init__(self, journal_store, auth):
        self.journal_store = journal_store
        self.auth = auth

    def _authorize(self, request):
        # Authorization must happen before query validation and all Journal IO.
        self.auth.check_origin(request)
        self.auth.require_action(request, "daily_brief.read")
        self.auth.require_action(request, "journal.read")

    def select_from_request(self, request: Request):
        self._authorize(request)
        pairs = request.query_params.multi_items()
        if any(key not in _ALLOWED_QUERY for key, _ in pairs):
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        if len({key for key, _ in pairs}) != len(pairs):
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        query = dict(pairs)
        if "date" not in query:
            raise HTTPException(status_code=422, detail="Invalid source selection request")
        day = query["date"]
        raw_limit = query.get("limit")
        if raw_limit is None:
            limit = 20
        elif _DECIMAL.fullmatch(raw_limit):
            limit = int(raw_limit)
        else:
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        return self._select_authorized(day, limit)

    def select(self, request: Request, day: str, limit: int = 20):
        """Internal direct-call seam; the public router uses raw request parsing."""
        self._authorize(request)
        return self._select_authorized(day, limit)

    def _select_authorized(self, day, limit):
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
        except (HTTPException, OSError, ValueError):
            return self._unavailable()

        if (not isinstance(snapshot, dict) or snapshot.get("available") is not True
                or not isinstance(snapshot.get("entries"), dict)):
            return self._unavailable()
        first_read_bytes = snapshot.get("bytes_read")
        if (not isinstance(first_read_bytes, int) or isinstance(first_read_bytes, bool)
                or first_read_bytes < 0 or first_read_bytes > _MAX_DAY_BYTES):
            return self._unavailable()

        entries = snapshot["entries"]
        if any(not isinstance(entry_id, str) or not _ROW_ID.fullmatch(entry_id)
               for entry_id in entries):
            return self._unavailable()
        candidates = []
        authority = SourceReferenceAuthority(
            journal_store=self.journal_store,
            permission_checks={"journal": lambda: None},
        )
        for entry_id in sorted(entries):
            row = entries[entry_id]
            if not isinstance(row, dict) or not isinstance(row.get("record"), dict):
                return self._unavailable()
            record = row["record"]
            if record.get("source") not in _ALLOWED_SOURCES:
                continue
            version = row.get("version")
            if not isinstance(version, str) or not _ROW_ID.fullmatch(version):
                return self._unavailable()
            reference = {"kind": "journal", "id": f"{day}:{entry_id}", "version": version}
            # Reuse the authoritative Brief verifier and its cached exact-day
            # snapshot. Any drift or ambiguity invalidates the whole response.
            try:
                verification = authority._verify_journal(reference)
            except (HTTPException, OSError, ValueError, KeyError, TypeError, AttributeError):
                return self._unavailable()
            if verification != "verified":
                return self._unavailable()
            if first_read_bytes + authority._journal_bytes > _MAX_REQUEST_BYTES:
                return self._unavailable()
            candidates.append({"kind": "journal", "id": reference["id"],
                               "date": day, "version": version})

        if not candidates:
            status, items = "empty", []
        else:
            # Full-day verification is complete before the deterministic ID
            # ordering and response limit are applied.
            items = sorted(candidates, key=lambda item: item["id"].split(":", 1)[1])[:limit]
            status = "real"
        return {"status": status, "items": items, "freshness": _freshness()}

    @staticmethod
    def _unavailable():
        return {"status": "unavailable", "items": [],
                "freshness": _freshness()}


def create_journal_source_options_router(service):
    router = APIRouter(prefix="/api/daily-brief")

    @router.get("/source-options/journal")
    def journal_source_options(request: Request):
        return service.select_from_request(request)

    return router
