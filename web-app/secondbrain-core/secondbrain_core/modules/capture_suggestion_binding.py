"""Internal-only fail-closed binding candidate for Hermes capture suggestions.

No production Hermes source adapter or Core consent ledger is registered. This
module defines the proof checks needed before such an adapter can be approved;
it intentionally exposes no HTTP route and cannot create Inbox entries.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re


_EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class VerifiedCaptureSuggestionSource:
    """Server adapter result, returned only after authenticating its source."""

    source_event_id: str
    original_text: str
    original_text_sha256: str
    source_record_version: str
    subject: str
    received_at: str
    expires_at: str


@dataclass(frozen=True)
class CoreCaptureConsentRecord:
    """Core-owned explicit consent audit row bound to one source version."""

    consent_id: str
    subject: str
    source_event_id: str
    original_text_sha256: str
    source_record_version: str
    decision: str
    recorded_at: str


@dataclass(frozen=True)
class TrustedCaptureSuggestionBinding:
    """Verified metadata only; never a bearer credential or approval by itself."""

    subject: str
    source_event_id: str
    original_text_sha256: str
    source_record_version: str
    consent_id: str
    binding_id: str


class TrustedCaptureSuggestionBindingAuthority:
    """Resolve a suggestion only from injected server-side authorities.

    ``source_reader.read_verified_suggestion`` must authenticate the original
    Hermes event and return the exact persisted record. ``consent_reader`` must
    return a Core-owned explicit user decision. Missing dependencies mean no
    trusted source exists and always fail closed.
    """

    def __init__(self, source_reader=None, consent_reader=None, clock=None):
        self.source_reader = source_reader
        self.consent_reader = consent_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(self, *, source_event_id, expected_text, expected_version,
                authenticated_subject, consent_id):
        if (self.source_reader is None or self.consent_reader is None
                or not isinstance(source_event_id, str) or not _EVENT_ID.fullmatch(source_event_id)
                or not isinstance(expected_text, str) or not expected_text.strip()
                or len(expected_text) > 200_000
                or not isinstance(expected_version, str) or not expected_version or len(expected_version) > 256
                or not isinstance(authenticated_subject, str) or not authenticated_subject
                or len(authenticated_subject) > 256
                or not isinstance(consent_id, str) or not consent_id or len(consent_id) > 128):
            return None
        try:
            source = self.source_reader.read_verified_suggestion(source_event_id)
            consent = self.consent_reader.read_consent(consent_id)
        except Exception:
            return None
        if not isinstance(source, VerifiedCaptureSuggestionSource):
            return None
        if not isinstance(consent, CoreCaptureConsentRecord):
            return None
        if (not isinstance(source.source_event_id, str)
                or not isinstance(source.original_text, str)
                or not isinstance(source.original_text_sha256, str)
                or not isinstance(source.source_record_version, str)
                or not isinstance(source.subject, str)
                or not isinstance(source.received_at, str)
                or not isinstance(source.expires_at, str)
                or not isinstance(consent.consent_id, str)
                or not isinstance(consent.subject, str)
                or not isinstance(consent.source_event_id, str)
                or not isinstance(consent.original_text_sha256, str)
                or not isinstance(consent.source_record_version, str)
                or not isinstance(consent.decision, str)
                or not isinstance(consent.recorded_at, str)
                or len(source.original_text) > 200_000
                or not source.source_record_version or len(source.source_record_version) > 256
                or not source.subject or len(source.subject) > 256
                or not consent.consent_id or len(consent.consent_id) > 128):
            return None
        digest = hashlib.sha256(source.original_text.encode("utf-8")).hexdigest()
        if (source.source_event_id != source_event_id
                or source.original_text != expected_text
                or source.original_text_sha256 != digest
                or not _SHA256.fullmatch(source.original_text_sha256)
                or source.source_record_version != expected_version
                or not source.source_record_version
                or source.subject != authenticated_subject):
            return None
        if (consent.consent_id != consent_id
                or consent.subject != authenticated_subject
                or consent.source_event_id != source_event_id
                or consent.original_text_sha256 != digest
                or consent.source_record_version != expected_version
                or consent.decision != "consented"):
            return None
        try:
            received_at = datetime.fromisoformat(source.received_at.replace("Z", "+00:00"))
            expires_at = datetime.fromisoformat(source.expires_at.replace("Z", "+00:00"))
            recorded_at = datetime.fromisoformat(consent.recorded_at.replace("Z", "+00:00"))
            now = self.clock()
            if (received_at.tzinfo is None or expires_at.tzinfo is None
                    or recorded_at.tzinfo is None or now.tzinfo is None):
                return None
            received_at = received_at.astimezone(timezone.utc)
            expires_at = expires_at.astimezone(timezone.utc)
            recorded_at = recorded_at.astimezone(timezone.utc)
            now = now.astimezone(timezone.utc)
            if now > expires_at or received_at > now or recorded_at > now or recorded_at < received_at:
                return None
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
        material = {"subject": authenticated_subject, "source_event_id": source_event_id,
                    "original_text_sha256": digest, "source_record_version": expected_version,
                    "consent_id": consent_id}
        binding_id = hashlib.sha256(json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        return TrustedCaptureSuggestionBinding(binding_id=binding_id, **material)
