"""Single-owner App session shared by the browser-facing business APIs."""
import hashlib
import hmac
import os
import secrets
import stat
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


class AppSessionAuth:
    COOKIE_NAME = "sb_app_session"
    SUPPORTED_ACTIONS = frozenset({
        "activity.read", "agent.health.read", "auth.logout", "auth.session",
        "automation.run", "automation.settings.read", "automation.settings.write",
        "automation.status.read", "calendar.read", "capture.read", "capture.write",
        "chat.approve_tool", "chat.manage", "chat.read", "chat.run", "chat.stop",
        "chat.write", "daily_brief.read", "daily_brief.write", "home.read",
        "inbox.read", "journal.append", "journal.read", "knowledge.read", "notes.read",
        "notes.create", "notes.write", "personal_memory.read", "personal_memory.write",
        "projects.read", "promote.read", "review.defer",
        "review.read", "task.read", "task.write", "vocabulary.read", "vocabulary.write",
        "inbox.proposals.read", "inbox.proposals.write",
        "planning.approve", "planning.execute", "planning.read", "planning.write",
    })

    def __init__(self, password_file, allowed_origins, session_ttl=28800):
        if not os.path.isabs(password_file):
            raise ValueError("App password path must be absolute")
        self.allowed_origins = frozenset(value.rstrip("/") for value in allowed_origins if value)
        if not self.allowed_origins:
            raise ValueError("At least one exact App Origin is required")
        self.session_ttl = int(session_ttl)
        self._sessions = {}
        self._failed = {}
        self._password = self._load_password(password_file)

    @staticmethod
    def _load_password(path):
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                    or info.st_uid != os.geteuid()):
                raise ValueError("App password must be a private regular file owned by the App UID")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                password = stream.read(4097).strip()
        finally:
            os.close(fd)
        if len(password) < 12 or len(password) > 4096:
            raise ValueError("App password must contain 12-4096 bytes")
        return password

    def check_origin(self, request):
        origin = request.headers.get("origin", "").rstrip("/")
        if origin not in self.allowed_origins:
            raise HTTPException(status_code=403, detail="Trusted App Origin required")
        expected_scheme = urlsplit(origin).scheme
        if (request.url.scheme != expected_scheme
                or urlsplit(origin).netloc.lower() != request.url.netloc.lower()):
            raise HTTPException(status_code=403, detail="Origin and trusted request host differ")

    def login(self, request, password):
        self.check_origin(request)
        address = request.client.host if request.client else "unknown"
        now = time.monotonic()
        failures, blocked_until = self._failed.get(address, (0, 0.0))
        if blocked_until > now:
            raise HTTPException(status_code=429, detail="Too many failed login attempts")
        supplied = password.encode("utf-8") if isinstance(password, str) else b""
        if not hmac.compare_digest(supplied, self._password):
            failures += 1
            self._failed[address] = (0, now + 60) if failures >= 5 else (failures, 0.0)
            raise HTTPException(status_code=401, detail="Login rejected")
        self._failed.pop(address, None)
        token = secrets.token_urlsafe(32)
        self._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + self.session_ttl
        return token

    def require_owner(self, request):
        origin = request.headers.get("origin")
        if origin:
            normalized = origin.rstrip("/")
            if normalized not in self.allowed_origins:
                raise HTTPException(status_code=403, detail="Trusted App Origin required")
            parsed = urlsplit(normalized)
            if parsed.scheme != request.url.scheme or parsed.netloc.lower() != request.url.netloc.lower():
                raise HTTPException(status_code=403, detail="Origin and trusted request host differ")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.check_origin(request)
        token = request.cookies.get(self.COOKIE_NAME, "")
        expiry = self._sessions.get(hashlib.sha256(token.encode()).hexdigest(), 0)
        if not token or expiry <= time.time():
            raise HTTPException(status_code=401, detail="App session required")
        return "owner"

    def require_action(self, request, action):
        """Authorization seam for business operations; V1 maps every action to its single owner."""
        if not isinstance(action, str) or not action:
            raise ValueError("An action name is required")
        if action not in self.SUPPORTED_ACTIONS:
            raise HTTPException(status_code=403, detail="Action is not enabled")
        return self.require_owner(request)

    def logout(self, request):
        token = request.cookies.get(self.COOKIE_NAME, "")
        if token:
            self._sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    @classmethod
    def set_cookie(cls, response, request, token, ttl):
        response.set_cookie(cls.COOKIE_NAME, token, max_age=ttl, httponly=True,
                            secure=request.url.scheme == "https", samesite="strict", path="/")

    @classmethod
    def clear_cookie(cls, response, request):
        response.delete_cookie(cls.COOKIE_NAME, httponly=True, secure=request.url.scheme == "https",
                               samesite="strict", path="/")
