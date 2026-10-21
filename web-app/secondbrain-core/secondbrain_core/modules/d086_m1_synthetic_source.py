"""D086-M1 synthetic-only server authority. No production adapter or route.

The fixture owner is the only writer. Requests supply only an event id, never
source bytes, subject, version or lifecycle. This is *not* Hermes authentication.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import hashlib
import threading

from .capture_suggestion_binding import VerifiedCaptureSuggestionSource


class SyntheticSourceAuthority:
    """In-memory test authority with monotonic anti-ABA revisions."""

    source_system = "synthetic.m1"

    def __init__(self, *, clock=None):
        self._records = {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

    @contextmanager
    def source_commit_guard(self, event_id):
        """Synthetic-only writer exclusion held through the SQLite commit.

        This models a source-side CAS/lease for tests; it does not establish a
        real Hermes lock or provide cross-system atomicity.
        """
        with self._lock:
            yield

    def register(self, *, event_id, subject, original_text, ttl_seconds=300):
        with self._lock:
            if event_id in self._records:
                raise ValueError("event exists")
            if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 3600:
                raise ValueError("invalid TTL")
            now = self._clock()
            if not isinstance(now, datetime) or now.tzinfo is None:
                raise ValueError("invalid clock")
            record = VerifiedCaptureSuggestionSource(
                source_event_id=event_id,
                original_text=original_text,
                original_text_sha256=hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
                source_record_version="1",
                subject=subject,
                received_at=now.astimezone(timezone.utc).isoformat(),
                expires_at=(now + timedelta(seconds=ttl_seconds)).astimezone(timezone.utc).isoformat(),
                source_system=self.source_system,
                lifecycle_status="active",
            )
            self._records[event_id] = record
            return record

    def read_verified_suggestion(self, event_id):
        """Trusted test-side read, not an authentication claim about Hermes."""
        with self._lock:
            return self._records.get(event_id)

    def revise(self, event_id, *, original_text=None, lifecycle_status="active"):
        with self._lock:
            previous = self._records[event_id]
            text = previous.original_text if original_text is None else original_text
            record = replace(
                previous,
                original_text=text,
                original_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                source_record_version=str(int(previous.source_record_version) + 1),
                lifecycle_status=lifecycle_status,
            )
            self._records[event_id] = record
            return record
