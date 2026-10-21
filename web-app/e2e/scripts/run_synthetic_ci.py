#!/usr/bin/env python3
"""Run an isolated Core + Vite + Playwright acceptance and clean its temp state."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import http.cookiejar
import argparse
import datetime
import struct
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "web-app" / "secondbrain-core"
FRONTEND = ROOT / "web-app" / "secondbrain-frontend"
E2E = Path(__file__).resolve().parents[1]
ARTIFACTS = E2E / "artifacts-sanitized"
CORE_URL = ""
WEB_URL = ""
OPAQUE_ID = __import__("re").compile(r"(?i)\b[0-9a-f]{32}\b")
REPORT_ID = __import__("re").compile(r"(?i)\b(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b")
SENSITIVE_KEYS = ("header", "cookie", "authorization", "bearer", "token", "credential", "passphrase",
                  "postdata", "post_data", "body", "content", "snapshot", "params", "value", "text",
                  "message", "resource", "payload", "stack", "source")
TRACE_SAFE_KEYS = {"type", "method", "url", "request", "response", "status", "statusCode",
                   "startTime", "endTime", "duration", "resourceType", "isNavigationRequest"}
FAILURE_SCREENSHOT_NAME = "test-failed-1.png"
# These are the exact Playwright 1.56.1 output directory names for the sole
# approved test file/title and its three fixed viewport cases. Playwright
# sanitizes and hash-truncates the long title; a substring/viewport match would
# broaden the screenshot allowlist to unrelated tests.
FAILURE_SCREENSHOT_DIR_VIEWPORTS = {
    "inbox-browser-explicit-Inb-3c225-ection-at-desktop-1440x1000": "desktop-1440x1000",
    "inbox-browser-explicit-Inb-33ff6-otection-at-tablet-820x1180": "tablet-820x1180",
    "inbox-browser-explicit-Inb-7095f-rotection-at-mobile-390x844": "mobile-390x844",
}
FAILURE_DIAGNOSTIC_STAGES = {
    "login", "session", "first_submit", "retry", "conflict",
    "ordinary_chat", "source_protection", "viewport_layout",
}
FAILURE_DIAGNOSTIC_CODES = {"assertion_failed", "timeout", "test_error"}
MAX_FAILURE_DIAGNOSTIC_BYTES = 512
MAX_FAILURE_SCREENSHOTS = len(FAILURE_SCREENSHOT_DIR_VIEWPORTS)
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
MAX_SCREENSHOT_WIDTH = 2048
MAX_SCREENSHOT_HEIGHT = 1600
ALLOW_FAILURE_SCREENSHOT_PUBLICATION = False


def ephemeral_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def clean_trace_value(value):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            lowered = str(key).lower()
            if key not in TRACE_SAFE_KEYS or any(word in lowered for word in SENSITIVE_KEYS):
                continue
            if lowered in {"url", "requesturl"} and isinstance(child, str):
                parts = urlsplit(child)
                if parts.scheme and parts.hostname not in {"127.0.0.1", "localhost"}:
                    result[key] = "<blocked-origin>"
                else:
                    result[key] = OPAQUE_ID.sub("<opaque-id>", parts.path or child.split("?", 1)[0])
                continue
            result[key] = clean_trace_value(child)
        return result
    if isinstance(value, list):
        return [clean_trace_value(item) for item in value]
    if isinstance(value, str):
        return OPAQUE_ID.sub("<opaque-id>", value)
    return value


def sanitize_trace_archives(artifacts_root: Path) -> None:
    for archive in artifacts_root.rglob("trace.zip"):
        temporary = archive.with_suffix(".sanitized.zip")
        with zipfile.ZipFile(archive, "r") as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                name = item.filename
                # Trace archives may contain DOM snapshots, screenshots, source
                # files, request/response bodies, and attachments. Publish only
                # the two structured metadata streams; screenshot/report
                # attachments are deliberately withheld because image redaction
                # cannot be proven by this sanitizer.
                if name not in {"trace.trace", "trace.network"}:
                    continue
                data = source.read(item)
                if name.endswith(("trace.trace", "trace.network", "trace.stacks")):
                    rows = []
                    for line in data.decode("utf-8", "replace").splitlines():
                        try:
                            rows.append(json.dumps(clean_trace_value(json.loads(line)), separators=(",", ":")))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                    data = ("\n".join(rows) + "\n").encode()
                target.writestr(name, data)
        os.chmod(temporary, 0o600)
        temporary.replace(archive)


def _sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if not parts.scheme or not parts.netloc:
        return OPAQUE_ID.sub("<opaque-id>", value.split("?", 1)[0].split("#", 1)[0])
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:
        return "<redacted-url>"
    if host not in {"127.0.0.1", "localhost"}:
        return "<blocked-origin>"
    netloc = f"[{host}]" if host and ":" in host else str(host)
    if port is not None:
        netloc += f":{port}"
    return f"{parts.scheme}://{netloc}{OPAQUE_ID.sub('<opaque-id>', parts.path)}"


def _sanitize_junit(path: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] in {"system-out", "system-err"}:
                parent.remove(child)
        for child in parent:
            if child.tag.rsplit("}", 1)[-1] in {"failure", "error"}:
                child.attrib.clear()
                child.set("message", "failure details withheld")
                child.text = ""
        for key, value in tuple(parent.attrib.items()):
            if key.lower() in {"url", "requesturl"}:
                parent.attrib[key] = _sanitize_url(value)
            else:
                parent.attrib[key] = REPORT_ID.sub("<opaque-id>", value)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _sanitize_request_metadata(path: Path) -> None:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise RuntimeError("request metadata schema rejected")
    safe_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("request metadata row rejected")
        safe_entries.append({
            "method": str(entry.get("method", ""))[:12],
            "path": _sanitize_url(str(entry.get("path", ""))),
            "status": entry.get("status") if isinstance(entry.get("status"), int) else None,
            "elapsed_ms": entry.get("elapsed_ms") if isinstance(entry.get("elapsed_ms"), int) else None,
        })
    path.write_text(json.dumps(safe_entries, indent=2) + "\n", encoding="utf-8")


def _sanitize_run_summary(path: Path) -> None:
    summary = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise RuntimeError("run summary schema rejected")
    allowed = {"result", "core", "web", "browser", "promote_enabled", "hermes",
               "raw_record_count", "journal_files", "knowledge_files", "exit_code",
               "python", "node", "html_report_uploaded", "screenshots_uploaded"}
    path.write_text(json.dumps({key: summary[key] for key in allowed if key in summary}, indent=2) + "\n",
                    encoding="utf-8")


def _validate_failure_diagnostics(value) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > MAX_FAILURE_SCREENSHOTS:
        raise RuntimeError("failure diagnostic schema rejected; upload withheld")
    validated = []
    seen_viewports = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"viewport", "stage", "code"}:
            raise RuntimeError("failure diagnostic fields rejected; upload withheld")
        viewport = entry["viewport"]
        stage = entry["stage"]
        code = entry["code"]
        if (not isinstance(viewport, str) or viewport not in FAILURE_SCREENSHOT_DIR_VIEWPORTS.values()
                or not isinstance(stage, str) or stage not in FAILURE_DIAGNOSTIC_STAGES
                or not isinstance(code, str) or code not in FAILURE_DIAGNOSTIC_CODES
                or viewport in seen_viewports):
            raise RuntimeError("failure diagnostic value rejected; upload withheld")
        seen_viewports.add(viewport)
        validated.append({"viewport": viewport, "stage": stage, "code": code})
    return validated


def _collect_failure_diagnostics(raw_root: Path) -> list[dict[str, str]]:
    junit_path = raw_root / "junit.xml"
    summary_path = raw_root / "run-summary.json"
    if junit_path.is_symlink() or summary_path.is_symlink():
        raise RuntimeError("failure diagnostic source symlink rejected; upload withheld")
    if not junit_path.exists():
        if summary_path.exists():
            if summary_path.stat().st_size > 4096 or not summary_path.is_file():
                raise RuntimeError("failure diagnostic run summary rejected; upload withheld")
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
                raise RuntimeError("failure diagnostic run summary rejected; upload withheld") from error
            if not isinstance(summary, dict):
                raise RuntimeError("failure diagnostic run summary rejected; upload withheld")
            if summary.get("result") == "FAIL":
                raise RuntimeError("failed browser run has no JUnit diagnostics; upload withheld")
        return []
    if not junit_path.is_file():
        raise RuntimeError("failure diagnostic JUnit path rejected; upload withheld")

    try:
        junit = ET.parse(junit_path).getroot()
    except (ET.ParseError, OSError) as error:
        raise RuntimeError("failure diagnostic JUnit rejected; upload withheld") from error
    failed_cases = sum(
        1 for element in junit.iter()
        if element.tag.rsplit("}", 1)[-1] == "testcase"
        and any(child.tag.rsplit("}", 1)[-1] in {"failure", "error"} for child in element)
    )
    if summary_path.exists():
        if summary_path.stat().st_size > 4096 or not summary_path.is_file():
            raise RuntimeError("failure diagnostic run summary rejected; upload withheld")
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
            raise RuntimeError("failure diagnostic run summary rejected; upload withheld") from error
        if not isinstance(summary, dict):
            raise RuntimeError("failure diagnostic run summary rejected; upload withheld")
        if summary.get("result") == "FAIL" and failed_cases == 0:
            raise RuntimeError("failed browser run has no failed testcase diagnostics; upload withheld")

    results = raw_root / "test-results"
    if results.is_symlink():
        raise RuntimeError("failure diagnostic result root symlink rejected; upload withheld")
    diagnostics = []
    if results.exists():
        if not results.is_dir():
            raise RuntimeError("failure diagnostic result root rejected; upload withheld")
        for directory in results.iterdir():
            if directory.is_symlink():
                raise RuntimeError("failure diagnostic directory symlink rejected; upload withheld")
            if not directory.is_dir():
                continue
            source = directory / "failure-summary.json"
            if not source.exists() and not source.is_symlink():
                continue
            viewport = FAILURE_SCREENSHOT_DIR_VIEWPORTS.get(directory.name)
            if viewport is None or source.is_symlink() or not source.is_file():
                raise RuntimeError("failure diagnostic source path rejected; upload withheld")
            if source.stat().st_size > MAX_FAILURE_DIAGNOSTIC_BYTES:
                raise RuntimeError("failure diagnostic size rejected; upload withheld")
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
                raise RuntimeError("failure diagnostic JSON rejected; upload withheld") from error
            if (not isinstance(raw, dict) or set(raw) != {"schema_version", "viewport", "stage", "code"}
                    or type(raw.get("schema_version")) is not int or raw.get("schema_version") != 1
                    or raw.get("viewport") != viewport):
                raise RuntimeError("failure diagnostic source schema rejected; upload withheld")
            diagnostics.append({"viewport": viewport, "stage": raw.get("stage"), "code": raw.get("code")})

    diagnostics = _validate_failure_diagnostics(diagnostics)
    if failed_cases != len(diagnostics):
        raise RuntimeError("failure diagnostics do not match failed test cases; upload withheld")
    viewport_order = {name: index for index, name in enumerate(FAILURE_SCREENSHOT_DIR_VIEWPORTS.values())}
    diagnostics.sort(key=lambda entry: viewport_order[entry["viewport"]])
    return diagnostics


def sanitize_text_reports(artifacts_root: Path, password_path: Path) -> None:
    secret = password_path.read_text(encoding="utf-8").strip().encode()
    for path in artifacts_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "junit.xml":
            _sanitize_junit(path)
        elif path.name == "failure-diagnostics.json":
            normalized = _validate_failure_diagnostics(json.loads(path.read_text(encoding="utf-8")))
            path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
        elif path.name == "local-http-request-metadata.json":
            _sanitize_request_metadata(path)
        elif path.name == "run-summary.json":
            _sanitize_run_summary(path)
        else:
            continue
        content = path.read_bytes()
        if secret and secret in content:
            content = content.replace(secret, b"<redacted>")
            path.write_bytes(content)
        os.chmod(path, 0o600)


def verify_artifact_redaction(artifacts_root: Path, password_path: Path) -> None:
    secret = password_path.read_bytes().strip()
    screenshot_viewports = []
    for path in artifacts_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
            raise RuntimeError("non-allowlisted image artifact found; upload withheld")
        if path.suffix.lower() == ".html":
            raise RuntimeError("active HTML artifact found; upload withheld")
        if path.suffix.lower() == ".png":
            if not is_allowlisted_failure_screenshot(artifacts_root, path):
                raise RuntimeError("non-allowlisted PNG artifact found; upload withheld")
            relative = path.relative_to(artifacts_root)
            screenshot_viewports.append(FAILURE_SCREENSHOT_DIR_VIEWPORTS[relative.parts[1]])
            _verify_sanitized_png(path, secret)
            continue
        blobs = [path.read_bytes()]
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                blobs.extend(archive.read(name) for name in archive.namelist())
        joined = b"\n".join(blobs).lower()
        if any(secret and secret in blob for blob in blobs):
            raise RuntimeError("report redaction check failed; artifacts are withheld")
        if any(marker in joined for marker in (b"sb_app_session", b"authorization:", b"cookie:",
                                                b"set-cookie:", b"synthetic-request-body",
                                                b"synthetic-response-body", b"synthetic-cookie-value",
                                                b"synthetic-query-secret", b"synthetic-auth-secret",
                                                b"synthetic-cookie-header-value")):
            raise RuntimeError("sensitive report marker found; artifacts are withheld")
        if re.search(rb"https?://[^\s\"<>]*\?[^\s\"<>]*", joined):
            raise RuntimeError("URL query data found; artifacts are withheld")
        if re.search(rb"https?://[^/\s@]+@[^/\s]+", joined):
            raise RuntimeError("URL user-info found; artifacts are withheld")
    if len(screenshot_viewports) > MAX_FAILURE_SCREENSHOTS or len(set(screenshot_viewports)) != len(screenshot_viewports):
        raise RuntimeError("duplicate or excessive failure screenshots; upload withheld")
    diagnostic_path = artifacts_root / "failure-diagnostics.json"
    if diagnostic_path.exists() or diagnostic_path.is_symlink():
        if diagnostic_path.is_symlink() or not diagnostic_path.is_file() or diagnostic_path.stat().st_size > MAX_FAILURE_DIAGNOSTIC_BYTES:
            raise RuntimeError("failure diagnostics artifact rejected; upload withheld")
        try:
            _validate_failure_diagnostics(json.loads(diagnostic_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
            raise RuntimeError("failure diagnostics artifact rejected; upload withheld") from error


def _screenshots_are_allowed_for_this_run() -> bool:
    return (ALLOW_FAILURE_SCREENSHOT_PUBLICATION and sys.platform == "linux"
            and os.environ.get("CI") == "true"
            and os.environ.get("GITHUB_ACTIONS") == "true")


def _failure_screenshot_candidates(raw_root: Path) -> list[Path]:
    if not _screenshots_are_allowed_for_this_run():
        return []
    results = raw_root / "test-results"
    if results.is_symlink() or not results.is_dir():
        return []
    candidates = []
    seen_viewports = set()
    for source in results.iterdir():
        # Playwright writes a failure screenshot directly under each test's
        # generated output directory. Do not recurse into trace resources or
        # accept arbitrary attached/user-provided image paths.
        if source.name not in FAILURE_SCREENSHOT_DIR_VIEWPORTS:
            continue
        viewport = FAILURE_SCREENSHOT_DIR_VIEWPORTS.get(source.name)
        if source.is_symlink() or not source.is_dir():
            raise RuntimeError("allowlisted failure result directory rejected; upload withheld")
        screenshot = source / FAILURE_SCREENSHOT_NAME
        if screenshot.is_symlink():
            raise RuntimeError("symlink failure screenshot rejected; upload withheld")
        if screenshot.is_file():
            if viewport in seen_viewports:
                raise RuntimeError("duplicate failure screenshot viewport rejected; upload withheld")
            seen_viewports.add(viewport)
            candidates.append(screenshot)
    if len(candidates) > MAX_FAILURE_SCREENSHOTS:
        raise RuntimeError("failure screenshot count exceeded the fixed synthetic test matrix")
    return candidates


def count_allowlisted_failure_screenshots(raw_root: Path) -> int:
    return len(_failure_screenshot_candidates(raw_root))


def is_allowlisted_failure_screenshot(artifacts_root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(artifacts_root)
    except ValueError:
        return False
    return (len(relative.parts) == 3 and relative.parts[0] == "test-results"
            and relative.parts[1] in FAILURE_SCREENSHOT_DIR_VIEWPORTS
            and relative.parts[2] == FAILURE_SCREENSHOT_NAME)


def _copy_publishable_files(raw_root: Path, staging_root: Path) -> int:
    def copy_regular(source: Path, target: Path) -> None:
        if source.is_symlink():
            raise RuntimeError("symlink report rejected; upload withheld")
        if not source.is_file():
            return
        if not source.resolve().is_relative_to(raw_root.resolve()):
            raise RuntimeError("report escaped the raw artifact root")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    fixed_files = ("junit.xml", "local-http-request-metadata.json", "run-summary.json")
    for relative in fixed_files:
        source = raw_root / relative
        if source.exists() or source.is_symlink():
            copy_regular(source, staging_root / relative)
    results = raw_root / "test-results"
    if results.exists():
        for source in results.rglob("trace.zip"):
            target = staging_root / source.relative_to(raw_root)
            copy_regular(source, target)
    diagnostics = _collect_failure_diagnostics(raw_root)
    diagnostic_viewports = {entry["viewport"] for entry in diagnostics}
    screenshots = _failure_screenshot_candidates(raw_root)
    for source in screenshots:
        viewport = FAILURE_SCREENSHOT_DIR_VIEWPORTS[source.parent.name]
        if viewport not in diagnostic_viewports:
            raise RuntimeError("failure screenshot has no matching fixed diagnostic; upload withheld")
        if not source.resolve().is_relative_to(raw_root.resolve()):
            raise RuntimeError("failure screenshot escaped the current raw run")
        target = staging_root / source.relative_to(raw_root)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if diagnostics:
        diagnostic_path = staging_root / "failure-diagnostics.json"
        diagnostic_path.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
        os.chmod(diagnostic_path, 0o600)
    return len(screenshots)


def _sanitize_failure_screenshots(staging_root: Path) -> None:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("PNG metadata sanitizer unavailable; upload withheld") from error

    for path in staging_root.rglob("*.png"):
        if not is_allowlisted_failure_screenshot(staging_root, path) or path.is_symlink():
            raise RuntimeError("non-allowlisted PNG artifact found; upload withheld")
        if path.stat().st_size > MAX_SCREENSHOT_BYTES:
            raise RuntimeError("failure screenshot exceeds the fixed size limit; upload withheld")
        temporary = path.with_suffix(".sanitized.png")
        try:
            with Image.open(path) as original:
                if original.format != "PNG" or getattr(original, "n_frames", 1) != 1:
                    raise RuntimeError("failure screenshot format rejected; upload withheld")
                width, height = original.size
                if (width <= 0 or height <= 0 or width > MAX_SCREENSHOT_WIDTH
                        or height > MAX_SCREENSHOT_HEIGHT or width * height > 3_200_000):
                    raise RuntimeError("failure screenshot dimensions rejected; upload withheld")
                original.load()
                mode = "RGBA" if "A" in original.getbands() or "transparency" in original.info else "RGB"
                pixels = original.convert(mode)
                # Reconstruct from pixels only. No EXIF, textual chunks, ICC,
                # comments, or other source metadata are passed to the encoder.
                clean = Image.frombytes(mode, pixels.size, pixels.tobytes())
                clean.save(temporary, format="PNG", optimize=False)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _verify_sanitized_png(path: Path, secret: bytes) -> None:
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format != "PNG" or image.info:
                raise RuntimeError("PNG metadata remains after sanitization; upload withheld")
            width, height = image.size
            if (width <= 0 or height <= 0 or width > MAX_SCREENSHOT_WIDTH
                    or height > MAX_SCREENSHOT_HEIGHT or width * height > 3_200_000):
                raise RuntimeError("PNG dimensions rejected; upload withheld")
        data = path.read_bytes()
        chunk_types = []
        cursor = 8
        while cursor + 12 <= len(data):
            length = struct.unpack(">I", data[cursor:cursor + 4])[0]
            end = cursor + 12 + length
            if end > len(data):
                raise RuntimeError("truncated PNG chunk; upload withheld")
            chunk_types.append(data[cursor + 4:cursor + 8])
            cursor = end
        if cursor != len(data) or not chunk_types or set(chunk_types) - {b"IHDR", b"IDAT", b"IEND"}:
            raise RuntimeError("PNG contains unsupported or metadata chunks; upload withheld")
        lowered = data.lower()
        if secret and secret.lower() in lowered:
            raise RuntimeError("PNG secret marker found; upload withheld")
        if any(marker in lowered for marker in (
            b"sb_app_session", b"authorization:", b"cookie:", b"set-cookie:",
            b"synthetic-request-body", b"synthetic-response-body", b"synthetic-cookie-value",
            b"synthetic-query-secret", b"synthetic-auth-secret", b"synthetic-cookie-header-value",
        )):
            raise RuntimeError("PNG sensitive metadata marker found; upload withheld")
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("invalid failure screenshot; upload withheld") from error


def publish_verified_reports(raw_root: Path, publish_root: Path, password_path: Path) -> int:
    """Atomically publish an allowlist of fully sanitized reports or publish nothing."""
    publish_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if publish_root.is_symlink() or (publish_root.exists() and not publish_root.is_dir()):
        raise RuntimeError("artifact publication path is not a regular directory")
    if publish_root.exists() and any(publish_root.iterdir()):
        raise RuntimeError("artifact publication path is not empty; upload withheld")
    publish_root.mkdir(mode=0o700, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".artifacts-verified-", dir=publish_root.parent))
    try:
        screenshot_count = _copy_publishable_files(raw_root, staging_root)
        sanitize_trace_archives(staging_root)
        _sanitize_failure_screenshots(staging_root)
        sanitize_text_reports(staging_root, password_path)
        summary_path = staging_root / "run-summary.json"
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if "screenshots_uploaded" in summary and summary["screenshots_uploaded"] != screenshot_count:
                raise RuntimeError("failure screenshot count does not match the run summary")
        verify_artifact_redaction(staging_root, password_path)
        for path in staging_root.rglob("*"):
            if path.is_file():
                os.chmod(path, 0o600)
            elif path.is_dir():
                os.chmod(path, 0o700)
        publish_root.rmdir()
        os.replace(staging_root, publish_root)
        return screenshot_count
    except Exception as error:
        shutil.rmtree(staging_root, ignore_errors=True)
        if publish_root.exists() and publish_root.is_dir() and not publish_root.is_symlink():
            for child in publish_root.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        elif not publish_root.exists():
            publish_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        raise RuntimeError("report validation failed; artifact upload withheld") from error


def artifact_run_directory() -> Path:
    run_id = os.environ.get("GITHUB_RUN_ID")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT")
    label = f"{run_id}-{attempt}" if run_id and attempt else f"local-{uuid.uuid4()}"
    return ARTIFACTS / label


def mark_verified_artifact_output() -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write("artifacts_verified=true\n")


def wait_http(url: str, process: subprocess.Popen, label: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited before readiness (exit={process.returncode})")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError(f"{label} readiness timeout")


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def wait_for_test_process(test_process: subprocess.Popen) -> int:
    try:
        test_process.wait(timeout=600)
    except subprocess.TimeoutExpired as error:
        stop(test_process)
        raise RuntimeError("Playwright browser acceptance exceeded its 10-minute limit") from error
    if test_process.returncode is None or test_process.returncode < 0:
        raise RuntimeError("Playwright runner terminated abnormally; artifact upload withheld")
    return test_process.returncode


def launch_browser_tests(env: dict[str, str], output_log) -> subprocess.Popen:
    return subprocess.Popen(["npm", "test"], cwd=E2E, env=env, stdout=output_log,
                            stderr=subprocess.STDOUT, start_new_session=True)


def assert_no_business_files(root: Path, label: str) -> None:
    files = [path for path in root.rglob("*") if path.is_file()]
    if files:
        raise RuntimeError(f"source-protection check failed: {label} contains {len(files)} file(s)")


def http_smoke(password_path: Path) -> list[dict]:
    """Exercise real Core HTTP through Vite without launching a browser."""
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_log: list[dict] = []

    def request(method: str, path: str, body: dict | None = None, *, opener=client, origin=WEB_URL):
        started = time.monotonic()
        data = json.dumps(body).encode() if body is not None else None
        request_headers = {"Origin": origin, "Content-Type": "application/json"} if body is not None else {"Origin": origin}
        req = urllib.request.Request(WEB_URL + path, data=data, headers=request_headers, method=method)
        try:
            response = opener.open(req, timeout=10)
            status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        request_log.append({"method": method, "path": OPAQUE_ID.sub("<opaque-id>", path),
                            "status": status, "elapsed_ms": round((time.monotonic() - started) * 1000)})
        parsed = None
        try:
            parsed = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            pass
        return status, parsed, payload

    status, _, _ = request("GET", "/chat/blank")
    if status != 200:
        raise RuntimeError("Vite /chat/blank did not return HTTP 200")
    with urllib.request.urlopen(WEB_URL + "/", timeout=10) as page:
        page_html = page.read().decode("utf-8", "replace")
    if 'id="root"' not in page_html or "/src/main.tsx" not in page_html:
        raise RuntimeError("Vite did not serve the expected local frontend shell")

    password = password_path.read_text(encoding="utf-8").strip()
    status, _, _ = request("POST", "/api/auth/login", {"password": password})
    del password
    if status != 200:
        raise RuntimeError("synthetic App login failed")
    status, _, _ = request("GET", "/api/auth/session")
    if status != 200:
        raise RuntimeError("synthetic App session check failed")

    denied_payload = {"original_text": "synthetic origin denial", "source_channel": "web",
                      "source_event_id": f"e2e-{uuid.uuid4()}",
                      "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "intent": "journal_intent"}
    denied_status, _, _ = request("POST", "/api/inbox/entries", denied_payload, origin="https://untrusted.invalid")
    if denied_status != 403:
        raise RuntimeError("untrusted Origin was not rejected by Core with HTTP 403")

    payload = {"original_text": f"记一下：本地 HTTP 合成验收 {uuid.uuid4()}",
               "source_channel": "web", "source_event_id": f"e2e-{uuid.uuid4()}",
               "occurred_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "intent": "journal_intent"}
    status, accepted, _ = request("POST", "/api/inbox/entries", payload)
    if status != 202 or not isinstance(accepted, dict):
        raise RuntimeError("real Core Inbox POST did not return HTTP 202")
    inbox_id = accepted.get("inbox_id")
    if not isinstance(inbox_id, str) or not __import__("re").fullmatch(r"[0-9a-f]{32}", inbox_id):
        raise RuntimeError("Core returned an invalid Inbox identifier")
    replay_status, replay, _ = request("POST", "/api/inbox/entries", payload)
    if replay_status != 202 or not isinstance(replay, dict) or replay.get("replayed") is not True or replay.get("inbox_id") != inbox_id:
        raise RuntimeError("exact idempotent replay did not return the original Inbox entry")
    get_status, current, _ = request("GET", f"/api/inbox/entries/{inbox_id}")
    if get_status != 200 or not isinstance(current, dict) or current.get("inbox_id") != inbox_id:
        raise RuntimeError("exact Inbox GET did not return the created entry")
    if current.get("source", {}).get("event_id") != payload["source_event_id"] or current.get("intent") != "journal_intent":
        raise RuntimeError("Inbox GET did not preserve the source identity and intent")
    conflict = {**payload, "original_text": payload["original_text"] + " changed"}
    conflict_status, _, _ = request("POST", "/api/inbox/entries", conflict)
    if conflict_status != 409:
        raise RuntimeError("same event identity with changed content did not return HTTP 409")

    anonymous = urllib.request.build_opener()
    unauth_status, _, _ = request("GET", f"/api/inbox/entries/{inbox_id}", opener=anonymous)
    if unauth_status != 401:
        raise RuntimeError("anonymous exact Inbox GET did not fail with HTTP 401")
    if any(entry["path"].startswith(("/api/journal/entries", "/api/knowledge", "/api/projects")) for entry in request_log):
        raise RuntimeError("HTTP smoke unexpectedly called a protected target API")
    return request_log


def main() -> int:
    global CORE_URL, WEB_URL, ALLOW_FAILURE_SCREENSHOT_PUBLICATION
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-smoke-only", action="store_true", help="run synthetic Core HTTP checks without launching a browser")
    options = parser.parse_args()
    # The workflow uploads only this directory. It starts empty on every run;
    # raw Playwright output lives in the private temp root below and is never a
    # parent or sibling matched by the upload-artifact path.
    publish_root = artifact_run_directory()
    publish_root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if publish_root.is_symlink() or (publish_root.exists() and not publish_root.is_dir()):
        raise RuntimeError("artifact publication path is not a regular directory")
    if publish_root.exists() and any(publish_root.iterdir()):
        raise RuntimeError("artifact publication path is not empty; upload withheld")
    publish_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(publish_root, 0o700)

    core_port, web_port = ephemeral_port(), ephemeral_port()
    while web_port == core_port:
        web_port = ephemeral_port()
    CORE_URL, WEB_URL = f"http://127.0.0.1:{core_port}", f"http://127.0.0.1:{web_port}"
    root = Path(tempfile.mkdtemp(prefix="secondbrain-a-web-e2e-"))
    os.chmod(root, 0o700)
    raw_artifacts = root / "playwright-raw"
    raw_artifacts.mkdir(mode=0o700)
    processes: list[subprocess.Popen] = []
    log_files = []
    result = 1
    try:
        dirs = {name: root / name for name in ("raw", "review", "state", "knowledge", "journal", "task")}
        for path in dirs.values():
            path.mkdir(mode=0o700)
        password_path = root / "app-password"
        password_path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        os.chmod(password_path, 0o600)

        env = os.environ.copy()
        env.update({
            "SB_REVIEW_ROOT": str(dirs["review"]),
            "SB_KNOWLEDGE_ROOT": str(dirs["knowledge"]),
            "SB_PROMOTE_STATE_ROOT": str(dirs["state"]),
            "SB_CAPTURE_RAW_ROOT": str(dirs["raw"]),
            "SB_JOURNAL_ROOT": str(dirs["journal"]),
            "SB_TASK_ROOT": str(dirs["task"]),
            "SB_APP_PASSWORD_FILE": str(password_path),
            "SB_DASHBOARD_ORIGINS": WEB_URL,
            "SB_CORE_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "SB_PROMOTE_ENABLED": "false",
            "SB_HERMES_API_URL": "",
            "SB_PERSONAL_MEMORY_ENABLED": "false",
            "SB_PERSONAL_LEARNING_ENABLED": "false",
            "SB_E2E_BASE_URL": WEB_URL,
            "SB_CORE_PROXY_TARGET": CORE_URL,
            "SB_E2E_PASSWORD_FILE": str(password_path),
            "SB_E2E_RAW_ARTIFACTS": str(raw_artifacts),
            "PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(raw_artifacts / "junit.xml"),
            "PLAYWRIGHT_HTML_OUTPUT_DIR": str(raw_artifacts / "html"),
            "CI": "true",
        })
        core_log = (root / "core.log").open("wb")
        log_files.append(core_log)
        core = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "secondbrain_core.app:create_app", "--factory",
            "--host", "127.0.0.1", "--port", str(core_port),
        ], cwd=CORE, env=env, stdout=core_log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(core)
        wait_http(CORE_URL + "/health", core, "Core")
        with urllib.request.urlopen(CORE_URL + "/health", timeout=5) as health_response:
            health = json.loads(health_response.read())
        if health.get("promote_enabled") is not False or health.get("hermes_configured") is not False:
            raise RuntimeError("Core did not start with Promote and Hermes integrations disabled")
        web_log = (root / "vite.log").open("wb")
        log_files.append(web_log)
        web = subprocess.Popen([
            "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort",
        ], cwd=FRONTEND, env=env, stdout=web_log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(web)
        wait_http(WEB_URL + "/chat/blank", web, "Vite")

        node = subprocess.run(["node", "--version"], cwd=E2E, check=True, capture_output=True, text=True).stdout.strip()
        python = subprocess.run([sys.executable, "--version"], cwd=E2E, check=True, capture_output=True, text=True).stdout.strip()
        request_log = None
        if options.http_smoke_only:
            request_log = http_smoke(password_path)
            (raw_artifacts / "local-http-request-metadata.json").write_text(json.dumps(request_log, indent=2) + "\n", encoding="utf-8")
            test_returncode = 0
        else:
            ALLOW_FAILURE_SCREENSHOT_PUBLICATION = (
                sys.platform == "linux" and env.get("CI") == "true"
                and os.environ.get("GITHUB_ACTIONS") == "true"
            )
            test_log = (root / "playwright-runner.log").open("wb")
            log_files.append(test_log)
            test_process = launch_browser_tests(env, test_log)
            processes.append(test_process)
            test_returncode = wait_for_test_process(test_process)

        raw_files = [path for path in dirs["raw"].iterdir() if path.is_file()]
        if test_returncode == 0:
            expected_raw = 1 if options.http_smoke_only else 3
            if len(raw_files) != expected_raw:
                raise RuntimeError(f"expected one Raw record per viewport; found {len(raw_files)}")
            assert_no_business_files(dirs["journal"], "Journal root")
            assert_no_business_files(dirs["knowledge"], "Knowledge root")
        screenshot_count = count_allowlisted_failure_screenshots(raw_artifacts)
        summary = {
            "result": "PASS" if test_returncode == 0 else "FAIL",
            "core": "real localhost HTTP",
            "web": "local Vite",
            "browser": "NOT RUN (local stop gate)" if options.http_smoke_only else "Playwright Linux Chromium (workflow runner only)",
            "promote_enabled": False,
            "hermes": "fixture-only Chat endpoints; no Hermes service or credentials",
            "raw_record_count": len(raw_files),
            "journal_files": sum(path.is_file() for path in dirs["journal"].rglob("*")),
            "knowledge_files": sum(path.is_file() for path in dirs["knowledge"].rglob("*")),
            "exit_code": test_returncode,
            "python": python,
            "node": node,
            "html_report_uploaded": False,
            "screenshots_uploaded": screenshot_count,
        }
        (raw_artifacts / "run-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        os.chmod(raw_artifacts / "run-summary.json", 0o600)
        publish_verified_reports(raw_artifacts, publish_root, password_path)
        mark_verified_artifact_output()
        result = test_returncode
        return result
    finally:
        for process in reversed(processes):
            stop(process)
        for log_file in log_files:
            log_file.close()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"synthetic acceptance harness failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
