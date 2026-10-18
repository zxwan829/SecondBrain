"""Single-owner, Core-only Promote unlock and short-lived browser session."""
import hashlib
import hmac
import os
import secrets
import stat
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


class CorePromoteAuth:
    """No Hermes session trust: secret file and sessions exist only in Core."""

    COOKIE_NAME = "sb_core_promote"

    def __init__(self, secret_file, allowed_origins, app_auth=None, allowed_hosts=None,
                 session_ttl=900):
        self.secret_file = os.path.abspath(secret_file) if secret_file else None
        self.allowed_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)
        if not self.allowed_origins:
            raise ValueError("At least one exact Dashboard origin is required")
        self.allowed_hosts = frozenset(host.lower() for host in (allowed_hosts or ()))
        self.session_ttl = min(max(int(session_ttl), 1), 900)
        self.app_auth = app_auth
        self._binding_key = secrets.token_bytes(32)
        self._sessions = {}
        self._failed = {}
        try:
            if not self.secret_file:
                raise ValueError("Promote unlock secret is not configured")
            self._secret = self._load_secret()
            self._secret_error = False
        except (OSError, ValueError):
            self._secret = None
            self._secret_error = True

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

    def _check_origin(self, request, *, allow_originless_same_origin=False):
        origin_header = request.headers.get("origin")
        origin = (origin_header or "").rstrip("/")
        fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
        host = request.headers.get("host", "").lower()
        parsed = urlsplit(origin) if origin else None
        host_url = urlsplit("//" + host) if host else None
        allowed_origin_hosts = {urlsplit(allowed).netloc.lower() for allowed in self.allowed_origins}
        trusted_host = bool(host and host == request.url.netloc.lower() and
                            host in allowed_origin_hosts and host_url and host_url.hostname and
                            (not self.allowed_hosts or host_url.hostname.lower() in self.allowed_hosts))
        if request.url.scheme != "https" or not trusted_host or fetch_site == "cross-site":
            raise HTTPException(status_code=403, detail={"code": "trusted_origin_required"})
        if origin_header is None:
            if not allow_originless_same_origin or fetch_site != "same-origin":
                raise HTTPException(status_code=403, detail={"code": "trusted_origin_required"})
            return
        if (origin not in self.allowed_origins or parsed is None or
                parsed.netloc.lower() != host):
            raise HTTPException(status_code=403, detail={"code": "trusted_origin_required"})

    def require_app(self, request, *, allow_originless_same_origin=False):
        self._check_origin(request, allow_originless_same_origin=allow_originless_same_origin)
        if self.app_auth is None:
            raise HTTPException(status_code=503, detail={"code": "app_session_binding_unavailable"})
        try:
            self.app_auth.require_owner(request)
        except HTTPException as exc:
            code = "app_session_required" if exc.status_code == 401 else "trusted_origin_required"
            raise HTTPException(status_code=exc.status_code, detail={"code": code}) from exc
        app_token = request.cookies.get(self.app_auth.COOKIE_NAME, "")
        if not app_token:
            raise HTTPException(status_code=401, detail={"code": "app_session_required"})
        return hmac.new(self._binding_key, app_token.encode("utf-8"), hashlib.sha256).hexdigest()

    def unlock(self, request, passphrase):
        self._check_origin(request)
        app_binding = self.require_app(request)
        if self._secret_error or self._secret is None:
            raise HTTPException(status_code=503, detail={"code": "promote_unlock_unavailable"})
        address = request.client.host if request.client else "unknown"
        now = time.monotonic()
        failures, blocked_until = self._failed.get(address, (0, 0.0))
        if blocked_until > now:
            raise HTTPException(status_code=429, detail={"code": "unlock_rate_limited"})
        if not isinstance(passphrase, str) or not hmac.compare_digest(
            passphrase.encode("utf-8"), self._secret
        ):
            failures += 1
            self._failed[address] = (0, now + 60) if failures >= 5 else (failures, 0.0)
            raise HTTPException(status_code=401, detail={"code": "promote_unlock_rejected"})
        self._failed.pop(address, None)
        token = secrets.token_urlsafe(32)
        self._sessions[hashlib.sha256(token.encode()).hexdigest()] = {
            "expires": time.time() + self.session_ttl,
            "app_binding": app_binding,
        }
        return token

    def require_owner(self, request, *, allow_originless_same_origin=False):
        app_binding = self.require_app(request, allow_originless_same_origin=allow_originless_same_origin)
        token = request.cookies.get(self.COOKIE_NAME, "")
        if not token:
            raise HTTPException(status_code=401, detail={"code": "promote_session_required"})
        digest = hashlib.sha256(token.encode()).hexdigest()
        session = self._sessions.get(digest)
        if not session or session["expires"] <= time.time():
            self._sessions.pop(digest, None)
            raise HTTPException(status_code=401, detail={"code": "promote_session_expired"})
        if not hmac.compare_digest(session["app_binding"], app_binding):
            self._sessions.pop(digest, None)
            raise HTTPException(status_code=401, detail={"code": "promote_session_binding_expired"})
        return "owner"

    def require_action(self, request, action):
        """Compatibility policy seam; legacy Core unlock currently authorizes one owner."""
        if not isinstance(action, str) or not action:
            raise ValueError("An action name is required")
        return self.require_owner(request)

    def lock(self, request):
        self._check_origin(request)
        if self.app_auth is not None:
            self.app_auth.require_owner(request)
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
