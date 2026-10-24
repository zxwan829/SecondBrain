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

ALLOW_NAMES = {"read", "write", "close", "fstat", "munmap", "rt_sigaction", "fsync",
               "getuid", "getgid", "geteuid", "getegid", "exit_group", "openat",
               "newfstatat", "linkat"}
DENIED_PROBE_SYSCALLS = {"chmod", "fchmodat", "fchmodat2", "socket", "fork", "clone", "clone3",
                         "prctl", "truncate", "unlink", "rename"}
DENIED_SYSCALL_NAMES = {"chmod", "fchmodat", "fchmodat2", "socket", "fork", "clone", "clone3",
                        "prctl", "truncate", "unlink", "unlinkat", "rename", "renameat", "renameat2"}


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
        trace_prefix = root / "syscalls.trace"
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "SB_D090_SECCOMP_WRITER": "synthetic-only",
        }
        process = subprocess.run(
            [strace, "-ff", "-qq", "-s", "8192", "-e", "trace=all", "-o", str(trace_prefix), sys.executable,
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
        trace_files = list(root.glob("syscalls.trace.*"))
        writer_pid_match = re.search(r"^SECCOMP_READY writer_pid=(\d+)\b", process.stdout, re.MULTILINE)
        assert writer_pid_match, (
            f"helper did not report its post-filter Writer PID; rc={process.returncode}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
        writer_pid = writer_pid_match.group(1)
        child_trace = root / f"syscalls.trace.{writer_pid}"
        assert child_trace in trace_files, (
            f"strace -ff has no trace for reported Writer PID {writer_pid}; files={trace_files}"
        )
        trace_lines = child_trace.read_text(encoding="utf-8").splitlines()
        marker_indices = [i for i, line in enumerate(trace_lines) if "SECCOMP_READY" in line]
        assert len(marker_indices) == 1, f"expected one untruncated readiness marker for Writer PID {writer_pid}: {marker_indices}"
        marker_index = marker_indices[0]
        marker = trace_lines[marker_index]
        allowed_numbers = re.search(r"allow_syscalls=([0-9,]+)", marker)
        assert allowed_numbers, f"marker missing exact filter allowlist: {marker}"
        assert set(allowed_numbers.group(1).split(",")) == {"0", "1", "3", "5", "11", "13", "74", "102", "104", "107", "108", "231", "257", "262", "265"}
        rows = []
        for line in trace_lines[marker_index + 1:]:
            match = re.match(r"^([A-Za-z0-9_]+)\(.*\)\s+=\s+(.+)$", line)
            if match:
                rows.append((match.group(1), match.group(2)))
        successful = {name for name, result in rows if not result.startswith("-1 ")}
        eperm = {name for name, result in rows if result.startswith("-1 EPERM")}
        eacces = {name for name, result in rows if result.startswith("-1 EACCES")}
        print(
            f"SECCOMP_WRITER_PID_TRACE pid={writer_pid} successful={sorted(successful)} "
            f"EPERM={sorted(eperm)} EACCES={sorted(eacces)}",
            flush=True,
        )
        assert process.returncode == 0, (
            f"exact Writer seccomp helper failed rc={process.returncode}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}\n"
            f"PID-scoped post-filter trace rows: {rows}"
        )
        assert f"SECCOMP_READY writer_pid={writer_pid} " in process.stdout
        assert "uid=31003 gid=31103 euid=31003 egid=31103" in process.stdout
        assert "PASS exact_writer_publish=1 landlock_eacces=1 seccomp_eperm=7" in process.stdout
        assert sentinel.read_text(encoding="utf-8") == "synthetic protected sentinel"
        assert (target_root / "approved.md").read_bytes() == b"# synthetic approved bytes\n"
        assert sorted(path.name for path in target_root.iterdir()) == ["approved.md"]

        assert ALLOW_NAMES <= successful, f"required syscalls not successful in child trace: {ALLOW_NAMES-successful}"
        assert successful <= ALLOW_NAMES, f"unallowlisted successful child syscalls: {successful-ALLOW_NAMES}"
        denied_rows = [(name, result) for name, result in rows if result.startswith("-1 EPERM")]
        landlock_rows = [(name, result) for name, result in rows if result.startswith("-1 EACCES")]
        assert len(denied_rows) == 7, f"expected exactly 7 seccomp EPERM denials in Writer PID trace: {denied_rows}"
        assert len(landlock_rows) == 1 and landlock_rows[0][0] == "openat", (
            f"expected exactly one Landlock EACCES denial on openat, observed {landlock_rows}"
        )
        denied_names = {name for name, _ in denied_rows}
        assert denied_names <= DENIED_SYSCALL_NAMES, f"unexpected syscall attributed to seccomp denials: {denied_names}"
        denied_categories = [
            {"truncate"},
            {"unlink", "unlinkat"},
            {"rename", "renameat", "renameat2"},
            {"chmod", "fchmodat", "fchmodat2"},
            {"socket"},
            {"fork", "clone", "clone3"},
            {"prctl"},
        ]
        assert all(sum(name in category for name in denied_names) == 1 for category in denied_categories), (
            f"seccomp EPERM calls do not map one-to-one to the seven intended probes: {denied_names}"
        )
