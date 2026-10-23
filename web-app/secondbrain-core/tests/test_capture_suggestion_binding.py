from datetime import datetime, timezone
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import multiprocessing
import os
import stat
from types import SimpleNamespace

from secondbrain_core.modules.capture_suggestion_binding import (
    CaptureSuggestionBindingConflict,
    CaptureSuggestionBindingStoreError,
    CaptureSuggestionConsentDecisionCandidate,
    CoreCaptureConsentRecord,
    TrustedCaptureSuggestionActionContext,
    TrustedCaptureSuggestionBindingAuthority,
    TrustedCaptureSuggestionBindingStore,
    VerifiedCaptureSuggestionSource,
    validate_capture_suggestion_acceptance,
    validate_verified_capture_suggestion_source,
)


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
TEXT = "synthetic suggestion source text"
EVENT_ID = "synthetic-hermes-event-0001"
VERSION = "1"
SUBJECT = "synthetic-owner"
CONSENT_ID = "synthetic-consent-0001"
SOURCE_SYSTEM = "synthetic.hermes"
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
                  expires_at="2026-10-20T12:05:00Z",
                  source_system=SOURCE_SYSTEM, lifecycle_status="active")
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
        allowed_source_systems={SOURCE_SYSTEM},
    )


def resolve(service=None, **overrides):
    args = dict(source_event_id=EVENT_ID, expected_text=TEXT, expected_version=VERSION,
                authenticated_subject=SUBJECT, consent_id=CONSENT_ID)
    args.update(overrides)
    return (service or authority()).resolve(**args)


