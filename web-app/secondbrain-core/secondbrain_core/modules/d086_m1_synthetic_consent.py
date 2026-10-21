"""Synthetic-only persistent consent candidate for D086-M1.

This module is intentionally not registered with create_app and is not an
identity provider. SyntheticActionProofAuthority models server-side Web action
checks for local tests only; its proof does not authenticate a real person or
browser. The SQLite ledger is limited to pre-existing private synthetic roots.
"""
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat


_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_EVENT = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SOURCE_SYSTEM = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_INTENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ALLOWED_ACTIONS = frozenset({"accept", "revoke", "expire"})


class SyntheticConsentError(RuntimeError):
    """Consent candidate failed closed."""


class SyntheticConsentConflict(SyntheticConsentError):
    """The exact source slot or action idempotency key conflicts."""


class SyntheticConsentUnavailable(SyntheticConsentError):
    """The synthetic local store is unsafe or its commit outcome is unknown."""


@dataclass(frozen=True)
class SyntheticActionProof:
    action: str
    subject: str
    source_system: str
    source_event_id: str
    source_version: str
    source_sha256: str
    intent: str
    action_key: str
    origin: str
    issued_at: str
    action_expires_at: str
    expires_at: str
    consent_id: str | None
    expected_revision: int | None
    signature: str


@dataclass(frozen=True)
class SyntheticConsent:
    consent_id: str
    subject: str
    source_system: str
    source_event_id: str
    source_version: str
    source_sha256: str
    intent: str
    state: str
    revision: int
    expires_at: str
    replayed: bool = False


