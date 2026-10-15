"""Fail-closed, file-backed Organizer schedule and model controls."""
import json
import os
import re
import stat
import tempfile
import threading
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request

from .siliconflow_organizer import MODEL_DEFAULT, SiliconFlowOrganizerModel


INTERVAL_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
DEFAULT_SETTINGS = {
    "enabled": False,
    "mode": "interval",
    "interval_hours": 4,
    "daily_time": "00:30",
    "timezone": "Asia/Shanghai",
}
DEFAULT_MODEL_SETTINGS = {"provider": "siliconflow", "model": MODEL_DEFAULT,
                         "model_enabled": False, "scheduler_enabled": False,
                         "monthly_soft_budget_cny": 10}


class OrganizerControlStore:
    """Organizer model controls and a separate, owner-only provider key file."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise RuntimeError("Organizer control root must be a real directory")
        info = os.stat(self.root, follow_symlinks=False)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError("Organizer control root must be private and owned by the App UID")
        self.settings_path = self.root / "model-settings.json"
        self.secret_path = self.root / "siliconflow-api-key"
        self._lock = threading.RLock()

    def read(self):
        with self._lock:
            value = dict(DEFAULT_MODEL_SETTINGS)
            if self.settings_path.exists():
                if self.settings_path.is_symlink() or not self.settings_path.is_file():
                    raise RuntimeError("Organizer model settings must be a regular file")
                info = os.stat(self.settings_path, follow_symlinks=False)
                if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise RuntimeError("Organizer model settings must be private")
                saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if (not isinstance(saved, dict) or saved.get("provider") != "siliconflow"
                        or saved.get("model") != MODEL_DEFAULT
                        or type(saved.get("model_enabled")) is not bool
                        or type(saved.get("scheduler_enabled")) is not bool):
                    raise RuntimeError("Unsupported Organizer model settings")
                value.update(saved)
            value["api_key_configured"] = self.has_secret()
            return value

    def has_secret(self):
        try:
            info = os.stat(self.secret_path, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or self.secret_path.is_symlink()):
            raise RuntimeError("Organizer API key file must be private and owned by the App UID")
        return info.st_size > 0

    def write_settings(self, value):
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail="Model settings must be an object")
        provider, model = value.get("provider", "siliconflow"), value.get("model", MODEL_DEFAULT)
        model_enabled = value.get("model_enabled", False)
        scheduler_enabled = value.get("scheduler_enabled", False)
        if provider != "siliconflow" or model != MODEL_DEFAULT:
            raise HTTPException(status_code=422, detail="Unsupported Organizer provider or model")
        if type(model_enabled) is not bool or type(scheduler_enabled) is not bool:
            raise HTTPException(status_code=422, detail="Organizer enable flags must be boolean")
        if model_enabled and not self.has_secret():
            raise HTTPException(status_code=409, detail="Configure an API key before enabling the model")
        saved = {"provider": provider, "model": model, "model_enabled": model_enabled,
                 "scheduler_enabled": scheduler_enabled,
                 "monthly_soft_budget_cny": DEFAULT_MODEL_SETTINGS["monthly_soft_budget_cny"]}
        payload = json.dumps(saved, ensure_ascii=False, sort_keys=True).encode("utf-8")
        with self._lock:
            fd, temp_path = tempfile.mkstemp(prefix=".model-settings-", dir=self.root)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp_path, self.settings_path)
                self._sync_directory()
            finally:
                try: os.unlink(temp_path)
                except FileNotFoundError: pass
        return self.read()

    def save_secret(self, secret):
        if (not isinstance(secret, str) or not secret or len(secret.encode("utf-8")) > 4096
                or any(ord(char) < 33 or ord(char) > 126 for char in secret)):
            raise HTTPException(status_code=422, detail="API key is empty or malformed")
        with self._lock:
            fd, temp_path = tempfile.mkstemp(prefix=".api-key-", dir=self.root)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(secret.encode("utf-8")); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp_path, self.secret_path)
                self._sync_directory()
            finally:
                try: os.unlink(temp_path)
                except FileNotFoundError: pass
        return {"api_key_configured": self.has_secret()}

    def delete_secret(self):
        with self._lock:
            try:
                self.secret_path.unlink()
                self._sync_directory()
            except FileNotFoundError:
                pass
        return {"api_key_configured": False}

    def _sync_directory(self):
        fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def load_model(self):
        settings = self.read()
        if not settings["model_enabled"]:
            return None
        if not settings["api_key_configured"]:
            raise RuntimeError("Organizer model is enabled but no API key is configured")
        return SiliconFlowOrganizerModel.from_secret_file(str(self.secret_path), model=MODEL_DEFAULT)


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


def create_auto_organize_router(auth, runner, controls):
    router = APIRouter(prefix="/api/automation/organize")

    @router.get("/settings")
    def settings(request: Request):
        auth.require_action(request, "automation.settings.read")
        return runner.settings.read()

    @router.put("/settings")
    def update_settings(request: Request, body: dict):
        auth.require_action(request, "automation.settings.write")
        return runner.update_settings(body)

    @router.get("/status")
    def status(request: Request):
        auth.require_action(request, "automation.status.read")
        return runner.status()

    @router.post("/run")
    async def run_now(request: Request):
        auth.require_action(request, "automation.run")
        return await runner.run(reason="manual")

    @router.get("/model-settings")
    def model_settings(request: Request):
        auth.require_action(request, "automation.settings.read")
        return controls.read()

    @router.put("/model-settings")
    def update_model_settings(request: Request, body: dict):
        auth.require_action(request, "automation.settings.write")
        with runner.configuration_change():
            saved = controls.write_settings(body)
            # Configuration changes are inert: no provider call, scheduler task, or job starts here.
            runner.model = controls.load_model()
            runner.scheduler_enabled = False  # Takes effect only on a later app start; no task starts during settings save.
        return saved

    @router.put("/api-key")
    def save_api_key(request: Request, body: dict):
        auth.require_action(request, "automation.settings.write")
        with runner.configuration_change():
            result = controls.save_secret(body.get("api_key"))
            if controls.read()["model_enabled"]:
                runner.model = controls.load_model()
        return result

    @router.delete("/api-key")
    def delete_api_key(request: Request):
        auth.require_action(request, "automation.settings.write")
        with runner.configuration_change():
            runner.model = None
            result = controls.delete_secret()
            values = controls.read()
            values["model_enabled"] = False
            controls.write_settings(values)
        return result

    @router.post("/connection-test")
    def mock_connection_test(request: Request):
        auth.require_action(request, "automation.settings.write")
        config = controls.read()
        return {"kind": "local_mock", "provider": config["provider"], "model": config["model"],
                "api_key_configured": config["api_key_configured"],
                "message": "本地 Mock 配置检查通过；未连接 SiliconFlow，未发送 API 请求。"}

    return router
