"""Real UID/GID and Unix-kernel credential checks for an isolated Linux run.

This test deliberately skips unless run as root inside a disposable Linux
runner/container with ``SB_WRITER_OS_ISOLATION=disposable-linux``. It changes
ownership only below its dedicated synthetic temporary root in ``/tmp``. It is
not a macOS or same-UID substitute for the OS isolation acceptance.
"""
import hashlib
import json
import multiprocessing
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


CORE_UID = 31001
CORE_GID = 31002
WRITER_UID = 31003
WRITER_GID = 31004
OTHER_UID = 31005
OUTPUT = b"<!-- approved synthetic Linux OS isolation fixture -->\n# Fixture\n"
REQUEST_ID = "linux-os-isolation-001"


def _writer_process(knowledge_root, receipt_root, socket_path, ready):
    # The test runner starts this child as root, then gives the Writer a
    # private real UID/GID and the explicitly shared Core access GID.
    from secondbrain_core.modules.restricted_knowledge_writer import main

    os.chdir("/")
    os.setgroups([CORE_GID])
    os.setresgid(WRITER_GID, CORE_GID, CORE_GID)
    os.setresuid(WRITER_UID, WRITER_UID, WRITER_UID)
    ready.put((os.getuid(), os.getgid(), os.geteuid(), os.getegid()))
    os.environ.update({
        "SB_KNOWLEDGE_WRITER_ROOT": knowledge_root,
        "SB_KNOWLEDGE_WRITER_RECEIPT_ROOT": receipt_root,
        "SB_KNOWLEDGE_WRITER_SOCKET": socket_path,
        "SB_CORE_UID": str(CORE_UID),
        "SB_CORE_GID": str(CORE_GID),
    })
    main()


def _drop_to(uid, real_gid, effective_gid):
    os.setgroups([CORE_GID])
    os.setresgid(real_gid, effective_gid, effective_gid)
    os.setresuid(uid, uid, uid)


