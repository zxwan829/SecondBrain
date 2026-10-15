"""Fail-closed AI organization settings and capability boundary.

The settings store is ready for an in-app scheduler, but execution remains disabled
until a no-tools, bounded model adapter and durable history contract are verified.
"""
import json
import os
import re
import tempfile
import threading
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request


INTERVAL_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DEFAULT_SETTINGS = {
    "enabled": True,
    "mode": "interval",
    "interval_hours": 4,
    "daily_time": "00:30",
    "timezone": "Asia/Shanghai",
}


class OrganizeSettingsStore:
    """Private atomic JSON settings store rooted in Core's existing state mount."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise RuntimeError("AI organization state root must be a real directory")
        root_info = os.stat(self.root, follow_symlinks=False)
        if root_info.st_uid != os.geteuid() or root_info.st_mode & 0o077:
            raise RuntimeError("AI organization state root must be owned by the App UID")
        self.path = self.root / "settings.json"
        self._lock = threading.RLock()

    def read(self):
        with self._lock:
            if not self.path.exists():
                return {**DEFAULT_SETTINGS, "updated_at": None}
            if self.path.is_symlink() or not self.path.is_file():
                raise RuntimeError("AI organization settings path is not a regular file")
            info = os.stat(self.path, follow_symlinks=False)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise RuntimeError("AI organization settings file must be private and owned by the App UID")
            with self.path.open("r", encoding="utf-8") as stream:
                value = json.load(stream)
            return validate_settings(value)

    def write(self, value):
        value = validate_settings(value)
        value["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        with self._lock:
            fd, temp_name = tempfile.mkstemp(prefix=".settings-", dir=self.root)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, self.path)
                dir_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
        return value


def validate_settings(value):
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="Settings must be an object")
    enabled = value.get("enabled")
    mode = value.get("mode")
    interval = value.get("interval_hours", DEFAULT_SETTINGS["interval_hours"])
    daily_time = value.get("daily_time", DEFAULT_SETTINGS["daily_time"])
    tz_name = value.get("timezone", DEFAULT_SETTINGS["timezone"])
    if not isinstance(enabled, bool) or mode not in {"fixed_time", "interval"}:
        raise HTTPException(status_code=422, detail="Invalid automation mode or enabled flag")
    if type(interval) is not int or interval not in INTERVAL_HOURS:
        raise HTTPException(status_code=422, detail="Unsupported interval")
    if not isinstance(daily_time, str) or not TIME_RE.fullmatch(daily_time):
        raise HTTPException(status_code=422, detail="Daily time must use HH:MM")
    if not isinstance(tz_name, str) or len(tz_name) > 80:
        raise HTTPException(status_code=422, detail="Invalid time zone")
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown time zone") from exc
    return {"enabled": enabled, "mode": mode, "interval_hours": interval,
            "daily_time": daily_time, "timezone": tz_name,
            "updated_at": value.get("updated_at")}


def next_scheduled_at(settings, *, now=None, interval_anchor=None):
    """Compute a display/scheduler candidate; interval cadence anchors durably to last run."""
    settings = validate_settings(settings)
    if not settings["enabled"]:
        return None
    now = now or datetime.now(timezone.utc)
    if settings["mode"] == "interval":
        anchor = interval_anchor or now
        candidate = anchor + timedelta(hours=settings["interval_hours"])
        return candidate if candidate > now else now
    zone = ZoneInfo(settings["timezone"])
    local_now = now.astimezone(zone)
    hour, minute = map(int, settings["daily_time"].split(":"))
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def create_auto_organize_router(auth, state_root):
    router = APIRouter(prefix="/api/automation/organize")
    store = OrganizeSettingsStore(Path(state_root) / "ai-organize")

    @router.get("/settings")
    def settings(request: Request):
        auth.require_action(request, "automation.settings.read")
        return store.read()

    @router.put("/settings")
    def update_settings(request: Request, body: dict):
        auth.require_action(request, "automation.settings.write")
        return store.write(body)

    @router.get("/status")
    def status(request: Request):
        auth.require_action(request, "automation.status.read")
        return {"execution_available": False, "state": "blocked",
                "last_run_at": None, "next_run_at": None,
                "last_draft_count": None,
                "blocked_reason": "Hermes 当前可读取持久化消息，但尚未验证可禁用工具的受限模型调用与成本上限；后台整理未激活。"}

    @router.post("/run")
    def run_now(request: Request):
        auth.require_action(request, "automation.run")
        raise HTTPException(status_code=503, detail={
            "code": "organizer_unavailable",
            "message": "自动整理执行器尚未通过安全验证，当前不会调用模型或创建草稿。",
        })

    return router
