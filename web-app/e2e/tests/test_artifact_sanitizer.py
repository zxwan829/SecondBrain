import importlib.util
import json
import zipfile
from pathlib import Path
import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_synthetic_ci.py"
SPEC = importlib.util.spec_from_file_location("run_synthetic_ci", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def test_trace_sanitizer_removes_auth_headers_bodies_external_urls_and_opaque_ids(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    results = artifacts / "test-results" / "capture"
    results.mkdir(parents=True)
    archive = results / "trace.zip"
    opaque = "a" * 32
    record = {
        "type": "request",
        "method": "POST",
        "url": f"http://127.0.0.1:4173/api/inbox/entries/{opaque}?token=synthetic-secret",
        "headers": [{"name": "cookie", "value": "session-secret"}],
        "postData": "synthetic-private-text",
        "status": 202,
    }
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("trace.trace", json.dumps(record) + "\n")
        output.writestr("resources/response.json", "synthetic-private-response")
        output.writestr("resources/failure.png", b"synthetic-screenshot")
    monkeypatch.setattr(module, "ARTIFACTS", artifacts)

    module.sanitize_trace_archives()

    with zipfile.ZipFile(archive) as sanitized:
        names = sanitized.namelist()
        trace = sanitized.read("trace.trace").decode()
        assert "resources/response.json" not in names
        assert "resources/failure.png" in names
        assert "synthetic-secret" not in trace
        assert "session-secret" not in trace
        assert "synthetic-private-text" not in trace
        assert opaque not in trace
        assert "status" in trace and "202" in trace


def test_workflow_is_manual_read_only_and_secret_free():
    workflow = (Path(__file__).parents[3] / ".github" / "workflows" / "a-web-playwright-synthetic.yml").read_text()
    assert "  workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "  pull_request:" not in workflow
    assert "  workflow_call:" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "contents: write" not in workflow
    assert "secrets." not in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "persist-credentials: false" in workflow
    assert "if: always()" in workflow
    assert "retention-days: 7" in workflow


def test_html_and_junit_sanitizer_redacts_generated_password_cookie_and_ids(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    secret_file = tmp_path / "password"
    secret_file.write_text("synthetic-only-passphrase\n")
    opaque = "b" * 32
    (artifacts / "report.html").write_text(f"{opaque} synthetic-only-passphrase sb_app_session")
    (artifacts / "junit.xml").write_text(f"{opaque} synthetic-only-passphrase sb_app_session")
    monkeypatch.setattr(module, "ARTIFACTS", artifacts)

    module.sanitize_text_reports(secret_file)
    module.verify_artifact_redaction(secret_file)

    for report in artifacts.iterdir():
        content = report.read_text()
        assert opaque not in content
        assert "synthetic-only-passphrase" not in content
        assert "sb_app_session" not in content


def test_unredactable_archive_is_withheld(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    secret_file = tmp_path / "password"
    secret_file.write_text("synthetic-only-passphrase\n")
    archive_path = artifacts / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("unknown.dat", "synthetic-only-passphrase")
    monkeypatch.setattr(module, "ARTIFACTS", artifacts)

    with pytest.raises(RuntimeError, match="artifact upload withheld"):
        module.sanitize_or_withhold_artifacts(secret_file)

    assert list(artifacts.iterdir()) == []
