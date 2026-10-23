import hashlib
import os
import socket
import struct
import threading
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from secondbrain_core.modules import d090_authority_writer as d090


CONTENT = "# Synthetic approved note\n".encode()
SOURCE_SHA = hashlib.sha256(b"synthetic source").hexdigest()


class SyntheticProof:
    test_only = True

    def verify(self, _proof, binding):
        return _proof == binding


def authority(tmp_path, publish, *, proof=True, allow_synthetic=True):
    root = tmp_path / "authority"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    signer = d090.Ed25519GrantSigner("test-key-1", Ed25519PrivateKey.generate())
    verifier = SyntheticProof() if proof else None
    core = d090.D090Authority(
        str(root), signer, publish,
        role_ids=d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
        synthetic_proof_verifier=verifier,
        allow_synthetic_proof=allow_synthetic,
        allow_synthetic_identities=True,
    )
    return core, signer


def issue(core, content=CONTENT, operation="operation-1", expires_at=None):
    expires_at = expires_at or int(time.time()) + 120
    proof = {
        "approval_id": "approval-1", "operation_id": operation, "source_revision": "rev-7",
        "source_sha256": SOURCE_SHA, "target_id": "target-1",
        "content_sha256": hashlib.sha256(content).hexdigest(), "content_length": len(content),
    }
    return core.issue_grant(
        proof=proof, approval_id="approval-1", operation_id=operation,
        source_revision="rev-7", source_sha256=SOURCE_SHA, approved_bytes=content,
        target_id="target-1", expires_at=expires_at, nonce="nonce-1",
    )


def test_missing_real_human_proof_fails_closed_without_issuing_a_grant(tmp_path):
    core, _ = authority(tmp_path, lambda *_: pytest.fail("Writer must not be called"), proof=False)
    with pytest.raises(d090.HumanProofUnavailable):
        issue(core)
    db = core._connect()
    try:
        assert db.execute("SELECT count(*) FROM grants").fetchone()[0] == 0
    finally:
        db.close()


def test_three_role_identity_configuration_must_be_distinct():
    with pytest.raises(d090.D090Rejected, match="role_uid_not_separated"):
        d090.D090RoleIds(1, 1, 3, 10, 11, 12).validate()
    with pytest.raises(d090.D090Rejected, match="role_gid_not_separated"):
        d090.D090RoleIds(1, 2, 3, 10, 10, 12).validate()


def test_authority_ledger_symlink_is_rejected_without_changing_target_permissions(tmp_path):
    root = tmp_path / "authority"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    outside = tmp_path / "preserve.txt"
    outside.write_text("synthetic", encoding="utf-8")
    outside.chmod(0o644)
    (root / "authority.sqlite3").symlink_to(outside)
    signer = d090.Ed25519GrantSigner("test-key-1", Ed25519PrivateKey.generate())
    with pytest.raises(d090.D090Rejected, match="authority_ledger_unsafe"):
        d090.D090Authority(
            str(root), signer, lambda *_: {},
            role_ids=d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
            allow_synthetic_identities=True,
        )
    assert outside.stat().st_mode & 0o777 == 0o644


def test_test_only_proof_needs_explicit_opt_in(tmp_path):
    core, _ = authority(tmp_path, lambda *_: pytest.fail("Writer must not be called"), allow_synthetic=False)
    with pytest.raises(d090.HumanProofUnavailable):
        issue(core)


def test_non_test_proof_provider_is_not_accepted_before_real_verifier_exists(tmp_path):
    root = tmp_path / "authority"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    signer = d090.Ed25519GrantSigner("test-key-1", Ed25519PrivateKey.generate())
    with pytest.raises(d090.HumanProofUnavailable, match="non_test_proof_provider_not_implemented"):
        d090.D090Authority(
            str(root), signer, lambda *_: {},
            role_ids=d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
            synthetic_proof_verifier=lambda *_: True,
            allow_synthetic_proof=True,
            allow_synthetic_identities=True,
        )


def test_signed_grant_binds_source_content_target_expiry_and_exact_replay(tmp_path):
    calls = []

    def publish(grant, content):
        calls.append((grant["operation_id"], content))
        return {"operation_id": grant["operation_id"], "content_sha256": hashlib.sha256(content).hexdigest(), "status": "published"}

    core, _ = authority(tmp_path, publish)
    grant = issue(core)
    assert issue(core, expires_at=grant["expires_at"]) == grant
    assert core.commit(grant, CONTENT)["status"] == "published"
    assert core.commit(grant, CONTENT)["status"] == "published"
    assert calls == [("operation-1", CONTENT)]
    with pytest.raises(d090.D090Rejected, match="grant_binding_mismatch"):
        core.commit(grant, b"changed")
    tampered = dict(grant, target_id="other-target")
    with pytest.raises(d090.D090Rejected, match="grant_signature_invalid"):
        core.commit(tampered, CONTENT)


