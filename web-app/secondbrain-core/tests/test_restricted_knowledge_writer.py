import base64
import hashlib
import json
import os
import socket
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from secondbrain_core.modules.restricted_knowledge_writer import (
    RecoveryRequired,
    RestrictedWriterIPCClient,
    RestrictedKnowledgeWriter,
    WriterRejected,
    _peer_uid,
    serve_unix_socket,
)
from secondbrain_core.modules import restricted_knowledge_writer as writer_module


CORE_UID = 4242
OUTPUT = b"<!-- approved synthetic output -->\n# Synthetic\n"


def make_writer(tmp_path, **kwargs):
    knowledge = tmp_path / "knowledge"
    receipts = tmp_path / "receipts"
    knowledge.mkdir(mode=0o700)
    receipts.mkdir(mode=0o700)
    os.chmod(knowledge, 0o750)
    os.chmod(receipts, 0o700)
    return RestrictedKnowledgeWriter(
        str(knowledge), str(receipts), CORE_UID, expected_core_gid=knowledge.stat().st_gid,
        peer_uid_reader=lambda _sock: CORE_UID,
        **kwargs,
    ), knowledge, receipts


def request(**changes):
    payload = {
        "protocol": 1,
        "request_id": "synthetic-request-001",
        "target_filename": "synthetic-note.md",
        "review_sha256": hashlib.sha256(b"approved synthetic review").hexdigest(),
        "output_sha256": hashlib.sha256(OUTPUT).hexdigest(),
        "output_base64": base64.b64encode(OUTPUT).decode("ascii"),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    return {**payload, **changes}


def test_exact_request_create_only_and_safe_retry(tmp_path):
    writer, knowledge, receipts = make_writer(tmp_path)

    assert writer.handle(request(), CORE_UID) == {
        "status": "written", "request_id": "synthetic-request-001",
        "output_sha256": hashlib.sha256(OUTPUT).hexdigest(),
    }
    assert (knowledge / "synthetic-note.md").read_bytes() == OUTPUT
    assert writer.handle(request(), CORE_UID)["status"] == "already_written"
    assert len(list(knowledge.iterdir())) == 1
    assert json.loads((receipts / "synthetic-request-001.json").read_text())["state"] == "written"


def test_hardlinked_receipt_fails_closed_on_replay(tmp_path):
    writer, _, receipts = make_writer(tmp_path)
    writer.handle(request(), CORE_UID)
    os.link(receipts / "synthetic-request-001.json", receipts / "unexpected-link.json")
    with pytest.raises(RecoveryRequired, match="receipt_state_unsafe"):
        writer.handle(request(), CORE_UID)


@pytest.mark.parametrize("peer_uid", [0, 4243, None])
def test_wrong_or_missing_kernel_peer_is_rejected_before_write(tmp_path, peer_uid):
    writer, knowledge, _ = make_writer(tmp_path)
    with pytest.raises(WriterRejected, match="peer_rejected"):
        writer.handle(request(), peer_uid)
    assert list(knowledge.iterdir()) == []


def test_writer_refuses_same_uid_configuration(tmp_path):
    knowledge = tmp_path / "knowledge"
    receipts = tmp_path / "receipts"
    knowledge.mkdir(mode=0o750)
    receipts.mkdir(mode=0o700)
    os.chmod(knowledge, 0o750)
    os.chmod(receipts, 0o700)
    with pytest.raises(WriterRejected, match="writer_core_uid_not_separated"):
        RestrictedKnowledgeWriter(
            str(knowledge), str(receipts), os.geteuid(), expected_core_gid=knowledge.stat().st_gid,
            peer_uid_reader=lambda _sock: os.geteuid(),
        )


@pytest.mark.parametrize("changes", [
    {"extra": "caller root"},
    {"target_filename": "../outside.md"},
    {"target_filename": "nested/target.md"},
    {"output_sha256": "0" * 64},
    {"expires_at": "2000-01-01T00:00:00+00:00"},
    {"expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
])
def test_malformed_scope_expiry_and_digest_fail_closed(tmp_path, changes):
    writer, knowledge, _ = make_writer(tmp_path)
    with pytest.raises(WriterRejected):
        writer.handle(request(**changes), CORE_UID)
    assert list(knowledge.iterdir()) == []


def test_existing_target_symlink_and_hardlink_are_never_overwritten(tmp_path):
    writer, knowledge, _ = make_writer(tmp_path)
    target = knowledge / "synthetic-note.md"
    target.write_bytes(b"existing")
    with pytest.raises(WriterRejected, match="target_exists"):
        writer.handle(request(), CORE_UID)
    assert target.read_bytes() == b"existing"

    other = knowledge / "other.md"
    os.link(target, other)
    with pytest.raises(WriterRejected, match="target_exists"):
        writer.handle(request(), CORE_UID)
    assert target.stat().st_nlink == 2


def test_crash_after_file_fsync_leaves_recovery_required_without_rewrite(tmp_path, monkeypatch):
    writer, knowledge, receipts = make_writer(tmp_path)
    write_record = writer_module.RestrictedKnowledgeWriter._write_record

    def crash_before_final_receipt(receipts_fd, name, record, *, create_only):
        if record.get("state") == "written":
            raise OSError("synthetic crash after target fsync before receipt")
        return write_record(receipts_fd, name, record, create_only=create_only)

    monkeypatch.setattr(
        writer_module.RestrictedKnowledgeWriter,
        "_write_record",
        staticmethod(crash_before_final_receipt),
    )
    with pytest.raises(RecoveryRequired, match="writer_io_recovery_required"):
        writer.handle(request(), CORE_UID)
    target = knowledge / "synthetic-note.md"
    assert target.read_bytes() == OUTPUT
    record = json.loads((receipts / "synthetic-request-001.json").read_text())
    assert record["state"] == "writing"

    retry = RestrictedKnowledgeWriter(
        str(knowledge), str(receipts), CORE_UID,
        expected_core_gid=knowledge.stat().st_gid,
        peer_uid_reader=lambda _sock: CORE_UID,
    )
    with pytest.raises(RecoveryRequired, match="recovery_required"):
        retry.handle(request(), CORE_UID)
    assert len(list(knowledge.iterdir())) == 1


def test_replay_with_changed_approved_binding_is_rejected(tmp_path):
    writer, knowledge, _ = make_writer(tmp_path)
    writer.handle(request(), CORE_UID)
    altered_output = b"different approved bytes"
    replay = request(
        output_base64=base64.b64encode(altered_output).decode("ascii"),
        output_sha256=hashlib.sha256(altered_output).hexdigest(),
    )
    with pytest.raises(WriterRejected, match="request_replay_conflict"):
        writer.handle(replay, CORE_UID)
    assert (knowledge / "synthetic-note.md").read_bytes() == OUTPUT


def test_concurrent_same_request_writes_one_target(tmp_path):
    writer, knowledge, _ = make_writer(tmp_path)
    barrier = threading.Barrier(2)

    def write_once():
        barrier.wait()
        return writer.handle(request(), CORE_UID)["status"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(write_once)
        second = executor.submit(write_once)
        statuses = sorted([first.result(), second.result()])
    assert statuses == ["already_written", "written"]
    assert len(list(knowledge.iterdir())) == 1


def test_unix_socket_frame_is_bounded_and_uses_injected_peer_verifier(tmp_path):
    writer, knowledge, _ = make_writer(tmp_path)
    server, client = socket.socketpair()
    try:
        worker = threading.Thread(target=writer.handle_socket, args=(server,))
        worker.start()
        client.sendall((json.dumps(request()) + "\n").encode("utf-8"))
        response = json.loads(client.recv(2048).decode("utf-8"))
        worker.join(timeout=2)
    finally:
        server.close()
        client.close()
    assert response["status"] == "written"
    assert (knowledge / "synthetic-note.md").read_bytes() == OUTPUT


def test_duplicate_json_fields_are_rejected_over_ipc(tmp_path):
    writer, knowledge, _ = make_writer(tmp_path)
    server, client = socket.socketpair()
    try:
        worker = threading.Thread(target=writer.handle_socket, args=(server,))
        worker.start()
        client.sendall(b'{"protocol":1,"protocol":1}\n')
        response = json.loads(client.recv(2048).decode("utf-8"))
        worker.join(timeout=2)
    finally:
        server.close()
        client.close()
    assert response == {"status": "rejected"}
    assert list(knowledge.iterdir()) == []


def test_socket_listener_fails_closed_when_os_group_is_not_provisioned(tmp_path):
    writer, knowledge, _ = make_writer(tmp_path)
    writer.expected_core_gid = os.getegid()
    socket_parent = tempfile.mkdtemp(prefix="sbw-", dir="/tmp")
    socket_path = os.path.join(socket_parent, "writer.sock")
    try:
        with pytest.raises(WriterRejected, match="socket_parent_permissions_unsafe"):
            serve_unix_socket(writer, socket_path, threading.Event())
        assert not os.path.exists(socket_path)
        assert list(knowledge.iterdir()) == []
    finally:
        os.rmdir(socket_parent)


def test_kernel_peer_credentials_fail_closed_when_unavailable():
    left, right = socket.socketpair()
    try:
        if hasattr(socket, "SO_PEERCRED"):
            assert _peer_uid(left) == os.geteuid()
        else:
            with pytest.raises(WriterRejected, match="peer_credentials_unavailable"):
                _peer_uid(left)
    finally:
        left.close()
        right.close()


def test_core_client_and_writer_exchange_exact_synthetic_bytes_over_socketpair(tmp_path, monkeypatch):
    writer, knowledge, _ = make_writer(tmp_path)
    server, client_socket = socket.socketpair()
    worker = threading.Thread(target=writer.handle_socket, args=(server,))
    worker.start()

    class ConnectedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            client_socket.close()

        def settimeout(self, _timeout):
            return None

        def connect(self, _path):
            return None

        def sendall(self, data):
            return client_socket.sendall(data)

        def shutdown(self, how):
            return client_socket.shutdown(how)

        def recv(self, size):
            return client_socket.recv(size)

    monkeypatch.setattr(writer_module.socket, "socket", lambda *_args: ConnectedSocket())
    client = RestrictedWriterIPCClient("/tmp/synthetic-writer.sock")
    try:
        response = client.write_approved(
            "synthetic-request-001", "synthetic-note.md",
            hashlib.sha256(b"approved synthetic review").hexdigest(), OUTPUT,
        )
        worker.join(timeout=2)
    finally:
        server.close()
        if client_socket.fileno() >= 0:
            client_socket.close()
    assert response["status"] == "written"
    assert response["output_sha256"] == hashlib.sha256(OUTPUT).hexdigest()
    assert (knowledge / "synthetic-note.md").read_bytes() == OUTPUT


@pytest.mark.parametrize("target_state", ["missing", "unreadable"])
def test_written_receipt_with_missing_or_unreadable_target_requires_manual_recovery(tmp_path, target_state):
    writer, knowledge, _ = make_writer(tmp_path)
    writer.handle(request(), CORE_UID)
    target = knowledge / "synthetic-note.md"
    target.unlink()
    if target_state == "unreadable":
        target.mkdir()

    with pytest.raises(RecoveryRequired):
        writer.handle(request(), CORE_UID)
    assert target.exists() is (target_state == "unreadable")
    assert len(list(knowledge.iterdir())) == (1 if target_state == "unreadable" else 0)


def test_corrupt_written_receipt_fails_closed_on_replay(tmp_path):
    writer, knowledge, receipts = make_writer(tmp_path)
    writer.handle(request(), CORE_UID)
    (receipts / "synthetic-request-001.json").write_text("{broken receipt", encoding="utf-8")

    with pytest.raises(RecoveryRequired, match="receipt_state_invalid"):
        writer.handle(request(), CORE_UID)
    assert (knowledge / "synthetic-note.md").read_bytes() == OUTPUT
    assert len(list(knowledge.iterdir())) == 1
