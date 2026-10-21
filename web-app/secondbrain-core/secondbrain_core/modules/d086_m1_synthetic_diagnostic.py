"""Offline read-only, redacted diagnostic for explicitly synthetic roots.

All filesystem traversal is descriptor-relative with O_NOFOLLOW. The database
is bounded-read through its verified descriptor and deserialized into an
in-memory SQLite connection because sqlite3.connect(path) cannot bind to the
already-verified descriptor. No temp DB, sidecar, repair or recovery write is
created. This is still not an operator authentication mechanism.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from .d086_m1_synthetic_consent import SyntheticConsentLedger


_RAW_NAME = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SIDECARS = frozenset({
    SyntheticConsentLedger.database_name + "-journal",
    SyntheticConsentLedger.database_name + "-wal",
    SyntheticConsentLedger.database_name + "-shm",
})


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
                 max_raw_bytes=200_000, max_digest_prefixes=10,
                 time_budget_seconds=5.0):
        raw = os.fspath(root)
        if not os.path.isabs(raw):
            raise ValueError("synthetic diagnostic root must be absolute")
        if (type(max_files) is not int or max_files < 1
                or type(max_total_bytes) is not int or max_total_bytes < 1
                or type(max_raw_bytes) is not int or max_raw_bytes < 1
                or type(max_digest_prefixes) is not int or max_digest_prefixes < 0
                or type(time_budget_seconds) not in (int, float)
                or not 0.001 <= time_budget_seconds <= 60):
            raise ValueError("invalid synthetic diagnostic budget")
        self.root = Path(raw)
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes
        self.max_raw_bytes = max_raw_bytes
        self.max_digest_prefixes = min(max_digest_prefixes, 10)
        self.time_budget_seconds = float(time_budget_seconds)
        self._deadline = None

    def _check_time(self):
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise TimeoutError("diagnostic time budget exceeded")

    def _before_open_hook(self, stage):
        """Deterministic test seam for replace/rename fault injection only."""

    @staticmethod
    def _signature(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_size,
                st.st_mtime_ns, st.st_ctime_ns, st.st_nlink)

    @staticmethod
    def _require_dir(st, *, mode=0o700):
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != mode):
            raise ValueError("unsafe directory")

    @staticmethod
    def _require_file(st, *, mode=0o600, max_bytes):
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != mode or st.st_nlink != 1
                or st.st_size < 0 or st.st_size > max_bytes):
            raise ValueError("unsafe file")

    def _open_canonical_root(self):
        """Walk each canonical component from / with no symlink following."""
        canonical = Path(os.path.realpath(self.root))
        if canonical != self.root:
            raise ValueError("root is not canonical")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        current = os.open("/", flags)
        try:
            for index, component in enumerate(canonical.parts[1:]):
                self._check_time()
                self._before_open_hook(f"before_root_component_{index}")
                self._check_time()
                next_fd = os.open(component, flags, dir_fd=current)
                os.close(current)
                current = next_fd
            root_stat = os.fstat(current)
            self._require_dir(root_stat)
            expected = self.root.lstat()
            if (stat.S_ISLNK(expected.st_mode)
                    or (root_stat.st_dev, root_stat.st_ino) != (expected.st_dev, expected.st_ino)):
                raise ValueError("root identity changed")
            return current, self._signature(root_stat)
        except BaseException:
            os.close(current)
            raise

    def _read_fd(self, fd, limit):
        self._check_time()
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("file size or type is unsafe")
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        remaining = limit + 1
        while remaining:
            self._check_time()
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
        after = os.fstat(fd)
        if len(data) > limit or self._signature(before) != self._signature(after):
            raise ValueError("file changed during bounded read")
        self._check_time()
        return data, self._signature(after)

    def _open_child_dir(self, root_fd, name, stage):
        self._check_time()
        before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        self._require_dir(before)
        self._check_time()
        self._before_open_hook(stage)
        self._check_time()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(name, flags, dir_fd=root_fd)
        after = os.fstat(fd)
        if self._signature(before) != self._signature(after):
            os.close(fd)
            raise ValueError("directory replaced during open")
        return fd, self._signature(after)

    def _open_regular(self, parent_fd, name, *, max_bytes, stage):
        self._check_time()
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        self._require_file(before, max_bytes=max_bytes)
        self._check_time()
        self._before_open_hook(stage)
        self._check_time()
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        after = os.fstat(fd)
        if self._signature(before) != self._signature(after):
            os.close(fd)
            raise ValueError("file replaced during open")
        return fd, self._signature(after)

    @staticmethod
    def _verify_name_identity(parent_fd, name, expected_signature):
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if SyntheticOperatorDiagnostic._signature(current) != expected_signature:
            raise ValueError("directory entry replaced during diagnostic")

    def _read_database(self, db_fd, db_signature):
        raw, after_signature = self._read_fd(db_fd, self.max_total_bytes)
        if after_signature != db_signature:
            raise ValueError("database changed during read")
        conn = sqlite3.connect(":memory:")
        try:
            deserialize = getattr(conn, "deserialize", None)
            if not callable(deserialize):
                raise ValueError("read-only in-memory SQLite deserialize unavailable")
            conn.set_progress_handler(lambda: int(time.monotonic() >= self._deadline), 1000)
            deserialize(raw)
            conn.execute("PRAGMA query_only=ON")
            integrity = conn.execute("PRAGMA quick_check(1)").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            consent_count = conn.execute("SELECT count(*) FROM consent_records").fetchone()[0]
            admission_count = conn.execute("SELECT count(*) FROM inbox_operations").fetchone()[0]
            manifests = conn.execute(
                "SELECT inbox_id,relative_path,sha256,byte_length,verified FROM inbox_raw_manifest"
            ).fetchall()
            audit_rows = conn.execute(
                "SELECT consent_id,action,action_key,revision,payload_hash,previous_hash,entry_hash,created_at "
                "FROM consent_audit ORDER BY consent_id,seq"
            ).fetchall()
            return consent_count, admission_count, manifests, audit_rows
        finally:
            conn.close()

    def run(self) -> SyntheticDiagnosticReport:
        self._deadline = time.monotonic() + self.time_budget_seconds
        findings = []
        prefixes = []
        root_fd = raw_fd = db_fd = None
        raw_file_fds = []
        try:
            root_fd, root_signature = self._open_canonical_root()
            self._before_open_hook("after_root_open")
            self._check_time()
            root_names = set(os.listdir(root_fd))
            db_name = SyntheticConsentLedger.database_name
            if root_names != {db_name, "Raw"}:
                raise ValueError("unexpected root entries or SQLite sidecars")
            raw_fd, raw_signature = self._open_child_dir(root_fd, "Raw", "before_raw_dir_open")
            self._before_open_hook("after_raw_dir_open")
            self._check_time()
            db_fd, db_signature = self._open_regular(
                root_fd, db_name, max_bytes=self.max_total_bytes, stage="before_db_open")
            self._before_open_hook("after_db_open")
            self._check_time()
            db_stat = os.fstat(db_fd)

            raw_names = tuple(sorted(os.listdir(raw_fd)))
            if len(raw_names) + 1 > self.max_files:
                raise ValueError("file count budget exceeded")
            total_bytes = db_stat.st_size
            raw_records = {}
            for name in raw_names:
                self._check_time()
                if not _RAW_NAME.fullmatch(name) or name in {".", ".."}:
                    raise ValueError("invalid Raw name")
                fd, signature = self._open_regular(
                    raw_fd, name, max_bytes=self.max_raw_bytes,
                    stage="before_raw_file_open")
                raw_file_fds.append(fd)
                data, read_signature = self._read_fd(fd, self.max_raw_bytes)
                if signature != read_signature:
                    raise ValueError("Raw entry changed during read")
                total_bytes += len(data)
                if total_bytes > self.max_total_bytes:
                    raise ValueError("total byte budget exceeded")
                raw_records[name] = (data, signature)

            consent_count, admission_count, manifests, audit_rows = self._read_database(
                db_fd, db_signature)
            manifest_by_name = {}
            missing_count = corrupt_count = 0
            for inbox_id, relative, expected_digest, expected_size, verified in manifests:
                self._check_time()
                if (not isinstance(relative, str) or not relative.startswith("Raw/")
                        or "/" in relative[4:] or relative[4:] not in raw_records
                        or verified != 1 or not isinstance(expected_digest, str)
                        or len(expected_digest) != 64 or type(expected_size) is not int
                        or expected_size < 0):
                    missing_count += 1
                    if self.max_digest_prefixes and isinstance(expected_digest, str):
                        prefixes.append(expected_digest[:12])
                    continue
                name = relative[4:]
                manifest_by_name[name] = (inbox_id, expected_digest, expected_size)
                data, _ = raw_records[name]
                actual = hashlib.sha256(data).hexdigest()
                if len(data) != expected_size or actual != expected_digest:
                    corrupt_count += 1
                    if self.max_digest_prefixes:
                        prefixes.append(actual[:12])

            orphan_names = sorted(set(raw_names) - set(manifest_by_name))
            orphan_count = len(orphan_names)
            for name in orphan_names[:self.max_digest_prefixes]:
                data, _ = raw_records[name]
                prefixes.append(hashlib.sha256(data).hexdigest()[:12])

            previous_by_consent = {}
            for consent_id, action, action_key, revision, payload_hash, previous_hash, entry_hash, created_at in audit_rows:
                self._check_time()
                previous = previous_by_consent.get(consent_id, "0" * 64)
                expected = hashlib.sha256(
                    f"{previous}:{consent_id}:{action}:{action_key}:{revision}:{payload_hash}:{created_at}".encode()
                ).hexdigest()
                if previous_hash != previous or entry_hash != expected:
                    findings.append("consent_audit_invalid")
                    break
                previous_by_consent[consent_id] = entry_hash

            # Recheck every anchored descriptor and directory entry before
            # returning. Replacement never redirects these reads; any changed
            # name/identity produces a generic unavailable report.
            if self._signature(os.fstat(root_fd)) != root_signature:
                raise ValueError("root descriptor changed")
            if self._signature(os.fstat(raw_fd)) != raw_signature:
                raise ValueError("Raw descriptor changed")
            self._verify_name_identity(root_fd, "Raw", raw_signature)
            self._verify_name_identity(root_fd, db_name, db_signature)
            for name, (_, signature) in raw_records.items():
                self._verify_name_identity(raw_fd, name, signature)
            current_root_fd, current_root_signature = self._open_canonical_root()
            try:
                if current_root_signature != root_signature:
                    raise ValueError("root pathname identity changed")
            finally:
                os.close(current_root_fd)

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
        except (OSError, ValueError, sqlite3.Error, TypeError, IndexError, TimeoutError):
            return SyntheticDiagnosticReport(
                status="unavailable", consent_count=0, admission_count=0,
                raw_count=0, orphan_count=0, missing_count=0, corrupt_count=0,
                findings=("synthetic_store_unavailable",), digest_prefixes=(),
            )
        finally:
            for fd in raw_file_fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
            for fd in (db_fd, raw_fd, root_fd):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
