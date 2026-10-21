import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


E2E = Path(__file__).parents[1]
SCRIPT = E2E / "scripts" / "run_synthetic_ci.py"
SPEC = importlib.util.spec_from_file_location("run_synthetic_ci", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def _write_secret(path: Path, value: str = "synthetic-only-passphrase") -> Path:
    path.write_text(value + "\n")
    return path


def _seed_raw_reports(raw: Path, secret: str = "synthetic-only-passphrase") -> None:
    (raw / "test-results" / "capture").mkdir(parents=True)
    (raw / "junit.xml").write_text(
        '<testsuites><testsuite tests="1"><testcase classname="Inbox" name="safe" '
        'url="http://127.0.0.1:4173/?token=SYNTHETIC_QUERY_SECRET"><failure '
        f'message="{secret}">Authorization: Bearer SYNTHETIC_AUTH_SECRET; '
        'Cookie: sb_app_session=SYNTHETIC_COOKIE_HEADER_VALUE; '
        'SYNTHETIC_REQUEST_BODY SYNTHETIC_RESPONSE_BODY</failure><system-out>'
        'Cookie: sb_app_session=SYNTHETIC_COOKIE_VALUE</system-out></testcase></testsuite></testsuites>'
    )
    (raw / "local-http-request-metadata.json").write_text(json.dumps([{
        "method": "POST", "path": "/api/inbox/entries?token=SYNTHETIC_QUERY_SECRET",
        "status": 202, "elapsed_ms": 4, "headers": {"Cookie": "SYNTHETIC_COOKIE_VALUE"},
        "request_body": "SYNTHETIC_REQUEST_BODY", "response_body": "SYNTHETIC_RESPONSE_BODY",
    }]))
    (raw / "run-summary.json").write_text(json.dumps({
        "result": "FAIL", "exit_code": 1, "python": "3.12", "node": "v22",
        "passphrase": secret, "private_payload": "SYNTHETIC_RESPONSE_BODY",
    }))
    trace = raw / "test-results" / "capture" / "trace.zip"
    with zipfile.ZipFile(trace, "w") as archive:
        archive.writestr("trace.trace", json.dumps({
            "type": "request", "method": "POST",
            "url": "http://127.0.0.1:4173/api/inbox/entries?token=SYNTHETIC_QUERY_SECRET",
            "headers": [{"name": "authorization", "value": "SYNTHETIC_AUTH_SECRET"}],
            "postData": "SYNTHETIC_REQUEST_BODY", "opaque_id": "a" * 32,
        }) + "\n")
        archive.writestr("trace.network", "{}\n")
        archive.writestr("trace.stacks", "{}\n")
        archive.writestr("resources/response.json", "SYNTHETIC_RESPONSE_BODY")
        archive.writestr("resources/failure.png", b"SYNTHETIC_COOKIE_VALUE")
    (raw / "html").mkdir()
    (raw / "html" / "index.html").write_text("SYNTHETIC_RESPONSE_BODY")
    (raw / "test-results" / "capture" / "test-failed-1.png").write_bytes(b"SYNTHETIC_COOKIE_VALUE")
    (raw / "runner.log").write_text("SYNTHETIC_AUTH_SECRET SYNTHETIC_RESPONSE_BODY")


def test_trace_sanitizer_drops_bodies_headers_queries_and_attachments(tmp_path):
    artifacts = tmp_path / "artifacts"
    trace_dir = artifacts / "test-results" / "capture"
    trace_dir.mkdir(parents=True)
    archive = trace_dir / "trace.zip"
    opaque = "a" * 32
    record = {
        "type": "request", "method": "POST",
        "url": f"http://127.0.0.1:4173/api/inbox/entries/{opaque}?token=SYNTHETIC_QUERY_SECRET",
        "headers": [{"name": "cookie", "value": "SYNTHETIC_COOKIE_VALUE"}],
        "postData": "SYNTHETIC_REQUEST_BODY", "status": 202,
    }
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("trace.trace", json.dumps(record) + "\n")
        output.writestr("resources/response.json", "SYNTHETIC_RESPONSE_BODY")
        output.writestr("resources/failure.png", b"SYNTHETIC_COOKIE_VALUE")

    module.sanitize_trace_archives(artifacts)

    with zipfile.ZipFile(archive) as sanitized:
        names = sanitized.namelist()
        trace = sanitized.read("trace.trace").decode()
        assert names == ["trace.trace"]
        for marker in ("SYNTHETIC_QUERY_SECRET", "SYNTHETIC_COOKIE_VALUE", "SYNTHETIC_REQUEST_BODY", opaque):
            assert marker not in trace
        assert "?token=" not in trace
        assert '"status":202' in trace


def test_workflow_uploads_only_exact_sanitized_directory_and_is_manual_read_only():
    workflow = (Path(__file__).parents[3] / ".github" / "workflows" / "a-web-playwright-synthetic.yml").read_text()
    runner = SCRIPT.read_text()
    config = (E2E / "playwright.config.ts").read_text()
    assert "  workflow_dispatch:" in workflow
    assert "  push:" not in workflow and "  pull_request:" not in workflow and "  workflow_call:" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "contents: write" not in workflow and "secrets." not in workflow
    assert "runs-on: ubuntu-24.04" in workflow and "persist-credentials: false" in workflow
    assert "path: web-app/e2e/artifacts-sanitized/" in workflow
    assert "path: web-app/e2e/artifacts-sanitized/${{ github.run_id }}-${{ github.run_attempt }}/" in workflow
    assert "path: web-app/e2e/artifacts/" not in workflow
    assert "path: web-app/e2e/artifacts-raw/" not in workflow
    assert "if: always()" in workflow and "if-no-files-found: ignore" in workflow
    assert "steps.synthetic.outputs.artifacts_verified == 'true'" in workflow
    assert 'prefix=".artifacts-verified-"' in runner
    assert "os.replace(staging_root, publish_root)" in runner
    assert "SB_E2E_RAW_ARTIFACTS" in runner and "artifacts-sanitized" in runner
    assert "SB_E2E_RAW_ARTIFACTS" in config and "artifacts-raw" in config
    assert runner.index("wait_for_test_process(test_process)") < runner.index("publish_verified_reports(raw_artifacts, publish_root, password_path)")
    assert runner.index("publish_verified_reports(raw_artifacts, publish_root, password_path)") < runner.rindex("mark_verified_artifact_output()")


def test_allowlisted_publish_redacts_reports_and_omits_html_screenshots_and_unknown_files(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir(mode=0o700)
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)

    module.publish_verified_reports(raw, published, secret)

    published_files = {path.relative_to(published).as_posix() for path in published.rglob("*") if path.is_file()}
    assert published_files == {
        "junit.xml", "local-http-request-metadata.json", "run-summary.json",
        "test-results/capture/trace.zip",
    }
    content = "\n".join(path.read_text(errors="ignore") for path in published.rglob("*") if path.is_file() and not zipfile.is_zipfile(path))
    with zipfile.ZipFile(published / "test-results/capture/trace.zip") as archive:
        content += "\n" + "\n".join(archive.read(name).decode("utf-8", "replace") for name in archive.namelist())
        assert archive.namelist() == ["trace.trace", "trace.network"]
    for marker in ("synthetic-only-passphrase", "SYNTHETIC_QUERY_SECRET", "SYNTHETIC_AUTH_SECRET",
                   "SYNTHETIC_COOKIE_VALUE", "SYNTHETIC_COOKIE_HEADER_VALUE", "SYNTHETIC_REQUEST_BODY",
                   "SYNTHETIC_RESPONSE_BODY", "sb_app_session", "?token="):
        assert marker.lower() not in content.lower()
    assert "failure details withheld" in content
    assert "SYNTHETIC_RESPONSE_BODY" in (raw / "html" / "index.html").read_text()
    assert (raw / "runner.log").exists()
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in published.rglob("*") if path.is_file())


