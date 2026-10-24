"""Synthetic Landlock ABI/capability/FD test helper; never touches real data."""
from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import platform
import sys
from pathlib import Path


ARCH = platform.machine().lower()
if ARCH not in {"x86_64", "amd64", "aarch64", "arm64"}:
    raise RuntimeError(f"unsupported syscall ABI architecture: {ARCH}")

LIBC = ctypes.CDLL(None, use_errno=True)
SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
LINUX_CAPABILITY_VERSION_3 = 0x20080522

# Filesystem access rights from linux/landlock.h through ABI v3.
EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
MAKE_SYM = 1 << 12
REFER = 1 << 13
TRUNCATE = 1 << 14


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class CapData(ctypes.Structure):
    _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32),
                ("inheritable", ctypes.c_uint32)]


def fail_errno(operation: str):
    error = ctypes.get_errno()
    raise OSError(error, f"{operation}: {os.strerror(error)}")


def landlock_abi() -> int:
    result = LIBC.syscall(SYS_LANDLOCK_CREATE_RULESET, None, 0,
                          LANDLOCK_CREATE_RULESET_VERSION)
    if result < 0:
        error = ctypes.get_errno()
        if error in (errno.ENOSYS, errno.EOPNOTSUPP):
            print(f"SKIP Landlock unavailable errno={error}", flush=True)
            return 0
        fail_errno("query Landlock ABI")
    return int(result)


def cap_status() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("CapEff:", "CapPrm:", "CapInh:", "NoNewPrivs:")):
            key, value = line.split(":", 1)
            values[key] = int(value.strip(), 16 if key.startswith("Cap") else 10)
    return values


def drop_capabilities():
    header = CapHeader(LINUX_CAPABILITY_VERSION_3, 0)
    data = (CapData * 2)()
    if LIBC.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        fail_errno("drop all effective/permitted/inheritable capabilities")
    if any(cap_status().get(name, -1) != 0 for name in ("CapEff", "CapPrm", "CapInh")):
        raise AssertionError("capability sets are not empty after capset")


def add_path_rule(ruleset_fd: int, path: Path, allowed: int):
    parent_fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    try:
        attr = PathBeneathAttr(allowed, parent_fd)
        if LIBC.syscall(SYS_LANDLOCK_ADD_RULE, ruleset_fd,
                        LANDLOCK_RULE_PATH_BENEATH,
                        ctypes.byref(attr), 0) != 0:
            fail_errno(f"add Landlock rule for {path.name}")
    finally:
        os.close(parent_fd)


def assert_denied(label: str, callback):
    try:
        callback()
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EPERM):
            raise AssertionError(f"{label} failed for unexpected reason: {exc}") from exc
        print(f"DENIED {label} errno={exc.errno}", flush=True)
        return
    raise AssertionError(f"Landlock unexpectedly allowed {label}")


def main():
    if sys.platform != "linux":
        print("SKIP unsupported platform", flush=True)
        return 77
    if os.environ.get("SB_D090_LANDLOCK_HELPER") != "synthetic-only":
        raise RuntimeError("helper requires explicit synthetic-only marker")
    root = Path(sys.argv[1]).resolve()
    allowed_fd = int(sys.argv[2])
    stage = root / "stage"
    publish = root / "publish"
    protected = root / "protected"
    sentinel = protected / "sentinel.txt"

    open_fds = []
    for fd in range(3, 128):
        try:
            fcntl.fcntl(fd, fcntl.F_GETFD)
            open_fds.append(fd)
        except OSError:
            pass
    if open_fds != [allowed_fd]:
        raise AssertionError(f"FD allowlist mismatch: inherited {open_fds}, expected {[allowed_fd]}")
    if os.fstat(allowed_fd).st_ino != os.stat(stage / "seed.txt").st_ino:
        raise AssertionError("allowlisted FD is not the synthetic staging seed")
    abi = landlock_abi()
    if abi == 0:
        return 77
    if abi < 3:
        print(f"SKIP Landlock ABI {abi}; ABI >= 3 is required for truncation coverage", flush=True)
        return 77

    if LIBC.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        fail_errno("set no_new_privs")
    drop_capabilities()
    before = cap_status()
    if before.get("CapEff") or before.get("CapPrm") or before.get("CapInh"):
        raise AssertionError("non-zero capabilities before Landlock")
    if before.get("NoNewPrivs") != 1:
        raise AssertionError("no_new_privs did not take effect")

    handled = (EXECUTE | WRITE_FILE | READ_FILE | READ_DIR | REMOVE_DIR | REMOVE_FILE |
               MAKE_CHAR | MAKE_DIR | MAKE_REG | MAKE_SOCK | MAKE_FIFO | MAKE_BLOCK |
               MAKE_SYM | REFER | TRUNCATE)
    attr = RulesetAttr(handled)
    ruleset_fd = LIBC.syscall(SYS_LANDLOCK_CREATE_RULESET, ctypes.byref(attr),
                              ctypes.sizeof(attr), 0)
    if ruleset_fd < 0:
        fail_errno("create Landlock ruleset")
    stage_rights = handled
    publish_rights = READ_FILE | READ_DIR | WRITE_FILE | MAKE_REG | REMOVE_FILE | REFER
    try:
        add_path_rule(ruleset_fd, stage, stage_rights)
        add_path_rule(ruleset_fd, publish, publish_rights)
        if LIBC.syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0) != 0:
            fail_errno("restrict self with Landlock")
    finally:
        os.close(ruleset_fd)

    # A staged synthetic publication is intentionally the only allowed mutation target.
    payload = stage / "candidate.md"
    payload.write_bytes(b"synthetic candidate")
    os.replace(payload, publish / "published.md")
    if (publish / "published.md").read_bytes() != b"synthetic candidate":
        raise AssertionError("synthetic staging/publish operation failed")

    assert_denied("open protected file for write",
                  lambda: os.open(sentinel, os.O_WRONLY | os.O_CLOEXEC))
    assert_denied("truncate protected file",
                  lambda: os.truncate(sentinel, 0))
    assert_denied("unlink protected file", lambda: os.unlink(sentinel))
    assert_denied("rename protected file", lambda: os.rename(sentinel, protected / "moved.txt"))
    # Kernel documentation lists stat/chmod/chown/setxattr/utime as currently
    # unrestrictable by Landlock. This helper makes no assertion about them.
    print(f"PASS abi={abi} no_new_privs=1 cap_eff_prm_inh=0 fd_allowlist=1 publish=1 metadata=NOT_ENFORCED_BY_LANDLOCK",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