class SyntheticActionProofAuthority:
    """Test-only HMAC issuer/verifier for an asserted server action boundary.

    The secret and issuer live only in synthetic tests. Calling this class is
    not equivalent to an authenticated Web session, human click, CSRF check,
    or Core permission decision.
    """

    def __init__(self, *, secret: bytes, allowed_origin: str):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("synthetic proof key must contain at least 32 bytes")
        if not isinstance(allowed_origin, str) or not allowed_origin.startswith("https://"):
            raise ValueError("synthetic origin must be an exact HTTPS origin")
        self._secret = secret
        self.allowed_origin = allowed_origin

    @staticmethod
    def _payload(proof: SyntheticActionProof) -> bytes:
        material = asdict(proof)
        material.pop("signature", None)
        return json.dumps(material, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")

    def issue_test_proof(self, *, action: str, subject: str, source_system: str,
                         source_event_id: str, source_version: str,
                         source_sha256: str, intent: str, action_key: str,
                         origin: str, issued_at: str, action_expires_at: str,
                         expires_at: str,
                         consent_id: str | None = None,
                         expected_revision: int | None = None) -> SyntheticActionProof:
        """Create a local test fixture proof; never call from a production route."""
        proof = SyntheticActionProof(
            action=action, subject=subject, source_system=source_system,
            source_event_id=source_event_id, source_version=source_version,
            source_sha256=source_sha256, intent=intent, action_key=action_key,
            origin=origin, issued_at=issued_at, action_expires_at=action_expires_at,
            expires_at=expires_at,
            consent_id=consent_id, expected_revision=expected_revision,
            signature="",
        )
        if not self.verify_fields(proof, allow_unsigned=True):
            raise ValueError("invalid synthetic action proof fields")
        mac = hmac.new(self._secret, self._payload(proof), hashlib.sha256).hexdigest()
        return SyntheticActionProof(**{**asdict(proof), "signature": mac})

    def verify_fields(self, proof: SyntheticActionProof, *, allow_unsigned=False) -> bool:
        if type(proof) is not SyntheticActionProof:
            return False
        if (proof.action not in _ALLOWED_ACTIONS or not isinstance(proof.subject, str)
                or not proof.subject or len(proof.subject) > 256
                or not isinstance(proof.source_system, str)
                or not _SOURCE_SYSTEM.fullmatch(proof.source_system)
                or not isinstance(proof.source_event_id, str)
                or not _EVENT.fullmatch(proof.source_event_id)
                or not isinstance(proof.source_version, str)
                or not re.fullmatch(r"[1-9][0-9]{0,63}", proof.source_version)
                or not isinstance(proof.source_sha256, str)
                or not _SHA256.fullmatch(proof.source_sha256)
                or not isinstance(proof.intent, str) or not _INTENT.fullmatch(proof.intent)
                or not isinstance(proof.action_key, str) or not _KEY.fullmatch(proof.action_key)
                or proof.origin != self.allowed_origin
                or not isinstance(proof.issued_at, str)
                or not isinstance(proof.action_expires_at, str)
                or not isinstance(proof.expires_at, str)):
            return False
        try:
            issued = datetime.fromisoformat(proof.issued_at.replace("Z", "+00:00"))
            action_expires = datetime.fromisoformat(proof.action_expires_at.replace("Z", "+00:00"))
            source_expires = datetime.fromisoformat(proof.expires_at.replace("Z", "+00:00"))
            if (issued.tzinfo is None or action_expires.tzinfo is None
                    or source_expires.tzinfo is None or action_expires <= issued
                    or (proof.action == "accept" and source_expires <= issued)):
                return False
        except (TypeError, ValueError, OverflowError):
            return False
        if proof.action == "accept":
            if proof.consent_id is not None or proof.expected_revision is not None:
                return False
        elif (not isinstance(proof.consent_id, str) or not proof.consent_id
              or len(proof.consent_id) > 128
              or type(proof.expected_revision) is not int or proof.expected_revision < 1):
            return False
        if allow_unsigned:
            return proof.signature == ""
        if not isinstance(proof.signature, str) or not re.fullmatch(r"[a-f0-9]{64}", proof.signature):
            return False
        expected = hmac.new(self._secret, self._payload(proof), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, proof.signature)


class SyntheticConsentLedger:
    """Append-only synthetic consent audit backed by one local SQLite DB.

    The root must already exist, be canonical, owned by the current UID, and
    have mode 0700. The DB is created exclusively with mode 0600. No chmod,
    directory creation, route registration, real-data access, or recovery write
    is performed. SQLite transaction/journal recovery is an engine property,
    not an application-level replay or repair action.
    """

    database_name = "d086-m1-consent.sqlite3"

    def __init__(self, root: str | os.PathLike, proof_authority: SyntheticActionProofAuthority,
                 *, clock=None, timeout_seconds: float = 5.0):
        raw = os.fspath(root)
        if not os.path.isabs(raw):
            raise SyntheticConsentUnavailable("synthetic root must be absolute")
        self.root = Path(raw)
        self.proof_authority = proof_authority
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.timeout_seconds = timeout_seconds
        self._validate_root()
        self.root_identity = self._root_identity()
        self.database_path = self.root / self.database_name
        self._ensure_database_file()
        self.database_identity = self._database_identity()
        self._initialize()

    def _validate_root(self):
        try:
            st = self.root.lstat()
            canonical = Path(os.path.realpath(self.root))
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic root unavailable") from exc
        if (canonical != self.root or not stat.S_ISDIR(st.st_mode)
                or stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o700):
            raise SyntheticConsentUnavailable("synthetic root must be canonical, owned, and mode 0700")

    def _root_identity(self):
        st = self.root.stat(follow_symlinks=False)
        return st.st_dev, st.st_ino

    def _ensure_database_file(self):
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.database_path, flags, 0o600)
        except FileExistsError:
            return
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic DB creation failed") from exc
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _database_identity(self):
        try:
            st = self.database_path.lstat()
        except OSError as exc:
            raise SyntheticConsentUnavailable("synthetic DB unavailable") from exc
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
            raise SyntheticConsentUnavailable("synthetic DB file is unsafe")
        return st.st_dev, st.st_ino

    def _check_paths(self):
        self._validate_root()
        if self._root_identity() != self.root_identity:
            raise SyntheticConsentUnavailable("synthetic root identity changed")
        if self._database_identity() != self.database_identity:
            raise SyntheticConsentUnavailable("synthetic DB identity changed")

    def _connect(self):
        self._check_paths()
        try:
            conn = sqlite3.connect(self.database_path, timeout=self.timeout_seconds,
                                   isolation_level=None)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={int(self.timeout_seconds * 1000)}")
            conn.execute("PRAGMA synchronous=FULL")
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if mode.lower() != "delete":
                conn.close()
                raise SyntheticConsentUnavailable("synthetic DB journal mode is not DELETE")
            self._check_paths()
            return conn
        except SyntheticConsentUnavailable:
            raise
        except sqlite3.Error as exc:
            raise SyntheticConsentUnavailable("synthetic DB unavailable") from exc

    @contextmanager
    def transaction(self):
        """Expose a single serialization domain for S3's synthetic CAS model."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            try:
                conn.commit()
            except sqlite3.Error as exc:
                raise SyntheticConsentUnavailable("synthetic commit outcome unknown") from exc
        except BaseException:
            if conn.in_transaction:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            raise
        finally:
            conn.close()

    def _initialize(self):
        conn = self._connect()
        try:
            if conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise SyntheticConsentUnavailable("synthetic DB journal mode is not DELETE")
            conn.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS consent_records (
                    consent_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('active','revoked','expired')),
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    accept_key TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(subject, source_system, source_event_id)
                );
                CREATE TABLE IF NOT EXISTS consent_audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    consent_id TEXT NOT NULL REFERENCES consent_records(consent_id),
                    action TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_hash TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(consent_id, action, action_key)
                );
                CREATE TRIGGER IF NOT EXISTS consent_audit_no_update
                BEFORE UPDATE ON consent_audit BEGIN
                    SELECT RAISE(ABORT, 'consent audit is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS consent_audit_no_delete
                BEFORE DELETE ON consent_audit BEGIN
                    SELECT RAISE(ABORT, 'consent audit is append-only');
                END;
                COMMIT;
            """)
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.rollback()
            raise SyntheticConsentUnavailable("synthetic consent schema unavailable") from exc
        finally:
            conn.close()

    @staticmethod
    def _now_iso(now: datetime) -> str:
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise SyntheticConsentUnavailable("synthetic clock must be timezone-aware")
        return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _payload_hash(proof: SyntheticActionProof) -> str:
        return hashlib.sha256(SyntheticActionProofAuthority._payload(proof)).hexdigest()

    def _append_audit(self, conn, *, consent_id: str, proof: SyntheticActionProof,
                      revision: int, now_iso: str):
        previous = conn.execute(
            "SELECT entry_hash FROM consent_audit WHERE consent_id=? ORDER BY seq DESC LIMIT 1",
            (consent_id,),
        ).fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        payload_hash = self._payload_hash(proof)
        entry_hash = hashlib.sha256(
            f"{previous_hash}:{consent_id}:{proof.action}:{proof.action_key}:{revision}:{payload_hash}:{now_iso}".encode()
        ).hexdigest()
        conn.execute(
            "INSERT INTO consent_audit(consent_id,action,action_key,revision,payload_hash,previous_hash,entry_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (consent_id, proof.action, proof.action_key, revision, payload_hash,
             previous_hash, entry_hash, now_iso),
        )

    def _verified(self, proof, expected_action):
        if not self.proof_authority.verify_fields(proof):
            raise SyntheticConsentUnavailable("synthetic action proof is invalid")
        if proof.action != expected_action:
            raise SyntheticConsentUnavailable("synthetic action type mismatch")
        try:
            now = self.clock()
            issued = datetime.fromisoformat(proof.issued_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(proof.action_expires_at.replace("Z", "+00:00"))
            if now.tzinfo is None or issued > now or now >= expires:
                raise SyntheticConsentUnavailable("synthetic action proof expired")
            return self._now_iso(now)
        except SyntheticConsentUnavailable:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise SyntheticConsentUnavailable("synthetic action proof time invalid") from exc

    def accept(self, proof: SyntheticActionProof) -> SyntheticConsent:
        now_iso = self._verified(proof, "accept")
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(proof.expires_at.replace("Z", "+00:00"))
        if expires <= now:
            raise SyntheticConsentConflict("source suggestion expired")
        consent_id = hashlib.sha256(
            f"{proof.subject}\0{proof.source_system}\0{proof.source_event_id}\0{proof.source_version}\0{proof.source_sha256}\0{proof.intent}\0{proof.action_key}".encode()
        ).hexdigest()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT consent_id,source_version,source_sha256,intent,state,revision,expires_at,accept_key "
                "FROM consent_records WHERE subject=? AND source_system=? AND source_event_id=?",
                (proof.subject, proof.source_system, proof.source_event_id),
            ).fetchone()
            if row:
                prior = conn.execute(
                    "SELECT payload_hash FROM consent_audit WHERE consent_id=? AND action='accept' AND action_key=?",
                    (row[0], proof.action_key),
                ).fetchone()
                if (row[0] != consent_id or row[1] != proof.source_version
                        or row[2] != proof.source_sha256 or row[3] != proof.intent
                        or row[7] != proof.action_key or not prior
                        or prior[0] != self._payload_hash(proof)):
                    raise SyntheticConsentConflict("source slot already has a different consent")
                return SyntheticConsent(row[0], proof.subject, proof.source_system,
                                        proof.source_event_id, row[1], row[2], row[3],
                                        row[4], row[5], row[6], replayed=True)
            conn.execute(
                "INSERT INTO consent_records(consent_id,subject,source_system,source_event_id,source_version,source_sha256,intent,state,revision,accept_key,expires_at,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (consent_id, proof.subject, proof.source_system, proof.source_event_id,
                 proof.source_version, proof.source_sha256, proof.intent, "active", 1,
                 proof.action_key, proof.expires_at, now_iso),
            )
            self._append_audit(conn, consent_id=consent_id, proof=proof,
                               revision=1, now_iso=now_iso)
            return SyntheticConsent(consent_id, proof.subject, proof.source_system,
                                    proof.source_event_id, proof.source_version,
                                    proof.source_sha256, proof.intent, "active", 1,
                                    proof.expires_at)

    def _transition(self, proof: SyntheticActionProof, action: str) -> SyntheticConsent:
        now_iso = self._verified(proof, action)
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT subject,source_system,source_event_id,source_version,source_sha256,intent,state,revision,expires_at "
                "FROM consent_records WHERE consent_id=?",
                (proof.consent_id,),
            ).fetchone()
            if not row:
                raise SyntheticConsentConflict("consent does not exist")
            exact = (row[0], row[1], row[2], row[3], row[4], row[5]) == (
                proof.subject, proof.source_system, proof.source_event_id,
                proof.source_version, proof.source_sha256, proof.intent,
            ) and row[8] == proof.expires_at
            if not exact:
                raise SyntheticConsentConflict("consent binding does not match")
            prior = conn.execute(
                "SELECT payload_hash,revision FROM consent_audit WHERE consent_id=? AND action=? AND action_key=?",
                (proof.consent_id, action, proof.action_key),
            ).fetchone()
            if prior:
                if prior[0] != self._payload_hash(proof):
                    raise SyntheticConsentConflict("action key reused with different consent data")
                current = conn.execute(
                    "SELECT state,revision,expires_at FROM consent_records WHERE consent_id=?",
                    (proof.consent_id,),
                ).fetchone()
                return SyntheticConsent(proof.consent_id, *row[:6], current[0],
                                        current[1], current[2], replayed=True)
            if row[6] != "active" or row[7] != proof.expected_revision:
                raise SyntheticConsentConflict("consent state or revision changed")
            if action == "expire":
                expiry = datetime.fromisoformat(row[8].replace("Z", "+00:00"))
                now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
                if now < expiry:
                    raise SyntheticConsentConflict("consent has not expired")
            new_revision = row[7] + 1
            new_state = "revoked" if action == "revoke" else "expired"
            conn.execute("UPDATE consent_records SET state=?,revision=? WHERE consent_id=?",
                         (new_state, new_revision, proof.consent_id))
            self._append_audit(conn, consent_id=proof.consent_id, proof=proof,
                               revision=new_revision, now_iso=now_iso)
            return SyntheticConsent(proof.consent_id, *row[:6], new_state,
                                    new_revision, row[8])

    def revoke(self, proof: SyntheticActionProof) -> SyntheticConsent:
        return self._transition(proof, "revoke")

    def expire(self, proof: SyntheticActionProof) -> SyntheticConsent:
        return self._transition(proof, "expire")

    def get(self, *, subject: str, source_system: str, source_event_id: str):
        self._verified_readable()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT consent_id,subject,source_system,source_event_id,source_version,source_sha256,intent,state,revision,expires_at "
                "FROM consent_records WHERE subject=? AND source_system=? AND source_event_id=?",
                (subject, source_system, source_event_id),
            ).fetchone()
            return SyntheticConsent(*row) if row else None
        except sqlite3.Error as exc:
            raise SyntheticConsentUnavailable("synthetic consent read failed") from exc
        finally:
            conn.close()

    def _verified_readable(self):
        self._check_paths()

    def verify_audit_chain(self, consent_id: str) -> bool:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT action,action_key,revision,payload_hash,previous_hash,entry_hash,created_at "
                "FROM consent_audit WHERE consent_id=? ORDER BY seq",
                (consent_id,),
            ).fetchall()
        finally:
            conn.close()
        previous = "0" * 64
        for action, action_key, revision, payload_hash, previous_hash, entry_hash, created_at in rows:
            expected = hashlib.sha256(
                f"{previous}:{consent_id}:{action}:{action_key}:{revision}:{payload_hash}:{created_at}".encode()
            ).hexdigest()
            if previous_hash != previous or entry_hash != expected:
                return False
            previous = entry_hash
        return bool(rows)
