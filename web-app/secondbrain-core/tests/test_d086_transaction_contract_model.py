"""Pure synthetic D086 S3 contract model; no application/storage imports."""
from dataclasses import dataclass, replace
import hashlib
import json


@dataclass(frozen=True)
class AdmissionModel:
    actor: str = "synthetic-owner"
    event_id: str = "synthetic-event-1"
    intent: str = "journal_intent"
    idempotency_key: str = "synthetic-key-1"
    source_version: int = 4
    source_digest: str = "a" * 64
    consent_revision: int = 7
    consent_active: bool = True
    checked_revision: int | None = None
    raw_staged: bool = False
    commit_record_durable: bool = False
    inbox_ids: tuple[str, ...] = ()
    rejected: bool = False


def check_consent(model):
    if not model.consent_active:
        return replace(model, rejected=True)
    return replace(model, checked_revision=model.consent_revision)


def stage_raw(model):
    if model.checked_revision is None or model.rejected:
        return replace(model, rejected=True)
    return replace(model, raw_staged=True)


def revoke(model):
    return replace(model, consent_revision=model.consent_revision + 1,
                   consent_active=False)


def commit(model):
    # This single pure transition models the shared consent-revision CAS plus
    # durable WAL record as one linearization point. It performs no I/O.
    if (not model.raw_staged or model.rejected or not model.consent_active
            or model.checked_revision != model.consent_revision):
        return replace(model, rejected=True)
    return replace(model, commit_record_durable=True)


def deterministic_inbox_id(model):
    material = (model.actor, model.event_id, model.intent,
                model.idempotency_key, model.source_version,
                model.source_digest, model.checked_revision)
    return hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


def materialize_committed(model):
    if not model.commit_record_durable:
        return model
    inbox_id = deterministic_inbox_id(model)
    if inbox_id in model.inbox_ids:
        return model
    return replace(model, inbox_ids=model.inbox_ids + (inbox_id,))


def operation_status(model):
    if model.rejected:
        return "CONFLICT"
    if not model.commit_record_durable:
        return "UNKNOWN_DURABILITY" if model.raw_staged else "NOT_COMMITTED"
    if not model.inbox_ids:
        return "COMMIT_DURABLE_PENDING_INBOX"
    return "INBOX_COMMITTED"


def replay_result(existing, candidate):
    if not existing.commit_record_durable or not candidate.commit_record_durable:
        return "unknown"
    same_slot = (existing.event_id, existing.intent) == (
        candidate.event_id, candidate.intent,
    )
    if not same_slot:
        return "new-slot"
    exact = (existing.actor, existing.idempotency_key, existing.source_version,
             existing.source_digest, existing.consent_revision) == (
        candidate.actor, candidate.idempotency_key, candidate.source_version,
        candidate.source_digest, candidate.consent_revision,
    )
    return "replay" if exact else "conflict"


def test_s3_revoke_wins_before_cas_means_zero_inbox():
    checked = check_consent(AdmissionModel())
    staged = stage_raw(checked)
    revoked = revoke(staged)
    after = commit(revoked)
    assert after.rejected is True
    assert after.commit_record_durable is False
    assert after.inbox_ids == ()
    assert after.raw_staged is True  # no implicit cleanup/repair


def test_s3_commit_wins_before_revoke_keeps_one_inbox_without_rollback():
    checked = check_consent(AdmissionModel())
    committed = commit(stage_raw(checked))
    assert committed.commit_record_durable is True
    after_revoke = revoke(committed)
    materialized = materialize_committed(after_revoke)
    assert len(materialized.inbox_ids) == 1
    assert materialized.consent_active is False
    assert materialize_committed(materialized).inbox_ids == materialized.inbox_ids


def test_s3_crash_before_commit_is_unknown_and_never_success():
    staged = stage_raw(check_consent(AdmissionModel()))
    # A restart with no provable commit record cannot infer acceptance from Raw.
    assert staged.raw_staged is True
    assert staged.commit_record_durable is False
    assert staged.inbox_ids == ()
    assert operation_status(staged) == "UNKNOWN_DURABILITY"
    assert replay_result(staged, staged) == "unknown"


def test_s3_crash_after_durable_commit_is_pending_until_separate_action():
    committed = commit(stage_raw(check_consent(AdmissionModel())))
    assert operation_status(committed) == "COMMIT_DURABLE_PENDING_INBOX"
    assert committed.inbox_ids == ()
    # This pure transition stands only for a future separately approved action;
    # no recovery is invoked by the model or any application code.
    simulated = materialize_committed(committed)
    assert operation_status(simulated) == "INBOX_COMMITTED"
    assert len(simulated.inbox_ids) == 1


def test_s3_exact_replay_is_stable_and_tuple_drift_conflicts_without_key_bypass():
    first = commit(stage_raw(check_consent(AdmissionModel())))
    replay = commit(stage_raw(check_consent(AdmissionModel())))
    one = materialize_committed(first)
    two = materialize_committed(replay)
    assert one.inbox_ids == two.inbox_ids
    assert replay_result(first, replay) == "replay"
    for changed in (
        replace(replay, idempotency_key="rotated-key"),
        replace(replay, actor="other-owner"),
        replace(replay, source_version=5),
        replace(replay, source_digest="b" * 64),
        replace(replay, consent_revision=8),
    ):
        assert replay_result(first, changed) == "conflict"
