"""Synthetic-only persistent consent and revocation tests for D086-M1."""
from datetime import datetime, timedelta, timezone
import multiprocessing
import os
from pathlib import Path
import sqlite3

import pytest

from secondbrain_core.modules.d086_m1_synthetic_consent import (
    SyntheticActionProofAuthority,
    SyntheticConsentConflict,
    SyntheticConsentLedger,
    SyntheticConsentUnavailable,
)


NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
SECRET = b"synthetic-only-secret-for-tests-32-bytes-minimum"
ORIGIN = "https://synthetic.example"


def make_authority():
    return SyntheticActionProofAuthority(secret=SECRET, allowed_origin=ORIGIN)


def make_proof(authority, *, action="accept", key="accept-1", now=NOW,
               source_expires=NOW + timedelta(hours=1), consent_id=None,
               revision=None, intent="save_note", event="event-1", version="1",
               digest="a" * 64, subject="synthetic-owner"):
    return authority.issue_test_proof(
        action=action, subject=subject, source_system="synthetic.m1",
        source_event_id=event, source_version=version, source_sha256=digest,
        intent=intent, action_key=key, origin=ORIGIN,
        issued_at=(now - timedelta(seconds=1)).isoformat(),
        action_expires_at=(now + timedelta(minutes=5)).isoformat(),
        expires_at=source_expires.isoformat(), consent_id=consent_id,
        expected_revision=revision,
    )


def make_ledger(tmp_path, *, clock=lambda: NOW):
    root = tmp_path / "synthetic-private"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root, SyntheticConsentLedger(root, make_authority(), clock=clock)


def test_persistent_accept_exact_retry_and_audit_chain(tmp_path):
    root, ledger = make_ledger(tmp_path)
    proof = make_proof(ledger.proof_authority)
    created = ledger.accept(proof)
    assert created.state == "active" and created.revision == 1
    assert ledger.verify_audit_chain(created.consent_id)

    reopened = SyntheticConsentLedger(root, make_authority(), clock=lambda: NOW)
    replay = reopened.accept(proof)
    assert replay == type(created)(**{**created.__dict__, "replayed": True})
    assert reopened.get(subject="synthetic-owner", source_system="synthetic.m1",
                        source_event_id="event-1").consent_id == created.consent_id
    assert reopened.verify_audit_chain(created.consent_id)


def test_changed_intent_or_rotated_key_conflicts_in_existing_source_slot(tmp_path):
    _, ledger = make_ledger(tmp_path)
    authority = ledger.proof_authority
    accepted = ledger.accept(make_proof(authority))
    with pytest.raises(SyntheticConsentConflict):
        ledger.accept(make_proof(authority, key="accept-2"))
    with pytest.raises(SyntheticConsentConflict):
        ledger.accept(make_proof(authority, intent="different_intent"))
    assert ledger.get(subject="synthetic-owner", source_system="synthetic.m1",
                      source_event_id="event-1").consent_id == accepted.consent_id


def test_revoke_is_revision_cas_append_only_and_idempotent(tmp_path):
    _, ledger = make_ledger(tmp_path)
    authority = ledger.proof_authority
    accepted = ledger.accept(make_proof(authority))
    revoke = make_proof(authority, action="revoke", key="revoke-1",
                        consent_id=accepted.consent_id, revision=1)
    result = ledger.revoke(revoke)
    assert (result.state, result.revision) == ("revoked", 2)
    assert ledger.revoke(revoke).replayed
    stale = make_proof(authority, action="revoke", key="revoke-2",
                       consent_id=accepted.consent_id, revision=1)
    with pytest.raises(SyntheticConsentConflict):
        ledger.revoke(stale)
    conn = sqlite3.connect(ledger.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE consent_audit SET action='forged' WHERE consent_id=?",
                         (accepted.consent_id,))
    finally:
        conn.close()
    assert ledger.verify_audit_chain(accepted.consent_id)


