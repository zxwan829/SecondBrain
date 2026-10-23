"""Authenticated read-only Projects and explicit source-backed Activity views."""
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request

from .projects_source_read import ProjectsSourceReadStore
from .source_reference_authority import SourceReferenceAuthority


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_LIMIT = 100
_MAX_OFFSET = 100_000
_DEFAULT_JOURNAL_LOOKBACK_DAYS = 365
_PROJECTS_MAX_LIMIT = 50
_PROJECTS_MAX_OFFSET = 5000


def _checked_at():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _project_page(limit, offset):
    if not isinstance(limit, int) or not 1 <= limit <= _PROJECTS_MAX_LIMIT:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 50")
    if not isinstance(offset, int) or not 0 <= offset <= _PROJECTS_MAX_OFFSET:
        raise HTTPException(status_code=400, detail="offset must be between 0 and 5000")


def _project_item(document, source_version, note_verifier=None, notes_permission_available=True):
    item = {key: document[key] for key in ("id", "title", "status", "next_step", "updated_at")
            if key in document}
    # When Notes reads are not authorized, give every visible project the same
    # partial status so the presence of a particular link cannot be inferred.
    unverified_association = not notes_permission_available
    for key in ("recent_activity", "linked_notes"):
        if key not in document:
            continue
        references = document[key] if key == "linked_notes" else [document[key]]
        if key == "recent_activity":
            # The frozen field has no event ID/version; never join by time.
            unverified_association = True
        elif references:
            if note_verifier is None or any(note_verifier(ref) != "verified" for ref in references):
                unverified_association = True
    item["source_ref"] = {"id": document["id"], "version": source_version}
    return item, unverified_association


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
        return [], False
    rows = []
    complete = True
    # Activity is a read-only projection. Do not create the TaskStore lock
    # file merely to read its bounded, race-checked snapshot.
    for task in store.list_for_projection_read_only()["tasks"]:
        if not isinstance(task, dict):
            complete = False
            continue
        operation_id = task.get("operation_id")
        task_id = task.get("id")
        if (not isinstance(operation_id, str) or not operation_id
                or not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{32}", task_id)):
            complete = False
            continue
        occurred = _occurred_at(task.get("created_at"), zone)
        if occurred is not None and _within_window(occurred, start, end, zone):
            row = {
                "activity_id": _opaque_id("task", operation_id, task_id),
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

        history = task.get("history")
        if not isinstance(history, list) or not history:
            complete = False
            continue
        created_event = history[0]
        created_at = _occurred_at(task.get("created_at"), zone)
        created_history_at = (_occurred_at(created_event.get("at"), zone)
                              if isinstance(created_event, dict) else None)
        if (not isinstance(created_event, dict) or created_event.get("event") != "created"
                or created_at is None or created_history_at != created_at):
            complete = False
            continue
        previous_at = created_history_at
        for index, event in enumerate(history[1:], start=1):
            changes = event.get("changes") if isinstance(event, dict) else None
            valid_changes = (isinstance(changes, dict) and bool(changes)
                             and set(changes) <= {"title", "due_date", "status"}
                             and all(isinstance(change, dict) and set(change) == {"from", "to"}
                                     and change["from"] != change["to"]
                                     for change in changes.values()))
            if (not isinstance(event, dict) or event.get("event") != "updated" or not valid_changes):
                complete = False
                continue
            updated_at = _occurred_at(event.get("at"), zone)
            if updated_at is None or updated_at <= previous_at:
                complete = False
                continue
            previous_at = updated_at
            if _within_window(updated_at, start, end, zone):
                rows.append({
                    "activity_id": _opaque_id("task_update", task_id, f"{index}:{event['at']}"),
                    "kind": "task",
                    "status": "updated",
                    "occurred_at": updated_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                })
        current_updated_at = _occurred_at(task.get("updated_at"), zone)
        if current_updated_at is None or current_updated_at != previous_at:
            complete = False
    return rows, complete


def _project_rows(store, start, end, zone):
    """Project update events derived only from the explicit, bounded index.

    The source document SHA is the event revision. The route deliberately
    returns neither project title/body nor filesystem location.
    """
    if store is None:
        return [], False
    try:
        snapshot = store.read_snapshot()
    except Exception:
        return [], True
    if not snapshot.available:
        return [], True
    rows = []
    for source in snapshot.documents:
        document = source.document
        occurred = _occurred_at(document.get("updated_at"), zone)
        if occurred is None or not _within_window(occurred, start, end, zone):
            continue
        rows.append({
            "activity_id": _opaque_id("project", source.sha256, source.project_id),
            "kind": "project",
            "status": "updated",
            "occurred_at": occurred.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "project_id": source.project_id,
            "project_status": document["status"],
        })
    return rows, not snapshot.complete


def _daily_brief_rows(store, start, end, zone):
    """Project only verified successful Brief audit receipts into Activity."""
    if store is None:
        return [], False
    try:
        events, complete = store.read_activity_events()
    except Exception:
        return [], True
    rows = []
    for event in events:
        occurred = _occurred_at(event.get("recorded_at"), zone)
        if occurred is None or not _within_window(occurred, start, end, zone):
            continue
        rows.append({
            "activity_id": _opaque_id("daily_brief", event["request_id"], event["brief_id"]),
            "kind": "daily_brief",
            "status": "created",
            "occurred_at": occurred.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "daily_brief_date": event["date"],
        })
    return rows, not complete


def _personal_memory_rows(store, start, end, zone):
    """Project only operation type/time from the bounded Personal Memory log."""
    if store is None:
        return [], False
    try:
        events = store.read_activity_events()
    except Exception:
        return [], True
    rows = []
    complete = isinstance(events, list)
    if not complete:
        return [], True
    status_by_operation = {
        "create": "created", "correct": "corrected",
        "revoked": "revoked", "expired": "expired",
    }
    for event in events:
        if not isinstance(event, dict):
            complete = False
            continue
        event_id, operation = event.get("event_id"), event.get("operation")
        occurred = _occurred_at(event.get("recorded_at"), zone)
        if (not isinstance(event_id, str) or not event_id or len(event_id) > 128
                or operation not in status_by_operation or occurred is None):
            complete = False
            continue
        if _within_window(occurred, start, end, zone):
            rows.append({
                "activity_id": _opaque_id("personal_memory", event_id, event_id),
                "kind": "personal_memory",
                "status": status_by_operation[operation],
                "occurred_at": occurred.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            })
    return rows, not complete


def create_projects_activity_router(auth, journal_store=None, task_store=None,
                                    projects_store=None, notes_store=None,
                                    daily_brief_audit_store=None, memory_store=None):
    router = APIRouter(prefix="/api")
    projects_store = projects_store or ProjectsSourceReadStore(None)

    @router.get("/projects")
    def projects(request: Request, limit: int = 1, offset: int = 0):
        auth.require_action(request, "projects.read")
        _project_page(limit, offset)
        checked_at = _checked_at()
        try:
            snapshot = projects_store.read_snapshot()
        except Exception:
            snapshot = None
        if snapshot is None:
            return {"status": "unavailable", "items": [],
                    "pagination": {"limit": limit, "offset": offset, "has_more": False},
                    "source": None, "freshness": {"checked_at": checked_at}}
        if not snapshot.configured:
            status, items, source, has_more = "not_configured", [], None, False
        elif not snapshot.available:
            status, items, source, has_more = "unavailable", [], None, False
        else:
            note_authority = SourceReferenceAuthority(
                notes_store=notes_store,
                permission_checks={"notes": lambda: auth.require_action(request, "notes.read")},
            )
            try:
                auth.require_action(request, "notes.read")
                notes_permission_available = True
            except HTTPException:
                notes_permission_available = False
            mapped = [_project_item(row.document, row.sha256, note_authority.verify_project_note,
                                    notes_permission_available)
                      for row in snapshot.documents]
            rows = [item for item, _unverified in mapped]
            associations_unverified = any(unverified for _, unverified in mapped)
            page = rows[offset:offset + limit]
            has_more = snapshot.has_more or offset + len(page) < len(rows)
            status = ("partial" if not snapshot.complete or associations_unverified else
                      "empty" if not rows else "real")
            items, source = page, {"kind": "explicit-project-index"}
        return {
            "status": status,
            "items": items,
            "pagination": {"limit": limit, "offset": offset, "has_more": has_more},
            "source": source,
            "freshness": {"checked_at": checked_at},
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

        candidates = [
            ("journal", journal_store, "journal.read"),
            ("tasks", task_store, "task.read"),
            ("projects", projects_store if projects_store.configured else None, "projects.read"),
            ("daily_brief", daily_brief_audit_store if daily_brief_audit_store is not None
             and daily_brief_audit_store.configured else None,
             "daily_brief.read"),
            ("personal_memory", memory_store, "personal_memory.read"),
        ]
        configured = [(name, store, action) for name, store, action in candidates if store is not None]
        if not configured:
            return {
                "status": "unavailable", "items": [],
                "pagination": {"limit": limit, "offset": offset, "has_more": False},
                "source": [], "freshness": {"checked_at": datetime.now(timezone.utc).isoformat()},
            }

        # Authorize every configured source before its first read. A denied
        # source is omitted and makes the response partial; it is never probed.
        authorized, denied = [], False
        for name, store, action in configured:
            try:
                auth.require_action(request, action)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                denied = True
                continue
            authorized.append((name, store))

        rows = []
        read_failed = denied
        for name, store in authorized:
            if name == "journal":
                rows.extend(_journal_rows(store, start, end, zone))
            elif name == "tasks":
                try:
                    task_rows, complete = _task_rows(store, start, end, zone)
                    rows.extend(task_rows)
                    read_failed = read_failed or not complete
                except HTTPException:
                    # Task projection has a fixed byte budget. Keep other
                    # available sources but never imply completeness.
                    read_failed = True
            elif name == "projects":
                project_rows, partial = _project_rows(store, start, end, zone)
                rows.extend(project_rows)
                read_failed = read_failed or partial
            elif name == "daily_brief":
                brief_rows, partial = _daily_brief_rows(store, start, end, zone)
                rows.extend(brief_rows)
                read_failed = read_failed or partial
            elif name == "personal_memory":
                memory_rows, partial = _personal_memory_rows(store, start, end, zone)
                rows.extend(memory_rows)
                read_failed = read_failed or partial
        rows.sort(key=lambda row: (row["occurred_at"], row["activity_id"]), reverse=True)
        page_rows = rows[offset:offset + limit]
        missing_source = len(authorized) < len(configured) or len(authorized) < 2
        return {
            "status": "partial" if missing_source or default_window or read_failed else ("ok" if rows else "empty"),
            "items": page_rows,
            "pagination": {"limit": limit, "offset": offset, "has_more": offset + limit < len(rows)},
            "source": [name for name, _store in authorized],
            "freshness": {"checked_at": datetime.now(timezone.utc).isoformat()},
        }

    return router