def test_sanitizer_exception_leaves_upload_tree_empty_and_raw_tree_unpublished(tmp_path, monkeypatch):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    original_failure = "injected sanitizer failure"

    def fail_sanitizer(_root):
        raise ValueError(original_failure)

    monkeypatch.setattr(module, "sanitize_trace_archives", fail_sanitizer)
    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []
    assert "SYNTHETIC_RESPONSE_BODY" in (raw / "html" / "index.html").read_text()


def test_leak_validation_failure_discards_staging_and_keeps_publish_root_empty(tmp_path, monkeypatch):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    monkeypatch.setattr(module, "sanitize_text_reports", lambda _root, _secret: None)

    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


@pytest.mark.parametrize("returncode", [-9, None])
def test_abnormal_or_incomplete_test_process_is_rejected_before_publish(returncode, tmp_path, monkeypatch):
    class Process:
        pid = 1

        def wait(self, timeout):
            if returncode is None:
                raise subprocess.TimeoutExpired("playwright", timeout)
            self.returncode = returncode

        def poll(self):
            return self.returncode

    process = Process()
    process.returncode = returncode
    monkeypatch.setattr(module, "stop", lambda _process: None)
    github_output = tmp_path / "github-output"
    github_output.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    with pytest.raises(RuntimeError, match="abnormally|10-minute limit"):
        module.wait_for_test_process(process)
    publish_root = tmp_path / "artifacts-sanitized"
    publish_root.mkdir()
    assert list(publish_root.iterdir()) == []
    assert "artifacts_verified=true" not in github_output.read_text()


