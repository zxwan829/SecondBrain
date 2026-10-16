#!/usr/bin/env python3
"""One-shot, fail-closed driver for the isolated NAS Compose test proposal.

This is not part of production Compose. Running it creates and removes scoped
test assets; the NAS path is deliberately fixed and run-id constrained.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tarfile


BASE = pathlib.Path("/volume1/docker/secondbrain-test/d077-phase1c")
COMPOSE = pathlib.Path(__file__).with_name("compose.nas-isolated.yaml")
HERMES_IMAGE = "nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db"
EXPECTED_HERMES_ID = "sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6"
EXPECTED_HERMES_REVISION = "749220ef0007f8d87bd1531f1c24b0fe93816385"
APP_PASSWORD = "d077-synthetic-owner-password"
HERMES_KEY = "d077-hermes-api-server-synthetic-key"
SOURCE_IMAGE_PREFIX = "secondbrain-d077-core:"
RUN_IMAGE_PREFIX = "sb-d077-core:"
LABEL_TASK = "d077.task=phase1c"
DOCKER_PREFIX = ["docker"]


class SafeFailure(RuntimeError):
    def __init__(self, stage: str, exception_class: str = "RuntimeError"):
        super().__init__("isolated_compose_failed")
        self.stage = stage
        self.exception_class = exception_class


def safe_run_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", value))


def parse_targets(values: list[str]) -> str:
    parsed = []
    for value in values:
        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}:\d{1,5}", value):
            raise ValueError("invalid_target")
        host, port_text = value.split(":", 1)
        address = ipaddress.ip_address(host)
        if (not address.is_private or address.is_loopback or address.is_link_local
                or address.is_multicast or address.is_unspecified
                or not 1 <= int(port_text) <= 65535):
            raise ValueError("invalid_target")
        if value not in parsed:
            parsed.append(value)
    if len(parsed) < 2:
        raise ValueError("two_verified_deny_targets_required")
    return ",".join(parsed)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(args: list[str], *, timeout: int = 90, check: bool = True) -> subprocess.CompletedProcess:
    if args and args[0] == "docker":
        args = [*DOCKER_PREFIX, *args[1:]]
    try:
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise SafeFailure("command_timeout", "TimeoutExpired") from None
    except OSError as exc:
        raise SafeFailure("command_unavailable", type(exc).__name__) from None
    if check and result.returncode:
        raise SafeFailure("command_failed", "CommandError")
    return result


def image_details(image: str) -> dict:
    result = command(["docker", "image", "inspect", image, "--format", "{{json .}}"])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SafeFailure("image_inspect", "InvalidJSON") from None


def verify_export(archive: pathlib.Path, source_sha: str) -> tuple[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise SafeFailure("source_sha", "ValueError")
    if not archive.is_file() or archive.is_symlink():
        raise SafeFailure("archive_preflight", "FileNotFoundError")
    sums = archive.parent / "SHA256SUMS"
    metadata_file = archive.parent / "metadata.json"
    if (not sums.is_file() or sums.is_symlink()
            or not metadata_file.is_file() or metadata_file.is_symlink()):
        raise SafeFailure("archive_manifest", "FileNotFoundError")
    rows = [line.split(maxsplit=1) for line in sums.read_text(encoding="ascii").splitlines()
            if line.strip()]
    if (len(rows) != 1 or len(rows[0]) != 2 or rows[0][1].lstrip("* ") != archive.name
            or rows[0][0] != sha256_file(archive)):
        raise SafeFailure("archive_checksum", "ChecksumMismatch")
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SafeFailure("archive_metadata", "InvalidJSON") from None
    if (metadata.get("source_sha") != source_sha or metadata.get("os") != "linux"
            or metadata.get("architecture") != "amd64"
            or metadata.get("test_task") != "d077-phase1c"):
        raise SafeFailure("archive_identity", "IdentityMismatch")
    if archive.stat().st_size > 4 * 1024 * 1024 * 1024:
        raise SafeFailure("archive_size", "SizeLimitExceeded")
    try:
        with tarfile.open(archive, mode="r:") as image_tar:
            member = image_tar.getmember("manifest.json")
            if member.size > 1024 * 1024:
                raise SafeFailure("archive_manifest_size", "SizeLimitExceeded")
            manifest = json.loads(image_tar.extractfile(member).read())
    except (tarfile.TarError, KeyError, AttributeError, json.JSONDecodeError):
        raise SafeFailure("archive_manifest", "InvalidArchive") from None
    if (len(manifest) != 1 or manifest[0].get("RepoTags") != [f"{SOURCE_IMAGE_PREFIX}{source_sha}"]):
        raise SafeFailure("archive_tags", "IdentityMismatch")
    return source_sha, metadata.get("image_id", "")


def stage_export_bundle(source_archive: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    """Copy one verified archive and its two sidecars into the private run root."""
    if source_archive.is_symlink() or not source_archive.is_file():
        raise SafeFailure("archive_preflight", "FileNotFoundError")
    for name in ("SHA256SUMS", "metadata.json"):
        sidecar = source_archive.parent / name
        if sidecar.is_symlink() or not sidecar.is_file():
            raise SafeFailure("archive_manifest", "FileNotFoundError")
        shutil.copyfile(sidecar, destination / name)
        (destination / name).chmod(0o400)
    staged_archive = destination / "core-linux-amd64.tar"
    shutil.copyfile(source_archive, staged_archive)
    staged_archive.chmod(0o400)
    return staged_archive


def prepare_core_data(data: pathlib.Path, *, memory_enabled: bool) -> None:
    subdirs = ["home", "review", "knowledge", "promote", "raw"]
    if memory_enabled:
        subdirs.append("memory")
    for subdir in subdirs:
        (data / subdir).mkdir(mode=0o700)
    for filename, content in (("app-password", APP_PASSWORD), ("hermes-key", HERMES_KEY)):
        target = data / filename
        target.write_text(content + "\n", encoding="utf-8")
        target.chmod(0o600)


def prepare_root(run_id: str, harness_source: pathlib.Path, deny_targets: str,
                 core_image: str) -> pathlib.Path:
    if not safe_run_id(run_id):
        raise SafeFailure("run_id", "ValueError")
    if os.geteuid() == 0:
        raise SafeFailure("runtime_uid", "RootNotAllowed")
    if not harness_source.is_file() or harness_source.is_symlink():
        raise SafeFailure("harness_source", "FileNotFoundError")
    if not BASE.is_dir() or BASE.is_symlink():
        raise SafeFailure("approved_parent_preflight", "DirectoryNotFound")
    root = BASE / run_id
    if root.exists() or root.is_symlink() or root.resolve(strict=False).parent != BASE.resolve():
        raise SafeFailure("run_root_preflight", "PathConflict")
    root.mkdir(mode=0o700)
    try:
        for name in ("hermes-home", "core-enabled", "core-disabled"):
            (root / name).mkdir(mode=0o700)
        (root / "harness.py").write_bytes(harness_source.read_bytes())
        (root / "harness.py").chmod(0o400)
        prepare_core_data(root / "core-enabled", memory_enabled=True)
        prepare_core_data(root / "core-disabled", memory_enabled=False)
        profile = root / "hermes-home" / "config.yaml"
        profile.write_text(
            "model:\n  provider: custom\n  default: d077-deterministic-stub\n"
            "  base_url: http://stub:19002/v1\n  api_key: d077-hermes-synthetic-api-key-only\n"
            "  api_mode: chat_completions\nmemory:\n  memory_enabled: false\n"
            "  user_profile_enabled: false\nagent:\n  enabled_toolsets: []\n"
            "  max_iterations: 1\n  max_tool_calls: 1\n"
            "auxiliary:\n  background_review:\n    enabled: false\nmcp_servers: {}\n",
            encoding="utf-8")
        profile.chmod(0o600)
        env = {
            "D077_RUN_ID": run_id,
            "D077_RUN_ROOT": str(root),
            "D077_CORE_IMAGE": core_image,
            "D077_UID": str(os.getuid()),
            "D077_GID": str(os.getgid()),
            "D077_DENY_EGRESS_TARGETS": deny_targets,
        }
        env_file = root / "compose.env"
        env_file.write_text("".join(f"{key}={value}\n" for key, value in env.items()), encoding="utf-8")
        env_file.chmod(0o600)
        return root
    except Exception:
        if root.resolve(strict=False).parent == BASE.resolve() and root.name == run_id:
            shutil.rmtree(root)
        raise


def compose_args(project: str, env_file: pathlib.Path) -> list[str]:
    return ["docker", "compose", "--project-name", project, "--env-file", str(env_file),
            "--file", str(COMPOSE)]


def validate_compose(project: str, env_file: pathlib.Path, root: pathlib.Path) -> None:
    result = command(compose_args(project, env_file) + ["config", "--format", "json"])
    try:
        config = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SafeFailure("compose_config", "InvalidJSON") from None
    if set(config.get("services", {})) != {"hermes", "stub", "core", "core-off"}:
        raise SafeFailure("compose_services", "IdentityMismatch")
    if config.get("networks", {}).get("isolated", {}).get("internal") is not True:
        raise SafeFailure("compose_network", "IsolationMismatch")
    for service in config["services"].values():
        if service.get("ports") or service.get("build") or service.get("privileged"):
            raise SafeFailure("compose_surface", "IsolationMismatch")
        for mount in service.get("volumes", []):
            source = pathlib.Path(mount.get("source", "")).resolve(strict=False)
            if root.resolve() not in source.parents and source != root.resolve():
                raise SafeFailure("compose_mount", "IsolationMismatch")
        if service.get("network_mode") == "host" or set(service.get("networks", {})) != {"isolated"}:
            raise SafeFailure("compose_network_membership", "IsolationMismatch")
    if config["services"]["hermes"].get("image") != HERMES_IMAGE:
        raise SafeFailure("compose_hermes_image", "IdentityMismatch")


def filtered_output(result: subprocess.CompletedProcess) -> None:
    allowed = ("D077_HARNESS_FAILURE ", "D077_NETWORK_PREFLIGHT ",
               "D077_HERMES_NETWORK_PREFLIGHT ", "D077_ENABLED_RESULT ",
               "D077_FLAGS_OFF_RESULT ")
    for line in result.stdout.splitlines():
        if line.startswith(allowed):
            print(line, flush=True)


def compose_exec(base: list[str], service: str, mode: str, *, timeout: int = 150) -> None:
    python = "/opt/hermes/.venv/bin/python3" if service == "hermes" else "python"
    result = command(base + ["exec", "--no-TTY", service, python, "/tmp/harness.py", mode],
                     timeout=timeout, check=False)
    filtered_output(result)
    if result.returncode:
        raise SafeFailure(f"{service}_{mode[2:].replace('-', '_')}", "PeerFailed")


def inspect_runtime_peer(base: list[str], service: str, expected_network_id: str,
                         expected_memory: int, expected_nano_cpus: int, expected_pids: int,
                         expected_image: str, run_id: str) -> None:
    listing = command(base + ["ps", "--quiet", service])
    ids = listing.stdout.splitlines()
    if len(ids) != 1:
        raise SafeFailure("runtime_peer_count", "IsolationMismatch")
    details = json.loads(command(["docker", "inspect", ids[0], "--format", "{{json .}}"] ).stdout)
    config, host = details.get("Config", {}), details.get("HostConfig", {})
    networks = details.get("NetworkSettings", {}).get("Networks", {})
    labels = config.get("Labels") or {}
    if (config.get("User") != f"{os.getuid()}:{os.getgid()}"
            or config.get("Image") != expected_image
            or labels.get("d077.task") != "phase1c" or labels.get("d077.run") != run_id
            or host.get("ReadonlyRootfs") is not True
            or host.get("Privileged") is True or host.get("CapDrop") != ["ALL"]
            or "no-new-privileges:true" not in host.get("SecurityOpt", [])
            or host.get("Memory") != expected_memory
            or host.get("NanoCpus") != expected_nano_cpus
            or host.get("PidsLimit") != expected_pids
            or host.get("PortBindings") not in (None, {})
            or len(networks) != 1
            or next(iter(networks.values())).get("NetworkID") != expected_network_id):
        raise SafeFailure("runtime_peer_assertions", "IsolationMismatch")


def docker_route_conflict(network: dict) -> bool:
    candidate = [ipaddress.ip_network(item["Subnet"], strict=False)
                 for config in network.get("IPAM", {}).get("Config", [])
                 for item in [config] if item.get("Subnet")]
    if not candidate:
        return True
    networks = command(["docker", "network", "ls", "-q"], check=False).stdout.splitlines()
    # The candidate network is included in this list; compare every subnet from
    # other networks, excluding the exact created network ID.
    for network_id in networks:
        if network_id == network.get("Id"):
            continue
        inspected = command(["docker", "network", "inspect", network_id,
                             "--format", "{{json .IPAM.Config}}"], check=False)
        if inspected.returncode:
            continue
        try:
            configs = json.loads(inspected.stdout)
        except json.JSONDecodeError:
            raise SafeFailure("network_inventory", "InvalidJSON") from None
        for config in configs or []:
            subnet = config.get("Subnet")
            if subnet and any(left.version == right.version and left.overlaps(right)
                              for left in candidate for right in [ipaddress.ip_network(subnet, strict=False)]):
                return True
    routes = command(["ip", "-j", "route", "show", "table", "all"], check=False)
    if routes.returncode == 0:
        try:
            route_rows = json.loads(routes.stdout)
        except json.JSONDecodeError:
            raise SafeFailure("host_route_inventory", "InvalidJSON") from None
        for route in route_rows:
            destination = route.get("dst")
            if not destination or destination == "default":
                continue
            try:
                route_network = ipaddress.ip_network(destination, strict=False)
            except ValueError:
                continue
            if any(left == route_network for left in candidate):
                continue
            if any(left.version == route_network.version and left.overlaps(route_network)
                   for left in candidate):
                return True
    else:
        raise SafeFailure("host_route_inventory", "RouteCommandUnavailable")
    return False


def owned_ids(kind: str, run_id: str) -> list[str]:
    docker_kind = {"containers": "container", "networks": "network"}[kind]
    all_flag = ["-a"] if docker_kind == "container" else []
    result = command(["docker", docker_kind, "ls", *all_flag, "-q", "--filter", f"label={LABEL_TASK}",
                      "--filter", f"label=d077.run={run_id}"], check=False)
    return [item for item in result.stdout.splitlines() if re.fullmatch(r"[0-9a-f]{12,64}", item)]


def cleanup(run_id: str, image_tag: str, root: pathlib.Path | None,
            loaded_source_tag: str | None) -> None:
    # Query explicit labels and inspect each resource before removing its ID.
    for kind in ("container", "network"):
        plural = "containers" if kind == "container" else "networks"
        ids = owned_ids(plural, run_id)
        approved = []
        for resource_id in ids:
            inspect = command(["docker", kind, "inspect", resource_id, "--format",
                               '{{index .Config.Labels "d077.task"}}|{{index .Config.Labels "d077.run"}}']
                              if kind == "container" else
                              ["docker", kind, "inspect", resource_id, "--format",
                               '{{index .Labels "d077.task"}}|{{index .Labels "d077.run"}}'], check=False)
            if inspect.returncode == 0 and inspect.stdout.strip() == f"phase1c|{run_id}":
                approved.append(resource_id)
            else:
                raise SafeFailure("cleanup_label_check", "LabelMismatch")
        if approved:
            command(["docker", "rm", "-f", *approved] if kind == "container"
                    else ["docker", "network", "rm", *approved], timeout=60)
        if owned_ids(plural, run_id):
            raise SafeFailure("cleanup_inventory", "ResidualAssets")
    for tag in (image_tag, loaded_source_tag):
        if tag:
            result = command(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], check=False)
            if result.returncode == 0:
                command(["docker", "image", "rm", tag], timeout=60)
                if command(["docker", "image", "inspect", tag], check=False).returncode == 0:
                    raise SafeFailure("cleanup_image_inventory", "ResidualAssets")
    if root is not None and root.exists():
        if root.parent.resolve() != BASE.resolve() or root.name != run_id or root.is_symlink():
            raise SafeFailure("cleanup_path_check", "PathConflict")
        shutil.rmtree(root)
        if root.exists():
            raise SafeFailure("cleanup_path_inventory", "ResidualAssets")


def run_once(args: argparse.Namespace) -> None:
    run_id = args.run_id
    if not safe_run_id(run_id):
        raise SafeFailure("run_id", "ValueError")
    # Validate the effective Docker socket permission before creating the run
    # directory or importing/tagging any image. This can use an existing
    # command-scoped `sudo -n` grant, never sudo for this Python process.
    if command(["docker", "version", "--format", "{{.Server.Version}}"], check=False).returncode:
        raise SafeFailure("docker_access_preflight", "PermissionDenied")
    deny_targets = parse_targets(args.deny_target)
    source_sha, expected_image_id = verify_export(args.archive, args.source_sha)
    source_tag = f"{SOURCE_IMAGE_PREFIX}{source_sha}"
    run_tag = f"{RUN_IMAGE_PREFIX}{run_id}"
    if command(["docker", "image", "inspect", run_tag], check=False).returncode == 0:
        raise SafeFailure("run_image_tag_preflight", "PathConflict")
    source_exists = command(["docker", "image", "inspect", source_tag], check=False).returncode == 0
    loaded_by_run = not source_exists
    try:
        hermes = image_details(HERMES_IMAGE)
    except Exception:
        raise SafeFailure("hermes_image_inspect", "ImageUnavailable") from None
    hermes_labels = hermes.get("Config", {}).get("Labels") or {}
    if (hermes.get("Id") != EXPECTED_HERMES_ID or hermes.get("Os") != "linux"
            or hermes.get("Architecture") != "amd64"
            or hermes_labels.get("org.opencontainers.image.revision") != EXPECTED_HERMES_REVISION):
        raise SafeFailure("hermes_image_identity", "IdentityMismatch")
    root = prepare_root(run_id, args.harness_source, deny_targets, run_tag)
    staged_archive = root / "core-linux-amd64.tar"
    try:
        staged_archive = stage_export_bundle(args.archive, root)
        if verify_export(staged_archive, source_sha) != (source_sha, expected_image_id):
            raise SafeFailure("staged_archive_identity", "IdentityMismatch")
    except Exception:
        shutil.rmtree(root)
        raise
    project = f"sb-d077-phase1c-{run_id}"
    base = compose_args(project, root / "compose.env")
    success_record = None
    try:
        if loaded_by_run:
            command(["docker", "load", "--input", str(staged_archive)], timeout=300)
        core = image_details(source_tag)
        labels = core.get("Config", {}).get("Labels") or {}
        if (core.get("Id") != expected_image_id or core.get("Os") != "linux"
                or core.get("Architecture") != "amd64"
                or labels.get("org.opencontainers.image.revision") != source_sha
                or labels.get("com.secondbrain.test.task") != "d077-phase1c"):
            raise SafeFailure("loaded_core_identity", "IdentityMismatch")
        command(["docker", "image", "tag", source_tag, run_tag])
        if (command(["docker", "container", "ls", "-aq", "--filter",
                     f"label=com.docker.compose.project={project}"], check=False).stdout.strip()
                or command(["docker", "network", "ls", "-q", "--filter",
                            f"label=com.docker.compose.project={project}"], check=False).stdout.strip()):
            raise SafeFailure("project_preflight", "ProjectExists")
        validate_compose(project, root / "compose.env", root)
        command(base + ["up", "--detach", "hermes", "stub", "core"])
        created = True
        # Compose-generated container/network labels and limits are checked
        # before any run; Core performs service, public, NAS and router probes.
        inspect_network = command(["docker", "network", "ls", "-q", "--filter",
                                  f"label=com.docker.compose.project={project}"])
        if len(inspect_network.stdout.splitlines()) != 1:
            raise SafeFailure("network_inventory", "IsolationMismatch")
        network_id = inspect_network.stdout.strip()
        network = json.loads(command(["docker", "network", "inspect", network_id,
                                      "--format", "{{json .}}"] ).stdout)
        endpoint_names = {row.get("Name", "").removeprefix(f"{project}-")
                          for row in network.get("Containers", {}).values()}
        if (not network.get("Internal") or network.get("Options", {}).get("com.docker.network.bridge.name")
                or endpoint_names != {"hermes-1", "stub-1", "core-1"}
                or docker_route_conflict(network)):
            raise SafeFailure("network_internal_assertion", "IsolationMismatch")
        inspect_runtime_peer(base, "hermes", network_id, 1536 * 1024 * 1024,
                             1_000_000_000, 128, HERMES_IMAGE, run_id)
        inspect_runtime_peer(base, "stub", network_id, 256 * 1024 * 1024,
                             250_000_000, 32, run_tag, run_id)
        inspect_runtime_peer(base, "core", network_id, 768 * 1024 * 1024,
                             750_000_000, 96, run_tag, run_id)
        compose_exec(base, "core", "--network-preflight", timeout=120)
        compose_exec(base, "hermes", "--hermes-network-preflight", timeout=20)
        compose_exec(base, "stub", "--egress-probe", timeout=20)
        compose_exec(base, "core", "--enabled-scenario", timeout=600)
        command(base + ["stop", "core"], timeout=30)
        command(base + ["up", "--detach", "core-off"], timeout=60)
        inspect_runtime_peer(base, "core-off", network_id, 768 * 1024 * 1024,
                             750_000_000, 96, run_tag, run_id)
        compose_exec(base, "core-off", "--egress-probe", timeout=20)
        compose_exec(base, "core-off", "--flags-off", timeout=180)
        success_record = {"status": "PASS", "hermes_image_id": hermes["Id"],
                          "core_image_id": core["Id"], "core_source_sha": source_sha,
                          "network": "single_internal", "provider": "deterministic_stub_only",
                          "cleanup": "PASS"}
    finally:
        cleanup(run_id, run_tag, root if root.exists() else None,
                None if source_exists else source_tag)
    print("D077_V0215_RESULT " + json.dumps(success_record, sort_keys=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--archive", required=True, type=pathlib.Path)
    parser.add_argument("--harness-source", required=True, type=pathlib.Path)
    parser.add_argument("--deny-target", action="append", default=[])
    parser.add_argument("--docker-sudo", action="store_true",
                        help="use the existing non-interactive sudo grant for /usr/local/bin/docker")
    args = parser.parse_args()
    global DOCKER_PREFIX
    if args.docker_sudo:
        DOCKER_PREFIX = ["sudo", "-n", "/usr/local/bin/docker"]
    signal.signal(signal.SIGALRM, lambda _signum, _frame: (_ for _ in ()).throw(
        SafeFailure("overall_timeout", "TimeoutExpired")))
    signal.alarm(20 * 60)
    try:
        run_once(args)
        return 0
    except SafeFailure as exc:
        print(json.dumps({"status": "FAILED", "stage": exc.stage,
                          "exception_class": exc.exception_class}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "stage": "unexpected",
                          "exception_class": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
