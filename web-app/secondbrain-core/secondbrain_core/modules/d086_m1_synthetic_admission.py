"""Synthetic-only S3 CAS model; it never wires into the real Inbox route.

SQLite owns consent revisions, admission operations and Raw manifests in one
transaction domain. Raw bytes are fsynced before SQLite commit. A crash between
the Raw fsync and DB commit may leave an orphan; this module intentionally does
not repair or delete it. The filesystem and SQLite are not claimed to be one
atomic transaction.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat

from .capture_suggestion_binding import (
    MAX_SOURCE_TEXT_UTF8_BYTES,
    validate_verified_capture_suggestion_source,
)
from .d086_m1_synthetic_consent import (
    SyntheticConsentConflict,
    SyntheticConsentUnavailable,
)


_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True)
class SyntheticAdmission:
    operation_id: str
    inbox_id: str
    consent_id: str
    subject: str
    source_system: str
    source_event_id: str
    source_version: str
    source_sha256: str
    intent: str
    consent_revision: int
    raw_relative_path: str
    replayed: bool = False


class SyntheticInboxAdmission:
    """Synthetic-only admission over an injected reader and signed action.

    Callers never supply source DTOs, text, subject or version. The reader is
    injected at service construction and must provide a source commit guard
    held through SQLite commit. This models a synthetic source lock only; it
    does not prove real Hermes locking/CAS or production authentication.
    """

    def __init__(self, ledger, *, source_reader, raw_directory="Raw", clock=None,
                 max_raw_bytes=MAX_SOURCE_TEXT_UTF8_BYTES):
        self.ledger = ledger
        self.source_reader = source_reader
        if raw_directory != "Raw":
            raise ValueError("synthetic Raw directory name is fixed")
        if type(max_raw_bytes) is not int or not 1 <= max_raw_bytes <= MAX_SOURCE_TEXT_UTF8_BYTES:
            raise ValueError("invalid synthetic Raw byte budget")
        self.raw_root = ledger.root / raw_directory
        self.clock = clock or ledger.clock
        self.max_raw_bytes = max_raw_bytes
        self._ensure_raw_root()
        self._initialize()

    def _ensure_raw_root(self):
        root_fd = raw_fd = None
        directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                           | getattr(os, "O_NOFOLLOW", 0))
        try:
            root_fd = os.open(self.ledger.root, directory_flags)
            root_stat = os.fstat(root_fd)
            if ((root_stat.st_dev, root_stat.st_ino) != self.ledger.root_identity
                    or not stat.S_ISDIR(root_stat.st_mode)):
                raise SyntheticConsentUnavailable("synthetic root identity changed")
            try:
                os.mkdir("Raw", mode=0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            except FileExistsError:
                pass
            raw_fd = os.open("Raw", directory_flags, dir_fd=root_fd)
            st = os.fstat(raw_fd)
            named = os.stat("Raw", dir_fd=root_fd, follow_symlinks=False)
            if ((st.st_dev, st.st_ino) != (named.st_dev, named.st_ino)
                    or not stat.S_ISDIR(st.st_mode)
                    or st.st_uid != os.geteuid()
                    or stat.S_IMODE(st.st_mode) != 0o700):
                raise SyntheticConsentUnavailable("synthetic Raw root is unsafe")
            self._raw_identity = (st.st_dev, st.st_ino)
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw root unavailable") from exc
        finally:
            if raw_fd is not None:
                os.close(raw_fd)
            if root_fd is not None:
                os.close(root_fd)

    @contextmanager
    def _pinned_raw_directory(self):
        """Pin root/Raw and reject a replaced configured directory entry."""
        root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        raw_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        root_fd = raw_fd = None
        try:
            root_fd = os.open(self.ledger.root, root_flags)
            root_stat = os.fstat(root_fd)
            if ((root_stat.st_dev, root_stat.st_ino) != self.ledger.root_identity
                    or not stat.S_ISDIR(root_stat.st_mode)):
                raise SyntheticConsentUnavailable("synthetic root identity changed")
            raw_fd = os.open("Raw", raw_flags, dir_fd=root_fd)
            self._assert_raw_directory(root_fd, raw_fd)
            yield root_fd, raw_fd
        except SyntheticConsentUnavailable:
            raise
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw root unavailable") from exc
        finally:
            if raw_fd is not None:
                os.close(raw_fd)
            if root_fd is not None:
                os.close(root_fd)

    def _assert_raw_directory(self, root_fd, raw_fd):
        try:
            pinned = os.fstat(raw_fd)
            named = os.stat("Raw", dir_fd=root_fd, follow_symlinks=False)
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw root changed") from exc
        expected = self._raw_identity
        if ((pinned.st_dev, pinned.st_ino) != expected
                or (named.st_dev, named.st_ino) != expected
                or not stat.S_ISDIR(pinned.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or pinned.st_uid != os.geteuid()
                or stat.S_IMODE(pinned.st_mode) != 0o700):
            raise SyntheticConsentUnavailable("synthetic Raw root identity changed")

    def _raw_checkpoint(self, _name):
        """No-op fault-injection seam used only by local synthetic tests."""

    def _initialize(self):
        try:
            with self.ledger.transaction() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS inbox_operations (
                    operation_id TEXT PRIMARY KEY,
                    consent_id TEXT NOT NULL UNIQUE REFERENCES consent_records(consent_id),
                    action_key TEXT NOT NULL,
                    inbox_id TEXT NOT NULL UNIQUE,
                    subject TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    consent_revision INTEGER NOT NULL,
                    raw_relative_path TEXT NOT NULL UNIQUE,
                    raw_sha256 TEXT NOT NULL,
                    raw_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(subject, source_system, source_event_id)
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS inbox_raw_manifest (
                    inbox_id TEXT PRIMARY KEY REFERENCES inbox_operations(inbox_id),
                    relative_path TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL,
                    byte_length INTEGER NOT NULL,
                    verified INTEGER NOT NULL CHECK(verified=1)
                )""")
        except SyntheticConsentUnavailable:
            raise

    @staticmethod
    def _now_iso(now):
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise SyntheticConsentUnavailable("synthetic clock must be timezone-aware")
        return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _raw_name(self, relative):
        if (not isinstance(relative, str) or not relative.startswith("Raw/")
                or not _KEY.fullmatch(relative[4:])):
            raise SyntheticConsentUnavailable("synthetic Raw reference is invalid")
        return relative[4:]

    def _read_raw(self, root_fd, raw_fd, relative):
        name = self._raw_name(relative)
        try:
            self._assert_raw_directory(root_fd, raw_fd)
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=raw_fd)
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode)
                    or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600
                    or st.st_nlink != 1):
                raise SyntheticConsentUnavailable("synthetic Raw object is unsafe")
            with os.fdopen(fd, "rb") as stream:
                fd = None
                raw = stream.read(self.max_raw_bytes + 1)
            self._assert_raw_directory(root_fd, raw_fd)
            return raw
        except SyntheticConsentUnavailable:
            raise
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw object unavailable") from exc
        finally:
            if "fd" in locals() and fd is not None:
                os.close(fd)

    def _stage_raw(self, *, root_fd, raw_fd, inbox_id, raw_bytes, digest):
        relative = f"{inbox_id}.raw"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = None
        try:
            self._raw_checkpoint("before_child_create")
            self._assert_raw_directory(root_fd, raw_fd)
            fd = os.open(relative, flags, 0o600, dir_fd=raw_fd)
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid()
                    or stat.S_IMODE(opened.st_mode) != 0o600 or opened.st_nlink != 1):
                raise SyntheticConsentUnavailable("synthetic Raw object is unsafe")
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(raw_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            self._raw_checkpoint("after_file_fsync")
            self._assert_raw_directory(root_fd, raw_fd)
            os.fsync(raw_fd)
            current = self._read_raw(root_fd, raw_fd, f"Raw/{relative}")
            if len(current) != len(raw_bytes) or hashlib.sha256(current).hexdigest() != digest:
                raise SyntheticConsentUnavailable("synthetic Raw verification failed")
            self._assert_raw_directory(root_fd, raw_fd)
            return f"Raw/{relative}"
        except FileExistsError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw id collision") from exc
        except SyntheticConsentUnavailable:
            raise
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw durability check failed") from exc
        finally:
            if fd is not None:
                os.close(fd)

    def admit_from_reader(self, action_proof):
        """Read source from the injected authority and admit a signed action."""
        reader = self.source_reader
        read_source = getattr(reader, "read_verified_suggestion", None)
        source_guard = getattr(reader, "source_commit_guard", None)
        if not callable(read_source) or not callable(source_guard):
            raise SyntheticConsentUnavailable("trusted synthetic source guard unavailable")
        if not self.ledger.proof_authority.verify_fields(action_proof):
            raise SyntheticConsentConflict("synthetic admission action proof invalid")
        if action_proof.action != "admit" or not self._proof_matches_request(action_proof):
            raise SyntheticConsentConflict("synthetic admission action binding invalid")
        action_now = datetime.fromisoformat(
            self.ledger._verified(action_proof, "admit").replace("Z", "+00:00"))
        action_key = action_proof.action_key
        consent_id = action_proof.consent_id
        expected_consent_revision = action_proof.expected_revision
        intent = action_proof.intent
        now_iso = self._now_iso(action_now)

        # The synthetic source lock spans actual double read, raw staging and
        # SQLite commit. Real remote source systems need a separately proven
        # revision CAS/lock; a last read alone cannot close that TOCTOU window.
        with source_guard(action_proof.source_event_id):
            with self._pinned_raw_directory() as (root_fd, raw_fd):
                with self.ledger.transaction(
                        before_commit=lambda: self._check_raw_commit(root_fd, raw_fd)) as conn:
                    first = read_source(action_proof.source_event_id)
                    second = read_source(action_proof.source_event_id)
                    expected_text = getattr(first, "original_text", "")
                    source = validate_verified_capture_suggestion_source(
                        first, second, allowed_source_systems={"synthetic.m1"},
                        expected_event_id=action_proof.source_event_id,
                        expected_text=expected_text,
                        expected_version=action_proof.source_version,
                        expected_subject=action_proof.subject,
                        now=action_now,
                    )
                    if source is None or source.original_text_sha256 != action_proof.source_sha256:
                        raise SyntheticConsentConflict("trusted source validation failed closed")
                    try:
                        raw_bytes = source.original_text.encode("utf-8")
                    except UnicodeError as exc:
                        raise SyntheticConsentConflict("source encoding invalid") from exc
                    if len(raw_bytes) > self.max_raw_bytes:
                        raise SyntheticConsentConflict("source exceeds synthetic Raw budget")
                    digest = hashlib.sha256(raw_bytes).hexdigest()
                    if digest != source.original_text_sha256:
                        raise SyntheticConsentConflict("source digest changed")

                    prior = conn.execute(
                        "SELECT operation_id,inbox_id,consent_id,subject,source_system,source_event_id,source_version,source_sha256,intent,consent_revision,raw_relative_path,raw_sha256,action_key "
                        "FROM inbox_operations WHERE subject=? AND source_system=? AND source_event_id=?",
                        (source.subject, source.source_system, source.source_event_id),
                    ).fetchone()
                    if prior:
                        exact = (prior[2], prior[3], prior[4], prior[5], prior[6], prior[7],
                                 prior[8], prior[9], prior[12]) == (
                            consent_id, source.subject, source.source_system,
                            source.source_event_id, source.source_record_version,
                            source.original_text_sha256, intent, expected_consent_revision,
                            action_key,
                        )
                        if not exact:
                            raise SyntheticConsentConflict("source event already admitted with different intent or key")
                        raw = self._read_raw(root_fd, raw_fd, prior[10])
                        if hashlib.sha256(raw).hexdigest() != prior[11]:
                            raise SyntheticConsentUnavailable("synthetic Raw manifest verification failed")
                        return SyntheticAdmission(*prior[:11], replayed=True)

                    consent = conn.execute(
                        "SELECT subject,source_system,source_event_id,source_version,source_sha256,intent,state,revision,expires_at "
                        "FROM consent_records WHERE consent_id=?",
                        (consent_id,),
                    ).fetchone()
                    expected = (source.subject, source.source_system, source.source_event_id,
                                source.source_record_version, source.original_text_sha256,
                                intent, "active", expected_consent_revision)
                    if not consent or consent[:8] != expected or consent[8] != action_proof.expires_at:
                        raise SyntheticConsentConflict("consent state or revision changed")
                    expires = datetime.fromisoformat(consent[8].replace("Z", "+00:00"))
                    if expires.tzinfo is None or action_now >= expires:
                        raise SyntheticConsentConflict("consent expired")
                    operation_id = secrets.token_hex(16)
                    inbox_id = hashlib.sha256(
                        f"{consent_id}\0{action_key}\0{source.original_text_sha256}".encode()
                    ).hexdigest()[:32]
                    relative = self._stage_raw(root_fd=root_fd, raw_fd=raw_fd,
                                               inbox_id=inbox_id, raw_bytes=raw_bytes, digest=digest)

                    # Re-read at the commit edge while both synthetic source and
                    # SQLite CAS guards remain held.
                    final_source = read_source(action_proof.source_event_id)
                    still_current = validate_verified_capture_suggestion_source(
                        source, final_source, allowed_source_systems={"synthetic.m1"},
                        expected_event_id=action_proof.source_event_id,
                        expected_text=source.original_text,
                        expected_version=action_proof.source_version,
                        expected_subject=action_proof.subject,
                        now=self.clock(),
                    )
                    if still_current is None or still_current.original_text_sha256 != action_proof.source_sha256:
                        raise SyntheticConsentConflict("source changed before commit")
                    self._raw_checkpoint("before_manifest_commit")
                    self._assert_raw_directory(root_fd, raw_fd)
                    conn.execute(
                        "INSERT INTO inbox_operations(operation_id,consent_id,action_key,inbox_id,subject,source_system,source_event_id,source_version,source_sha256,intent,consent_revision,raw_relative_path,raw_sha256,raw_bytes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (operation_id, consent_id, action_key, inbox_id, source.subject,
                         source.source_system, source.source_event_id,
                         source.source_record_version, source.original_text_sha256,
                         intent, expected_consent_revision, relative, digest, len(raw_bytes),
                         now_iso),
                    )
                    conn.execute(
                        "INSERT INTO inbox_raw_manifest(inbox_id,relative_path,sha256,byte_length,verified) VALUES(?,?,?,?,1)",
                        (inbox_id, relative, digest, len(raw_bytes)),
                    )
                    # Recheck after the SQL rows are staged and immediately before
                    # the transaction context commits. Any observed rename rolls
                    # back both rows; the Raw object remains untouched as an orphan.
                    self._raw_checkpoint("before_transaction_commit")
                    self._assert_raw_directory(root_fd, raw_fd)
                    return SyntheticAdmission(operation_id, inbox_id, consent_id,
                                              source.subject, source.source_system,
                                              source.source_event_id, source.source_record_version,
                                              digest, intent, expected_consent_revision,
                                              relative)

    @staticmethod
    def _proof_matches_request(action_proof):
        return (isinstance(action_proof.source_event_id, str)
                and isinstance(action_proof.subject, str)
                and isinstance(action_proof.source_version, str)
                and isinstance(action_proof.source_sha256, str)
                and isinstance(action_proof.intent, str)
                and isinstance(action_proof.action_key, str)
                and _KEY.fullmatch(action_proof.action_key) is not None
                and isinstance(action_proof.consent_id, str)
                and type(action_proof.expected_revision) is int
                and action_proof.expected_revision >= 1)

    def _check_raw_commit(self, root_fd, raw_fd):
        self._raw_checkpoint("database_commit")
        self._assert_raw_directory(root_fd, raw_fd)

    def get_by_event(self, *, subject, source_system, source_event_id):
        with self._pinned_raw_directory() as (root_fd, raw_fd):
            with self.ledger.transaction(
                    before_commit=lambda: self._assert_raw_directory(root_fd, raw_fd)) as conn:
                row = conn.execute(
                    "SELECT operation_id,inbox_id,consent_id,subject,source_system,source_event_id,source_version,source_sha256,intent,consent_revision,raw_relative_path "
                    "FROM inbox_operations WHERE subject=? AND source_system=? AND source_event_id=?",
                    (subject, source_system, source_event_id),
                ).fetchone()
                if not row:
                    return None
                raw = self._read_raw(root_fd, raw_fd, row[10])
                if hashlib.sha256(raw).hexdigest() != row[7]:
                    raise SyntheticConsentUnavailable("synthetic Raw manifest verification failed")
                return SyntheticAdmission(*row)
