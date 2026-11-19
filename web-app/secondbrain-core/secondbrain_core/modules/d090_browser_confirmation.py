"""Authority-owned browser confirmation, using the existing App session validator."""

import hashlib
import secrets
import threading
import time

from .d090_authority_writer import HumanProofUnavailable


class BrowserConfirmation:
    def __init__(self, app_auth):
        self._auth = app_auth
        self._pending = {}
        self._lock = threading.Lock()

    def _session(self, request):
        self._auth.check_origin(request)
        subject = self._auth.require_owner(request)
        token = request.cookies[self._auth.COOKIE_NAME]
        return subject, hashlib.sha256(token.encode()).digest()

    def prepare(self, request, binding):
        session = self._session(request)
        now = int(time.time())
        nonce = secrets.token_urlsafe(32)
        with self._lock:
            self._pending = {key: entry for key, entry in self._pending.items()
                             if entry[1]["expires_at"] > now}
            if len(self._pending) >= 128:
                raise HumanProofUnavailable("confirmation_capacity_exceeded")
            exact = {**binding, "nonce": nonce, "expires_at": now + 60}
            self._pending[nonce] = (session, exact)
        return dict(exact)

    def consume(self, request, binding):
        session = self._session(request)
        if request.method != "POST":
            raise HumanProofUnavailable("confirmation_post_required")
        with self._lock:
            expected = self._pending.get(binding["nonce"])
            if expected != (session, binding) or binding["expires_at"] <= int(time.time()):
                raise HumanProofUnavailable("confirmation_missing_or_mismatched")
            del self._pending[binding["nonce"]]
