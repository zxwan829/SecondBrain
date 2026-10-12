"""Single-owner, Core-only Promote unlock and short-lived browser session."""
import hashlib
import hmac
import os
import secrets
import stat
import time

from fastapi import HTTPException, Request


class CorePromoteAuth:
    """No Hermes session trust: secret file and sessions exist only in Core."""

    COOKIE_NAME = "sb_core_promote"

    def __init__(self, secret_file, allowed_origins, session_ttl=3600):
        if not os.path.isabs(secret_file):
            raise ValueError("Promote unlock secret path must be absolute")
        self.secret_file = os.path.abspath(secret_file)
        self.allowed_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)
        if not self.allowed_origins:
            raise ValueError("At least one exact Dashboard origin is required")
        self.session_ttl = int(session_ttl)
        self._sessions = {}
        self._secret = self._load_secret()

    def _load_secret(self):
        fd = os.open(self.secret_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                    or info.st_uid != os.geteuid()):
                raise ValueError("Promote unlock secret must be a private regular file (mode 0600 or stricter)")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                secret = stream.read(4097).strip()
        finally:
            os.close(fd)
        if len(secret) < 32 or len(secret) > 4096:
            raise ValueError("Promote unlock secret must contain 32-4096 bytes")
        return secret

    def _check_origin(self, request):
        origin = request.headers.get("origin", "").rstrip("/")
        if request.url.scheme != "https" or origin not in self.allowed_origins:
            raise HTTPException(status_code=403, detail="Trusted Dashboard Origin required")

    def unlock(self, request, passphrase):
        self._check_origin(request)
        if not isinstance(passphrase, str) or not hmac.compare_digest(
            passphrase.encode("utf-8"), self._secret
        ):
            raise HTTPException(status_code=401, detail="Promote unlock rejected")
        token = secrets.token_urlsafe(32)
        now = time.time()
        self._sessions[hashlib.sha256(token.encode()).hexdigest()] = now + self.session_ttl
        return token

    def require_owner(self, request):
        self._check_origin(request)
        token = request.cookies.get(self.COOKIE_NAME, "")
        if not token:
            raise HTTPException(status_code=401, detail="Promote session required")
        digest = hashlib.sha256(token.encode()).hexdigest()
        expires = self._sessions.get(digest, 0)
        if expires <= time.time():
            self._sessions.pop(digest, None)
            raise HTTPException(status_code=401, detail="Promote session expired")
        return "owner"

    def lock(self, request):
        self._check_origin(request)
        token = request.cookies.get(self.COOKIE_NAME, "")
        if token:
            self._sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    @staticmethod
    def set_session_cookie(response, request, token, ttl):
        response.set_cookie(
            key=CorePromoteAuth.COOKIE_NAME,
            value=token,
            max_age=ttl,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/api/promote",
        )

    @staticmethod
    def clear_session_cookie(response):
        response.delete_cookie(
            key=CorePromoteAuth.COOKIE_NAME,
            path="/api/promote",
            httponly=True,
            samesite="strict",
        )
