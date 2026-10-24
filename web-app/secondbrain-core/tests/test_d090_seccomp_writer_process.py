"""Synthetic x86_64 Linux test of seccomp around the exact D090 Writer publish method."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


HELPER = Path(__file__).with_name("d090_seccomp_writer_process_helper.py")
WRITER_UID = 31003
WRITER_GID = 31103

ALLOWED_RUNTIME_SYSCALLS = {
    "read", "write", "close", "fstat", "mmap", "mprotect", "munmap", "brk",
    "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "ioctl", "pread64",
    "pwrite64", "mremap", "madvise", "nanosleep", "getpid", "exit", "fcntl",
    "fsync", "truncate", "getcwd", "rename", "gettid", "futex", "clock_gettime",
    "exit_group", "openat", "newfstatat", "unlinkat", "renameat", "linkat",
    "getuid", "getgid", "geteuid", "getegid",
    "getrandom", "rseq",
}
DENIED_PROBE_SYSCALLS = {
    "fchmodat", "fchmodat2", "chmod", "socket", "fork", "clone", "clone3", "prctl",
}


@pytest.mark.skipif(
    sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"},
    reason="requires isolated Ubuntu x86_64 Linux",
)
@pytest.mark.skipif(os.geteuid() != 0, reason="requires ephemeral runner root to set up synthetic UID/GID")
def test_seccomp_allowlist_covers_exact_writer_publish_runtime():
    strace = shutil.which("strace")
    assert strace, "strace is required to inventory the exact post-filter syscall surface"
    with tempfile.TemporaryDirectory(prefix="secondbrain-d090-seccomp-") as temporary:
        root = Path(temporary)
        target_root = root / "publish"
        protected_root = root / "protected"
        target_root.mkdir(mode=0o700)
        protected_root.mkdir(mode=0o700)
        sentinel = protected_root / "sentinel.txt"
        sentinel.write_text("synthetic protected sentinel", encoding="utf-8")
        os.chown(root, WRITER_UID, WRITER_GID)
        os.chown(target_root, WRITER_UID, WRITER_GID)
        os.chown(protected_root, WRITER_UID, WRITER_GID)
        os.chown(sentinel, WRITER_UID, WRITER_GID)
        trace_path = root / "syscalls.trace"
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "SB_D090_SECCOMP_WRITER": "synthetic-only",
        }
        process = subprocess.run(
            [strace, "-f", "-qq", "-o", str(trace_path), sys.executable,
             str(HELPER), str(root)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            close_fds=True,
            env=environment,
            timeout=12,
            check=False,
        )
        trace_lines = trace_path.read_text(encoding="utf-8").splitlines()
        marker_index = next(i for i, line in enumerate(trace_lines) if "SECCOMP_READY" in line)
        observed = sorted({
            match.group(1)
            for line in trace_lines[marker_index:]
            if (match := re.search(r"\b([a-zA-Z0-9_]+)\(", line))
        })
        print("SECCOMP_RUNTIME_SYSCALLS_OBSERVED " + ",".join(observed))
        assert process.returncode == 0, (
            f"exact Writer seccomp helper failed rc={process.returncode}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}\n"
            f"post-filter syscalls: {observed}"
        )
        assert "SECCOMP_READY uid=31003 gid=31103 euid=31003 egid=31103" in process.stdout
        assert "PASS exact_writer_publish=1" in process.stdout
        assert sentinel.read_text(encoding="utf-8") == "synthetic protected sentinel"
        assert (target_root / "approved.md").read_bytes() == b"# synthetic approved bytes\n"
        assert sorted(path.name for path in target_root.iterdir()) == ["approved.md"]

        assert observed, "no post-seccomp runtime syscall trace was captured"
        assert {"openat", "write", "fsync", "linkat", "close"} <= set(observed), (
            f"expected actual Writer publish syscalls missing: {observed}"
        )
        assert {"truncate", "unlinkat", "renameat"} <= set(observed), (
            f"expected Landlock-denied filesystem syscalls missing: {observed}"
        )
        assert {"socket", "prctl"} <= set(observed)
        assert {"fchmodat", "fchmodat2"} & set(observed)
        assert {"fork", "clone", "clone3"} & set(observed)
        assert set(observed) <= ALLOWED_RUNTIME_SYSCALLS | DENIED_PROBE_SYSCALLS, (
            f"post-seccomp syscall not in allowlist or explicit denial probes: "
            f"{sorted(set(observed) - ALLOWED_RUNTIME_SYSCALLS - DENIED_PROBE_SYSCALLS)}"
        )
        print(
            "SECCOMP_RUNTIME_SYSCALLS allowed="
            + ",".join(sorted(set(observed) & ALLOWED_RUNTIME_SYSCALLS))
            + " denied="
            + ",".join(sorted(set(observed) & DENIED_PROBE_SYSCALLS))
        )
