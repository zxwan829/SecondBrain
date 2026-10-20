from datetime import datetime, timezone
import hashlib

from secondbrain_core.modules.capture_suggestion_binding import (
    CoreCaptureConsentRecord,
    TrustedCaptureSuggestionBindingAuthority,
    VerifiedCaptureSuggestionSource,
)


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
TEXT = "synthetic suggestion source text"
EVENT_ID = "synthetic-hermes-event-0001"
VERSION = "record-v1"
SUBJECT = "synthetic-owner"
CONSENT_ID = "synthetic-consent-0001"
DIGEST = hashlib.sha256(TEXT.encode()).hexdigest()


class SyntheticSourceReader:
    def __init__(self, record):
        self.record = record

    def read_verified_suggestion(self, source_event_id):
        assert source_event_id == self.record.source_event_id
        return self.record


class SyntheticConsentReader:
    def __init__(self, record):
        self.record = record

    def read_consent(self, consent_id):
        assert consent_id == self.record.consent_id
        return self.record


def source_record(**changes):
    fields = dict(source_event_id=EVENT_ID, original_text=TEXT,
                  original_text_sha256=DIGEST, source_record_version=VERSION,
                  subject=SUBJECT, received_at="2026-10-20T11:58:00Z",
                  expires_at="2026-10-20T12:05:00Z")
    fields.update(changes)
    return VerifiedCaptureSuggestionSource(**fields)


def consent_record(**changes):
    fields = dict(consent_id=CONSENT_ID, subject=SUBJECT, source_event_id=EVENT_ID,
                  original_text_sha256=DIGEST, source_record_version=VERSION,
                  decision="consented", recorded_at="2026-10-20T11:59:00Z")
    fields.update(changes)
    return CoreCaptureConsentRecord(**fields)


def authority(source=None, consent=None):
    return TrustedCaptureSuggestionBindingAuthority(
        SyntheticSourceReader(source or source_record()),
        SyntheticConsentReader(consent or consent_record()),
        clock=lambda: NOW,
    )


def resolve(service=None, **overrides):
    args = dict(source_event_id=EVENT_ID, expected_text=TEXT, expected_version=VERSION,
                authenticated_subject=SUBJECT, consent_id=CONSENT_ID)
    args.update(overrides)
    return (service or authority()).resolve(**args)


def test_no_trusted_server_adapters_means_no_binding():
    assert resolve(TrustedCaptureSuggestionBindingAuthority()) is None
    assert resolve(TrustedCaptureSuggestionBindingAuthority(source_reader=SyntheticSourceReader(source_record()))) is None


def test_exact_server_source_and_core_consent_yield_deterministic_metadata_binding():
    first = resolve()
    second = resolve()
    assert first == second
    assert first.source_event_id == EVENT_ID
    assert first.subject == SUBJECT
    assert first.original_text_sha256 == DIGEST
    assert first.source_record_version == VERSION
    assert first.consent_id == CONSENT_ID
    assert len(first.binding_id) == 64
    assert TEXT not in repr(first)
    assert "session" not in repr(first).lower() and "run" not in repr(first).lower()


def test_source_event_text_hash_version_or_subject_drift_fails_closed():
    for bad_source in (
        source_record(original_text="different text"),
        source_record(original_text_sha256="0" * 64),
        source_record(source_record_version="record-v2"),
        source_record(subject="different-owner"),
        source_record(source_event_id="different-event"),
    ):
        assert resolve(authority(source=bad_source)) is None
    assert resolve(expected_text="web-supplied replacement") is None
    assert resolve(expected_version="web-supplied-version") is None
    assert resolve(authenticated_subject="web-supplied-subject") is None
    assert resolve(source_event_id="web-supplied-event") is None
    assert resolve(expected_text="x" * 200_001) is None
    assert resolve(expected_version="v" * 257) is None


def test_missing_mismatched_or_unapproved_consent_fails_closed():
    for bad_consent in (
        consent_record(subject="other-owner"),
        consent_record(source_event_id="other-event"),
        consent_record(original_text_sha256="0" * 64),
        consent_record(source_record_version="record-v2"),
        consent_record(decision="rejected"),
        consent_record(consent_id="other-consent"),
    ):
        assert resolve(authority(consent=bad_consent)) is None
    assert resolve(consent_id="") is None


def test_expired_or_malformed_source_and_consent_times_fail_closed():
    assert resolve(authority(source=source_record(expires_at="2026-10-20T11:59:59Z"))) is None
    assert resolve(authority(source=source_record(expires_at="not-a-time"))) is None
    assert resolve(authority(source=source_record(received_at="not-a-time"))) is None
    assert resolve(authority(source=source_record(received_at="2026-10-20T12:01:00Z"))) is None
    assert resolve(authority(consent=consent_record(recorded_at="2026-10-20T12:00:01Z"))) is None
    assert resolve(authority(consent=consent_record(recorded_at="2026-10-20T11:57:00Z"))) is None
    assert resolve(authority(consent=consent_record(recorded_at="no-timezone"))) is None


def test_authority_backend_errors_and_untyped_records_fail_closed():
    class BrokenReader:
        def read_verified_suggestion(self, event_id):
            raise PermissionError("synthetic source permission denied")

    assert resolve(TrustedCaptureSuggestionBindingAuthority(
        BrokenReader(), SyntheticConsentReader(consent_record()), clock=lambda: NOW,
    )) is None
    assert resolve(TrustedCaptureSuggestionBindingAuthority(
        SyntheticSourceReader({"source_event_id": EVENT_ID}),
        SyntheticConsentReader(consent_record()), clock=lambda: NOW,
    )) is None