def test_expiry_transition_uses_fresh_action_proof_after_source_ttl(tmp_path):
    current = [NOW]
    _, ledger = make_ledger(tmp_path, clock=lambda: current[0])
    authority = ledger.proof_authority
    accepted = ledger.accept(make_proof(authority, source_expires=NOW + timedelta(seconds=3)))
    current[0] = NOW + timedelta(seconds=4)
    expire = make_proof(authority, action="expire", key="expire-1", now=current[0],
                         source_expires=NOW + timedelta(seconds=3),
                         consent_id=accepted.consent_id, revision=1)
    result = ledger.expire(expire)
    assert (result.state, result.revision) == ("expired", 2)


def test_proof_mutation_wrong_origin_and_untrusted_path_fail_closed(tmp_path):
    root, ledger = make_ledger(tmp_path)
    authority = ledger.proof_authority
    proof = make_proof(authority)
    from dataclasses import replace
    with pytest.raises(SyntheticConsentUnavailable):
        ledger.accept(replace(proof, intent="delete_everything"))
    with pytest.raises(ValueError):
        authority.issue_test_proof(
            action="accept", subject="x", source_system="synthetic.m1",
            source_event_id="event", source_version="1", source_sha256="a" * 64,
            intent="save_note", action_key="k", origin="https://evil.example",
            issued_at=NOW.isoformat(), action_expires_at=(NOW + timedelta(minutes=1)).isoformat(),
            expires_at=(NOW + timedelta(hours=1)).isoformat())
    assert stat_mode(root / ledger.database_name) == 0o600
    assert ledger.verify_audit_chain("not-created") is False


def stat_mode(path):
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


def _accept_worker(root, barrier, output):
    authority = make_authority()
    ledger = SyntheticConsentLedger(root, authority, clock=lambda: NOW)
    proof = make_proof(authority, key="same-exact-action")
    barrier.wait(timeout=10)
    try:
        output.put(("ok", ledger.accept(proof).consent_id))
    except Exception as exc:  # reported to parent; no exception details with paths
        output.put((type(exc).__name__, ""))


def _die_with_uncommitted_row(root):
    conn = sqlite3.connect(Path(root) / SyntheticConsentLedger.database_name,
                           isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT INTO consent_records(consent_id,subject,source_system,source_event_id,source_version,source_sha256,intent,state,revision,accept_key,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        ("crash-before-commit", "synthetic-owner", "synthetic.m1", "crash-event", "1", "a"*64,
         "save_note", "active", 1, "crash-key", (NOW+timedelta(hours=1)).isoformat(), NOW.isoformat()),
    )
    os._exit(71)


def test_multiprocess_exact_accept_serializes_to_one_persistent_slot(tmp_path):
    root = tmp_path / "synthetic-private"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    SyntheticConsentLedger(root, make_authority(), clock=lambda: NOW)
    ctx = multiprocessing.get_context("spawn")
    barrier, output = ctx.Barrier(2), ctx.Queue()
    workers = [ctx.Process(target=_accept_worker, args=(str(root), barrier, output))
               for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(15)
    assert all(not worker.is_alive() and worker.exitcode == 0 for worker in workers)
    results = [output.get(timeout=2) for _ in workers]
    assert all(kind == "ok" for kind, _ in results)
    assert len({consent_id for _, consent_id in results}) == 1
    ledger = SyntheticConsentLedger(root, make_authority(), clock=lambda: NOW)
    assert ledger.get(subject="synthetic-owner", source_system="synthetic.m1",
                      source_event_id="event-1").revision == 1


def test_process_termination_before_sqlite_commit_rolls_back_then_restart_works(tmp_path):
    root, ledger = make_ledger(tmp_path)
    authority = ledger.proof_authority
    proof = make_proof(authority)
    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(target=_die_with_uncommitted_row, args=(str(root),))
    worker.start()
    worker.join(10)
    assert worker.exitcode == 71
    reopened = SyntheticConsentLedger(root, make_authority(), clock=lambda: NOW)
    assert reopened.get(subject="synthetic-owner", source_system="synthetic.m1",
                       source_event_id="crash-event") is None
    assert reopened.accept(proof).state == "active"
