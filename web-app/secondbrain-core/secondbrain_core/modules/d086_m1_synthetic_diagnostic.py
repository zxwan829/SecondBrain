"""Offline read-only, redacted operator diagnostic for synthetic D086-M1.

This function accepts only an explicitly supplied synthetic root. It creates
no files, opens SQLite in read-only mode, performs no recovery, and returns no
paths, source text, subjects, event IDs, consent IDs, or full digests.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote

from .d086_m1_synthetic_consent import SyntheticConsentLedger


@dataclass(frozen=True)
class SyntheticDiagnosticReport:
    status: str
    consent_count: int
    admission_count: int
    raw_count: int
    orphan_count: int
    missing_count: int
    corrupt_count: int
    findings: tuple[str, ...]
    digest_prefixes: tuple[str, ...]


class SyntheticOperatorDiagnostic:
    """Read-only synthetic status/count verifier with strict resource caps."""

    def __init__(self, root: str | os.PathLike, *, max_files=5000,
                 max_total_bytes=64 * 1024 * 1024,
                 max_raw_bytes=200_000, max_digest_prefixes=10):
        raw = os.fspath(root)
        if not os.path.isabs(raw):
            raise ValueError("synthetic diagnostic root must be absolute")
        if (type(max_files) is not int or max_files < 1
                or type(max_total_bytes) is not int or max_total_bytes < 1
                or type(max_raw_bytes) is not int or max_raw_bytes < 1
                or type(max_digest_prefixes) is not int or max_digest_prefixes < 0):
            raise ValueError("invalid synthetic diagnostic budget")
        self.root = Path(raw)
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes
        self.max_raw_bytes = max_raw_bytes
        self.max_digest_prefixes = min(max_digest_prefixes, 10)

    def _inventory(self):
        root_st = self.root.lstat()
        if (Path(os.path.realpath(self.root)) != self.root
                or not stat.S_ISDIR(root_st.st_mode)
                or stat.S_ISLNK(root_st.st_mode)
                or root_st.st_uid != os.geteuid()
                or stat.S_IMODE(root_st.st_mode) != 0o700):
            raise ValueError("unsafe root")
        db = self.root / SyntheticConsentLedger.database_name
        raw = self.root / "Raw"
        db_st = db.lstat()
        raw_st = raw.lstat()
        if (not stat.S_ISREG(db_st.st_mode) or stat.S_ISLNK(db_st.st_mode)
                or db_st.st_uid != os.geteuid() or stat.S_IMODE(db_st.st_mode) != 0o600
                or db_st.st_nlink != 1 or not stat.S_ISDIR(raw_st.st_mode)
                or stat.S_ISLNK(raw_st.st_mode) or raw_st.st_uid != os.geteuid()
                or stat.S_IMODE(raw_st.st_mode) != 0o700):
            raise ValueError("unsafe store path")
        entries = list(self.root.iterdir())
        if set(entry.name for entry in entries) != {db.name, "Raw"}:
            raise ValueError("unexpected synthetic root entry")
        signature = {
            ".": (root_st.st_dev, root_st.st_ino, root_st.st_mode, root_st.st_uid),
            db.name: self._stat_signature(db_st),
            "Raw": (raw_st.st_dev, raw_st.st_ino, raw_st.st_mode, raw_st.st_uid),
        }
        files = []
        total_bytes = db_st.st_size
        for child in raw.iterdir():
            st = child.lstat()
            if (not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)
                    or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600
                    or st.st_nlink != 1 or child.name in {".", ".."}):
                raise ValueError("unsafe Raw entry")
            files.append(child.name)
            signature[f"Raw/{child.name}"] = self._stat_signature(st)
            total_bytes += st.st_size
        if (len(files) + 1 > self.max_files or total_bytes > self.max_total_bytes
                or any((self.root / suffix).exists() for suffix in (
                    db.name + "-journal", db.name + "-wal", db.name + "-shm"))):
            raise ValueError("synthetic resource budget or sidecar exceeded")
        return db, raw, tuple(sorted(files)), signature, total_bytes

    @staticmethod
    def _stat_signature(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_size,
                st.st_mtime_ns, st.st_nlink)

    @staticmethod
    def _read_regular(path, limit):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("Raw size or type is unsafe")
            chunks = []
            remaining = limit + 1
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            data = b"".join(chunks)
            after = os.fstat(fd)
            if (len(data) > limit or SyntheticOperatorDiagnostic._stat_signature(before)
                    != SyntheticOperatorDiagnostic._stat_signature(after)):
                raise ValueError("Raw changed during diagnostic read")
            return data
        finally:
            os.close(fd)

    def run(self) -> SyntheticDiagnosticReport:
        findings = []
        prefixes = []
        try:
            db, raw_root, raw_names, before, total_bytes = self._inventory()
            uri = f"file:{quote(str(db), safe='/')}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=0.5)
            try:
                conn.execute("PRAGMA query_only=ON")
                integrity = conn.execute("PRAGMA quick_check(1)").fetchone()
                if not integrity or integrity[0] != "ok":
                    findings.append("sqlite_integrity_failed")
                consent_count = conn.execute("SELECT count(*) FROM consent_records").fetchone()[0]
                admission_count = conn.execute("SELECT count(*) FROM inbox_operations").fetchone()[0]
                manifests = conn.execute(
                    "SELECT inbox_id,relative_path,sha256,byte_length,verified FROM inbox_raw_manifest"
                ).fetchall()
                audit_rows = conn.execute(
                    "SELECT consent_id,action,action_key,revision,payload_hash,previous_hash,entry_hash,created_at "
                    "FROM consent_audit ORDER BY consent_id,seq"
                ).fetchall()
            finally:
                conn.close()

            manifest_by_name = {}
            missing_count = corrupt_count = 0
            for inbox_id, relative, expected_digest, expected_size, verified in manifests:
                if (not isinstance(relative, str) or not relative.startswith("Raw/")
                        or "/" in relative[4:] or relative[4:] not in raw_names
                        or verified != 1 or not isinstance(expected_digest, str)
                        or len(expected_digest) != 64 or type(expected_size) is not int
                        or expected_size < 0):
                    missing_count += 1
                    if self.max_digest_prefixes and isinstance(expected_digest, str):
                        prefixes.append(expected_digest[:12])
                    continue
                raw_name = relative[4:]
                manifest_by_name[raw_name] = (inbox_id, expected_digest, expected_size)
                try:
                    content = self._read_regular(raw_root / raw_name, self.max_raw_bytes)
                    actual_digest = hashlib.sha256(content).hexdigest()
                    if len(content) != expected_size or actual_digest != expected_digest:
                        corrupt_count += 1
                        if self.max_digest_prefixes:
                            prefixes.append(actual_digest[:12])
                except (OSError, ValueError):
                    corrupt_count += 1
                    if self.max_digest_prefixes:
                        prefixes.append(expected_digest[:12])

            orphan_names = sorted(set(raw_names) - set(manifest_by_name))
            orphan_count = len(orphan_names)
            for name in orphan_names[:self.max_digest_prefixes]:
                try:
                    content = self._read_regular(raw_root / name, self.max_raw_bytes)
                    prefixes.append(hashlib.sha256(content).hexdigest()[:12])
                except (OSError, ValueError):
                    findings.append("raw_orphan_unreadable")

            previous_by_consent = {}
            for consent_id, action, action_key, revision, payload_hash, previous_hash, entry_hash, created_at in audit_rows:
                previous = previous_by_consent.get(consent_id, "0" * 64)
                expected = hashlib.sha256(
                    f"{previous}:{consent_id}:{action}:{action_key}:{revision}:{payload_hash}:{created_at}".encode()
                ).hexdigest()
                if previous_hash != previous or entry_hash != expected:
                    findings.append("consent_audit_invalid")
                    break
                previous_by_consent[consent_id] = entry_hash

            try:
                _, _, _, after, _ = self._inventory()
            except (OSError, ValueError):
                after = None
            if before != after:
                findings.append("store_changed_during_read")
            if orphan_count:
                findings.append("raw_orphans_present")
            if missing_count:
                findings.append("raw_manifest_missing")
            if corrupt_count:
                findings.append("raw_integrity_failed")
            status = "healthy" if not findings else "attention_required"
            return SyntheticDiagnosticReport(
                status=status, consent_count=consent_count,
                admission_count=admission_count, raw_count=len(raw_names),
                orphan_count=orphan_count, missing_count=missing_count,
                corrupt_count=corrupt_count, findings=tuple(sorted(set(findings))),
                digest_prefixes=tuple(prefixes[:self.max_digest_prefixes]),
            )
        except (OSError, ValueError, sqlite3.Error, TypeError, IndexError):
            return SyntheticDiagnosticReport(
                status="unavailable", consent_count=0, admission_count=0,
                raw_count=0, orphan_count=0, missing_count=0, corrupt_count=0,
                findings=("synthetic_store_unavailable",), digest_prefixes=(),
            )
