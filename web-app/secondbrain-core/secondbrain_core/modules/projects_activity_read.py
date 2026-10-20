"""Authenticated read-only Projects and explicit Journal/Task Activity views."""
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_LIMIT = 100
_MAX_OFFSET = 100_000
_DEFAULT_JOURNAL_LOOKBACK_DAYS = 365


def _page(limit, offset):
    if not isinstance(limit, int) or not 1 <= limit <= _MAX_LIMIT:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    if not isinstance(offset, int) or not 0 <= offset <= _MAX_OFFSET:
        raise HTTPException(status_code=400, detail="offset is invalid")


def _parse_day(value, name):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"{name} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} is invalid") from exc


def _timezone(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise HTTPException(status_code=400, detail="timezone is invalid")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="timezone is invalid") from exc


def _occurred_at(value, zone):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=zone)
    return stamp.astimezone(timezone.utc)


def _opaque_id(kind, operation_id, record_id):
    digest = hashlib.sha256(
        f"secondbrain-activity-v1\0{kind}\0{operation_id}\0{record_id}".encode("utf-8")
    ).hexdigest()
    return digest[:32]


def _within_window(stamp, start, end, zone):
    if stamp is None:
        return False
    local_day = stamp.astimezone(zone).date()
    return (start is None or local_day >= start) and (end is None or local_day <= end)


def _journal_rows(store, start, end, zone):
    if store is None:
        return []
    rows = []
    days = (date.fromordinal(start.toordinal() + offset).isoformat()
            for offset in range((end - start).days + 1))
    for day in days:
        data = store.read(day)
        for record in data["entries"]:
            operation_id = record.get("operation_id")
            session_id = record.get("session_id")
            if not isinstance(operation_id, str) or not operation_id or not isinstance(session_id, str) or not session_id:
                continue
            occurred = _occurred_at(record.get("created_at"), zone)
            if occurred is None or not _within_window(occurred, start, end, zone):
                continue
            rows.append({
                "activity_id": _opaque_id("journal", operation_id, record.get("id") or day),
                "kind": "journal",
                "status": "succeeded",
                "occurred_at": occurred.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "journal_date": record.get("date") if isinstance(record.get("date"), str) else day,
            })
    return rows


def _task_rows(store, start, end, zone):
    if store is None:
        return []
    rows = []
    for task in store.list_for_projection()["tasks"]:
        operation_id = task.get("operation_id")
        session_id = task.get("session_id")
        if not isinstance(operation_id, str) or not operation_id or not isinstance(session_id, str) or not session_id:
            continue
        occurred = _occurred_at(task.get("created_at"), zone)
        if occurred is None or not _within_window(occurred, start, end, zone):
            continue
        row = {
            "activity_id": _opaque_id("task", operation_id, task.get("id") or operation_id),
            "kind": "task",
            "status": "succeeded",
            "occurred_at": occurred.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }
        due_date = task.get("due_date")
        if isinstance(due_date, str) and _DATE.fullmatch(due_date):
            row["task_due_date"] = due_date
        task_status = task.get("status")
        if task_status in {"open", "completed"}:
            row["task_status"] = task_status
        rows.append(row)
    return rows


def create_projects_activity_router(auth, journal_store=None, task_store=None):
    router = APIRouter(prefix="/api")

    @router.get("/projects")
    def projects(request: Request, limit: int = 1, offset: int = 0):
        auth.require_action(request, "projects.read")
        _page(limit, offset)
        return {
            "status": "not_configured",
            "items": [],
            "pagination": {"limit": limit, "offset": offset, "has_more": False},
            "source": None,
        }

    @router.get("/activity")
    def activity(request: Request, limit: int = 50, offset: int = 0,
                 from_day: Optional[str] = Query(default=None, alias="from"),
                 to_day: Optional[str] = Query(default=None, alias="to"),
                 timezone_name: str = Query(default="Asia/Shanghai", alias="timezone")):
        auth.require_action(request, "activity.read")
        _page(limit, offset)
        default_window = from_day is None and to_day is None
        if (from_day is None) != (to_day is None):
            raise HTTPException(status_code=400, detail="from and to must be supplied together")
        zone = _timezone(timezone_name)
        start = end = None
        if from_day is not None:
            start, end = _parse_day(from_day, "from"), _parse_day(to_day, "to")
            if end < start:
                raise HTTPException(status_code=400, detail="to must not be before from")
            if (end - start).days > 30:
                raise HTTPException(status_code=400, detail="Activity window cannot exceed 31 days")
        else:
            # Query exact date paths in a bounded lookback; never enumerate
            # the Journal directory. The response is marked partial because
            # older Journal files may exist beyond this finite lookback.
            end = datetime.now(zone).date()
            start = end - timedelta(days=_DEFAULT_JOURNAL_LOOKBACK_DAYS - 1)

        configured = [name for name, store in (("journal", journal_store), ("tasks", task_store)) if store is not None]
        if not configured:
            return {
                "status": "unavailable", "items": [],
                "pagination": {"limit": limit, "offset": offset, "has_more": False},
                "source": [], "freshness": {"checked_at": datetime.now(timezone.utc).isoformat()},
            }

        rows = _journal_rows(journal_store, start, end, zone)
        task_read_failed = False
        try:
            rows.extend(_task_rows(task_store, start, end, zone))
        except HTTPException:
            # Task projection has a fixed byte budget. Keep other available
            # sources, but never imply a complete Activity result on overflow.
            task_read_failed = True
        rows.sort(key=lambda row: (row["occurred_at"], row["activity_id"]), reverse=True)
        page_rows = rows[offset:offset + limit]
        missing_source = len(configured) < 2
        return {
            "status": "partial" if missing_source or default_window or task_read_failed else ("ok" if rows else "empty"),
            "items": page_rows,
            "pagination": {"limit": limit, "offset": offset, "has_more": offset + limit < len(rows)},
            "source": configured,
            "freshness": {"checked_at": datetime.now(timezone.utc).isoformat()},
        }

    return router
