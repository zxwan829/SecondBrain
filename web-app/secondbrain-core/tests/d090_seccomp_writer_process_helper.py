"""Synthetic OS wrapper that calls the exact D090 StrictCreateOnlyWriter.publish."""
from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import platform
import socket
import sys
from pathlib import Path

from secondbrain_core.modules import d090_authority_writer as d090
from d090_landlock_process_helper import (
    MAKE_REG,
    READ_DIR,
    READ_FILE,
    REFER,
    TRUNCATE,
    WRITE_FILE,
    RulesetAttr,
    add_path_rule,
    assert_denied,
    cap_status,
    drop_capabilities,
    fail_errno,
    install_minimal_seccomp,
    landlock_abi,
)


LIBC = ctypes.CDLL(None, use_errno=True)
PR_SET_NO_NEW_PRIVS = 38
PR_CAPBSET_DROP = 24
PR_CAP_AMBIENT = 47
PR_CAP_AMBIENT_CLEAR_ALL = 4
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LINUX_CAPABILITY_VERSION_3 = 0x20080522
CONTENT = b"# synthetic approved bytes\n"
WRITER_UID = 31003
WRITER_GID = 31103


class CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class CapData(ctypes.Structure):
    _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32),
                ("inheritable", ctypes.c_uint32)]


def set_no_new_privs_and_drop_to_writer():
    if os.geteuid() != 0:
        raise RuntimeError("synthetic UID transition requires the isolated Linux runner root setup")
    if LIBC.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        fail_errno("set no_new_privs")
    if LIBC.prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) != 0:
        fail_errno("clear ambient capabilities")
    last_cap = int(Path("/proc/sys/kernel/cap_last_cap").read_text(encoding="ascii").strip())
    for capability in range(last_cap + 1):
        if LIBC.prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) != 0:
            fail_errno(f"drop capability bounding set entry {capability}")
    os.setgroups([])
    os.setgid(WRITER_GID)
    os.setuid(WRITER_UID)
    if os.geteuid() != WRITER_UID or os.getegid() != WRITER_GID:
        raise AssertionError("synthetic Writer identity transition failed")
    if any(cap_status().get(name, -1) != 0 for name in ("CapEff", "CapPrm", "CapInh")):
        # A setuid drop should clear the sets; capset is an explicit second check.
        drop_capabilities()
    status = Path("/proc/self/status").read_text(encoding="utf-8")
    if "NoNewPrivs:\t1" not in status:
        raise AssertionError("no_new_privs is not active before Landlock/seccomp")
    after_drop = cap_status()
    if any(after_drop.get(name, -1) != 0 for name in ("CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd")):
        raise AssertionError("effective, permitted, inheritable, ambient, and bounding capabilities must be zero")


def install_writer_landlock(target_root: Path):
    abi = landlock_abi()
    if abi < 3:
        raise RuntimeError(f"Landlock ABI >=3 required, observed {abi}")
    handled = (1 << 15) - 1
    handled |= TRUNCATE
    attr = RulesetAttr(handled)
    ruleset_fd = LIBC.syscall(SYS_LANDLOCK_CREATE_RULESET, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    if ruleset_fd < 0:
        fail_errno("create Writer Landlock ruleset")
    try:
        # The actual Writer target directory receives only the candidate rights.
        add_path_rule(ruleset_fd, target_root, READ_FILE | READ_DIR | WRITE_FILE | MAKE_REG | REFER)
        if LIBC.syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0) != 0:
            fail_errno("restrict synthetic Writer with Landlock")
    finally:
        os.close(ruleset_fd)
    return abi


