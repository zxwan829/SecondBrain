"""Bounded synthetic Landlock enforcement check for Linux candidate review."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


HELPER = Path(__file__).with_name("d090_landlock_process_helper.py")


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux Landlock")
def test_landlock_abi_capabilities_fd_allowlist_and_synthetic_boundary():
    with tempfile.TemporaryDirectory(prefix="secondbrain-d090-landlock-") as temporary:
        root = Path(temporary)
        stage = root / "stage"
        publish = root / "publish"
        protected = root / "protected"
        for directory in (stage, publish, protected):
            directory.mkdir(mode=0o700)
        (stage / "seed.txt").write_text("synthetic seed", encoding="utf-8")
        sentinel = protected / "sentinel.txt"
        sentinel.write_text("synthetic protected sentinel", encoding="utf-8")

        # Pass only the explicit staging descriptor; close_fds closes any others.
        allowed_fd = os.open(stage / "seed.txt", os.O_RDONLY | os.O_CLOEXEC)
        try:
            environment = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "SB_D090_LANDLOCK_HELPER": "synthetic-only",
            }
            process = subprocess.run(
                [sys.executable, str(HELPER), str(root), str(allowed_fd)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                close_fds=True,
                pass_fds=(allowed_fd,),
                env=environment,
                timeout=8,
                check=False,
            )
        finally:
            os.close(allowed_fd)

        if process.returncode == 77 and process.stdout.startswith("SKIP "):
            pytest.skip(process.stdout.strip())
        assert process.returncode == 0, (
            f"synthetic Landlock helper failed rc={process.returncode}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
        assert "PASS abi=" in process.stdout
        assert "DENIED open protected file for write" in process.stdout
        assert "DENIED truncate protected file" in process.stdout
        assert "DENIED unlink protected file" in process.stdout
        assert "DENIED rename protected file" in process.stdout
        assert "metadata=NOT_ENFORCED_BY_LANDLOCK" in process.stdout
        assert sentinel.read_text(encoding="utf-8") == "synthetic protected sentinel"
        assert sorted(path.name for path in publish.iterdir()) == ["published.md"]
        assert (publish / "published.md").read_bytes() == b"synthetic candidate"