def test_revocation_before_commit_prevents_writer_call(tmp_path):
    calls = []
    core, _ = authority(tmp_path, lambda *_: calls.append("called"))
    grant = issue(core)
    assert core.revoke("operation-1") == "revoked"
    with pytest.raises(d090.D090Rejected, match="grant_revoked"):
        core.commit(grant, CONTENT)
    assert calls == []


def test_commit_and_revoke_share_sqlite_serialization_domain(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def publish(grant, content):
        entered.set()
        assert release.wait(3)
        return {"operation_id": grant["operation_id"], "content_sha256": hashlib.sha256(content).hexdigest(), "status": "published"}

    first, signer = authority(tmp_path, publish)
    grant = issue(first)
    second = d090.D090Authority(str(tmp_path / "authority"), signer, publish,
                                role_ids=d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
                                allow_synthetic_identities=True)
    result = []
    commit_thread = threading.Thread(target=lambda: result.append(first.commit(grant, CONTENT)))
    commit_thread.start()
    assert entered.wait(3)
    revoke_result = []
    revoke_thread = threading.Thread(target=lambda: revoke_result.append(second.revoke("operation-1")))
    revoke_thread.start()
    time.sleep(0.05)
    assert revoke_thread.is_alive()
    release.set()
    commit_thread.join(3)
    revoke_thread.join(3)
    assert not commit_thread.is_alive() and not revoke_thread.is_alive()
    assert result[0]["status"] == "published"
    assert revoke_result == ["committed"]


def test_uncertain_writer_result_is_durable_and_never_retried(tmp_path):
    calls = []

    def fail(grant, _content):
        calls.append(grant["operation_id"])
        raise TimeoutError("synthetic timeout")

    core, signer = authority(tmp_path, fail)
    grant = issue(core)
    with pytest.raises(d090.D090RecoveryRequired, match="writer_outcome_uncertain"):
        core.commit(grant, CONTENT)
    reopened = d090.D090Authority(str(tmp_path / "authority"), signer, fail,
                                  role_ids=d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
                                  allow_synthetic_identities=True)
    with pytest.raises(d090.D090RecoveryRequired, match="operation_recovery_required"):
        reopened.commit(grant, CONTENT)
    assert reopened.revoke("operation-1") == "in_progress"
    assert calls == ["operation-1"]


def test_peer_mismatch_is_rejected_before_reading_request_body(monkeypatch):
    monkeypatch.setattr(d090.socket, "SO_PEERCRED", 123, raising=False)

    class Connection:
        body_read = False

        def getsockopt(self, *_args):
            return struct.pack("3i", 1, 501, 20)

        def recvmsg(self, *_args):
            self.body_read = True
            raise AssertionError("body read before peer rejection")

    conn = Connection()
    with pytest.raises(d090.D090Rejected, match="authority_peer_rejected"):
        d090.authority_peer_before_body(conn, 502, 20)
    assert not conn.body_read


def test_wrong_gid_is_rejected_before_reading_request_body(monkeypatch):
    monkeypatch.setattr(d090.socket, "SO_PEERCRED", 123, raising=False)

    class Connection:
        body_read = False

        def getsockopt(self, *_args):
            return struct.pack("3i", 1, 501, 21)

        def recvmsg(self, *_args):
            self.body_read = True
            raise AssertionError("body read before peer rejection")

    conn = Connection()
    with pytest.raises(d090.D090Rejected, match="authority_peer_rejected"):
        d090.authority_peer_before_body(conn, 501, 20)
    assert not conn.body_read


def test_writer_binds_peer_to_configured_authority_before_body_and_cannot_be_overridden(
        tmp_path, monkeypatch):
    monkeypatch.setattr(d090.socket, "SO_PEERCRED", 123, raising=False)
    root = tmp_path / "knowledge"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    signer = d090.Ed25519GrantSigner("test-key-1", Ed25519PrivateKey.generate())
    role_ids = d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103)
    writer = d090.StrictCreateOnlyWriter(
        str(root), signer.public_key, signer.key_id, {"target-1": "approved.md"},
        role_ids, allow_synthetic_identities=True,
    )

    class Connection:
        body_read = False

        def getsockopt(self, *_args):
            # Synthetic non-Authority peer; SO_PEERCRED is mocked, not OS proof.
            return struct.pack("3i", 1, 3999, 3999)

        def recvmsg(self, *_args):
            self.body_read = True
            raise AssertionError("Writer read request body from non-Authority peer")

    conn = Connection()
    try:
        with pytest.raises(d090.D090Rejected, match="authority_peer_rejected"):
            writer.handle_connection(conn)
        assert not conn.body_read

        # There is no per-call UID/GID override in the handler API.
        with pytest.raises(TypeError):
            writer.handle_connection(conn, 3999, 3999)
        assert not conn.body_read
    finally:
        writer.close()


