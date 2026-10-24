"""Real Linux UID/GID and SO_PEERCRED integration for synthetic D090 data."""
from __future__ import annotations

import os
import grp
import pwd
import select
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from secondbrain_core.modules import d090_authority_writer as d090


pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or os.geteuid() != 0
    or not hasattr(socket, "SO_PEERCRED") or not hasattr(os, "O_TMPFILE")
    or not Path("/proc/self/fd").is_dir(),
    reason="requires disposable Linux root runner, SO_PEERCRED and O_TMPFILE",
)

HELPER = Path(__file__).with_name("d090_linux_process_helper.py")


def _unused_block(start: int, count: int, lookup) -> int:
    for base in range(start, start + 5000):
        all_unused = True
        for value in range(base, base + count):
            try:
                lookup(value)
                all_unused = False
                break
            except KeyError:
                pass
        if all_unused:
            return base
    raise RuntimeError("no unused synthetic role identity range")


def _drop_identity(uid: int, gid: int):
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


def _command(mode: str, roles: d090.D090RoleIds, socket_path: Path,
             helper: Path, **extra) -> list[str]:
    values = (roles.core_uid, roles.authority_uid, roles.writer_uid,
              roles.core_gid, roles.authority_gid, roles.writer_gid)
    command = [sys.executable, str(helper), mode, "--socket-path", str(socket_path),
               "--role-ids", ",".join(str(value) for value in values)]
    for key, value in extra.items():
        if isinstance(value, bool):
            if value:
                command.append("--" + key.replace("_", "-"))
        else:
            command.extend(("--" + key.replace("_", "-"), str(value)))
    return command


def _readline(process: subprocess.Popen, timeout: float = 10) -> str:
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    if not ready:
        raise AssertionError("synthetic child did not report progress before timeout")
    line = process.stdout.readline()
    if not line:
        raise AssertionError(f"synthetic child exited early: {process.stderr.read()}")
    return line.strip()


def _spawn(command: list[str], uid: int, gid: int, module_root: Path) -> subprocess.Popen:
    child_env = os.environ.copy()
    existing_pythonpath = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = str(module_root) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, close_fds=True, env=child_env,
        preexec_fn=lambda: _drop_identity(uid, gid),
    )


def _prepare(root: Path, roles: d090.D090RoleIds, operation_id: str):
    root.chmod(0o711)
    authority_root = root / "authority"
    authority_root.mkdir(mode=0o700)
    os.chown(authority_root, roles.authority_uid, roles.authority_gid)
    knowledge_root = root / "knowledge"
    knowledge_root.mkdir(mode=0o700)
    os.chown(knowledge_root, roles.writer_uid, roles.writer_gid)
    socket_root = root / "socket"
    socket_root.mkdir(mode=0o711)
    os.chown(socket_root, roles.writer_uid, roles.writer_gid)
    socket_path = socket_root / "writer.sock"

    private = Ed25519PrivateKey.generate()
    private_path = authority_root / "test-private.pem"
    private_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    private_path.chmod(0o600)
    os.chown(private_path, roles.authority_uid, roles.authority_gid)
    public_path = root / "test-public.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    public_path.chmod(0o644)
    return authority_root, knowledge_root, socket_path, private_path, public_path


def _run_case(*, drop_response: bool):
    base = Path(tempfile.mkdtemp(prefix="secondbrain-d090-linux-"))
    base.chmod(0o711)
    processes: list[subprocess.Popen] = []
    try:
        helper = base / "d090_linux_process_helper.py"
        shutil.copyfile(HELPER, helper)
        helper.chmod(0o644)
        module_root = base / "role_modules"
        module_root.mkdir(mode=0o755)
        shutil.copytree(Path(__file__).parents[1] / "secondbrain_core",
                        module_root / "secondbrain_core")
        for path in (module_root / "secondbrain_core").rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        (module_root / "secondbrain_core").chmod(0o755)
        uid0 = _unused_block(41000, 3, pwd.getpwuid)
        gid0 = _unused_block(51000, 3, grp.getgrgid)
        roles = d090.D090RoleIds(uid0, uid0 + 1, uid0 + 2,
                                 gid0, gid0 + 1, gid0 + 2)
        if any(value < 0 for value in (roles.core_uid, roles.authority_uid,
                                      roles.writer_uid, roles.core_gid,
                                      roles.authority_gid, roles.writer_gid)):
            raise AssertionError("invalid synthetic role IDs")
        authority_root, knowledge_root, socket_path, private_path, public_path = _prepare(
            base, roles, "synthetic-operation",
        )
        writer_proc = _spawn(_command(
            "writer", roles, socket_path, helper, knowledge_root=knowledge_root,
            public_key=public_path, drop_response=drop_response,
        ), roles.writer_uid, roles.writer_gid, module_root)
        processes.append(writer_proc)
        assert _readline(writer_proc) == "READY"
        os.chown(socket_path, roles.authority_uid, roles.authority_gid)
        socket_path.chmod(0o660)

        if not drop_response:
            # Deliberately expose only the disposable test socket for one probe.
            # The Writer must reject the real, wrong UID/GID before reading its body.
            socket_path.chmod(0o666)
            probe = _spawn(
                _command("probe", roles, socket_path, helper),
                roles.core_uid, roles.core_gid, module_root,
            )
            processes.append(probe)
            assert _readline(writer_proc) == "REJECTED authority_peer_rejected"
            assert probe.wait(timeout=5) == 0
            os.chown(socket_path, roles.authority_uid, roles.authority_gid)
            socket_path.chmod(0o660)

        authority_cmd = _command(
            "authority", roles, socket_path, helper, ledger_root=authority_root,
            private_key=private_path, operation_id="synthetic-operation",
            expect_recovery=drop_response,
        )
        authority_proc = _spawn(authority_cmd, roles.authority_uid, roles.authority_gid, module_root)
        processes.append(authority_proc)
        result = _readline(authority_proc)
        assert authority_proc.wait(timeout=8) == 0, authority_proc.stderr.read()
        assert writer_proc.wait(timeout=8) == 0, writer_proc.stderr.read()
        if drop_response:
            assert '"result": "recovery_required"' in result
            assert '"state": "recovery_required"' in result
        else:
            assert '"result": "committed_and_replayed"' in result
            assert '"status": "published"' in result
        output = knowledge_root / "synthetic-note.md"
        assert output.read_bytes() == b"# Synthetic D090 process-boundary note\n"
        assert sorted(path.name for path in knowledge_root.iterdir()) == ["synthetic-note.md"]
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        shutil.rmtree(base, ignore_errors=True)


def test_authority_writer_real_uids_peer_credentials_replay_and_recovery():
    _run_case(drop_response=False)
    _run_case(drop_response=True)
