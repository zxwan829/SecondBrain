import json
import os

import pytest

from secondbrain_core.modules.daily_brief_store import DailyBriefRecordReadStore


DAY = "2026-10-20"
ZONE = "Asia/Shanghai"
REFS = [{"kind": "task", "id": "a" * 32, "version": "a" * 64}]


def make_root(tmp_path):
    root = tmp_path / "briefs"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def record_payload(*, day=DAY, timezone=ZONE, refs=None, **overrides):
    payload = {
        "brief_id": "brief-synthetic",
        "date": day,
        "timezone": timezone,
        "generated_at": "2026-10-20T08:00:00+08:00",
        "generation_status": "generated",
        "categories": ["synthetic"],
        "summary": "Synthetic durable brief",
        "source_refs": REFS if refs is None else refs,
    }
    payload.update(overrides)
    return payload


def write_record(root, *, day=DAY, timezone=ZONE, refs=None, **overrides):
    path = root / f"{day}.json"
    path.write_text(json.dumps(record_payload(day=day, timezone=timezone, refs=refs,
                                             **overrides), separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def test_unconfigured_daily_brief_has_no_record_and_no_trusted_claim(tmp_path):
    snapshot = DailyBriefRecordReadStore(None).read(DAY, ZONE)
    assert snapshot.configured is False
    assert snapshot.found is False
    assert snapshot.record is None
    assert snapshot.source_verification == "unverified"


def test_daily_brief_reads_exact_day_and_verifies_only_with_injected_source_proof(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    write_record(root)
    (root / "2026-10-19.json").write_text("not read", encoding="utf-8")
    monkeypatch.setattr(os, "scandir", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Daily Brief must use exact date lookup, not enumerate history")))

    store = DailyBriefRecordReadStore(str(root))
    snapshot = store.read(DAY, ZONE)
    assert snapshot.configured is True
    assert snapshot.available is True
    assert snapshot.found is True
    assert snapshot.record["summary"] == "Synthetic durable brief"
    assert len(snapshot.sha256) == 64
    assert snapshot.source_verification == "unverified"

    verified = store.read(DAY, ZONE, source_verifier=lambda ref: ref == REFS[0])
    assert verified.source_verification == "verified"


def test_all_source_failures_are_not_misreported_as_partial(tmp_path):
    root = make_root(tmp_path)
    write_record(root, refs=[REFS[0], {**REFS[0], "id": "another-note"}])
    store = DailyBriefRecordReadStore(str(root))
    assert store.read(DAY, ZONE, source_verifier=lambda _ref: False).source_verification == "missing"
    assert store.read(DAY, ZONE, source_verifier=lambda _ref: "unavailable").source_verification == "unavailable"
    assert store.read(DAY, ZONE, source_verifier=lambda _ref: "stale").source_verification == "stale"
    assert store.read(DAY, ZONE, source_verifier=lambda _ref: (_ for _ in ()).throw(
        RuntimeError("synthetic verifier failure"))).source_verification == "failed"


def test_mixed_source_verification_is_partial_only_when_some_refs_pass(tmp_path):
    root = make_root(tmp_path)
    write_record(root, refs=[REFS[0], {**REFS[0], "id": "missing-note"}])
    store = DailyBriefRecordReadStore(str(root))
    result = store.read(DAY, ZONE, source_verifier=lambda ref: ref["id"] == "a" * 32)
    assert result.source_verification == "partial"


def test_daily_brief_unconfigured_day_differs_from_unavailable_root(tmp_path):
    root = make_root(tmp_path)
    missing = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert missing.configured is True
    assert missing.available is True
    assert missing.found is False

    unavailable = DailyBriefRecordReadStore(str(tmp_path / "missing")).read(DAY, ZONE)
    assert unavailable.configured is True
    assert unavailable.available is False
    assert unavailable.found is False


@pytest.mark.parametrize("bad_payload", [
    b'{"date":"2026-10-20","date":"2026-10-20","timezone":"Asia/Shanghai","source_refs":[]}',
    b"not json",
])
def test_daily_brief_rejects_corrupt_or_duplicate_key_records(tmp_path, bad_payload):
    root = make_root(tmp_path)
    path = root / f"{DAY}.json"
    path.write_bytes(bad_payload)
    os.chmod(path, 0o600)

    snapshot = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert snapshot.available is False
    assert snapshot.found is True
    assert snapshot.record is None
    assert snapshot.source_verification == "unverified"


@pytest.mark.parametrize("field,value", [
    ("private_body", "not allowed"),
    ("brief_id", "../escape"),
    ("generation_status", "unknown"),
    ("generated_at", "2026-10-20 08:00:00"),
    ("categories", ["", 7]),
    ("summary", None),
    ("source_refs", [{}]),
    ("source_refs", [{"kind": "note", "id": "n", "version": "a" * 64}]),
])
def test_daily_brief_rejects_unknown_or_malformed_record_fields(tmp_path, field, value):
    root = make_root(tmp_path)
    write_record(root, **{field: value})
    snapshot = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert snapshot.available is False
    assert snapshot.record is None
    assert snapshot.source_verification == "unverified"


def test_daily_brief_requires_matching_date_timezone_but_allows_later_import_time(tmp_path):
    root = make_root(tmp_path)
    write_record(root, timezone="UTC")
    store = DailyBriefRecordReadStore(str(root))
    assert store.read(DAY, ZONE).available is False

    write_record(root, generated_at="2026-10-23T10:30:00+08:00")
    later_creation = store.read(DAY, ZONE)
    assert later_creation.available is True
    assert later_creation.record["date"] == DAY
    assert later_creation.record["generated_at"] == "2026-10-23T10:30:00+08:00"


def test_daily_brief_requires_single_link_private_bounded_record_and_reference_count(tmp_path):
    root = make_root(tmp_path)
    path = write_record(root, refs=[REFS[0], {**REFS[0], "id": "second"},
                                   {**REFS[0], "id": "third"}])
    assert DailyBriefRecordReadStore(str(root), max_source_refs=2).read(DAY, ZONE).available is False
    os.link(path, root / "other.json")
    assert DailyBriefRecordReadStore(str(root)).read(DAY, ZONE).available is False

    path.unlink()
    path = write_record(root)
    path.write_bytes(b" " * 4097)
    os.chmod(path, 0o600)
    assert DailyBriefRecordReadStore(str(root), max_record_bytes=4096).read(DAY, ZONE).available is False

    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o644)
    assert DailyBriefRecordReadStore(str(root)).read(DAY, ZONE).available is False


def test_daily_brief_refuses_symlink_record_and_bad_queries(tmp_path):
    root = make_root(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (root / f"{DAY}.json").symlink_to(outside)

    snapshot = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert snapshot.available is False
    assert snapshot.record is None
    with pytest.raises(ValueError, match="invalid query"):
        DailyBriefRecordReadStore(str(root)).read("2026-02-30", ZONE)


def test_empty_source_refs_only_allowed_for_explicit_generation_failure(tmp_path):
    root = make_root(tmp_path)
    write_record(root, refs=[])
    assert DailyBriefRecordReadStore(str(root)).read(DAY, ZONE).available is False
    write_record(root, refs=[], generation_status="failed")
    accepted = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert accepted.available is True
    assert accepted.record["generation_status"] == "failed"
