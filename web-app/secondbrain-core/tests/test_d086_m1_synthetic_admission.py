"""Synthetic-only same-SQLite consent/admission and Raw ordering tests."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import multiprocessing
import os
from pathlib import Path
import sqlite3
import threading

import pytest

from secondbrain_core.modules.d086_m1_synthetic_consent import (
    SyntheticActionProofAuthority,
    SyntheticConsentConflict,
    SyntheticConsentLedger,
    SyntheticConsentUnavailable,
)
from secondbrain_core.modules.d086_m1_synthetic_source import SyntheticSourceAuthority
from secondbrain_core.modules.d086_m1_synthetic_admission import SyntheticInboxAdmission


NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
SECRET = b"synthetic-only-secret-for-tests-32-bytes-minimum"
ORIGIN = "https://synthetic.example"


def make_context(root, *, event="event-1", intent="save_note", text="synthetic note",
                 expires=NOW + timedelta(hours=1), max_raw_bytes=200_000):
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    action_authority = SyntheticActionProofAuthority(secret=SECRET, allowed_origin=ORIGIN)
    ledger = SyntheticConsentLedger(root, action_authority, clock=lambda: NOW)
    source_authority = SyntheticSourceAuthority(clock=lambda: NOW)
    source = source_authority.register(event_id=event, subject="synthetic-owner",
                                       original_text=text,
                                       ttl_seconds=max(1, int((expires - NOW).total_seconds())))
    # Use exact source timestamps and binding for the persisted consent proof.
    proof = action_authority.issue_test_proof(
        action="accept", subject=source.subject, source_system=source.source_system,
        source_event_id=source.source_event_id, source_version=source.source_record_version,
        source_sha256=source.original_text_sha256, intent=intent,
        action_key=f"accept-{event}", origin=ORIGIN,
        issued_at=NOW.isoformat(), action_expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        expires_at=source.expires_at,
    )
    consent = ledger.accept(proof)
    admission = SyntheticInboxAdmission(ledger, source_reader=source_authority,
                                        clock=lambda: NOW,
                                        max_raw_bytes=max_raw_bytes)
    return ledger, source_authority, source, consent, admission


def admit(admission, source, consent, *, action_key="admit-1", intent="save_note"):
    proof = admission.ledger.proof_authority.issue_test_proof(
        action="admit", subject=source.subject,
        source_system=source.source_system,
        source_event_id=source.source_event_id,
        source_version=source.source_record_version,
        source_sha256=source.original_text_sha256, intent=intent,
        action_key=action_key, origin=ORIGIN,
        issued_at=NOW.isoformat(),
        action_expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        expires_at=source.expires_at, consent_id=consent.consent_id,
        expected_revision=consent.revision,
    )
    return admission.admit_from_reader(proof)


def revoke(ledger, consent, *, key="revoke-1"):
    proof = ledger.proof_authority.issue_test_proof(
        action="revoke", subject=consent.subject, source_system=consent.source_system,
        source_event_id=consent.source_event_id, source_version=consent.source_version,
        source_sha256=consent.source_sha256, intent=consent.intent,
        action_key=key, origin=ORIGIN,
        issued_at=NOW.isoformat(), action_expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        expires_at=consent.expires_at, consent_id=consent.consent_id,
        expected_revision=consent.revision,
    )
    return ledger.revoke(proof)


def test_source_consent_raw_manifest_same_db_commit_and_restart(tmp_path):
    root = tmp_path / "synthetic"
    ledger, source_authority, source, consent, admission = make_context(root)
    result = admit(admission, source, consent)
    assert result.source_sha256 == hashlib.sha256(b"synthetic note").hexdigest()
    assert (root / result.raw_relative_path).read_bytes() == b"synthetic note"
    replay = admit(admission, source, consent)
    assert replay.replayed and replay.inbox_id == result.inbox_id
    assert admission.get_by_event(subject="synthetic-owner", source_system="synthetic.m1",
                                  source_event_id="event-1") == replace(result, replayed=False)

    conn = sqlite3.connect(ledger.database_path)
    try:
        operation = conn.execute(
            "SELECT consent_id,raw_sha256,raw_bytes FROM inbox_operations WHERE inbox_id=?",
            (result.inbox_id,),
        ).fetchone()
        manifest = conn.execute(
            "SELECT relative_path,sha256,byte_length,verified FROM inbox_raw_manifest WHERE inbox_id=?",
            (result.inbox_id,),
        ).fetchone()
    finally:
        conn.close()
    assert operation == (consent.consent_id, result.source_sha256, len(b"synthetic note"))
    assert manifest == (result.raw_relative_path, result.source_sha256,
                        len(b"synthetic note"), 1)
    reopened = SyntheticConsentLedger(root, ledger.proof_authority, clock=lambda: NOW)
    reopened_admission = SyntheticInboxAdmission(reopened, source_reader=source_authority,
                                                 clock=lambda: NOW)
    assert reopened_admission.get_by_event(subject="synthetic-owner", source_system="synthetic.m1",
                                           source_event_id="event-1").inbox_id == result.inbox_id


def _replace_raw_entry_with_external_symlink(root, external, *, detached="Raw.detached"):
    (root / "Raw").rename(root / detached)
    (root / "Raw").symlink_to(external, target_is_directory=True)


def _count_admission_rows(ledger):
    conn = sqlite3.connect(ledger.database_path)
    try:
        return (conn.execute("SELECT count(*) FROM inbox_operations").fetchone()[0],
                conn.execute("SELECT count(*) FROM inbox_raw_manifest").fetchone()[0])
    finally:
        conn.close()


def test_raw_directory_replaced_after_constructor_fails_before_any_external_write(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    _replace_raw_entry_with_external_symlink(root, external)

    with pytest.raises(SyntheticConsentUnavailable):
        admit(admission, source, consent)

    assert list(external.iterdir()) == []
    assert _count_admission_rows(ledger) == (0, 0)
    assert list((root / "Raw.detached").iterdir()) == []


def test_raw_directory_replaced_at_child_open_boundary_fails_closed(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    fired = []

    def replace_before_create(checkpoint):
        if checkpoint == "before_child_create" and not fired:
            fired.append(True)
            _replace_raw_entry_with_external_symlink(root, external)

    admission._raw_checkpoint = replace_before_create
    with pytest.raises(SyntheticConsentUnavailable):
        admit(admission, source, consent)

    assert fired == [True]
    assert list(external.iterdir()) == []
    assert list((root / "Raw.detached").iterdir()) == []
    assert _count_admission_rows(ledger) == (0, 0)


def test_raw_directory_rename_to_valid_replacement_is_rejected_by_inode_identity(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    fired = []

    def replace_with_new_directory(checkpoint):
        if checkpoint == "before_child_create" and not fired:
            fired.append(True)
            (root / "Raw").rename(root / "Raw.detached")
            (root / "Raw").mkdir(mode=0o700)

    admission._raw_checkpoint = replace_with_new_directory
    with pytest.raises(SyntheticConsentUnavailable):
        admit(admission, source, consent)

    assert fired == [True]
    assert list((root / "Raw").iterdir()) == []
    assert list((root / "Raw.detached").iterdir()) == []
    assert _count_admission_rows(ledger) == (0, 0)


def test_raw_directory_rename_only_detach_after_write_leaves_uncommitted_orphan(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    fired = []

    def detach_after_fsync(checkpoint):
        if checkpoint == "after_file_fsync" and not fired:
            fired.append(True)
            (root / "Raw").rename(root / "Raw.detached")
            (root / "Raw").mkdir(mode=0o700)

    admission._raw_checkpoint = detach_after_fsync
    with pytest.raises(SyntheticConsentUnavailable):
        admit(admission, source, consent)

    assert fired == [True]
    assert list((root / "Raw").iterdir()) == []
    assert len(list((root / "Raw.detached").iterdir())) == 1
    assert _count_admission_rows(ledger) == (0, 0)


@pytest.mark.parametrize("checkpoint", ["after_file_fsync", "before_manifest_commit",
                                         "before_transaction_commit", "database_commit"])
def test_raw_directory_rename_after_stage_never_commits_manifest_or_writes_symlink_target(
        tmp_path, checkpoint):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    fired = []

    def replace_at_boundary(name):
        if name == checkpoint and not fired:
            fired.append(True)
            _replace_raw_entry_with_external_symlink(root, external)

    admission._raw_checkpoint = replace_at_boundary
    with pytest.raises(SyntheticConsentUnavailable):
        admit(admission, source, consent)

    assert fired == [True]
    assert list(external.iterdir()) == []
    # The already fsynced object remains in the renamed in-root directory;
    # this model deliberately neither deletes nor adopts that orphan.
    detached = list((root / "Raw.detached").iterdir())
    assert len(detached) == 1
    assert _count_admission_rows(ledger) == (0, 0)


def test_revocation_before_admission_blocks_and_after_commit_preserves_raw(tmp_path):
    root = tmp_path / "before"
    ledger, _, source, consent, admission = make_context(root)
    revoked = revoke(ledger, consent)
    assert revoked.revision == 2
    with pytest.raises(SyntheticConsentConflict):
        admit(admission, source, consent)
    assert list((root / "Raw").iterdir()) == []

    root_after = tmp_path / "after"
    ledger2, _, source2, consent2, admission2 = make_context(root_after, event="event-after")
    created = admit(admission2, source2, consent2)
    revoke(ledger2, consent2)
    assert (root_after / created.raw_relative_path).read_bytes() == b"synthetic note"
    assert admission2.get_by_event(subject="synthetic-owner", source_system="synthetic.m1",
                                   source_event_id="event-after").inbox_id == created.inbox_id


def test_drift_invalid_consent_revision_and_byte_budget_fail_closed(tmp_path):
    root = tmp_path / "synthetic"
    ledger, source_authority, source, consent, admission = make_context(root)
    admission.max_raw_bytes = 4
    with pytest.raises(SyntheticConsentConflict):
        admit(admission, source, consent)
    assert list((root / "Raw").iterdir()) == []
    admission.max_raw_bytes = 200_000

    class MutateBetweenActualReads:
        def __init__(self, authority):
            self.authority = authority
            self.calls = 0

        def source_commit_guard(self, event_id):
            return self.authority.source_commit_guard(event_id)

        def read_verified_suggestion(self, event_id):
            self.calls += 1
            if self.calls == 2:
                self.authority.revise(event_id, original_text="mutated during read")
            return self.authority.read_verified_suggestion(event_id)

    mutating_reader = MutateBetweenActualReads(source_authority)
    admission.source_reader = mutating_reader
    with pytest.raises(SyntheticConsentConflict):
        admit(admission, source, consent)
    assert mutating_reader.calls == 2
    assert list((root / "Raw").iterdir()) == []


def test_caller_supplied_source_dto_cannot_cross_admission_api(tmp_path):
    root = tmp_path / "synthetic"
    _, _, source, consent, admission = make_context(root)
    assert not hasattr(admission, "admit")
    forged = replace(source, subject="attacker", source_record_version="999")
    with pytest.raises(TypeError):
        admission.admit_from_reader(first_source_read=forged,
                                    second_source_read=forged,
                                    expected_subject="attacker")
    forged_proof = admission.ledger.proof_authority.issue_test_proof(
        action="admit", subject="attacker", source_system=source.source_system,
        source_event_id=source.source_event_id, source_version="999",
        source_sha256=hashlib.sha256(b"forged").hexdigest(), intent=consent.intent,
        action_key="forged", origin=ORIGIN, issued_at=NOW.isoformat(),
        action_expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        expires_at=consent.expires_at, consent_id=consent.consent_id,
        expected_revision=consent.revision,
    )
    with pytest.raises(SyntheticConsentConflict):
        admission.admit_from_reader(forged_proof)


def test_changed_intent_or_key_same_event_conflicts_but_distinct_event_is_valid(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    created = admit(admission, source, consent, action_key="admit-1")
    with pytest.raises(SyntheticConsentConflict):
        admit(admission, source, consent, action_key="rotated-key")
    with pytest.raises(SyntheticConsentConflict):
        admit(admission, source, consent, action_key="admit-1", intent="other_intent")

    _, _, source2, consent2, admission2 = make_context(root, event="event-2")
    distinct = admit(admission2, source2, consent2, action_key="admit-1")
    assert distinct.inbox_id != created.inbox_id
    assert len(list((root / "Raw").iterdir())) == 2


def _concurrent_admit_worker(root, barrier, output):
    action_authority = SyntheticActionProofAuthority(secret=SECRET, allowed_origin=ORIGIN)
    ledger = SyntheticConsentLedger(root, action_authority, clock=lambda: NOW)
    source_authority = SyntheticSourceAuthority(clock=lambda: NOW)
    admission = SyntheticInboxAdmission(ledger, source_reader=source_authority,
                                        clock=lambda: NOW)
    source = source_authority.register(event_id="event-1", subject="synthetic-owner",
                                      original_text="synthetic note", ttl_seconds=3600)
    proof = action_authority.issue_test_proof(
        action="accept", subject=source.subject, source_system=source.source_system,
        source_event_id=source.source_event_id, source_version=source.source_record_version,
        source_sha256=source.original_text_sha256, intent="save_note",
        action_key="accept-event-1", origin=ORIGIN, issued_at=NOW.isoformat(),
        action_expires_at=(NOW + timedelta(minutes=5)).isoformat(), expires_at=source.expires_at)
    consent = ledger.accept(proof)
    barrier.wait(timeout=10)
    try:
        result = admit(admission, source, consent)
        output.put(("ok", result.inbox_id))
    except Exception as exc:
        output.put((type(exc).__name__, ""))


@pytest.mark.parametrize("workers_count", [2, 4, 8])
def test_multiprocess_same_event_exact_admission_has_one_raw_and_manifest(tmp_path, workers_count):
    root = tmp_path / "synthetic"
    make_context(root)
    ctx = multiprocessing.get_context("spawn")
    barrier, output = ctx.Barrier(workers_count), ctx.Queue()
    workers = [ctx.Process(target=_concurrent_admit_worker, args=(str(root), barrier, output))
               for _ in range(workers_count)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(15)
    assert all(not worker.is_alive() and worker.exitcode == 0 for worker in workers)
    results = [output.get(timeout=5) for _ in workers]
    assert all(kind == "ok" for kind, _ in results)
    assert len({inbox_id for _, inbox_id in results}) == 1
    assert len(list((root / "Raw").iterdir())) == 1
    conn = sqlite3.connect(root / SyntheticConsentLedger.database_name)
    try:
        assert conn.execute("SELECT count(*) FROM inbox_operations").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM inbox_raw_manifest").fetchone()[0] == 1
    finally:
        conn.close()


def test_admission_and_revocation_race_obeys_sqlite_commit_order(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, source, consent, admission = make_context(root)
    barrier = threading.Barrier(2)

    def accept_admission():
        barrier.wait(timeout=5)
        try:
            return ("admitted", admit(admission, source, consent))
        except SyntheticConsentConflict:
            return ("blocked", None)

    def revoke_consent():
        barrier.wait(timeout=5)
        return ("revoked", revoke(ledger, consent))

    with ThreadPoolExecutor(max_workers=2) as pool:
        admission_future = pool.submit(accept_admission)
        revoke_future = pool.submit(revoke_consent)
        admission_result = admission_future.result(timeout=10)
        revoke_result = revoke_future.result(timeout=10)
    assert revoke_result[1].state == "revoked"
    if admission_result[0] == "admitted":
        created = admission_result[1]
        assert (root / created.raw_relative_path).read_bytes() == b"synthetic note"
        assert admission.get_by_event(subject="synthetic-owner", source_system="synthetic.m1",
                                      source_event_id="event-1").inbox_id == created.inbox_id
    else:
        assert list((root / "Raw").iterdir()) == []


def test_concurrent_source_revision_waits_until_sqlite_commit(tmp_path):
    root = tmp_path / "synthetic"
    _, authority, source, consent, admission = make_context(root)
    stage_reached = threading.Event()
    revision_attempted = threading.Event()
    updaters = []
    original_stage = admission._stage_raw

    def stage_then_race(**kwargs):
        path = original_stage(**kwargs)

        def revise():
            revision_attempted.set()
            authority.revise(source.source_event_id, original_text="after commit")

        updater = threading.Thread(target=revise)
        updaters.append(updater)
        updater.start()
        assert revision_attempted.wait(2)
        stage_reached.set()
        return path

    admission._stage_raw = stage_then_race
    result = admit(admission, source, consent)
    for updater in updaters:
        updater.join(5)
        assert not updater.is_alive()
    assert stage_reached.is_set()
    assert result.source_version == "1"
    assert authority.read_verified_suggestion(source.source_event_id).source_record_version == "2"


def test_source_mutation_at_final_precommit_read_fails_and_leaves_only_orphan(tmp_path):
    root = tmp_path / "synthetic"
    _, authority, source, consent, admission = make_context(root)
    original_read = authority.read_verified_suggestion
    calls = [0]

    def mutate_on_third_read(event_id):
        calls[0] += 1
        if calls[0] == 3:
            authority.revise(event_id, original_text="last-moment mutation")
        return original_read(event_id)

    authority.read_verified_suggestion = mutate_on_third_read
    with pytest.raises(SyntheticConsentConflict):
        admit(admission, source, consent)
    assert calls[0] == 3
    assert len(list((root / "Raw").iterdir())) == 1
    assert admission.get_by_event(subject="synthetic-owner", source_system="synthetic.m1",
                                  source_event_id="event-1") is None


def _die_after_raw_stage(root):
    action_authority = SyntheticActionProofAuthority(secret=SECRET, allowed_origin=ORIGIN)
    ledger = SyntheticConsentLedger(root, action_authority, clock=lambda: NOW)
    source_authority = SyntheticSourceAuthority(clock=lambda: NOW)
    source = source_authority.register(event_id="event-1", subject="synthetic-owner",
                                      original_text="synthetic note", ttl_seconds=3600)
    proof = action_authority.issue_test_proof(
        action="accept", subject=source.subject, source_system=source.source_system,
        source_event_id=source.source_event_id, source_version=source.source_record_version,
        source_sha256=source.original_text_sha256, intent="save_note",
        action_key="accept-event-1", origin=ORIGIN, issued_at=NOW.isoformat(),
        action_expires_at=(NOW + timedelta(minutes=5)).isoformat(), expires_at=source.expires_at)
    consent = ledger.accept(proof)
    admission = SyntheticInboxAdmission(ledger, source_reader=source_authority,
                                        clock=lambda: NOW)
    original_stage = admission._stage_raw

    def stage_then_die(**kwargs):
        original_stage(**kwargs)
        os._exit(72)

    admission._stage_raw = stage_then_die
    admit(admission, source, consent)


def test_kill_after_raw_fsync_before_db_commit_leaves_orphan_without_recovery_write(tmp_path):
    root = tmp_path / "synthetic"
    make_context(root)
    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(target=_die_after_raw_stage, args=(str(root),))
    worker.start()
    worker.join(10)
    assert worker.exitcode == 72
    reopened = SyntheticConsentLedger(root, SyntheticActionProofAuthority(
        secret=SECRET, allowed_origin=ORIGIN), clock=lambda: NOW)
    admission = SyntheticInboxAdmission(reopened,
                                        source_reader=SyntheticSourceAuthority(clock=lambda: NOW),
                                        clock=lambda: NOW)
    raw_files = list((root / "Raw").iterdir())
    assert len(raw_files) == 1 and raw_files[0].stat().st_size == len(b"synthetic note")
    assert admission.get_by_event(subject="synthetic-owner", source_system="synthetic.m1",
                                  source_event_id="event-1") is None
    conn = sqlite3.connect(reopened.database_path)
    try:
        assert conn.execute("SELECT count(*) FROM inbox_operations").fetchone()[0] == 0
    finally:
        conn.close()

    # A retry with the same operation key fails closed on the orphan collision;
    # it neither deletes nor silently adopts/replays the unknown partial commit.
    _, _, source, consent, retry = make_context(root)
    with pytest.raises(SyntheticConsentUnavailable):
        admit(retry, source, consent)
    assert len(list((root / "Raw").iterdir())) == 1
    conn = sqlite3.connect(reopened.database_path)
    try:
        assert conn.execute("SELECT count(*) FROM inbox_operations").fetchone()[0] == 0
    finally:
        conn.close()
