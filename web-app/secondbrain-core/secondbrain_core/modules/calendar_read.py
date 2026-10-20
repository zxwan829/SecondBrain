"""Authenticated, date-bounded Calendar projection over Core Journal and Tasks."""
import hashlib
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_DAYS = 31


def _parse_date(value, name):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"{name} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} is invalid") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=400, detail=f"{name} is invalid")
    return parsed


def _zone(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise HTTPException(status_code=400, detail="timezone is invalid")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="timezone is invalid") from exc


def _opaque_id(kind, date_value, record_id):
    seed = f"secondbrain-calendar-v1\0{kind}\0{date_value}\0{record_id}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:32]


def _occurred_at(value, zone):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def create_calendar_read_router(auth, journal_store=None, task_store=None):
    router = APIRouter(prefix="/api")

    @router.get("/calendar")
    def calendar(request: Request,
                 from_day: str = Query(..., alias="from"),
                 to_day: str = Query(..., alias="to"),
                 timezone_name: str = Query("Asia/Shanghai", alias="timezone")):
        auth.require_action(request, "calendar.read")
        start = _parse_date(from_day, "from")
        end = _parse_date(to_day, "to")
        zone = _zone(timezone_name)
        if end < start:
            raise HTTPException(status_code=400, detail="to must not be before from")
        if (end - start).days >= _MAX_DAYS:
            raise HTTPException(status_code=400, detail="Calendar window cannot exceed 31 days")
        if (start.year, start.month) != (end.year, end.month):
            raise HTTPException(status_code=400, detail="Calendar window must stay within one month")

        items = []
        sources = []
        failed = False
        if journal_store is not None:
            try:
                for offset in range((end - start).days + 1):
                    day = date.fromordinal(start.toordinal() + offset).isoformat()
                    for index, record in enumerate(journal_store.read(day)["entries"]):
                        if not isinstance(record, dict):
                            continue
                        item = {
                            "id": _opaque_id("journal", day,
                                             str(record.get("id") or index)),
                            "kind": "journal",
                            "date": day,
                        }
                        occurred = _occurred_at(record.get("created_at"), zone)
                        if occurred is not None:
                            item["occurred_at"] = occurred
                        items.append(item)
                sources.append("journal")
            except (HTTPException, OSError, ValueError):
                failed = True
        if task_store is not None:
            try:
                for task in task_store.list_for_projection()["tasks"]:
                    due = task.get("due_date")
                    task_status = task.get("status")
                    if not isinstance(due, str) or not _DATE.fullmatch(due):
                        continue
                    try:
                        due_day = _parse_date(due, "task due_date")
                    except HTTPException:
                        failed = True
                        continue
                    if not start <= due_day <= end:
                        continue
                    if task_status not in {"open", "completed"}:
                        continue
                    task_id = task.get("id") or task.get("operation_id")
                    if not isinstance(task_id, str) or not task_id:
                        continue
                    items.append({
                        "id": _opaque_id("task", due, task_id),
                        "kind": "task",
                        "date": due,
                        "status": task_status,
                    })
                sources.append("tasks")
            except (HTTPException, OSError, ValueError):
                failed = True

        items.sort(key=lambda item: (item["date"], item["kind"], item["id"]))
        if not sources:
            status = "unavailable"
        elif failed or len(sources) < 2:
            status = "partial"
        else:
            status = "ok" if items else "empty"
        return {"status": status, "items": items, "source": sources,
                "freshness": {"checked_at": datetime.now(timezone.utc).isoformat()}}

    return router
