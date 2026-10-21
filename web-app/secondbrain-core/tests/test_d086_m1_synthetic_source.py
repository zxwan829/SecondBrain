"""Only synthetic D086 M1 source evidence; no real Hermes API or Inbox."""
from datetime import datetime, timedelta, timezone

from secondbrain_core.modules.capture_suggestion_binding import (
    validate_verified_capture_suggestion_source,
)
from secondbrain_core.modules.d086_m1_synthetic_source import SyntheticSourceAuthority


NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)


def validate(authority, record, *, expected_version="1"):
    first = authority.read_verified_suggestion("m1-event")
    second = authority.read_verified_suggestion("m1-event")
    return validate_verified_capture_suggestion_source(
        first, second, allowed_source_systems={"synthetic.m1"},
        expected_event_id="m1-event", expected_text=record.original_text,
        expected_version=expected_version, expected_subject="owner", now=NOW,
    )


def test_synthetic_source_exact_original_and_anti_aba():
    authority = SyntheticSourceAuthority(clock=lambda: NOW)
    original = authority.register(event_id="m1-event", subject="owner", original_text="原文")
    assert validate(authority, original) == original
    edited = authority.revise("m1-event", original_text="修改")
    assert validate(authority, original) is None
    assert edited.source_record_version == "2"
    restored = authority.revise("m1-event", original_text="原文")
    assert restored.original_text_sha256 == original.original_text_sha256
    assert restored.source_record_version == "3"
    assert validate(authority, original) is None
    assert validate(authority, restored, expected_version="3") == restored


def test_synthetic_source_deleted_expired_and_spoofed_metadata_fail_closed():
    authority = SyntheticSourceAuthority(clock=lambda: NOW)
    original = authority.register(event_id="m1-event", subject="owner", original_text="bytes")
    authority.revise("m1-event", lifecycle_status="deleted")
    assert validate(authority, original, expected_version="2") is None
    assert validate(authority, original) is None
    assert validate_verified_capture_suggestion_source(
        original, original, allowed_source_systems={"synthetic.m1"},
        expected_event_id="m1-event", expected_text=original.original_text,
        expected_version="1", expected_subject="forged-user", now=NOW,
    ) is None
    assert validate_verified_capture_suggestion_source(
        original, original, allowed_source_systems={"untrusted.hermes"},
        expected_event_id="m1-event", expected_text=original.original_text,
        expected_version="1", expected_subject="owner", now=NOW,
    ) is None
    assert validate_verified_capture_suggestion_source(
        original, original, allowed_source_systems={"synthetic.m1"},
        expected_event_id="m1-event", expected_text=original.original_text,
        expected_version="1", expected_subject="owner", now=NOW + timedelta(seconds=301),
    ) is None


def test_synthetic_source_reader_pair_drift_rejected():
    authority = SyntheticSourceAuthority(clock=lambda: NOW)
    first = authority.register(event_id="m1-event", subject="owner", original_text="start")
    second = authority.revise("m1-event", original_text="changed")
    assert validate_verified_capture_suggestion_source(
        first, second, allowed_source_systems={"synthetic.m1"},
        expected_event_id="m1-event", expected_text="start",
        expected_version="1", expected_subject="owner", now=NOW,
    ) is None
