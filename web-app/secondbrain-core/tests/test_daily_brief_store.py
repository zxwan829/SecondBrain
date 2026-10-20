import json
import os

import pytest

from secondbrain_core.modules.daily_brief_store import DailyBriefRecordReadStore


DAY = "2026-10-20"
ZONE = "Asia/Shanghai"


def make_root(tmp_path):
    root = tmp_path / "briefs"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def write_record(root, *, day=DAY, timezone=ZONE, refs=None):
    payload = {
        "date": day,
        "timezone": timezone,
        "generated_at": "2026-10-20T08:00:00+08:00",
        "categories": [],
        "summary": "Synthetic durable brief",
        "source_refs": refs if refs is not None else [{"source_id": "synthetic-ref", "sha256": "a" * 64}],
    }
    path = root / f"{day}.json"
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def test_unconfigured_daily_brief_has_no_record_and_no_trusted_claim(tmp_path):
    snapshot = DailyBriefRecordReadStore(None).read(DAY, ZONE)
    assert snapshot.configured is False
    assert snapshot.found is False
    assert snapshot.record is None
    assert snapshot.source_verification == "unverified"


def test_daily_brief_reads_one_exact_day_and_verifies_only_with_injected_source_proof(tmp_path, monkeypatch):
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

    verified = store.read(DAY, ZONE, source_verifier=lambda ref: (
        ref.get("source_id") == "synthetic-ref" and ref.get("sha256") == "a" * 64))
    assert verified.source_verification == "verified"
    partial = store.read(DAY, ZONE, source_verifier=lambda _ref: False)
    assert partial.source_verification == "partial"


def test_daily_brief_unconfigured_day_is_distinct_from_unavailable_root(tmp_path):
    root = make_root(tmp_path)
    store = DailyBriefRecordReadStore(str(root))
    missing = store.read(DAY, ZONE)
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


def test_daily_brief_requires_matching_date_timezone_and_valid_reference_count(tmp_path):
    root = make_root(tmp_path)
    write_record(root, timezone="UTC")
    mismatch = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert mismatch.available is False
    assert mismatch.record is None

    path = root / f"{DAY}.json"
    payload = json.loads(path.read_text())
    payload["timezone"] = ZONE
    payload["source_refs"] = [{}] * 3
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    bounded = DailyBriefRecordReadStore(str(root), max_source_refs=2).read(DAY, ZONE)
    assert bounded.available is False
    assert bounded.record is None


def test_daily_brief_refuses_symlink_hardlink_oversize_and_public_file(tmp_path):
    root = make_root(tmp_path)
    path = write_record(root)
    os.link(path, root / "other.json")
    linked = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert linked.available is False

    path.unlink()
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o600)
    path.write_bytes(b" " * 4097)
    os.chmod(path, 0o600)
    oversize = DailyBriefRecordReadStore(str(root), max_record_bytes=4096).read(DAY, ZONE)
    assert oversize.available is False

    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o644)
    public = DailyBriefRecordReadStore(str(root)).read(DAY, ZONE)
    assert public.available is False


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