class SyntheticAppendOnlyConsentAudit:
    """Test-only event list; never imported by Core application code."""

    def __init__(self):
        self._events = []

    @property
    def events(self):
        return tuple(self._events)

    @staticmethod
    def _fingerprint(event):
        material = {name: getattr(event, name) for name in (
            "decision", "actor_subject", "source_event_id", "source_record_version",
            "original_text_sha256", "intent", "idempotency_key",
        )}
        return hashlib.sha256(json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()

    def append(self, event):
        if (type(event) is not CaptureSuggestionConsentDecisionCandidate
                or event.decision != "accept"
                or event.semantic_fingerprint != self._fingerprint(event)):
            raise ValueError("invalid synthetic audit candidate")
        slot = (event.source_event_id, event.intent)
        for prior in self._events:
            if (prior.source_event_id, prior.intent) == slot:
                if prior == event:
                    return prior, True
                if (prior.semantic_fingerprint == event.semantic_fingerprint
                        and self._fingerprint(prior) == self._fingerprint(event)):
                    return prior, True
                raise ValueError("synthetic audit conflict")
        self._events.append(event)
        return event, False


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


def _record_binding_in_process(root, binding, result_queue):
    try:
        _, replayed = TrustedCaptureSuggestionBindingStore(root).record(binding)
        result_queue.put("replay" if replayed else "created")
    except CaptureSuggestionBindingConflict:
        result_queue.put("conflict")
    except Exception as exc:  # surfaced in the parent assertion
        result_queue.put(f"error:{type(exc).__name__}:{exc}")


def _run_process_race(root, bindings):
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    processes = [context.Process(target=_record_binding_in_process,
                                 args=(str(root), binding, result_queue))
                 for binding in bindings]
    for process in processes:
        process.start()
    results = [result_queue.get(timeout=30) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        assert not process.is_alive()
        assert process.exitcode == 0
    result_queue.close()
    return results


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
        source_record(source_record_version="2"),
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


def test_pure_source_verifier_requires_allowlisted_active_canonical_source():
    valid = source_record()
    assert validate_verified_capture_suggestion_source(
        valid, valid, allowed_source_systems={SOURCE_SYSTEM},
        expected_event_id=EVENT_ID, expected_text=TEXT,
        expected_version=VERSION, expected_subject=SUBJECT, now=NOW,
    ) == valid
    for invalid in (
        source_record(source_system="client.claimed-hermes"),
        source_record(lifecycle_status="edited"),
        source_record(lifecycle_status="deleted"),
        source_record(lifecycle_status="unknown"),
        source_record(source_record_version="0"),
        source_record(source_record_version="01"),
        source_record(source_record_version="+1"),
        source_record(source_record_version="record-v1"),
        source_record(subject="other-owner"),
        source_record(original_text=""),
        source_record(expires_at="2026-10-20T12:00:00Z"),
    ):
        assert validate_verified_capture_suggestion_source(
            invalid, invalid, allowed_source_systems={SOURCE_SYSTEM},
            expected_event_id=EVENT_ID, expected_text=TEXT,
            expected_version=VERSION, expected_subject=SUBJECT, now=NOW,
        ) is None
    assert validate_verified_capture_suggestion_source(
        valid, valid, allowed_source_systems=set(),
        expected_event_id=EVENT_ID, expected_text=TEXT,
        expected_version=VERSION, expected_subject=SUBJECT, now=NOW,
    ) is None


def test_pure_source_verifier_rejects_unstable_pair_and_aba_reuse():
    original = source_record(source_record_version="1")
    edited = source_record(original_text="edited", original_text_sha256=hashlib.sha256(
        b"edited").hexdigest(), source_record_version="2")
    restored = source_record(source_record_version="3")
    args = dict(allowed_source_systems={SOURCE_SYSTEM}, expected_event_id=EVENT_ID,
                expected_text=TEXT, expected_version="1", expected_subject=SUBJECT,
                now=NOW)
    assert validate_verified_capture_suggestion_source(original, edited, **args) is None
    # Restoring the original bytes creates a new source revision; the prior
    # binding's revision 1 cannot be replayed against revision 3.
    assert restored.original_text == original.original_text
    assert restored.original_text_sha256 == original.original_text_sha256
    assert restored.source_record_version != original.source_record_version
    assert validate_verified_capture_suggestion_source(restored, restored, **args) is None
    assert validate_verified_capture_suggestion_source(
        restored, restored, **{**args, "expected_version": "3"},
    ) == restored


def test_pure_source_verifier_enforces_utf8_bytes_and_has_no_reader_side_effects():
    text = "漢" * 66_667
    over_budget = source_record(original_text=text, original_text_sha256=hashlib.sha256(
        text.encode("utf-8")).hexdigest())
    args = dict(allowed_source_systems={SOURCE_SYSTEM}, expected_event_id=EVENT_ID,
                expected_text=text, expected_version=VERSION, expected_subject=SUBJECT,
                now=NOW)
    assert validate_verified_capture_suggestion_source(over_budget, over_budget, **args) is None

    class CountingReader:
        def __init__(self, record):
            self.record = record
            self.calls = 0

        def read_verified_suggestion(self, _event_id):
            self.calls += 1
            return self.record

    reader = CountingReader(source_record())
    assert validate_verified_capture_suggestion_source(
        reader.record, reader.record, **{**args, "expected_text": TEXT},
    ) == reader.record
    assert reader.calls == 0


def accept_candidate(*, source=None, action_context=None, intent="journal_intent",
                     idempotency_key="synthetic-decision-0001", now=NOW):
    record = source or source_record()
    context = action_context or TrustedCaptureSuggestionActionContext(
        authenticated_subject=SUBJECT, session_authenticated=True,
        origin_validated=True, permission_checked=True,
    )
    return validate_capture_suggestion_acceptance(
        record, record, allowed_source_systems={SOURCE_SYSTEM},
        action_context=context, intent=intent, idempotency_key=idempotency_key,
        now=now,
    )


def test_s2_accept_validator_returns_only_non_authorizing_candidate():
    candidate = accept_candidate()
    assert candidate is not None
    assert candidate.decision == "accept"
    assert candidate.actor_subject == SUBJECT
    assert candidate.source_event_id == EVENT_ID
    assert candidate.source_record_version == VERSION
    assert candidate.original_text_sha256 == DIGEST
    assert candidate.intent == "journal_intent"
    assert TEXT not in repr(candidate)
    assert "session" not in repr(candidate).lower()
    assert "run" not in repr(candidate).lower()
    later_replay = accept_candidate(now=datetime(2026, 10, 20, 12, 0, 1,
                                                   tzinfo=timezone.utc))
    assert later_replay.semantic_fingerprint == candidate.semantic_fingerprint
    assert later_replay.recorded_at != candidate.recorded_at


def test_s2_accept_validator_rejects_untrusted_or_incomplete_action_context():
    for context in (
        {"authenticated_subject": SUBJECT, "session": "forged", "run": "forged"},
        TrustedCaptureSuggestionActionContext(SUBJECT, False, True, True),
        TrustedCaptureSuggestionActionContext(SUBJECT, True, False, True),
        TrustedCaptureSuggestionActionContext(SUBJECT, True, True, False),
        TrustedCaptureSuggestionActionContext("other-subject", True, True, True),
    ):
        assert accept_candidate(action_context=context) is None
    assert accept_candidate(intent="") is None
    assert accept_candidate(intent="../../write") is None
    assert accept_candidate(idempotency_key="x" * 129) is None
    assert accept_candidate(now=datetime(2026, 10, 20, 12, 5,
                                           tzinfo=timezone.utc)) is None


def test_s2_mock_append_only_audit_exact_replay_and_conflicts():
    audit = SyntheticAppendOnlyConsentAudit()
    first = accept_candidate()
    assert audit.append(first) == (first, False)
    replay = accept_candidate(now=datetime(2026, 10, 20, 12, 0, 1,
                                           tzinfo=timezone.utc))
    stored, was_replay = audit.append(replay)
    assert was_replay is True
    assert stored == first
    assert len(audit.events) == 1

    # The same event/intent cannot rotate its key or change its bound version,
    # digest, actor, or decision to manufacture a second audit outcome.
    conflicting_candidates = (
        accept_candidate(idempotency_key="rotated-key"),
        replace(first, actor_subject="other-subject"),
        replace(first, source_record_version="2"),
        replace(first, original_text_sha256="0" * 64),
        replace(first, decision="revoke"),
    )
    for conflict in conflicting_candidates:
        try:
            audit.append(conflict)
        except ValueError:
            pass
        else:
            raise AssertionError("different accept tuple must conflict")
    assert audit.events == (first,)


def test_s2_validation_rejects_drift_without_appending_audit():
    audit = SyntheticAppendOnlyConsentAudit()
    changed = source_record(source_record_version="2")
    candidate = validate_capture_suggestion_acceptance(
        source_record(), changed, allowed_source_systems={SOURCE_SYSTEM},
        action_context=TrustedCaptureSuggestionActionContext(
            SUBJECT, True, True, True,
        ), intent="journal_intent", idempotency_key="synthetic-key", now=NOW,
    )
    assert candidate is None
    assert audit.events == ()


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
        consent_record(source_record_version="2"),
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


def test_candidate_ledger_true_process_cold_start_races_2_4_8(tmp_path):
    binding = resolve()
    for count in (2, 4, 8):
        root = tmp_path / f"cold-{count}"
        root.mkdir(mode=0o700)
        results = _run_process_race(root, [binding] * count)
        assert results.count("created") == 1
        assert results.count("replay") == count - 1
        assert not [result for result in results if result.startswith("error:")]
        state = json.loads((root / "capture-suggestion-bindings.json").read_text())
        assert len(state["records"]) == 1


def test_candidate_ledger_true_process_same_event_conflict_is_single_winner(tmp_path):
    first = resolve()
    second = changed_binding(first, original_text_sha256="6" * 64)
    results = _run_process_race(tmp_path, [first, second])
    assert results.count("created") == 1
    assert results.count("conflict") == 1


def test_interrupted_candidate_replace_recovers_prior_state_and_replays_after_restart(tmp_path, monkeypatch):
    store = TrustedCaptureSuggestionBindingStore(tmp_path)
    first = resolve()
    store.record(first)
    second_text = "second synthetic event"
    second_digest = hashlib.sha256(second_text.encode()).hexdigest()
    second = changed_binding(first, source_event_id="synthetic-hermes-event-0002",
                             original_text_sha256=second_digest,
                             consent_id="synthetic-consent-0002")

    def interrupted_write(state, root_fd):
        temp_path = tmp_path / ".capture-suggestion-bindings-interrupted.tmp"
        temp_path.write_text(json.dumps(state))
        temp_path.chmod(0o600)
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


def test_directory_fsync_failure_after_replace_is_ambiguous_then_replay_safe(tmp_path, monkeypatch):
    import secondbrain_core.modules.capture_suggestion_binding as binding_module

    binding = resolve()
    original_fsync = binding_module.os.fsync
    calls = 0

    def fail_first_directory_fsync(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic directory fsync failure after replace")
        return original_fsync(fd)

    monkeypatch.setattr(binding_module.os, "fsync", fail_first_directory_fsync)
    try:
        TrustedCaptureSuggestionBindingStore(tmp_path).record(binding)
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("post-replace directory fsync failure must not report durable success")
    assert (tmp_path / "capture-suggestion-bindings.json").exists()

    # Even after restarting the store, an exact replay cannot be called
    # duplicate until a directory fsync has succeeded.
    replay_fsync_calls = 0

    def fail_replay_directory_fsync(fd):
        nonlocal replay_fsync_calls
        replay_fsync_calls += 1
        raise OSError("synthetic replay directory fsync failure")

    monkeypatch.setattr(binding_module.os, "fsync", fail_replay_directory_fsync)
    try:
        TrustedCaptureSuggestionBindingStore(tmp_path).record(binding)
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("replay without durable directory fsync must not succeed")
    assert replay_fsync_calls == 1

    successful_replay_fsync_calls = 0

    def count_successful_replay_fsync(fd):
        nonlocal successful_replay_fsync_calls
        successful_replay_fsync_calls += 1
        return original_fsync(fd)

    monkeypatch.setattr(binding_module.os, "fsync", count_successful_replay_fsync)
    assert TrustedCaptureSuggestionBindingStore(tmp_path).record(binding) == (binding, True)
    assert successful_replay_fsync_calls == 1



def test_invalid_state_blocks_candidate_recovery_without_deleting_unknown_files(tmp_path):
    state_path = tmp_path / "capture-suggestion-bindings.json"
    state_path.write_text("not-json")
    state_path.chmod(0o600)
    orphan = tmp_path / ".capture-suggestion-bindings-stale.tmp"
    orphan.write_text("partial")
    orphan.chmod(0o600)
    try:
        TrustedCaptureSuggestionBindingStore(tmp_path).record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("corrupt durable state must require manual review")
    assert state_path.read_text() == "not-json"
    assert orphan.read_text() == "partial"


def test_candidate_store_rejects_non_private_root_modes_symlink_and_owner(tmp_path, monkeypatch):
    private_root = tmp_path / "private-root"
    private_root.mkdir(mode=0o700)
    broad_root = tmp_path / "broad-root"
    broad_root.mkdir(mode=0o755)
    broad_root.chmod(0o755)
    try:
        TrustedCaptureSuggestionBindingStore(broad_root)
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("group/world accessible root must be rejected")
    root_link = tmp_path / "root-link"
    root_link.symlink_to(private_root, target_is_directory=True)
    try:
        TrustedCaptureSuggestionBindingStore(root_link)
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("symlink root must be rejected")
    import secondbrain_core.modules.capture_suggestion_binding as binding_module
    actual_uid = os.geteuid()
    monkeypatch.setattr(binding_module.os, "geteuid", lambda: actual_uid + 1)
    try:
        TrustedCaptureSuggestionBindingStore(private_root)
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("root owned by another effective user must be rejected")


def test_candidate_store_rejects_root_path_replacement_after_validation(tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    store = TrustedCaptureSuggestionBindingStore(root)
    root.rename(tmp_path / "original-root")
    root.mkdir(mode=0o700)
    try:
        store.record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("replaced root path must not be trusted")


def test_candidate_store_rejects_state_symlink_hardlink_and_lock_symlink(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text('{"schema_version":1,"records":{}}')
    outside.chmod(0o600)
    symlink_root = tmp_path / "state-symlink-root"
    symlink_root.mkdir(mode=0o700)
    (symlink_root / "capture-suggestion-bindings.json").symlink_to(outside)
    try:
        TrustedCaptureSuggestionBindingStore(symlink_root).record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("state symlink must be rejected")
    assert outside.read_text() == '{"schema_version":1,"records":{}}'

    linked_root = tmp_path / "state-hardlink-root"
    linked_root.mkdir(mode=0o700)
    linked_state = linked_root / "capture-suggestion-bindings.json"
    linked_state.write_text('{"schema_version":1,"records":{}}')
    linked_state.chmod(0o600)
    os.link(linked_state, tmp_path / "state-hardlink-outside.json")
    try:
        TrustedCaptureSuggestionBindingStore(linked_root).record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("multiply linked state must be rejected")

    mode_root = tmp_path / "state-mode-root"
    mode_root.mkdir(mode=0o700)
    bad_mode_state = mode_root / "capture-suggestion-bindings.json"
    bad_mode_state.write_text('{"schema_version":1,"records":{}}')
    bad_mode_state.chmod(0o644)
    try:
        TrustedCaptureSuggestionBindingStore(mode_root).record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("group-readable state file must be rejected")

    lock_root = tmp_path / "lock-symlink-root"
    lock_root.mkdir(mode=0o700)
    (lock_root / ".capture-suggestion-bindings.lock").symlink_to(outside)
    try:
        TrustedCaptureSuggestionBindingStore(lock_root).record(resolve())
    except CaptureSuggestionBindingStoreError:
        pass
    else:
        raise AssertionError("lock symlink must be rejected")


def test_candidate_private_file_validator_rejects_wrong_owner_and_mode():
    actual_uid = os.geteuid()
    for file_stat in (
        SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=actual_uid + 1, st_nlink=1),
        SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=actual_uid, st_nlink=1),
        SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=actual_uid, st_nlink=2),
        SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=actual_uid, st_nlink=1),
    ):
        try:
            TrustedCaptureSuggestionBindingStore._validate_private_file(file_stat, "synthetic")
        except CaptureSuggestionBindingStoreError:
            pass
        else:
            raise AssertionError("unsafe owner, mode, link count or file type was accepted")


def test_candidate_store_preserves_unsafe_symlink_hardlink_and_mode_temp_files(tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("do-not-change")
    sentinel.chmod(0o600)
    for name, setup in (
        ("symlink", lambda root: (root / ".capture-suggestion-bindings-symlink.tmp").symlink_to(sentinel)),
        ("hardlink", lambda root: os.link(sentinel, root / ".capture-suggestion-bindings-hardlink.tmp")),
        ("mode", lambda root: (root / ".capture-suggestion-bindings-mode.tmp").write_text("unknown")),
    ):
        root = tmp_path / f"unsafe-temp-{name}"
        root.mkdir(mode=0o700)
        setup(root)
        if name == "mode":
            (root / ".capture-suggestion-bindings-mode.tmp").chmod(0o644)
        try:
            TrustedCaptureSuggestionBindingStore(root).record(resolve())
        except CaptureSuggestionBindingStoreError:
            pass
        else:
            raise AssertionError(f"unsafe {name} temp must be rejected")
        assert sentinel.read_text() == "do-not-change"
        assert (root / f".capture-suggestion-bindings-{name}.tmp").exists()


def test_source_and_consent_expiry_ordering_is_enforced():
    assert resolve(authority(source=source_record(
        received_at="2026-10-20T12:05:00Z", expires_at="2026-10-20T12:05:00Z",
    ))) is None
    assert resolve(authority(consent=consent_record(
        recorded_at="2026-10-20T12:06:00Z",
    ))) is None
