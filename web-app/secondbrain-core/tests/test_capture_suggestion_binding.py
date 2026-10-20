from datetime import datetime, timezone
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json

from secondbrain_core.modules.capture_suggestion_binding import (
    CaptureSuggestionBindingConflict,
    CaptureSuggestionBindingStoreError,
    CoreCaptureConsentRecord,
    TrustedCaptureSuggestionBindingAuthority,
    TrustedCaptureSuggestionBindingStore,
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


def changed_binding(binding, **changes):
    material = {"subject": binding.subject, "source_event_id": binding.source_event_id,
                "original_text_sha256": binding.original_text_sha256,
                "source_record_version": binding.source_record_version,
                "consent_id": binding.consent_id}
    material.update(changes)
    binding_id = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    return type(binding)(binding_id=binding_id, **material)


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


def test_source_and_consent_are_rechecked_and_drift_or_revocation_fails_closed():
    class ChangingSourceReader:
        def __init__(self):
            self.calls = 0

        def read_verified_suggestion(self, event_id):
            self.calls += 1
            if self.calls == 1:
                return source_record()
            return source_record(original_text="changed after initial read",
                                 original_text_sha256=hashlib.sha256(
                                     b"changed after initial read").hexdigest())

    class RevokingConsentReader:
        def __init__(self):
            self.calls = 0

        def read_consent(self, consent_id):
            self.calls += 1
            return consent_record(decision="consented" if self.calls == 1 else "revoked")

    source_reader = ChangingSourceReader()
    assert TrustedCaptureSuggestionBindingAuthority(
        source_reader, SyntheticConsentReader(consent_record()), clock=lambda: NOW,
    ).resolve(source_event_id=EVENT_ID, expected_text=TEXT, expected_version=VERSION,
              authenticated_subject=SUBJECT, consent_id=CONSENT_ID) is None
    consent_reader = RevokingConsentReader()
    assert TrustedCaptureSuggestionBindingAuthority(
        SyntheticSourceReader(source_record()), consent_reader, clock=lambda: NOW,
    ).resolve(source_event_id=EVENT_ID, expected_text=TEXT, expected_version=VERSION,
              authenticated_subject=SUBJECT, consent_id=CONSENT_ID) is None
    assert source_reader.calls == 2
    assert consent_reader.calls == 2


def test_utf8_byte_budget_rejects_multibyte_text_over_limit():
    # Character count is below 200k, but encoded UTF-8 exceeds the budget.
    text = "漢" * 66_667
    assert len(text) < 200_000
    assert len(text.encode("utf-8")) > 200_000
    assert resolve(expected_text=text) is None
    assert resolve(authority(source=source_record(
        original_text=text, original_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
    ))) is None


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


def test_candidate_ledger_is_idempotent_and_rejects_same_event_conflict(tmp_path):
    store = TrustedCaptureSuggestionBindingStore(tmp_path)
    binding = resolve()
    assert store.record(binding) == (binding, False)
    assert TrustedCaptureSuggestionBindingStore(tmp_path).record(binding) == (binding, True)
    conflict = changed_binding(binding, original_text_sha256="1" * 64)
    try:
        store.record(conflict)
    except CaptureSuggestionBindingConflict:
        pass
    else:
        raise AssertionError("same event with different content must conflict")


def test_candidate_ledger_concurrent_identical_records_have_one_create_and_replays(tmp_path):
    binding = resolve()

    def write_once(_):
        return TrustedCaptureSuggestionBindingStore(tmp_path).record(binding)[1]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write_once, range(24)))
    assert results.count(False) == 1
    assert results.count(True) == 23
    state = json.loads((tmp_path / "capture-suggestion-bindings.json").read_text())
    assert len(state["records"]) == 1


def test_candidate_ledger_concurrent_conflicting_bindings_only_commits_one(tmp_path):
    first = resolve()
    second = changed_binding(first, original_text_sha256="4" * 64)

    def write(binding):
        try:
            return TrustedCaptureSuggestionBindingStore(tmp_path).record(binding)[1]
        except CaptureSuggestionBindingConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (first, second)))
    assert results.count(False) == 1
    assert results.count("conflict") == 1
    state = json.loads((tmp_path / "capture-suggestion-bindings.json").read_text())
    assert len(state["records"]) == 1


def test_interrupted_candidate_replace_recovers_prior_state_and_replays_after_restart(tmp_path, monkeypatch):
    store = TrustedCaptureSuggestionBindingStore(tmp_path)
    first = resolve()
    store.record(first)
    second_text = "second synthetic event"
    second_digest = hashlib.sha256(second_text.encode()).hexdigest()
    second = changed_binding(first, source_event_id="synthetic-hermes-event-0002",
                             original_text_sha256=second_digest,
                             consent_id="synthetic-consent-0002")

    def interrupted_write(state):
        temp_path = tmp_path / ".capture-suggestion-bindings-interrupted.tmp"
        temp_path.write_text(json.dumps(state))
        raise OSError("synthetic interruption before atomic replace")

    monkeypatch.setattr(store, "_atomic_write", interrupted_write)
    try:
        store.record(second)
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("interrupted replace must fail closed")
    reopened = TrustedCaptureSuggestionBindingStore(tmp_path)
    assert reopened.record(first) == (first, True)
    assert not list(tmp_path.glob(".capture-suggestion-bindings-*.tmp"))
    assert reopened.record(second) == (second, False)
    assert reopened.record(second) == (second, True)


def test_invalid_state_blocks_candidate_recovery_without_deleting_unknown_files(tmp_path):
    state_path = tmp_path / "capture-suggestion-bindings.json"
    state_path.write_text("not-json")
    orphan = tmp_path / ".capture-suggestion-bindings-stale.tmp"
    orphan.write_text("partial")
    try:
        TrustedCaptureSuggestionBindingStore(tmp_path).record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("corrupt durable state must require manual review")
    assert state_path.read_text() == "not-json"
    assert orphan.read_text() == "partial"
