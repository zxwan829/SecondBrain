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

@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="requires Linux procfs")
def test_writer_rejects_socket_inherited_as_standard_input():
    import subprocess
    import sys
    parent, child = socket.socketpair()
    try:
        code = ('from secondbrain_core.modules.d090_writer_service import _check_fds; '
                '_check_fds({0, 1, 2})')
        result = subprocess.run([sys.executable, '-c', code], stdin=child,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        assert result.returncode != 0
        assert b'writer_unsafe_standard_fd' in result.stderr
    finally:
        parent.close()
        child.close()

@pytest.mark.skipif(not os.path.isdir('/proc/self/fd'), reason='requires Linux procfs')
def test_writer_rejects_non_null_character_device_and_extra_fd():
    import subprocess
    import sys
    code = ('from secondbrain_core.modules.d090_writer_service import _check_fds; '
            '_check_fds({0, 1, 2})')
    with open('/dev/zero', 'rb') as device:
        result = subprocess.run([sys.executable, '-c', code], stdin=device,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        assert result.returncode != 0 and b'writer_unsafe_standard_fd' in result.stderr
    extra_read, extra_write = os.pipe()
    try:
        result = subprocess.run([sys.executable, '-c', code], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                pass_fds=(extra_write,), timeout=10)
        assert result.returncode != 0 and b'writer_unexpected_inherited_fd' in result.stderr
    finally:
        os.close(extra_read)
        os.close(extra_write)