def test_startup_failure_never_places_raw_reports_in_upload_tree(tmp_path, monkeypatch):
    class ExitedProcess:
        pid = -1
        returncode = 17

        def poll(self):
            return self.returncode

    e2e = tmp_path / "e2e"
    core, frontend = tmp_path / "core", tmp_path / "frontend"
    e2e.mkdir(); core.mkdir(); frontend.mkdir()
    published = e2e / "artifacts-sanitized"
    monkeypatch.setattr(module, "E2E", e2e)
    monkeypatch.setattr(module, "CORE", core)
    monkeypatch.setattr(module, "FRONTEND", frontend)
    monkeypatch.setattr(module, "ARTIFACTS", published)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(RuntimeError, match="exited before readiness"):
        module.main()

    run_dirs = list(published.iterdir())
    assert len(run_dirs) == 1 and run_dirs[0].is_dir() and list(run_dirs[0].iterdir()) == []


def test_test_process_spawn_exception_cannot_mark_artifacts_verified(tmp_path, monkeypatch):
    published = tmp_path / "artifacts-sanitized" / "workflow-run-1"
    published.mkdir(parents=True)
    github_output = tmp_path / "github-output"
    github_output.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected spawn failure")))

    with pytest.raises(OSError, match="injected spawn failure"):
        module.launch_browser_tests({}, None)

    assert list(published.iterdir()) == []
    assert "artifacts_verified=true" not in github_output.read_text()


def test_invalid_trace_archive_is_withheld(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    (raw / "test-results" / "capture").mkdir(parents=True)
    (raw / "test-results" / "capture" / "trace.zip").write_bytes(b"not a zip")
    secret = _write_secret(tmp_path / "password")

    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


def test_atomic_publication_failure_discards_verified_staging(tmp_path, monkeypatch):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    monkeypatch.setattr(module.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("injected rename failure")))

    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert published.exists() and list(published.iterdir()) == []
    assert not list(tmp_path.glob(".artifacts-verified-*"))


def test_symlink_report_is_rejected_without_upload(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    outside = tmp_path / "outside.xml"
    outside.write_text("SYNTHETIC_RESPONSE_BODY")
    (raw / "junit.xml").symlink_to(outside)

    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []
