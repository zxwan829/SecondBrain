"""Read-only and redaction checks for synthetic operator diagnostics."""
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import time

from secondbrain_core.modules.d086_m1_synthetic_consent import (
    SyntheticActionProofAuthority,
    SyntheticConsentLedger,
)
from secondbrain_core.modules.d086_m1_synthetic_source import SyntheticSourceAuthority
from secondbrain_core.modules.d086_m1_synthetic_admission import SyntheticInboxAdmission
from secondbrain_core.modules.d086_m1_synthetic_diagnostic import SyntheticOperatorDiagnostic


NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
SECRET = b"synthetic-only-secret-for-tests-32-bytes-minimum"
ORIGIN = "https://synthetic.example"


def make_store(root, *, admitted=True):
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    authority = SyntheticActionProofAuthority(secret=SECRET, allowed_origin=ORIGIN)
    ledger = SyntheticConsentLedger(root, authority, clock=lambda: NOW)
    source_authority = SyntheticSourceAuthority(clock=lambda: NOW)
    text = "SENSITIVE-SYNTHETIC-CONTENT"
    source = source_authority.register(event_id="synthetic-event-private",
                                       subject="private-synthetic-subject",
                                       original_text=text, ttl_seconds=3600)
    proof = authority.issue_test_proof(
        action="accept", subject=source.subject, source_system=source.source_system,
        source_event_id=source.source_event_id, source_version=source.source_record_version,
        source_sha256=source.original_text_sha256, intent="save_note",
        action_key="synthetic-accept", origin=ORIGIN,
        issued_at=NOW.isoformat(), action_expires_at=(NOW+timedelta(minutes=5)).isoformat(),
        expires_at=source.expires_at,
    )
    consent = ledger.accept(proof)
    admission = SyntheticInboxAdmission(ledger, source_reader=source_authority,
                                        clock=lambda: NOW)
    if admitted:
        admission_proof = authority.issue_test_proof(
            action="admit", subject=source.subject, source_system=source.source_system,
            source_event_id=source.source_event_id, source_version="1",
            source_sha256=source.original_text_sha256, intent="save_note",
            action_key="synthetic-admission", origin=ORIGIN,
            issued_at=NOW.isoformat(),
            action_expires_at=(NOW + timedelta(minutes=5)).isoformat(),
            expires_at=source.expires_at, consent_id=consent.consent_id,
            expected_revision=consent.revision,
        )
        admission.admit_from_reader(admission_proof)
    return ledger, source, consent, admission


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        st = path.lstat()
        key = str(path.relative_to(root))
        result[key] = (st.st_dev, st.st_ino, st.st_mode, st.st_uid,
                       st.st_size, st.st_mtime_ns, st.st_nlink,
                       path.read_bytes() if path.is_file() and not path.is_symlink() else None)
    return result


def test_healthy_report_is_redacted_and_read_only(tmp_path):
    root = tmp_path / "synthetic"
    ledger, _, _, _ = make_store(root)
    before = snapshot(root)
    report = SyntheticOperatorDiagnostic(root).run()
    after = snapshot(root)
    rendered = repr(report)
    assert report.status == "healthy"
    assert (report.consent_count, report.admission_count, report.raw_count) == (1, 1, 1)
    assert report.orphan_count == report.missing_count == report.corrupt_count == 0
    assert "SENSITIVE-SYNTHETIC-CONTENT" not in rendered
    assert "private-synthetic-subject" not in rendered
    assert "synthetic-event-private" not in rendered
    assert str(root) not in rendered
    assert ledger.database_name not in rendered
    assert before == after
    assert not list(root.glob("*-journal"))
    assert not list(root.glob("*-wal"))
    assert not list(root.glob("*-shm"))


def test_orphan_and_corrupt_manifest_are_reported_without_repair(tmp_path):
    root = tmp_path / "synthetic"
    _, _, _, _ = make_store(root)
    raw_root = root / "Raw"
    (raw_root / "orphan-synthetic.raw").write_bytes(b"orphan synthetic bytes")
    os.chmod(raw_root / "orphan-synthetic.raw", 0o600)
    referenced = next(path for path in raw_root.iterdir() if path.name != "orphan-synthetic.raw")
    referenced.write_bytes(b"changed synthetic bytes")
    before = snapshot(root)
    report = SyntheticOperatorDiagnostic(root).run()
    after = snapshot(root)
    assert report.status == "attention_required"
    assert report.orphan_count == 1 and report.corrupt_count == 1
    assert "raw_orphans_present" in report.findings
    assert "raw_integrity_failed" in report.findings
    assert before == after
    assert referenced.read_bytes() == b"changed synthetic bytes"
    assert (raw_root / "orphan-synthetic.raw").read_bytes() == b"orphan synthetic bytes"


def test_symlink_bad_mode_sidecar_and_budget_fail_closed_without_changes(tmp_path):
    root = tmp_path / "synthetic"
    make_store(root, admitted=False)
    db = root / SyntheticConsentLedger.database_name
    before = snapshot(root)
    os.chmod(db, 0o640)
    report = SyntheticOperatorDiagnostic(root).run()
    assert report.status == "unavailable"
    os.chmod(db, 0o600)
    before = snapshot(root)

    sidecar = root / (SyntheticConsentLedger.database_name + "-wal")
    sidecar.write_bytes(b"synthetic sidecar")
    os.chmod(sidecar, 0o600)
    assert SyntheticOperatorDiagnostic(root).run().status == "unavailable"
    sidecar.unlink()
    assert before == snapshot(root)

    link = root / "Raw" / "unsafe-link"
    link.symlink_to(db)
    assert SyntheticOperatorDiagnostic(root).run().status == "unavailable"
    link.unlink()
    assert SyntheticOperatorDiagnostic(root, max_total_bytes=1).run().status == "unavailable"


def test_redacted_digest_prefixes_are_bounded_and_never_full_hash(tmp_path):
    root = tmp_path / "synthetic"
    _, _, _, _ = make_store(root, admitted=False)
    orphan = root / "Raw" / "orphan.raw"
    orphan.write_bytes(b"synthetic orphan with unique material")
    os.chmod(orphan, 0o600)
    report = SyntheticOperatorDiagnostic(root, max_digest_prefixes=1).run()
    digest = hashlib.sha256(orphan.read_bytes()).hexdigest()
    assert report.status == "attention_required"
    assert len(report.digest_prefixes) == 1
    assert report.digest_prefixes[0] == digest[:12]
    assert digest not in repr(report)
    assert "orphan.raw" not in repr(report)


def test_db_symlink_swap_between_lstat_and_open_fails_without_reading_target(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root, admitted=False)
    db = root / SyntheticConsentLedger.database_name
    saved = root / "db.saved"
    decoy = tmp_path / "outside-db"
    decoy.write_bytes(b"outside synthetic database sentinel")
    os.chmod(decoy, 0o600)
    target_identity = (decoy.stat().st_dev, decoy.stat().st_ino)
    diagnostic = SyntheticOperatorDiagnostic(root)
    opened = []
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class SwapDbBeforeOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "before_db_open":
                db.rename(saved)
                db.symlink_to(decoy)

    report = SwapDbBeforeOpen(root).run()
    assert report.status == "unavailable"
    assert target_identity not in opened
    db.unlink()
    saved.rename(db)


def test_db_path_replacement_after_open_reads_only_pinned_database_fd(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root, admitted=False)
    db = root / SyntheticConsentLedger.database_name
    saved = root / "db.saved"
    decoy = tmp_path / "outside-db"
    decoy.write_bytes(b"outside synthetic database sentinel")
    os.chmod(decoy, 0o600)
    target_identity = (decoy.stat().st_dev, decoy.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class SwapDbAfterOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "after_db_open":
                db.rename(saved)
                db.symlink_to(decoy)

    report = SwapDbAfterOpen(root).run()
    assert report.status == "unavailable"
    assert target_identity not in opened
    db.unlink()
    saved.rename(db)


def test_raw_directory_swap_between_stat_and_open_rejects_symlink(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root, admitted=False)
    raw = root / "Raw"
    saved = root / "Raw.saved"
    outside = tmp_path / "outside-raw"
    outside.mkdir(mode=0o700)
    os.chmod(outside, 0o700)
    sentinel = outside / "sentinel.raw"
    sentinel.write_bytes(b"outside raw sentinel")
    os.chmod(sentinel, 0o600)
    outside_identity = (sentinel.stat().st_dev, sentinel.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class SwapRawBeforeOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "before_raw_dir_open":
                raw.rename(saved)
                raw.symlink_to(outside, target_is_directory=True)

    report = SwapRawBeforeOpen(root).run()
    assert report.status == "unavailable"
    assert outside_identity not in opened
    raw.unlink()
    saved.rename(raw)


def test_raw_directory_replacement_after_open_stays_on_anchored_fd(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root)
    raw = root / "Raw"
    saved = root / "Raw.saved"
    outside = tmp_path / "outside-raw"
    outside.mkdir(mode=0o700)
    os.chmod(outside, 0o700)
    sentinel = outside / "sentinel.raw"
    sentinel.write_bytes(b"outside raw sentinel")
    os.chmod(sentinel, 0o600)
    target_identity = (sentinel.stat().st_dev, sentinel.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class SwapRawAfterOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "after_raw_dir_open":
                raw.rename(saved)
                raw.symlink_to(outside, target_is_directory=True)

    report = SwapRawAfterOpen(root).run()
    assert report.status == "unavailable"
    assert target_identity not in opened
    raw.unlink()
    saved.rename(raw)


def test_root_replacement_after_fd_anchor_fails_closed_without_following_decoy(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root)
    moved = tmp_path / "original-root"
    decoy = tmp_path / "replacement-root"
    decoy.mkdir(mode=0o700)
    os.chmod(decoy, 0o700)
    sentinel = decoy / "sentinel"
    sentinel.write_bytes(b"must never be read")
    os.chmod(sentinel, 0o600)
    target_identity = (sentinel.stat().st_dev, sentinel.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class SwapRootAfterAnchor(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "before_db_open":
                root.rename(moved)
                root.symlink_to(decoy, target_is_directory=True)

    report = SwapRootAfterAnchor(root).run()
    assert report.status == "unavailable"
    assert target_identity not in opened
    root.unlink()
    moved.rename(root)


def test_root_replaced_with_valid_directory_after_open_reads_only_pinned_root(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root)
    moved = tmp_path / "original-root"
    decoy = tmp_path / "decoy-root"
    make_store(decoy)
    decoy_db = decoy / SyntheticConsentLedger.database_name
    decoy_identity = (decoy_db.stat().st_dev, decoy_db.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class ReplaceRootAfterOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "after_root_open":
                root.rename(moved)
                decoy.rename(root)

    report = ReplaceRootAfterOpen(root).run()
    assert report.status == "unavailable"
    assert decoy_identity not in opened
    root.rename(decoy)
    moved.rename(root)


def test_root_symlink_substitution_before_component_open_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root, admitted=False)
    moved = tmp_path / "original-root"
    decoy = tmp_path / "decoy-root"
    decoy.mkdir(mode=0o700)
    os.chmod(decoy, 0o700)

    class SwapRootBeforeOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == f"before_root_component_{len(Path(root).parts) - 2}":
                root.rename(moved)
                root.symlink_to(decoy, target_is_directory=True)

    report = SwapRootBeforeOpen(root).run()
    assert report.status == "unavailable"
    root.unlink()
    moved.rename(root)


def test_intermediate_parent_symlink_swap_is_rejected(tmp_path):
    parent = tmp_path
    root = parent / "synthetic"
    make_store(root, admitted=False)
    moved_parent = parent.with_name(parent.name + ".saved")
    decoy_parent = parent.with_name(parent.name + ".replacement")
    decoy_parent.mkdir(mode=0o700)
    os.chmod(decoy_parent, 0o700)

    class SwapIntermediateBeforeOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == f"before_root_component_{len(Path(root).parts) - 3}":
                parent.rename(moved_parent)
                parent.symlink_to(decoy_parent, target_is_directory=True)

    report = SwapIntermediateBeforeOpen(root).run()
    assert report.status == "unavailable"
    parent.unlink()
    moved_parent.rename(parent)


def test_valid_intermediate_directory_replacement_is_rejected_by_pinned_root_identity(tmp_path, monkeypatch):
    parent = tmp_path
    root = parent / "synthetic"
    make_store(root, admitted=False)
    moved_parent = parent.with_name(parent.name + ".saved")
    replacement_parent = parent.with_name(parent.name + ".replacement")
    replacement_parent.mkdir(mode=0o700)
    os.chmod(replacement_parent, 0o700)
    decoy_root = replacement_parent / "synthetic"
    make_store(decoy_root, admitted=False)
    decoy_db = decoy_root / SyntheticConsentLedger.database_name
    decoy_identity = (decoy_db.stat().st_dev, decoy_db.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class ReplaceParentWithValidDirectory(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == f"before_root_component_{len(Path(root).parts) - 3}":
                parent.rename(moved_parent)
                replacement_parent.rename(parent)

    report = ReplaceParentWithValidDirectory(root).run()
    assert report.status == "unavailable"
    assert decoy_identity not in opened
    parent.rename(replacement_parent)
    moved_parent.rename(parent)


def test_raw_child_symlink_swap_before_open_does_not_read_target(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    make_store(root)
    raw = root / "Raw"
    child = next(raw.iterdir())
    saved = raw / "child.saved"
    decoy = tmp_path / "outside-raw-file"
    decoy.write_bytes(b"outside raw file sentinel")
    os.chmod(decoy, 0o600)
    target_identity = (decoy.stat().st_dev, decoy.stat().st_ino)
    opened = []
    diagnostic = SyntheticOperatorDiagnostic(root)
    original_read = diagnostic._read_fd

    def tracked_read(fd, limit):
        st = os.fstat(fd)
        opened.append((st.st_dev, st.st_ino))
        return original_read(fd, limit)

    monkeypatch.setattr(diagnostic, "_read_fd", tracked_read)

    class SwapRawChildBeforeOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "before_raw_file_open":
                child.rename(saved)
                child.symlink_to(decoy)

    report = SwapRawChildBeforeOpen(root).run()
    assert report.status == "unavailable"
    assert target_identity not in opened
    child.unlink()
    saved.rename(child)


def test_time_budget_exhaustion_returns_redacted_unavailable(tmp_path):
    root = tmp_path / "synthetic"
    make_store(root)

    class SlowOpen(SyntheticOperatorDiagnostic):
        def _before_open_hook(self, stage):
            if stage == "before_root_component_0":
                time.sleep(0.02)

    report = SlowOpen(root, time_budget_seconds=0.005).run()
    assert report.status == "unavailable"
    assert report.findings == ("synthetic_store_unavailable",)
    assert str(root) not in repr(report)
