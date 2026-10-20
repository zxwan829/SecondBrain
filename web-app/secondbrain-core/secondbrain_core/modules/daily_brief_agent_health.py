"""Authenticated Daily Brief and minimal Agent Health read contracts."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request

from .daily_brief_store import DailyBriefRecordReadStore
from .source_reference_authority import SourceReferenceAuthority


def _valid_date(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD")
    return value


def _valid_timezone(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise HTTPException(status_code=400, detail="timezone is invalid")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="timezone is invalid") from exc
    return value


def _checked_at():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_daily_brief_agent_health_router(auth, hermes, brief_store=None, projects_store=None):
    router = APIRouter(prefix="/api")
    brief_store = brief_store or DailyBriefRecordReadStore(None)

    @router.get("/daily-brief")
    def daily_brief(request: Request,
                    day: str = Query(..., alias="date"),
                    timezone_name: str = Query("Asia/Shanghai", alias="timezone")):
        auth.require_action(request, "daily_brief.read")
        day = _valid_date(day)
        timezone_name = _valid_timezone(timezone_name)
        checked_at = _checked_at()
        source = {"kind": "core-daily-brief-store"} if brief_store.configured else None
        try:
            # Each request gets one bounded, exact-ID Projects snapshot. No
            # arbitrary caller path or cross-scope lookup enters this adapter.
            authority = SourceReferenceAuthority(
                projects_store,
                permission_check=lambda: auth.require_action(request, "projects.read"),
            )
            snapshot = brief_store.read(day, timezone_name, source_verifier=authority.verify)
        except Exception:
            return {"status": "unavailable", "items": [], "source": source,
                    "freshness": {"checked_at": checked_at}}
        if not snapshot.configured:
            status, items = "not_configured", []
        elif snapshot.failure_status == "unavailable":
            status, items = "unavailable", []
        elif snapshot.failure_status == "failed":
            status, items = "failed", []
        elif not snapshot.available:
            status, items = "unavailable", []
        elif not snapshot.found:
            status, items = "empty", []
        else:
            record = snapshot.record
            if record["generation_status"] == "failed":
                status, items = "failed", []
            elif record["generation_status"] == "stale" or snapshot.source_verification == "stale":
                status, items = "stale", []
            elif snapshot.source_verification == "unavailable":
                status, items = "unavailable", []
            elif snapshot.source_verification == "failed":
                status, items = "failed", []
            elif snapshot.source_verification != "verified":
                # Do not expose an unverified summary to the public API.
                status, items = "partial", []
            else:
                status = "partial" if record["generation_status"] == "partial" else "real"
                items = [{key: record[key] for key in (
                    "brief_id", "date", "timezone", "generated_at", "generation_status",
                    "categories", "summary", "source_refs",
                )}]
        return {"status": status, "items": items, "source": source,
                "freshness": {"checked_at": checked_at}}

    @router.get("/agent/health")
    async def agent_health(request: Request):
        auth.require_action(request, "agent.health.read")
        checked_at = _checked_at()
        if not getattr(hermes, "configured", False):
            return {"status": "not_configured", "source": None, "checked_at": checked_at}
        try:
            await hermes.capabilities()
        except HTTPException:
            return {"status": "unavailable", "source": "hermes-runtime",
                    "checked_at": checked_at}
        return {"status": "online", "source": "hermes-runtime", "checked_at": checked_at}

    return router
