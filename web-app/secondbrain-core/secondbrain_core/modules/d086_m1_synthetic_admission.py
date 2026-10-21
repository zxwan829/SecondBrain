"""Synthetic-only S3 CAS model; it never wires into the real Inbox route.

SQLite owns consent revisions, admission operations and Raw manifests in one
transaction domain. Raw bytes are fsynced before SQLite commit. A crash between
the Raw fsync and DB commit may leave an orphan; this module intentionally does
not repair or delete it. The filesystem and SQLite are not claimed to be one
atomic transaction.
"""
from dataclasses import dataclass
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
        try:
            self.raw_root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw root unavailable") from exc
        try:
            st = self.raw_root.lstat()
            if (not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)
                    or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o700
                    or self.raw_root.resolve(strict=True) != self.raw_root):
                raise SyntheticConsentUnavailable("synthetic Raw root is unsafe")
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw root unavailable") from exc

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

    def _raw_path(self, relative):
        if (not isinstance(relative, str) or not relative.startswith("Raw/")
                or not _KEY.fullmatch(relative[4:])):
            raise SyntheticConsentUnavailable("synthetic Raw reference is invalid")
        path = self.ledger.root / relative
        try:
            st = path.lstat()
            if (not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)
                    or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600
                    or st.st_nlink != 1):
                raise SyntheticConsentUnavailable("synthetic Raw object is unsafe")
            return path
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw object unavailable") from exc

    def _stage_raw(self, *, inbox_id, raw_bytes, digest):
        relative = f"{inbox_id}.raw"
        path = self.raw_root / relative
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            dir_fd = os.open(self.raw_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            verified = self._raw_path(f"Raw/{relative}")
            with verified.open("rb") as stream:
                current = stream.read(self.max_raw_bytes + 1)
            if len(current) != len(raw_bytes) or hashlib.sha256(current).hexdigest() != digest:
                raise SyntheticConsentUnavailable("synthetic Raw verification failed")
            return f"Raw/{relative}"
        except FileExistsError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw id collision") from exc
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic Raw durability check failed") from exc

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
            with self.ledger.transaction() as conn:
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
                    path = self._raw_path(prior[10])
                    with path.open("rb") as stream:
                        raw = stream.read(self.max_raw_bytes + 1)
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
                relative = self._stage_raw(inbox_id=inbox_id, raw_bytes=raw_bytes, digest=digest)

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

    def get_by_event(self, *, subject, source_system, source_event_id):
        with self.ledger.transaction() as conn:
            row = conn.execute(
                "SELECT operation_id,inbox_id,consent_id,subject,source_system,source_event_id,source_version,source_sha256,intent,consent_revision,raw_relative_path "
                "FROM inbox_operations WHERE subject=? AND source_system=? AND source_event_id=?",
                (subject, source_system, source_event_id),
            ).fetchone()
            if not row:
                return None
            path = self._raw_path(row[10])
            with path.open("rb") as stream:
                raw = stream.read(self.max_raw_bytes + 1)
            if hashlib.sha256(raw).hexdigest() != row[7]:
                raise SyntheticConsentUnavailable("synthetic Raw manifest verification failed")
            return SyntheticAdmission(*row)
