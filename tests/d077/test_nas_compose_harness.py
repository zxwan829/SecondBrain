#!/usr/bin/env python3
"""Offline safety checks for the future NAS Compose driver."""
from __future__ import annotations

import hashlib
import ipaddress
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
                harness.command(["ip", "route", "show", "table", "all"])

            self.assertEqual(run.call_args_list[0].args[0],
                             ["sudo", "-n", "/usr/local/bin/docker", "version"])
            self.assertEqual(run.call_args_list[1].args[0], ["ip", "route", "show", "table", "all"])
        finally:
            harness.DOCKER_PREFIX = original_prefix

    def test_old_iproute_text_route_inventory_detects_overlap_and_unknown(self):
        routes, tables = harness.parse_route_inventory(
            "default via 192.0.2.1 dev eth0 table main\n"
            "throw 172.16.0.0/12 table policy\n"
            "unicast 172.30.0.0/16 dev docker-test table main\n"
            "local 127.0.0.1 dev lo table local\n", 4)
        route_networks = [network for network, _device in routes]
        self.assertEqual(tables, {"main", "policy", "local"})
        self.assertTrue(any(route.overlaps(ipaddress.ip_network("172.30.0.0/24"))
                            for route in route_networks))
        self.assertFalse(any(route.overlaps(ipaddress.ip_network("10.50.0.0/24"))
                             for route in route_networks))
        self.assertNotIn(ipaddress.ip_network("172.16.0.0/12"), route_networks)
        with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
            harness.parse_route_inventory("unrecognized route row\n", 4)

    def test_exact_candidate_bridge_route_is_expected_but_other_exact_route_conflicts(self):
        network = ipaddress.ip_network("172.30.0.0/24")
        self.assertFalse(harness.has_host_route_conflict(
            [network], [(network, "docker-aabbccdd")], {"docker-aabbccdd"}))
        self.assertTrue(harness.has_host_route_conflict(
            [network], [(network, "eth0")], {"docker-aabbccdd"}))

    def test_policy_rule_table_missing_from_route_inventory_fails_closed(self):
        with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
            harness.validate_rule_tables("100: from 192.0.2.1 lookup missing-table\n", {"main"})
        with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
            harness.validate_rule_tables("unrecognized rule row\n", {"main"})

    def test_docker_network_inspect_error_fails_closed(self):
        results = [
            mock.Mock(returncode=0, stdout="other-network\n"),
            mock.Mock(returncode=1, stdout="", stderr="redacted"),
        ]
        with mock.patch.object(harness, "command", side_effect=results):
            with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
                harness.docker_route_conflict({"Id": "a" * 64, "Driver": "bridge", "IPAM": {"Config": [
                    {"Subnet": "172.30.0.0/24"}]}})

    def test_cgroup_v1_support_requires_cpu_quota_pids_and_memory_mounts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            controllers = "#subsys_name hierarchy num_cgroups enabled\n" + "\n".join(
                f"{name} 1 1 1" for name in ("cpu", "pids", "memory"))
            mount_rows = []
            for name, files in {
                "cpu": ("cpu.cfs_quota_us", "cpu.cfs_period_us"),
                "pids": ("pids.max",),
                "memory": ("memory.limit_in_bytes",),
            }.items():
                mount = root / name
                mount.mkdir()
                for filename in files:
                    (mount / filename).touch()
                mount_rows.append(
                    f"1 0 0:1 / {mount} rw - cgroup cgroup rw,{name}")
            harness.verify_cgroup_v1_support(controllers, "\n".join(mount_rows), [])
            with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
                harness.verify_cgroup_v1_support(controllers, "\n".join(mount_rows[:1]), [])
            with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
                harness.verify_cgroup_v1_support(
                    controllers, "\n".join(mount_rows), ["WARNING: No cpu cfs quota support"])

    def test_runtime_limits_must_match_effective_cgroup_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            paths = {name: root / name for name in ("cpu", "pids", "memory")}
            for path in paths.values():
                path.mkdir()
            (paths["cpu"] / "cpu.cfs_quota_us").write_text("75000")
            (paths["cpu"] / "cpu.cfs_period_us").write_text("100000")
            (paths["pids"] / "pids.max").write_text("96")
            (paths["memory"] / "memory.limit_in_bytes").write_text(str(768 * 1024 * 1024))
            with mock.patch.object(harness, "_cgroup_controller_path",
                                   side_effect=lambda _pid, controller: paths[controller]):
                harness.verify_runtime_cgroup_limits(
                    {"State": {"Pid": 123}}, 768 * 1024 * 1024, 750_000_000, 96)
                (paths["pids"] / "pids.max").write_text("max")
                with self.assertRaisesRegex(harness.SafeFailure, "isolated_compose_failed"):
                    harness.verify_runtime_cgroup_limits(
                        {"State": {"Pid": 123}}, 768 * 1024 * 1024, 750_000_000, 96)

    def test_created_approved_test_directories_are_private_and_removable(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(harness, "BASE", pathlib.Path(temporary) / "secondbrain-test" / "d077-phase1c"):
                created = harness.ensure_test_base()
                self.assertEqual(created, [harness.BASE.parent, harness.BASE])
                self.assertEqual(harness.BASE.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(harness.BASE.stat().st_mode & 0o777, 0o700)
                harness.remove_created_dirs(created)
                self.assertFalse(harness.BASE.parent.exists())


if __name__ == "__main__":
    unittest.main()