def main():
    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        print("SKIP unsupported Linux x86_64 runtime", flush=True)
        return 77
    if os.environ.get("SB_D090_SECCOMP_WRITER") != "synthetic-only":
        raise RuntimeError("helper requires explicit synthetic-only marker")
    root = Path(sys.argv[1]).resolve()
    target_root = root / "publish"
    protected_root = root / "protected"
    protected_sentinel = protected_root / "sentinel.txt"

    # The grant and key fixture are synthetic and prepared before confinement.
    signer = d090.Ed25519GrantSigner("synthetic-key", d090.Ed25519PrivateKey.generate())
    grant = {
        "protocol": d090.PROTOCOL,
        "key_id": signer.key_id,
        "approval_id": "synthetic-approval",
        "operation_id": "synthetic-operation",
        "source_revision": "synthetic-revision",
        "source_sha256": "a" * 64,
        "content_sha256": __import__("hashlib").sha256(CONTENT).hexdigest(),
        "content_length": len(CONTENT),
        "target_id": "target-1",
        "create_only": True,
        "expires_at": int(__import__("time").time()) + 120,
        "nonce": "synthetic-nonce",
        "audience": "secondbrain-knowledge-writer",
    }
    signed = {**grant, "signature": signer.sign(grant)}

    set_no_new_privs_and_drop_to_writer()
    abi = install_writer_landlock(target_root)
    writer = d090.StrictCreateOnlyWriter(
        str(target_root), signer.public_key, signer.key_id, {"target-1": "approved.md"},
        d090.D090RoleIds(31001, 31002, WRITER_UID, 31101, 31102, WRITER_GID),
        allow_synthetic_identities=True,
    )
    extra_fds = []
    for fd in range(3, 128):
        try:
            fcntl.fcntl(fd, fcntl.F_GETFD)
            extra_fds.append(fd)
        except OSError:
            pass
    if extra_fds != [writer.root_fd]:
        raise AssertionError(f"Writer FD allowlist mismatch: {extra_fds}, expected {[writer.root_fd]}")

    install_minimal_seccomp()
    from d090_landlock_process_helper import SECCOMP_ALLOW
    print(
        f"SECCOMP_READY landlock_abi={abi} fd_allowlist=1 "
        f"allow_syscalls={','.join(str(n) for n in sorted(SECCOMP_ALLOW))}",
        flush=True,
    )
    if (os.getuid(), os.getgid(), os.geteuid(), os.getegid()) != (WRITER_UID, WRITER_GID, WRITER_UID, WRITER_GID):
        raise AssertionError("seccomp identity syscalls returned unexpected Writer identity")
    print(f"WRITER_IDENTITY uid={os.getuid()} gid={os.getgid()} euid={os.geteuid()} egid={os.getegid()}", flush=True)

    receipt = writer.publish(signed, CONTENT)
    if receipt.get("status") != "published" or receipt.get("operation_id") != grant["operation_id"]:
        raise AssertionError("exact StrictCreateOnlyWriter.publish receipt mismatch")
    if (target_root / "approved.md").read_bytes() != CONTENT:
        raise AssertionError("exact Writer target content mismatch")

    # openat is seccomp-allowed, so its EACCES exercises Landlock. Destructive
    # syscall probes are denied by seccomp default policy and are not Landlock evidence.
    assert_denied("open protected sentinel for write",
                  lambda: os.open(protected_sentinel, os.O_WRONLY | os.O_CLOEXEC))
    assert_denied("seccomp truncate syscall", lambda: os.truncate(protected_sentinel, 0))
    assert_denied("seccomp unlink syscall", lambda: os.unlink(protected_sentinel))
    assert_denied("seccomp rename syscall", lambda: os.rename(protected_sentinel, protected_root / "moved.txt"))

    # Landlock does not enforce metadata changes. Since the published file is
    # owned by Writer, this otherwise-allowed chmod must be rejected by seccomp.
    assert_denied("chmod published target", lambda: os.chmod(target_root / "approved.md", 0o600))
    assert_denied("create network socket", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    assert_denied("fork child process", os.fork)
    def attempt_seccomp_change():
        ctypes.set_errno(0)
        result = LIBC.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.c_void_p())
        if result == 0:
            raise AssertionError("post-install prctl unexpectedly changed seccomp state")
        error = ctypes.get_errno()
        if error != errno.EPERM:
            raise OSError(error, f"post-install prctl failed unexpectedly: {os.strerror(error)}")
        raise PermissionError(error, "seccomp denied post-install prctl")
    assert_denied("change seccomp policy", attempt_seccomp_change)
    writer.close()
    print("PASS exact_writer_publish=1 landlock_denials=4 seccomp_metadata_socket_process_denials=3", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
