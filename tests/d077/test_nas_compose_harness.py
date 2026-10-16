#!/usr/bin/env python3
"""Offline safety checks for the future NAS Compose driver."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest
import io
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nas_compose_harness as harness  # noqa: E402


class NasComposeHarnessTests(unittest.TestCase):
    def test_run_id_is_a_limited_compose_project_component(self):
        self.assertTrue(harness.safe_run_id("run-20261016-a1"))
        for invalid in ("../run", "UpperCase", "run_id", "-run", "x" * 33):
            self.assertFalse(harness.safe_run_id(invalid))

    def test_deny_targets_require_two_valid_unique_ip_ports(self):
        self.assertEqual(
            harness.parse_targets(["192.168.3.1:443", "192.168.3.27:5001", "192.168.3.1:443"]),
            "192.168.3.1:443,192.168.3.27:5001",
        )
        for targets in ([], ["192.168.3.1:443"], ["192.168.3.999:443", "192.168.3.27:5001"],
                        ["192.168.3.1:0", "192.168.3.27:5001"]):
            with self.assertRaises(ValueError):
                harness.parse_targets(targets)

    def test_export_archive_requires_matching_checksum_and_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = pathlib.Path(temporary)
            archive = folder / "core-linux-amd64.tar"
            source_sha = "a" * 40
            manifest = json.dumps([{"Config": "config.json", "RepoTags": [
                f"secondbrain-d077-core:{source_sha}"], "Layers": ["layer/layer.tar"]}]).encode()
            with tarfile.open(archive, "w") as image_tar:
                info = tarfile.TarInfo("manifest.json")
                info.size = len(manifest)
                image_tar.addfile(info, io.BytesIO(manifest))
            (folder / "SHA256SUMS").write_text(
                f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="ascii")
            (folder / "metadata.json").write_text(json.dumps({
                "source_sha": source_sha,
                "os": "linux",
                "architecture": "amd64",
                "test_task": "d077-phase1c",
                "image_id": "sha256:" + "b" * 64,
            }), encoding="utf-8")

            stage = folder / "run-root"
            stage.mkdir()
            staged = harness.stage_export_bundle(archive, stage)
            result = harness.verify_export(staged, source_sha)

            self.assertEqual(result, (source_sha, "sha256:" + "b" * 64))
            self.assertTrue((stage / "SHA256SUMS").is_file())
            self.assertTrue((stage / "metadata.json").is_file())
            staged.chmod(0o600)
            staged.write_bytes(b"changed")
            with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
                harness.verify_export(staged, source_sha)

    def test_flags_off_data_root_does_not_precreate_memory_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            enabled = root / "enabled"
            disabled = root / "disabled"
            enabled.mkdir()
            disabled.mkdir()

            harness.prepare_core_data(enabled, memory_enabled=True)
            harness.prepare_core_data(disabled, memory_enabled=False)

            self.assertTrue((enabled / "memory").is_dir())
            self.assertFalse((disabled / "memory").exists())

    def test_sudo_mode_wraps_only_docker_cli_commands(self):
        original_prefix = harness.DOCKER_PREFIX
        try:
            harness.DOCKER_PREFIX = ["sudo", "-n", "/usr/local/bin/docker"]
            with mock.patch.object(harness.subprocess, "run") as run:
                run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                harness.command(["docker", "version"])
                harness.command(["ip", "-j", "route"])

            self.assertEqual(run.call_args_list[0].args[0],
                             ["sudo", "-n", "/usr/local/bin/docker", "version"])
            self.assertEqual(run.call_args_list[1].args[0], ["ip", "-j", "route"])
        finally:
            harness.DOCKER_PREFIX = original_prefix


if __name__ == "__main__":
    unittest.main()
