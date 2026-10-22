"""Non-production D090 Authority/Writer candidate.

This module is deliberately not imported by create_app. It reuses the bounded
input primitives from the original Writer candidate, but does not use its
Core-peer listener or direct-to-final O_EXCL write path. Human proof is absent
in this repository, so real grants are unavailable; synthetic proof requires
an explicit test-only opt-in.
"""
from __future__ import annotations

import base64
import array
import hashlib
import json
import os
import re
import socket
import sqlite3
import stat
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .restricted_knowledge_writer import MAX_OUTPUT_BYTES, _SHA256, _TARGET, _write_all


MAX_FRAME_BYTES = 1_500_000
MAX_GRANT_TTL_SECONDS = 600
PROTOCOL = "d090.writer-grant.v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_GRANT_KEYS = {
    "protocol", "key_id", "approval_id", "operation_id", "source_revision",
    "source_sha256", "content_sha256", "content_length", "target_id",
    "create_only", "expires_at", "nonce", "audience",
}


class D090Rejected(Exception):
    """A request failed closed without publishing a target."""


class D090RecoveryRequired(D090Rejected):
    """A previous publish has an ambiguous cross-store outcome."""


class HumanProofUnavailable(D090Rejected):
    """No trusted proof binds a human approval to this exact operation."""