def _run_as(uid, real_gid, effective_gid, source, *, env):
    def drop_identity():
        _drop_to(uid, real_gid, effective_gid)

    result = subprocess.run(
        [sys.executable, "-c", source], text=True, capture_output=True,
        cwd="/", env=env, timeout=10, preexec_fn=drop_identity, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(
    platform.system() != "Linux" or os.geteuid() != 0
    or not hasattr(socket, "SO_PEERCRED")
    or os.environ.get("SB_WRITER_OS_ISOLATION") != "disposable-linux",
    reason="requires explicit root inside a disposable Linux runner/container with SO_PEERCRED",
)
def test_real_linux_uids_kernel_peer_socket_permissions_and_recovery():
    root = Path(tempfile.mkdtemp(prefix="secondbrain-writer-os-isolation-"))
    os.chown(root, WRITER_UID, CORE_GID)
    os.chmod(root, 0o710)
    knowledge = root / "knowledge"
    receipts = root / "receipts"
    socket_parent = root / "ipc"
    for path in (knowledge, receipts, socket_parent):
        path.mkdir(mode=0o700)

    # Core can read/search Knowledge but only the Writer owner can mutate it.
    os.chown(knowledge, WRITER_UID, CORE_GID)
    os.chmod(knowledge, 0o750)
    os.chown(receipts, WRITER_UID, WRITER_GID)
    os.chmod(receipts, 0o700)
    os.chown(socket_parent, WRITER_UID, CORE_GID)
    os.chmod(socket_parent, 0o710)
    socket_path = str(socket_parent / "writer.sock")

    context = multiprocessing.get_context("fork")
    ready = context.Queue()
    stop = context.Process(target=_writer_process,
                           args=(str(knowledge), str(receipts), socket_path, ready))
    stop.start()
    try:
        assert ready.get(timeout=5) == (WRITER_UID, WRITER_GID, WRITER_UID, CORE_GID)
        deadline = time.monotonic() + 5
        while not os.path.exists(socket_path) and time.monotonic() < deadline:
            assert stop.is_alive(), "Writer process exited before creating its socket"
            time.sleep(0.02)
        assert os.path.exists(socket_path), "Writer socket did not become ready"

        parent_info = os.stat(socket_parent, follow_symlinks=False)
        socket_info = os.stat(socket_path, follow_symlinks=False)
        assert (parent_info.st_uid, parent_info.st_gid, stat.S_IMODE(parent_info.st_mode)) == (
            WRITER_UID, CORE_GID, 0o710,
        )
        assert stat.S_ISSOCK(socket_info.st_mode)
        assert (socket_info.st_uid, socket_info.st_gid, stat.S_IMODE(socket_info.st_mode)) == (
            WRITER_UID, CORE_GID, 0o660,
        )

        env = os.environ.copy()
        package_path = os.environ.get("SB_WRITER_TEST_PYTHONPATH")
        env["PYTHONPATH"] = package_path or os.pathsep.join(sys.path)
        env["SB_WRITER_TEST_KNOWLEDGE"] = str(knowledge)
        env["SB_WRITER_TEST_SOCKET"] = socket_path
        env["SB_WRITER_TEST_OUTPUT"] = OUTPUT.hex()
        env["SB_WRITER_TEST_REQUEST"] = REQUEST_ID
        valid_core = r'''
import hashlib, json, os, stat
from pathlib import Path
from secondbrain_core.modules.restricted_knowledge_writer import RestrictedWriterIPCClient
root = Path(os.environ["SB_WRITER_TEST_KNOWLEDGE"])
target = root / "synthetic-approved.md"
try:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
except PermissionError:
    direct_create = "denied"
else:
    os.close(fd)
    raise AssertionError("Core directly created a Knowledge file")
output = bytes.fromhex(os.environ["SB_WRITER_TEST_OUTPUT"])
client = RestrictedWriterIPCClient(os.environ["SB_WRITER_TEST_SOCKET"])
result = client.write_approved(os.environ["SB_WRITER_TEST_REQUEST"], target.name,
                               hashlib.sha256(b"approved synthetic review").hexdigest(), output)
try:
    fd = os.open(target, os.O_WRONLY)
except PermissionError:
    direct_overwrite = "denied"
else:
    os.close(fd)
    raise AssertionError("Core directly opened the Writer-owned Knowledge file for writing")
print(json.dumps({"status": result["status"], "direct_create": direct_create,
                  "direct_overwrite": direct_overwrite, "uid": os.getuid(),
                  "gid": os.getgid(), "euid": os.geteuid(), "egid": os.getegid()}))
'''
        first = _run_as(CORE_UID, CORE_GID, CORE_GID, valid_core, env=env)
        assert first == {"status": "written", "direct_create": "denied",
                         "direct_overwrite": "denied", "uid": CORE_UID,
                         "gid": CORE_GID, "euid": CORE_UID, "egid": CORE_GID}

        target = knowledge / "synthetic-approved.md"
        target_info = target.stat()
        assert (target_info.st_uid, target_info.st_gid, stat.S_IMODE(target_info.st_mode),
                target_info.st_nlink) == (WRITER_UID, CORE_GID, 0o640, 1)
        assert target.read_bytes() == OUTPUT
        assert (receipts / f"{REQUEST_ID}.json").stat().st_uid == WRITER_UID
        assert stat.S_IMODE((receipts / f"{REQUEST_ID}.json").stat().st_mode) == 0o600

        # A different UID with the shared socket group can reach the socket,
        # but the Writer's real SO_PEERCRED UID check rejects it before write.
        wrong_peer = r'''
import json, os
from secondbrain_core.modules.restricted_knowledge_writer import RestrictedWriterIPCClient, WriterRejected
try:
    RestrictedWriterIPCClient(os.environ["SB_WRITER_TEST_SOCKET"]).write_approved(
        "linux-os-other-peer", "other.md", "0" * 64, b"synthetic unauthorized bytes")
except WriterRejected:
    print(json.dumps({"status": "rejected", "uid": os.getuid(), "gid": os.getgid(),
                      "euid": os.geteuid(), "egid": os.getegid()}))
else:
    raise AssertionError("Writer accepted a different kernel peer UID")
'''
        rejected = _run_as(OTHER_UID, 31006, CORE_GID, wrong_peer, env=env)
        assert rejected == {"status": "rejected", "uid": OTHER_UID, "gid": 31006,
                            "euid": OTHER_UID, "egid": CORE_GID}
        assert not (knowledge / "other.md").exists()

        # Out-of-band corruption is test fixture setup. A legitimate retry
        # must demand recovery and must not overwrite the altered target.
        corrupted = b"synthetic out-of-band corruption"
        target.write_bytes(corrupted)
        retry = r'''
import json, os
from secondbrain_core.modules.restricted_knowledge_writer import RecoveryRequired, RestrictedWriterIPCClient
try:
    RestrictedWriterIPCClient(os.environ["SB_WRITER_TEST_SOCKET"]).write_approved(
        os.environ["SB_WRITER_TEST_REQUEST"], "synthetic-approved.md",
        __import__("hashlib").sha256(b"approved synthetic review").hexdigest(),
        bytes.fromhex(os.environ["SB_WRITER_TEST_OUTPUT"]))
except RecoveryRequired:
    print(json.dumps({"status": "recovery_required"}))
else:
    raise AssertionError("Writer did not require recovery for receipt/target mismatch")
'''
        assert _run_as(CORE_UID, CORE_GID, CORE_GID, retry, env=env) == {
            "status": "recovery_required",
        }
        assert target.read_bytes() == corrupted
    finally:
        if stop.is_alive():
            stop.terminate()
        stop.join(timeout=5)
        if stop.is_alive():
            stop.kill()
            stop.join(timeout=2)
        shutil.rmtree(root)
