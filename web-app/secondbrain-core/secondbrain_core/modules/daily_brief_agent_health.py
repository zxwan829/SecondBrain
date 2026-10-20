"""Authenticated Daily Brief and minimal Agent Health read contracts."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request


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


def create_daily_brief_agent_health_router(auth, hermes):
    router = APIRouter(prefix="/api")

    @router.get("/daily-brief")
    def daily_brief(request: Request,
                    day: str = Query(..., alias="date"),
                    timezone_name: str = Query("Asia/Shanghai", alias="timezone")):
        auth.require_action(request, "daily_brief.read")
        day = _valid_date(day)
        timezone_name = _valid_timezone(timezone_name)
        # No trusted Daily Brief source exists yet. Never generate a temporary
        # summary, read Hermes history, or call a model from this endpoint.
        return {"status": "not_configured", "items": [], "source": None}

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