@dataclass(frozen=True)
class D090RoleIds:
    """Configured numeric role identities; configuration is not OS evidence."""

    core_uid: int
    authority_uid: int
    writer_uid: int
    core_gid: int
    authority_gid: int
    writer_gid: int

    def validate(self) -> None:
        values = (self.core_uid, self.authority_uid, self.writer_uid,
                  self.core_gid, self.authority_gid, self.writer_gid)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise D090Rejected("role_identity_invalid")
        if len({self.core_uid, self.authority_uid, self.writer_uid}) != 3:
            raise D090Rejected("role_uid_not_separated")
        if len({self.core_gid, self.authority_gid, self.writer_gid}) != 3:
            raise D090Rejected("role_gid_not_separated")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise D090Rejected("ipc_duplicate_json_key")
        result[key] = value
    return result


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _check_root(path: str) -> str:
    absolute = os.path.abspath(path)
    info = os.stat(absolute, follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise D090Rejected("authority_root_unsafe")
    return absolute


def _assert_process_identity(expected_uid: int, expected_gid: int, allow_synthetic: bool) -> None:
    if allow_synthetic:
        return
    if os.geteuid() != expected_uid or os.getegid() != expected_gid:
        raise D090Rejected("process_identity_mismatch")


@dataclass(frozen=True)
class Ed25519GrantSigner:
    key_id: str
    private_key: Ed25519PrivateKey

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self.private_key.public_key()

    def sign(self, grant: Mapping[str, object]) -> str:
        if not _valid_id(self.key_id):
            raise ValueError("invalid_key_id")
        return base64.b64encode(self.private_key.sign(_canonical(grant))).decode("ascii")


class D090Authority:
    """Persistent single-use grant ledger with commit/revoke serialization.

    `proof_verifier` must validate a real trusted approval proof. No such source
    is implemented yet. A test-only verifier is accepted only when the caller
    separately enables `allow_synthetic_proof`; this module is not production
    wired and the flag is not read from an HTTP request or environment variable.
    """

    def __init__(
        self,
        ledger_root: str,
        signer: Ed25519GrantSigner,
        writer_publish: Callable[[dict, bytes], dict],
        *,
        role_ids: D090RoleIds,
        synthetic_proof_verifier: object | None = None,
        allow_synthetic_proof: bool = False,
        allow_synthetic_identities: bool = False,
    ):
        role_ids.validate()
        _assert_process_identity(role_ids.authority_uid, role_ids.authority_gid, allow_synthetic_identities)
        self.root = _check_root(ledger_root)
        self.db_path = os.path.join(self.root, "authority.sqlite3")
        self.signer = signer
        self.writer_publish = writer_publish
        self.role_ids = role_ids
        if synthetic_proof_verifier is not None and getattr(synthetic_proof_verifier, "test_only", False) is not True:
            raise HumanProofUnavailable("non_test_proof_provider_not_implemented")
        self.synthetic_proof_verifier = synthetic_proof_verifier
        self.allow_synthetic_proof = allow_synthetic_proof
        self.allow_synthetic_identities = allow_synthetic_identities
        self._lock = threading.RLock()
        self._init_db()

    def _validate_db_file(self) -> None:
        try:
            info = os.stat(self.db_path, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise D090Rejected("authority_ledger_missing") from exc
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077 or stat.S_IMODE(info.st_mode) & 0o600 != 0o600):
            raise D090Rejected("authority_ledger_unsafe")

    def _connect(self):
        self._validate_db_file()
        db = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA journal_mode=DELETE")
        return db

    def _init_db(self):
        try:
            fd = os.open(self.db_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            self._validate_db_file()
        else:
            try:
                os.fsync(fd)
                dfd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            finally:
                os.close(fd)
            self._validate_db_file()
        db = self._connect()
        try:
            db.execute("CREATE TABLE IF NOT EXISTS grants (operation_id TEXT PRIMARY KEY, grant_json BLOB NOT NULL, signature TEXT NOT NULL, state TEXT NOT NULL, receipt_json BLOB)")
        finally:
            db.close()

    def _begin(self):
        db = self._connect()
        db.execute("BEGIN IMMEDIATE")
        return db

    def issue_grant(
        self,
        *,
        proof: object,
        approval_id: str,
        operation_id: str,
        source_revision: str,
        source_sha256: str,
        approved_bytes: bytes,
        target_id: str,
        expires_at: int,
        nonce: str,
    ) -> dict:
        if self.synthetic_proof_verifier is None or not self.allow_synthetic_proof:
            raise HumanProofUnavailable("trusted_human_proof_unavailable")
        if (not isinstance(approved_bytes, bytes) or not approved_bytes
                or len(approved_bytes) > MAX_OUTPUT_BYTES):
            raise D090Rejected("invalid_approval_binding")
        proof_binding = {
            "approval_id": approval_id,
            "operation_id": operation_id,
            "source_revision": source_revision,
            "source_sha256": source_sha256,
            "target_id": target_id,
            "content_sha256": hashlib.sha256(approved_bytes).hexdigest(),
            "content_length": len(approved_bytes),
        }
        try:
            proof_valid = self.synthetic_proof_verifier.verify(proof, proof_binding)
        except Exception as exc:
            raise HumanProofUnavailable("trusted_human_proof_rejected") from exc
        if not proof_valid:
            raise HumanProofUnavailable("trusted_human_proof_rejected")
        if (not all(_valid_id(v) for v in (approval_id, operation_id, source_revision, target_id, nonce))
                or not isinstance(source_sha256, str) or not _SHA256.fullmatch(source_sha256)):
            raise D090Rejected("invalid_approval_binding")
        try:
            approved_bytes.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise D090Rejected("approved_bytes_not_utf8") from exc
        now = int(time.time())
        if isinstance(expires_at, bool) or not isinstance(expires_at, int) or expires_at <= now or expires_at - now > MAX_GRANT_TTL_SECONDS:
            raise D090Rejected("grant_expired_or_unbounded")
        grant = {
            "protocol": PROTOCOL, "key_id": self.signer.key_id,
            "approval_id": approval_id, "operation_id": operation_id,
            "source_revision": source_revision, "source_sha256": source_sha256,
            "content_sha256": hashlib.sha256(approved_bytes).hexdigest(),
            "content_length": len(approved_bytes), "target_id": target_id,
            "create_only": True, "expires_at": expires_at, "nonce": nonce,
            "audience": "secondbrain-knowledge-writer",
        }
        signature = self.signer.sign(grant)
        encoded = _canonical(grant)
        with self._lock:
            db = self._begin()
            try:
                previous = db.execute("SELECT grant_json, signature FROM grants WHERE operation_id=?", (operation_id,)).fetchone()
                if previous:
                    if previous == (encoded, signature):
                        db.execute("COMMIT")
                        return {**grant, "signature": signature}
                    raise D090Rejected("operation_binding_conflict")
                db.execute("INSERT INTO grants(operation_id, grant_json, signature, state) VALUES(?,?,?,'issued')", (operation_id, encoded, signature))
                db.execute("COMMIT")
                return {**grant, "signature": signature}
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            finally:
                db.close()

    def revoke(self, operation_id: str) -> str:
        with self._lock:
            db = self._begin()
            try:
                row = db.execute("SELECT state FROM grants WHERE operation_id=?", (operation_id,)).fetchone()
                if row is None:
                    raise D090Rejected("operation_unknown")
                if row[0] == "issued":
                    db.execute("UPDATE grants SET state='revoked' WHERE operation_id=?", (operation_id,))
                    db.execute("COMMIT")
                    return "revoked"
                if row[0] == "revoked":
                    db.execute("COMMIT")
                    return "revoked"
                if row[0] in ("committing", "recovery_required"):
                    db.execute("COMMIT")
                    return "in_progress"
                db.execute("COMMIT")
                return "committed"
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            finally:
                db.close()

    def commit(self, grant_with_signature: dict, approved_bytes: bytes) -> dict:
        operation_id = grant_with_signature.get("operation_id") if isinstance(grant_with_signature, dict) else None
        if not _valid_id(operation_id):
            raise D090Rejected("invalid_grant")
        signature = grant_with_signature.get("signature")
        grant = {key: value for key, value in grant_with_signature.items() if key != "signature"}
        if set(grant) != _GRANT_KEYS:
            raise D090Rejected("invalid_grant")
        try:
            self.signer.public_key.verify(base64.b64decode(signature, validate=True), _canonical(grant))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise D090Rejected("grant_signature_invalid") from exc
        digest = hashlib.sha256(approved_bytes).hexdigest() if isinstance(approved_bytes, bytes) else ""
        expiry = grant.get("expires_at")
        if (grant.get("protocol") != PROTOCOL or grant.get("key_id") != self.signer.key_id
                or grant.get("audience") != "secondbrain-knowledge-writer"
                or grant.get("create_only") is not True or isinstance(expiry, bool)
                or not isinstance(expiry, int) or expiry <= int(time.time())
                or grant.get("content_sha256") != digest or grant.get("content_length") != len(approved_bytes)):
            raise D090Rejected("grant_binding_mismatch")
        with self._lock:
            db = self._begin()
            try:
                row = db.execute("SELECT grant_json, signature, state, receipt_json FROM grants WHERE operation_id=?", (operation_id,)).fetchone()
                if row is None or row[0] != _canonical(grant) or row[1] != signature:
                    raise D090Rejected("grant_not_authoritative")
                if row[2] == "committed":
                    db.execute("COMMIT")
                    return json.loads(row[3])
                if row[2] == "revoked":
                    raise D090Rejected("grant_revoked")
                if row[2] != "issued":
                    raise D090RecoveryRequired("operation_recovery_required")
                # Persist an in-flight fence before the Writer can publish.
                db.execute("UPDATE grants SET state='committing' WHERE operation_id=?", (operation_id,))
                db.execute("COMMIT")
                db.close()
                db = self._begin()
                row = db.execute("SELECT state FROM grants WHERE operation_id=?", (operation_id,)).fetchone()
                if row is None or row[0] != "committing":
                    raise D090RecoveryRequired("operation_recovery_required")
                try:
                    receipt = self.writer_publish(grant_with_signature, approved_bytes)
                    if not isinstance(receipt, dict) or receipt.get("operation_id") != operation_id or receipt.get("content_sha256") != digest:
                        raise D090RecoveryRequired("writer_receipt_unverified")
                except Exception as exc:
                    db.execute("UPDATE grants SET state='recovery_required' WHERE operation_id=?", (operation_id,))
                    db.execute("COMMIT")
                    raise D090RecoveryRequired("writer_outcome_uncertain") from exc
                encoded_receipt = _canonical(receipt)
                db.execute("UPDATE grants SET state='committed', receipt_json=? WHERE operation_id=?", (encoded_receipt, operation_id))
                db.execute("COMMIT")
                return receipt
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            finally:
                db.close()


class StrictCreateOnlyWriter:
    """Writer candidate; publishes complete files with O_TMPFILE + no-replace link.

    It fails closed if Linux/proc-fd/O_TMPFILE are unavailable. A passing unit
    test cannot establish Landlock, seccomp, UID separation, or protection from
    a compromised same-UID Writer; those remain A's isolated Linux gate.
    """

    def __init__(self, target_root: str, public_key: Ed25519PublicKey, key_id: str,
                 target_map: Mapping[str, str], role_ids: D090RoleIds,
                 *, allow_synthetic_identities: bool = False):
        role_ids.validate()
        _assert_process_identity(role_ids.writer_uid, role_ids.writer_gid, allow_synthetic_identities)
        self.root = _check_root(target_root)
        self.root_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        self.public_key = public_key
        self.key_id = key_id
        self.target_map = dict(target_map)
        self.role_ids = role_ids

    def close(self):
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None

    def publish(self, grant_with_signature: dict, content: bytes) -> dict:
        grant = {key: value for key, value in grant_with_signature.items() if key != "signature"}
        signature_text = grant_with_signature.get("signature")
        try:
            self.public_key.verify(base64.b64decode(signature_text, validate=True), _canonical(grant))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise D090Rejected("grant_signature_invalid") from exc
        if set(grant) != _GRANT_KEYS or grant.get("protocol") != PROTOCOL or grant.get("key_id") != self.key_id:
            raise D090Rejected("invalid_grant")
        filename = self.target_map.get(grant.get("target_id"))
        digest = hashlib.sha256(content).hexdigest()
        expiry = grant.get("expires_at")
        if (not isinstance(filename, str) or not _TARGET.fullmatch(filename)
                or grant.get("audience") != "secondbrain-knowledge-writer"
                or grant.get("create_only") is not True or isinstance(expiry, bool)
                or not isinstance(expiry, int) or expiry <= int(time.time())
                or grant.get("content_sha256") != digest or grant.get("content_length") != len(content)
                or len(content) > MAX_OUTPUT_BYTES):
            raise D090Rejected("grant_binding_mismatch")
        try:
            content.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise D090Rejected("content_not_utf8") from exc
        tmpfile = getattr(os, "O_TMPFILE", None)
        if tmpfile is None or not os.path.isdir("/proc/self/fd"):
            raise D090Rejected("strict_create_only_primitive_unavailable")
        fd = -1
        publish_attempted = False
        try:
            fd = os.open(".", os.O_WRONLY | tmpfile | getattr(os, "O_CLOEXEC", 0), 0o640, dir_fd=self.root_fd)
            _write_all(fd, content)
            os.fsync(fd)
            # link() is an atomic no-replace operation: EEXIST leaves old bytes untouched.
            publish_attempted = True
            os.link(f"/proc/self/fd/{fd}", filename, dst_dir_fd=self.root_fd, follow_symlinks=True)
            to_close, fd = fd, -1
            os.close(to_close)
            os.fsync(self.root_fd)
        except FileExistsError as exc:
            raise D090Rejected("target_exists") from exc
        except OSError as exc:
            if publish_attempted:
                raise D090RecoveryRequired("publish_outcome_uncertain") from exc
            raise D090Rejected("strict_create_only_primitive_unavailable") from exc
        finally:
            if fd >= 0:
                os.close(fd)
        return {"operation_id": grant["operation_id"], "content_sha256": digest, "status": "published"}

    def handle_connection(self, conn: socket.socket, expected_authority_uid: int,
                          expected_authority_gid: int) -> None:
        """Handle one socket request after checking peer credentials, before body IO."""
        authority_peer_before_body(conn, expected_authority_uid, expected_authority_gid)
        request = receive_bounded_json_without_fds(conn)
        if set(request) != {"grant", "content_base64"} or not isinstance(request.get("grant"), dict):
            raise D090Rejected("ipc_invalid_request")
        encoded = request.get("content_base64")
        if not isinstance(encoded, str) or len(encoded) > ((MAX_OUTPUT_BYTES + 2) // 3) * 4:
            raise D090Rejected("ipc_content_invalid")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise D090Rejected("ipc_content_invalid") from exc
        receipt = self.publish(request["grant"], content)
        conn.sendall(_canonical(receipt) + b"\n")


def authority_peer_before_body(conn: socket.socket, expected_uid: int, expected_gid: int) -> None:
    """Check kernel peer UID/GID before the caller reads any request bytes."""
    if not hasattr(socket, "SO_PEERCRED"):
        raise D090Rejected("peer_credentials_unavailable")
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, gid = struct.unpack("3i", raw)
    except (OSError, struct.error) as exc:
        raise D090Rejected("peer_credentials_unavailable") from exc
    if uid != expected_uid or gid != expected_gid:
        raise D090Rejected("authority_peer_rejected")


class UnixWriterClient:
    """Authority-side bounded client for a pre-provisioned pathname socket."""

    def __init__(self, socket_path: str, *, timeout_seconds: float = 2.0):
        if not isinstance(socket_path, str) or not os.path.isabs(socket_path) or len(socket_path.encode()) >= 104:
            raise ValueError("invalid_writer_socket_path")
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    def __call__(self, grant: dict, content: bytes) -> dict:
        request = _canonical({
            "grant": grant,
            "content_base64": base64.b64encode(content).decode("ascii"),
        }) + b"\n"
        if len(request) > MAX_FRAME_BYTES:
            raise D090Rejected("ipc_request_too_large")
        flags = getattr(socket, "SOCK_CLOEXEC", 0)
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | flags)
        conn.set_inheritable(False)
        conn.settimeout(self.timeout_seconds)
        try:
            conn.connect(self.socket_path)
            conn.sendall(request)
            response = bytearray()
            while len(response) <= 4096:
                part = conn.recv(min(1024, 4097 - len(response)))
                if not part:
                    break
                response.extend(part)
                if b"\n" in part:
                    frame, trailing = bytes(response).split(b"\n", 1)
                    if trailing or len(frame) > 4096:
                        raise D090Rejected("ipc_response_invalid")
                    result = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_object)
                    if (not isinstance(result, dict) or set(result) != {"operation_id", "content_sha256", "status"}
                            or result.get("status") != "published"):
                        raise D090Rejected("ipc_response_invalid")
                    return result
            raise D090RecoveryRequired("writer_response_missing")
        finally:
            conn.close()


def receive_bounded_json_without_fds(conn: socket.socket, limit: int = MAX_FRAME_BYTES) -> dict:
    """Read one JSONL frame, rejecting ancillary descriptors and oversize input."""
    data = bytearray()
    while len(data) <= limit:
        chunk, ancillary, flags, _addr = conn.recvmsg(min(4096, limit + 1 - len(data)), socket.CMSG_SPACE(4 * struct.calcsize("i")))
        if flags & getattr(socket, "MSG_CTRUNC", 0) or ancillary:
            for level, kind, payload in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    usable = len(payload) - (len(payload) % struct.calcsize("i"))
                    descriptors = array.array("i")
                    descriptors.frombytes(payload[:usable])
                    for descriptor in descriptors:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
            raise D090Rejected("ipc_ancillary_data_rejected")
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            frame, trailing = bytes(data).split(b"\n", 1)
            if trailing:
                raise D090Rejected("ipc_multiple_frames_rejected")
            if len(frame) > limit:
                raise D090Rejected("ipc_frame_oversize")
            try:
                value = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_object)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise D090Rejected("ipc_invalid_json") from exc
            if not isinstance(value, dict):
                raise D090Rejected("ipc_invalid_request")
            return value
    raise D090Rejected("ipc_frame_incomplete_or_oversize")