def test_ipc_ancillary_file_descriptors_are_rejected():
    read_fd, write_fd = os.pipe()
    passed_fd = os.dup(write_fd)

    class Connection:
        done = False

        def recvmsg(self, *_args):
            if self.done:
                return b"", [], 0, None
            self.done = True
            return b"{}\n", [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack("i", passed_fd))], 0, None

    try:
        with pytest.raises(d090.D090Rejected, match="ipc_ancillary_data_rejected"):
            d090.receive_bounded_json_without_fds(Connection())
        with pytest.raises(OSError):
            os.fstat(passed_fd)
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_strict_writer_fails_closed_without_otmpfile_instead_of_fallback(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    signer = d090.Ed25519GrantSigner("test-key-1", Ed25519PrivateKey.generate())
    grant = {
        "protocol": d090.PROTOCOL, "key_id": signer.key_id, "approval_id": "approval-1",
        "operation_id": "operation-1", "source_revision": "rev-7", "source_sha256": SOURCE_SHA,
        "content_sha256": hashlib.sha256(CONTENT).hexdigest(), "content_length": len(CONTENT),
        "target_id": "target-1", "create_only": True, "expires_at": int(time.time()) + 120,
        "nonce": "nonce-1", "audience": "secondbrain-knowledge-writer",
    }
    signed = {**grant, "signature": signer.sign(grant)}
    writer = d090.StrictCreateOnlyWriter(
        str(root), signer.public_key, signer.key_id, {"target-1": "approved.md"},
        d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103), allow_synthetic_identities=True,
    )
    monkeypatch.delattr(d090.os, "O_TMPFILE", raising=False)
    try:
        with pytest.raises(d090.D090Rejected, match="strict_create_only_primitive_unavailable"):
            writer.publish(signed, CONTENT)
        assert list(root.iterdir()) == []
    finally:
        writer.close()


@pytest.mark.skipif(not hasattr(os, "O_TMPFILE") or not os.path.isdir("/proc/self/fd"),
                    reason="requires Linux O_TMPFILE and proc-fd link support")
def test_linux_writer_publishes_exactly_once_without_overwriting_existing_file(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    signer = d090.Ed25519GrantSigner("test-key-1", Ed25519PrivateKey.generate())
    roles = d090.D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103)
    writer = d090.StrictCreateOnlyWriter(
        str(root), signer.public_key, signer.key_id,
        {"target-1": "approved.md", "target-2": "existing.md"}, roles,
        allow_synthetic_identities=True,
    )

    def signed(operation_id, target_id):
        grant = {
            "protocol": d090.PROTOCOL, "key_id": signer.key_id, "approval_id": "approval-1",
            "operation_id": operation_id, "source_revision": "rev-7", "source_sha256": SOURCE_SHA,
            "content_sha256": hashlib.sha256(CONTENT).hexdigest(), "content_length": len(CONTENT),
            "target_id": target_id, "create_only": True, "expires_at": int(time.time()) + 120,
            "nonce": operation_id, "audience": "secondbrain-knowledge-writer",
        }
        return {**grant, "signature": signer.sign(grant)}

    try:
        first = signed("operation-1", "target-1")
        assert writer.publish(first, CONTENT)["status"] == "published"
        assert (root / "approved.md").read_bytes() == CONTENT
        with pytest.raises(d090.D090Rejected, match="target_exists"):
            writer.publish(first, CONTENT)
        existing = root / "existing.md"
        existing.write_bytes(b"preserve old bytes")
        with pytest.raises(d090.D090Rejected, match="target_exists"):
            writer.publish(signed("operation-2", "target-2"), CONTENT)
        assert existing.read_bytes() == b"preserve old bytes"
    finally:
        writer.close()


def test_frame_rejects_duplicate_json_keys():
    class Connection:
        done = False

        def recvmsg(self, _size, _ancillary_size):
            if self.done:
                return b"", [], 0, None
            self.done = True
            return b'{"grant":{},"grant":{}}\n', [], 0, None

    # JSON duplicate keys are rejected by validating the raw object-pairs hook.
    conn = Connection()
    with pytest.raises(d090.D090Rejected):
        d090.receive_bounded_json_without_fds(conn)


def test_frame_rejects_oversize_even_when_newline_is_in_same_read():
    class Connection:
        done = False

        def recvmsg(self, _size, _ancillary_size):
            if self.done:
                return b"", [], 0, None
            self.done = True
            return b"x" * 32 + b"\n", [], 0, None

    with pytest.raises(d090.D090Rejected, match="ipc_frame_oversize"):
        d090.receive_bounded_json_without_fds(Connection(), limit=16)
