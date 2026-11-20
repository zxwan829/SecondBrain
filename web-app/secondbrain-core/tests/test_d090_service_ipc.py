import os
import socket
import threading

import pytest

from secondbrain_core.modules.d090_authority_writer import D090Rejected, UnixWriterClient


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="requires Linux peer credentials")
def test_client_checks_server_identity_before_sending(tmp_path):
    path = str(tmp_path / "writer.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    received = []

    def serve():
        with listener.accept()[0] as conn:
            conn.settimeout(2)
            received.append(conn.recv(4096))

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        with pytest.raises(D090Rejected, match="authority_peer_rejected"):
            UnixWriterClient(path, writer_uid=os.getuid() + 1, writer_gid=os.getgid())({"grant": "secret"}, b"content")
        thread.join(3)
        assert not thread.is_alive()
        assert received == [b""]
    finally:
        listener.close()


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="requires Linux peer credentials")
def test_client_accepts_matching_writer_peer(tmp_path):
    path = str(tmp_path / "writer.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    received = []

    def serve():
        with listener.accept()[0] as conn:
            received.append(conn.recv(4096))
            conn.sendall(b'{"operation_id":"op","content_sha256":"abc","status":"published"}\n')

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        result = UnixWriterClient(path, writer_uid=os.getuid(), writer_gid=os.getgid())({"operation_id": "op"}, b"content")
        thread.join(3)
        assert not thread.is_alive()
        assert result["operation_id"] == "op"
        assert b'"content_base64":"Y29udGVudA=="' in received[0]
    finally:
        listener.close()
