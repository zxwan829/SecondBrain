import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, PngImagePlugin
import pytest


E2E = Path(__file__).parents[1]
SCRIPT = E2E / "scripts" / "run_synthetic_ci.py"
SPEC = importlib.util.spec_from_file_location("run_synthetic_ci", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def _screenshot_dir(viewport: str) -> str:
    return next(name for name, value in module.FAILURE_SCREENSHOT_DIR_VIEWPORTS.items() if value == viewport)


def _write_secret(path: Path, value: str = "synthetic-only-passphrase") -> Path:
    path.write_text(value + "\n")
    return path


def _write_junit(raw: Path, failed_viewports: set[str], *, cases=None, secret=None) -> None:
    if cases is None:
        cases = [
            (classname, name, viewport in failed_viewports)
            for (classname, name), viewport in module.FAILURE_JUNIT_TESTCASE_VIEWPORTS.items()
        ]
    testcase_xml = []
    for classname, name, failed in cases:
        if failed and secret:
            status = (
                f'<failure message="{secret}">Authorization: Bearer SYNTHETIC_AUTH_SECRET; '
                'Cookie: sb_app_session=SYNTHETIC_COOKIE_HEADER_VALUE; '
                'SYNTHETIC_REQUEST_BODY SYNTHETIC_RESPONSE_BODY</failure>'
                '<system-out>Cookie: sb_app_session=SYNTHETIC_COOKIE_VALUE</system-out>'
            )
            url = ' url="http://127.0.0.1:4173/?token=SYNTHETIC_QUERY_SECRET"'
        else:
            status = '<failure message="withheld" />' if failed else ""
            url = ""
        testcase_xml.append(f'<testcase classname="{classname}" name="{name}"{url}>{status}</testcase>')
    failures = sum(1 for _, _, failed in cases if failed)
    (raw / "junit.xml").write_text(
        f'<testsuites><testsuite tests="{len(cases)}" failures="{failures}">'
        + "".join(testcase_xml) + "</testsuite></testsuites>"
    )


def _seed_raw_reports(raw: Path, secret: str = "synthetic-only-passphrase", *, diagnostic_viewport: str = "desktop-1440x1000") -> None:
    (raw / "test-results" / "capture").mkdir(parents=True)
    diagnostic_dir = raw / "test-results" / _screenshot_dir(diagnostic_viewport)
    diagnostic_dir.mkdir(parents=True)
    (diagnostic_dir / "failure-summary.json").write_text(json.dumps({
        "schema_version": 2, "viewport": diagnostic_viewport,
        "stage": "viewport_layout", "code": "assertion_failed",
        "assertion_id": "activity_get_status_200", "activity_get_statuses": [200],
    }))
    _write_junit(raw, {diagnostic_viewport}, secret=secret)
    (raw / "local-http-request-metadata.json").write_text(json.dumps([{
        "method": "POST", "path": "/api/inbox/entries?token=SYNTHETIC_QUERY_SECRET",
        "status": 202, "elapsed_ms": 4, "headers": {"Cookie": "SYNTHETIC_COOKIE_VALUE"},
        "request_body": "SYNTHETIC_REQUEST_BODY", "response_body": "SYNTHETIC_RESPONSE_BODY",
    }]))
    (raw / "run-summary.json").write_text(json.dumps({
        "result": "FAIL", "exit_code": 1, "python": "3.12", "node": "v22",
        "passphrase": secret, "private_payload": "SYNTHETIC_RESPONSE_BODY", "screenshots_uploaded": 0,
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
    assert "ref: ${{ github.sha }}" in workflow
    assert "EXPECTED_SHA: ${{ github.sha }}" in workflow
    assert 'actual_sha="$(git rev-parse HEAD)"' in workflow
    assert 'test "$actual_sha" = "$EXPECTED_SHA"' in workflow
    assert "path: web-app/e2e/artifacts-sanitized/" in workflow
    assert "path: web-app/e2e/artifacts-sanitized/${{ github.run_id }}-${{ github.run_attempt }}/" in workflow
    assert "path: web-app/e2e/artifacts/" not in workflow
    assert "path: web-app/e2e/artifacts-raw/" not in workflow
    assert "wp5_conflict_only:" in workflow
    assert "--wp5-conflict-only" in workflow and "WP5_CONFLICT_ONLY" in workflow
    assert "if: always()" in workflow and "if-no-files-found: ignore" in workflow
    assert "steps.synthetic.outputs.artifacts_verified == 'true'" in workflow
    assert 'prefix=".artifacts-verified-"' in runner
    assert "os.replace(staging_root, publish_root)" in runner
    assert "SB_E2E_RAW_ARTIFACTS" in runner and "artifacts-sanitized" in runner
    assert "SB_E2E_RAW_ARTIFACTS" in config and "artifacts-raw" in config
    publish_call = "publish_verified_reports(raw_artifacts, publish_root, password_path, expected_failure_viewports)"
    assert runner.index("wait_for_test_process(test_process)") < runner.index(publish_call)
    assert runner.index(publish_call) < runner.rindex("mark_verified_artifact_output()")


def test_screenshot_source_is_fixed_local_synthetic_chromium_fixture():
    workflow = (Path(__file__).parents[3] / ".github" / "workflows" / "a-web-playwright-synthetic.yml").read_text()
    runner = SCRIPT.read_text()
    config = (E2E / "playwright.config.ts").read_text()
    browser_spec = (E2E / "tests" / "inbox-browser.spec.ts").read_text()
    assert "runs-on: ubuntu-24.04" in workflow
    assert "npx playwright install chromium" in workflow
    assert "screenshot: 'only-on-failure'" in config
    assert "serviceWorkers: 'block'" in config
    assert "ALLOW_FAILURE_SCREENSHOT_PUBLICATION = (" in runner
    assert 'sys.platform == "linux"' in runner and 'os.environ.get("GITHUB_ACTIONS") == "true"' in runner
    assert "new URL(request.url())" in browser_spec and "if (url.origin !== baseOrigin)" in browser_spec
    assert "await route.abort('blockedbyclient')" in browser_spec
    assert "synthetic-" in browser_spec and "randomUUID()" in browser_spec
    assert "Synthetic completion" in browser_spec
    assert "toHaveAttribute('type', 'password')" in browser_spec
    assert "inbox-browser-explicit-Inb-3c225-ection-at-desktop-1440x1000" in runner
    assert "inbox-browser-explicit-Inb-33ff6-otection-at-tablet-820x1180" in runner
    assert "inbox-browser-explicit-Inb-7095f-rotection-at-mobile-390x844" in runner


def test_junit_identity_allowlist_tracks_only_the_three_fixed_browser_cases():
    browser_spec = (E2E / "tests" / "inbox-browser.spec.ts").read_text()
    expected = {
        ("inbox-browser.spec.ts", f"explicit Inbox capture, retry, conflict and source protection at {viewport}"): viewport
        for viewport in ("desktop-1440x1000", "tablet-820x1180", "mobile-390x844")
    }
    assert module.FAILURE_JUNIT_TESTCASE_VIEWPORTS == expected
    assert "test(`explicit Inbox capture, retry, conflict and source protection at ${viewport.name}`" in browser_spec
    for viewport in expected.values():
        assert f"name: '{viewport}'" in browser_spec


@pytest.mark.parametrize("viewport", [
    "desktop-1440x1000", "tablet-820x1180", "mobile-390x844",
])
def test_exact_playwright_truncated_output_directory_is_allowlisted(viewport, tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw = tmp_path / "raw"
    screenshot = raw / "test-results" / _screenshot_dir(viewport) / "test-failed-1.png"
    _write_png(screenshot)
    assert module.count_allowlisted_failure_screenshots(raw) == 1



def test_wp5_autosave_probe_timeline_accepts_only_bounded_safe_events():
    diagnostic = {
        "viewport": "desktop-1440x1000", "stage": "notes_blocksuite_conflict",
        "code": "timeout", "assertion_id": "notes_blocksuite_conflict_rejected",
        "activity_get_statuses": [200],
        "wp5_autosave_events": [
            {"marker": "wp5-conflict-queue", "at_ms": 1000, "event": "notes-queue-unsaved"},
            {"marker": "wp5-conflict-queue", "at_ms": 1001, "event": "notes-save-timer-fired"},
            {"marker": "wp5-conflict-queue", "at_ms": 1002, "event": "browser-put-request"},
            {"marker": "wp5-conflict-queue", "at_ms": 1003, "event": "core-response", "status": 412},
        ],
    }
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    invalid = {**diagnostic, "wp5_autosave_events": [
        {"marker": "wrong-marker", "at_ms": 1000, "event": "browser-put-request"},
    ]}
    with pytest.raises(RuntimeError):
        module._validate_failure_diagnostics([invalid])
    over_bound = {**diagnostic, "wp5_autosave_events": [
        {"marker": "wp5-conflict-queue", "at_ms": index, "event": "browser-put-request"}
        for index in range(65)
    ]}
    with pytest.raises(RuntimeError):
        module._validate_failure_diagnostics([over_bound])


def test_wp5_canvas_save_diagnostic_is_finite_and_sanitized():
    diagnostic = {
        "viewport": "desktop-1440x1000", "stage": "notes_blocksuite_open", "code": "timeout",
        "assertion_id": "wp5_resource_checkpoint_010", "activity_get_statuses": [],
        "wp5_canvas_save": {
            "checkpoint": "saved_status", "status": "previous_dirty", "close_enabled": False,
            "readback_status": 200, "snapshot_matches_readback": False,
            "live_text_bounds": [[120, 360, 320, 128]], "saved_text_bounds": [[120, 360, 320, 120]],
            "layout_samples": [[128, 128, 130, 128, 20, 20, 18, 1, 1, 1, 1]],
        },
    }
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    invalid = {**diagnostic, "wp5_canvas_save": {**diagnostic["wp5_canvas_save"], "status": "private note body"}}
    with pytest.raises(RuntimeError):
        module._validate_failure_diagnostics([invalid])
    over_bound = {**diagnostic, "wp5_canvas_save": {**diagnostic["wp5_canvas_save"],
        "live_text_bounds": [[120, 360, 320, 1e10]]}}
    with pytest.raises(RuntimeError):
        module._validate_failure_diagnostics([over_bound])

@pytest.mark.parametrize("entry", [
    {"viewport": "desktop-1440x1000", "stage": "viewport_layout", "code": "assertion_failed", "assertion_id": "activity_get_status_200", "activity_get_statuses": [200], "details": "secret", "notes_collection_statuses": []},
    {"viewport": "desktop-1440x1000", "stage": "arbitrary text", "code": "test_error", "assertion_id": "activity_get_status_200", "activity_get_statuses": [200], "notes_collection_statuses": []},
    {"viewport": "desktop-1440x1000", "stage": "login", "code": "raw exception: token=secret", "assertion_id": "activity_get_status_200", "activity_get_statuses": [200], "notes_collection_statuses": []},
    {"viewport": "not-a-viewport", "stage": "login", "code": "timeout", "assertion_id": "activity_get_status_200", "activity_get_statuses": [200], "notes_collection_statuses": []},
])
def test_failure_diagnostic_unknown_or_sensitive_values_fail_closed(entry):
    with pytest.raises(RuntimeError):
        module._validate_failure_diagnostics([entry])


def test_failure_diagnostic_accepts_action_revocation_stage():
    diagnostic = {"viewport": "mobile-390x844", "stage": "permission_revocation", "code": "assertion_failed",
                  "assertion_id": "activity_get_status_200", "activity_get_statuses": [200, 403], "notes_collection_statuses": []}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]


def test_failure_diagnostic_can_include_bounded_notes_collection_statuses():
    diagnostic = {"viewport": "desktop-1440x1000", "stage": "notes_navigation", "code": "assertion_failed",
                  "assertion_id": "notes_collections", "activity_get_statuses": [200, 403],
                  "notes_collection_statuses": [403]}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["notes_collection_statuses"] = [True]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_can_include_bounded_note_item_read_failure():
    diagnostic = {"viewport": "desktop-1440x1000", "stage": "notes_reopen", "code": "assertion_failed",
                  "assertion_id": "notes_readback", "activity_get_statuses": [200],
                  "notes_item_read_statuses": [403], "notes_readback_failure": "note_file_permissions_unsafe"}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["notes_item_read_statuses"] = [600]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_can_include_bounded_notes_write_statuses():
    diagnostic = {"viewport": "desktop-1440x1000", "stage": "notes_blocksuite_conflict",
                  "code": "timeout", "assertion_id": "notes_blocksuite_conflict_rejected",
                  "activity_get_statuses": [200], "notes_write_statuses": [200, 412, None]}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["notes_write_statuses"] = [True]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["notes_item_read_statuses"] = [403]
    diagnostic["notes_readback_failure"] = "raw error text"
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_can_include_notes_seed_status():
    diagnostic = {"viewport": "desktop-1440x1000", "stage": "notes_frontmatter_seed", "code": "assertion_failed",
                  "assertion_id": "notes_frontmatter_seed", "activity_get_statuses": [200],
                  "notes_seed_status": 412}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["notes_seed_status"] = True
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["notes_seed_status"] = 600
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_can_include_bounded_blocksuite_runtime_state():
    diagnostic = {"viewport": "desktop-1440x1000", "stage": "notes_blocksuite_open", "code": "timeout",
                  "assertion_id": "notes_blocksuite_simple_open", "activity_get_statuses": [200],
                  "notes_ui_state": "fallback_message", "page_error_names": ["TypeError"],
                  "page_error_categories": ["nullish_property_access"],
                  "page_error_sources": ["blocksuite_module"], "blocksuite_module_statuses": [200, 504],
                  "page_error_summaries": ["Error: Cannot read properties of undefined (<quoted>)"]}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["notes_ui_state"] = "raw browser text"
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["notes_ui_state"] = "fallback_message"
    diagnostic["page_error_names"] = ["Error: private payload"]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["page_error_names"] = ["TypeError"]
    diagnostic["page_error_categories"] = ["raw browser message"]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["page_error_categories"] = ["nullish_property_access"]
    diagnostic["page_error_sources"] = ["/Users/private/path.tsx"]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["page_error_sources"] = ["blocksuite_module"]
    diagnostic["blocksuite_module_statuses"] = ["GET /secret"]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["blocksuite_module_statuses"] = [200, 504]
    diagnostic["page_error_summaries"] = ["/Users/person/private.txt"]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_can_include_sanitized_wp5_step_and_resource_statuses():
    diagnostic = {
        "viewport": "desktop-1440x1000", "stage": "notes_blocksuite_open", "code": "timeout",
        "assertion_id": "wp5_resource_content_visible", "activity_get_statuses": [200],
        "wp5_step": "rich_page_first_save",
        "blocksuite_request_statuses": [
            {"endpoint": "resource", "method": "POST", "status": 200},
            {"endpoint": "blob", "method": "PUT", "status": 201},
        ],
    }
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["wp5_step"] = "GET /api/notes/private"
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])
    diagnostic["wp5_step"] = "rich_page_first_save"
    diagnostic["blocksuite_request_statuses"] = [
        {"endpoint": "resource", "method": "PUT", "status": 700},
    ]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_can_include_bounded_daily_brief_get_statuses():
    diagnostic = {"viewport": "mobile-390x844", "stage": "daily_brief_read", "code": "timeout",
                  "assertion_id": "daily_brief_saved_readback", "activity_get_statuses": [200, 403],
                  "daily_brief_get_statuses": [200, 200]}
    assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]
    diagnostic["daily_brief_get_statuses"] = [True]
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_failure_diagnostic_accepts_fixed_navigation_and_layout_ids():
    stages_and_assertions = [
        ("post_revocation_navigation", "home_after_revocation"),
        ("agent_health", "home_after_agent_health"),
        ("today", "today_heading"),
        ("journal", "home_after_journal"),
        ("calendar", "calendar_heading"),
        ("permission_revocation", "activity_revocation_denial"),
        ("permission_revocation", "activity_revocation_empty"),
        ("permission_revocation", "activity_revocation_status_403"),
        ("calendar", "calendar_api_requests"),
        ("viewport_layout", "layout_no_horizontal_overflow"),
        ("viewport_layout", "home_api_response"),
        ("viewport_layout", "projects_navigation"),
        ("viewport_layout", "projects_api_response"),
        ("agent_health", "agent_health_navigation"),
        ("agent_health", "agent_health_api_response"),
        ("today", "today_navigation"),
        ("today", "today_api_response"),
        ("journal", "journal_navigation"),
        ("journal", "journal_api_response"),
        ("journal", "journal_append"),
        ("journal", "journal_saved_readback"),
        ("journal", "journal_refresh_readback"),
        ("calendar", "calendar_navigation"),
        ("calendar", "calendar_api_response"),
        ("viewport_layout", "layout_home"),
        ("viewport_layout", "layout_projects"),
        ("viewport_layout", "layout_activity"),
        ("agent_health", "layout_agent_health"),
        ("today", "layout_today"),
        ("journal", "layout_journal"),
        ("calendar", "layout_calendar"),
    ]
    for stage, assertion_id in stages_and_assertions:
        diagnostic = {"viewport": "mobile-390x844", "stage": stage, "code": "assertion_failed",
                      "assertion_id": assertion_id, "activity_get_statuses": [200, 403], "notes_collection_statuses": []}
        assert module._validate_failure_diagnostics([diagnostic]) == [diagnostic]


@pytest.mark.parametrize("statuses", [[True], ["200"], [99], [600], [200, 200, 200, 200, 200]])
def test_failure_diagnostic_rejects_non_http_or_unbounded_activity_statuses(statuses):
    diagnostic = {"viewport": "desktop-1440x1000", "stage": "viewport_layout",
                  "code": "assertion_failed", "assertion_id": "activity_get_status_200",
                  "activity_get_statuses": statuses, "notes_collection_statuses": []}
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([diagnostic])


def test_browser_activity_assertion_waits_for_core_response_and_uses_fixed_diagnostic_ids():
    browser_spec = (E2E / "tests" / "inbox-browser.spec.ts").read_text()
    assert "page.waitForResponse((response) =>" in browser_spec
    assert "expect(activityResponse?.status(), 'activity_get_http_200').toBe(200)" in browser_spec
    assert "&& request.path === '/api/activity' && request.status === 200)).toBe(true);" not in browser_spec
    assert "activity_get_statuses: observed?.activityReadStatuses ?? []" in browser_spec
    assert "home_after_revocation" in browser_spec
    assert "layout_no_horizontal_overflow" in browser_spec
    assert "setActivityReadRevoked(false)" in browser_spec
    assert "activity_revocation_status_403" in browser_spec


def test_browser_navigation_waits_for_page_apis_and_uses_unambiguous_mobile_safe_locators():
    browser_spec = (E2E / "tests" / "inbox-browser.spec.ts").read_text()
    assert "await expectSuccessfulGet(homeResponsePromise, observed, 'home_api_response')" in browser_spec
    assert "await expectSuccessfulGet(projectsResponsePromise, observed, 'projects_api_response')" in browser_spec
    assert "await expectSuccessfulGet(agentHealthResponsePromise, observed, 'agent_health_api_response')" in browser_spec
    assert "await expectSuccessfulGet(todayResponsePromise, observed, 'today_api_response')" in browser_spec
    assert "await expectSuccessfulGet(journalResponsePromise, observed, 'journal_api_response')" in browser_spec
    assert "await expectSuccessfulGet(calendarResponsePromise, observed, 'calendar_api_response')" in browser_spec
    assert "await expectSuccessfulGet(collectionsResponsePromise, observed, 'notes_collections')" in browser_spec
    assert "notes_collection_statuses: observed?.notesCollectionReadStatuses ?? []" in browser_spec
    assert "daily_brief_get_statuses: observed?.dailyBriefReadStatuses ?? []" in browser_spec
    assert "daily_brief_saved_readback" in browser_spec
    assert "getByRole('heading', { level: 1, name: 'Agent 状态', exact: true })" in browser_spec
    assert "await expect(menu).toHaveAttribute('aria-expanded', 'true')" in browser_spec
    assert "page.locator('.sidebar nav').getByRole('button', { name: '今日', exact: true })" in browser_spec
    assert "document.documentElement.scrollWidth" in browser_spec
    assert "document.body.scrollWidth" in browser_spec
    assert "expectNoHorizontalOverflow(page, observed, viewport, 'layout_calendar')" in browser_spec


def test_browser_fixture_allowlists_only_exact_synthetic_notes_routes():
    browser_spec = (E2E / "tests" / "inbox-browser.spec.ts").read_text()
    assert "const notesPath = params.size === 0" in browser_spec
    assert "url.pathname === '/api/notes'" in browser_spec
    assert "url.pathname === '/api/notes/drafts'" in browser_spec
    assert "^\\/api\\/notes\\/drafts\\/[0-9a-f]{8}" in browser_spec
    assert "url.pathname.startsWith('/api/notes')" not in browser_spec


def test_browser_fixture_allows_only_explicit_journal_read_and_append_routes():
    browser_spec = (E2E / "tests" / "inbox-browser.spec.ts").read_text()
    assert "const journalPath = route.request().method() === 'GET'" in browser_spec
    assert "const journalAppendPath = route.request().method() === 'POST' && url.pathname === '/api/journal/entries'" in browser_spec
    assert "!journalPath && !journalAppendPath" in browser_spec
    assert "url.pathname.startsWith('/api/journal')" not in browser_spec
    assert "journal_refresh_readback" in browser_spec


def test_failure_diagnostic_duplicate_viewports_and_excess_count_fail_closed():
    entry = {"viewport": "desktop-1440x1000", "stage": "login", "code": "timeout",
             "assertion_id": "test_setup", "activity_get_statuses": [], "notes_collection_statuses": []}
    with pytest.raises(RuntimeError, match="value rejected"):
        module._validate_failure_diagnostics([entry, entry.copy()])
    with pytest.raises(RuntimeError, match="schema rejected"):
        module._validate_failure_diagnostics([entry, entry, entry, entry])


def test_missing_fixed_viewport_diagnostic_fails_closed(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_junit(raw, {"desktop-1440x1000", "tablet-820x1180"})
    result_dir = raw / "test-results" / _screenshot_dir("desktop-1440x1000")
    result_dir.mkdir(parents=True)
    (result_dir / "failure-summary.json").write_text(json.dumps({
        "schema_version": 2, "viewport": "desktop-1440x1000", "stage": "first_submit", "code": "timeout",
        "assertion_id": "test_setup", "activity_get_statuses": [],
    }))
    with pytest.raises(RuntimeError, match="do not cover every failed testcase viewport"):
        module._collect_failure_diagnostics(raw)


def test_normal_failed_testcase_without_diagnostic_is_not_misclassified_as_setup(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_junit(raw, {"tablet-820x1180"})
    with pytest.raises(RuntimeError, match="do not cover every failed testcase viewport"):
        module._collect_failure_diagnostics(raw)


def test_explicit_setup_diagnostic_is_retained_for_its_failed_viewport(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_junit(raw, {"mobile-390x844"})
    result_dir = raw / "test-results" / _screenshot_dir("mobile-390x844")
    result_dir.mkdir(parents=True)
    (result_dir / "failure-summary.json").write_text(json.dumps({
        "schema_version": 2, "viewport": "mobile-390x844", "stage": "test_setup", "code": "test_error",
        "assertion_id": "test_setup", "activity_get_statuses": [],
    }))
    assert module._collect_failure_diagnostics(raw) == [{
        "viewport": "mobile-390x844", "stage": "test_setup", "code": "test_error",
        "assertion_id": "test_setup", "activity_get_statuses": [],
    }]


def test_failed_run_without_explicit_viewport_diagnostic_withholds_report(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir(mode=0o700)
    _write_junit(raw, set(module.FAILURE_JUNIT_TESTCASE_VIEWPORTS.values()))
    (raw / "run-summary.json").write_text(json.dumps({"result": "FAIL", "exit_code": 1}))
    secret = _write_secret(tmp_path / "password")

    with pytest.raises(RuntimeError, match="report validation failed; artifact upload withheld"):
        module.publish_verified_reports(raw, published, secret)

    assert not any(published.rglob("*"))


def _write_failure_diagnostic(raw: Path, viewport: str) -> None:
    result_dir = raw / "test-results" / _screenshot_dir(viewport)
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "failure-summary.json").write_text(json.dumps({
        "schema_version": 2, "viewport": viewport, "stage": "viewport_layout", "code": "assertion_failed",
        "assertion_id": "activity_get_status_200", "activity_get_statuses": [200],
    }))


def test_junit_failure_viewport_must_match_diagnostic_even_when_counts_match(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    _write_junit(raw, {"desktop-1440x1000"})
    _write_failure_diagnostic(raw, "tablet-820x1180")
    with pytest.raises(RuntimeError, match="report validation failed; artifact upload withheld"):
        module.publish_verified_reports(raw, published, _write_secret(tmp_path / "password"))
    assert not published.exists() or list(published.iterdir()) == []


def test_unrelated_failed_junit_testcase_is_rejected(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    cases = [
        (classname, name, viewport == "desktop-1440x1000")
        for (classname, name), viewport in module.FAILURE_JUNIT_TESTCASE_VIEWPORTS.items()
    ]
    cases.append(("tests/other.spec.ts", "desktop failure", True))
    _write_junit(raw, {"desktop-1440x1000"}, cases=cases)
    _write_failure_diagnostic(raw, "desktop-1440x1000")
    with pytest.raises(RuntimeError, match="testcase identity rejected"):
        module._collect_failure_diagnostics(raw)


def test_junit_classname_must_match_actual_playwright_filename_not_tests_path(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    cases = [
        ("tests/inbox-browser.spec.ts", name, viewport == "desktop-1440x1000")
        for (_, name), viewport in module.FAILURE_JUNIT_TESTCASE_VIEWPORTS.items()
    ]
    _write_junit(raw, {"desktop-1440x1000"}, cases=cases)
    with pytest.raises(RuntimeError, match="testcase identity rejected"):
        module._collect_failure_diagnostics(raw)


@pytest.mark.parametrize("bad_identity", [
    ("inbox-browser.spec.ts", "explicit Inbox capture, retry, conflict and source protection at desktop-1440x1000"),
    ("inbox-browser.spec.ts", "explicit Inbox capture, retry, conflict and source protection at desktop-1440x1000 (retry #1)"),
])
def test_duplicate_or_ambiguous_failed_junit_identity_is_rejected(tmp_path, bad_identity):
    raw = tmp_path / "raw"
    raw.mkdir()
    desktop_identity = next(identity for identity, viewport in module.FAILURE_JUNIT_TESTCASE_VIEWPORTS.items()
                            if viewport == "desktop-1440x1000")
    cases = [
        (classname, name, viewport == "desktop-1440x1000")
        for (classname, name), viewport in module.FAILURE_JUNIT_TESTCASE_VIEWPORTS.items()
        if viewport != "tablet-820x1180"
    ]
    # The first case duplicates an approved identity; the second adds a
    # near-match title that cannot be mapped to a viewport.
    cases.append((*bad_identity, True))
    if bad_identity == desktop_identity:
        with pytest.raises(RuntimeError, match="testcase set rejected"):
            _write_junit_and_collect(raw, cases)
    else:
        _write_junit_and_collect(raw, cases, expected_error="testcase identity rejected")


def _write_junit_and_collect(raw: Path, cases, expected_error=None):
    _write_junit(raw, set(), cases=cases)
    if expected_error:
        with pytest.raises(RuntimeError, match=expected_error):
            module._collect_failure_diagnostics(raw)
        return
    module._collect_failure_diagnostics(raw)


def test_exact_desktop_and_tablet_failures_accept_matching_diagnostics(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    failures = {"desktop-1440x1000", "tablet-820x1180"}
    _write_junit(raw, failures)
    for viewport in failures:
        _write_failure_diagnostic(raw, viewport)
    assert module._collect_failure_diagnostics(raw) == [
        {"viewport": "desktop-1440x1000", "stage": "viewport_layout", "code": "assertion_failed",
         "assertion_id": "activity_get_status_200", "activity_get_statuses": [200]},
        {"viewport": "tablet-820x1180", "stage": "viewport_layout", "code": "assertion_failed",
         "assertion_id": "activity_get_status_200", "activity_get_statuses": [200]},
    ]


def test_failed_run_without_junit_or_failed_testcase_diagnostics_is_withheld(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.mkdir(exist_ok=True)
    _write_junit(raw, set())
    (raw / "run-summary.json").write_text(json.dumps({"result": "FAIL"}))
    with pytest.raises(RuntimeError, match="failed browser run has no failed testcase diagnostics"):
        module._collect_failure_diagnostics(raw)

    (raw / "junit.xml").unlink()
    with pytest.raises(RuntimeError, match="no JUnit diagnostics"):
        module._collect_failure_diagnostics(raw)


def test_failure_diagnostic_malicious_source_payload_is_withheld(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    summary = raw / "test-results" / _screenshot_dir("desktop-1440x1000") / "failure-summary.json"
    summary.write_text(json.dumps({
        "schema_version": 2, "viewport": "desktop-1440x1000", "stage": "login",
        "code": "test_error", "assertion_id": "test_setup", "activity_get_statuses": [],
        "message": "SYNTHETIC_AUTH_SECRET",
    }))
    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


def test_failure_diagnostic_symlink_is_withheld(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    diagnostics = raw / "test-results" / _screenshot_dir("desktop-1440x1000") / "failure-summary.json"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({
        "schema_version": 2, "viewport": "desktop-1440x1000", "stage": "login", "code": "timeout",
        "assertion_id": "test_setup", "activity_get_statuses": [],
    }))
    diagnostics.unlink()
    diagnostics.symlink_to(outside)
    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


def test_failure_diagnostic_boolean_schema_version_is_rejected(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_junit(raw, {"desktop-1440x1000"})
    result_dir = raw / "test-results" / _screenshot_dir("desktop-1440x1000")
    result_dir.mkdir(parents=True)
    (result_dir / "failure-summary.json").write_text(json.dumps({
        "schema_version": True, "viewport": "desktop-1440x1000", "stage": "login", "code": "timeout",
        "assertion_id": "test_setup", "activity_get_statuses": [],
    }))
    with pytest.raises(RuntimeError, match="source schema rejected"):
        module._collect_failure_diagnostics(raw)


def test_allowlisted_publish_redacts_reports_and_omits_html_unknown_images_and_files(tmp_path):
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir(mode=0o700)
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)

    module.publish_verified_reports(raw, published, secret)

    published_files = {path.relative_to(published).as_posix() for path in published.rglob("*") if path.is_file()}
    assert published_files == {
        "junit.xml", "local-http-request-metadata.json", "run-summary.json", "failure-diagnostics.json",
        "test-results/capture/trace.zip",
    }
    assert json.loads((published / "failure-diagnostics.json").read_text()) == [{
        "viewport": "desktop-1440x1000", "stage": "viewport_layout", "code": "assertion_failed",
        "assertion_id": "activity_get_status_200", "activity_get_statuses": [200],
    }]
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


def _write_png(path: Path, *, metadata: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    for key, value in (metadata or {}).items():
        info.add_text(key, value)
    Image.new("RGB", (80, 40), color=(35, 45, 55)).save(path, format="PNG", pnginfo=info)


def _png_chunk_types(path: Path) -> list[bytes]:
    data = path.read_bytes()
    chunks = []
    cursor = 8
    while cursor + 12 <= len(data):
        size = struct.unpack(">I", data[cursor:cursor + 4])[0]
        chunks.append(data[cursor + 4:cursor + 8])
        cursor += 12 + size
    assert cursor == len(data)
    return chunks


def _enable_current_linux_browser_run(monkeypatch):
    monkeypatch.setattr(module, "ALLOW_FAILURE_SCREENSHOT_PUBLICATION", True)
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")


def test_run_summary_reports_journal_sources_separately_from_mutations(tmp_path):
    summary = tmp_path / "run-summary.json"
    summary.write_text(json.dumps({
        "journal_files": 1,
        "journal_source_fixture_files": 1,
        "journal_mutated_files": 0,
        "brief_files": 0,
        "brief_file_set_verified": False,
        "notes_files": 1,
        "authorization_header": "SYNTHETIC_SECRET",
    }))

    module._sanitize_run_summary(summary)

    result = json.loads(summary.read_text())
    assert result == {
        "journal_files": 1,
        "journal_source_fixture_files": 1,
        "journal_mutated_files": 0,
        "brief_files": 0,
        "brief_file_set_verified": False,
        "notes_files": 1,
    }


def test_daily_brief_file_set_assertion_rejects_unexpected_files_and_symlinks(tmp_path):
    brief_root = tmp_path / "briefs"
    brief_root.mkdir()
    operation_hash = "a" * 64
    (brief_root / "2026-10-21.json").write_text("synthetic")
    (brief_root / f".op-{operation_hash}.json").write_text("synthetic")
    (brief_root / f".op-lock-{operation_hash}").touch()
    (brief_root / ".date-lock-2026-10-21").touch()
    assert module._assert_exact_brief_file_set(brief_root, "2026-10-21.json") == 4

    (brief_root / ".date-lock-2026-10-21").unlink()
    with pytest.raises(RuntimeError, match="file set mismatch"):
        module._assert_exact_brief_file_set(brief_root, "2026-10-21.json")
    (brief_root / ".date-lock-2026-10-21").touch()

    (brief_root / ".pending-2026-10-21.json").write_text("synthetic")
    with pytest.raises(RuntimeError, match="file set mismatch"):
        module._assert_exact_brief_file_set(brief_root, "2026-10-21.json")
    (brief_root / ".pending-2026-10-21.json").unlink()

    (brief_root / "unexpected.json").write_text("synthetic")
    with pytest.raises(RuntimeError, match="file set mismatch"):
        module._assert_exact_brief_file_set(brief_root, "2026-10-21.json")

    (brief_root / "unexpected.json").unlink()
    (brief_root / "linked.json").symlink_to(brief_root / "2026-10-21.json")
    with pytest.raises(RuntimeError, match="non-regular entry"):
        module._assert_exact_brief_file_set(brief_root, "2026-10-21.json")


def test_current_linux_fixture_failure_png_is_allowlisted_and_metadata_is_removed(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir(mode=0o700)
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    screenshot = raw / "test-results" / _screenshot_dir("desktop-1440x1000") / "test-failed-1.png"
    _write_png(screenshot, metadata={
        "Comment": "synthetic-query-secret SYNTHETIC_RESPONSE_BODY",
        "Description": "synthetic-only-passphrase SYNTHETIC_COOKIE_VALUE",
    })
    summary = json.loads((raw / "run-summary.json").read_text())
    summary["screenshots_uploaded"] = 1
    (raw / "run-summary.json").write_text(json.dumps(summary))

    assert module.count_allowlisted_failure_screenshots(raw) == 1
    assert module.publish_verified_reports(raw, published, secret) == 1

    published_png = published / screenshot.relative_to(raw)
    assert published_png.is_file()
    with Image.open(published_png) as image:
        assert image.format == "PNG"
        assert image.info == {}
        assert image.size == (80, 40)
    data = published_png.read_bytes().lower()
    for marker in (b"synthetic-query-secret", b"synthetic-response-body", b"synthetic-only-passphrase",
                   b"synthetic-cookie-value", b"comment", b"description"):
        assert marker not in data
    assert _png_chunk_types(published_png) == [b"IHDR", b"IDAT", b"IEND"]
    assert json.loads((published / "run-summary.json").read_text())["screenshots_uploaded"] == 1


def test_pngs_outside_failure_name_viewport_or_current_run_are_never_published(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _write_png(raw / "test-results" / _screenshot_dir("desktop-1440x1000") / "test-failed-2.png")
    _write_png(raw / "test-results" / "unrelated-test-desktop-1440x1000" / "test-failed-1.png")
    _write_png(raw / "test-results" / "inbox-browser-explicit-Inb-3c225-ection-at-desktop-1440x1000-spoof" / "test-failed-1.png")
    _write_png(raw / "test-results" / _screenshot_dir("mobile-390x844") / "attachment.png")
    _write_png(raw / "test-results" / _screenshot_dir("mobile-390x844") / "resources" / "failure.png")

    assert module.count_allowlisted_failure_screenshots(raw) == 0
    assert module.publish_verified_reports(raw, published, secret) == 0
    assert not list(published.rglob("*.png"))


def test_failure_screenshot_is_not_published_outside_github_linux_browser_context(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ALLOW_FAILURE_SCREENSHOT_PUBLICATION", True)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    _write_png(raw / "test-results" / _screenshot_dir("tablet-820x1180") / "test-failed-1.png")
    secret = _write_secret(tmp_path / "password")

    assert module.count_allowlisted_failure_screenshots(raw) == 0
    assert module.publish_verified_reports(raw, published, secret) == 0
    assert not list(published.rglob("*.png"))


def test_final_gate_detects_unsanitized_png_metadata_and_withholds_entire_upload(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _seed_raw_reports(raw)
    screenshot = raw / "test-results" / _screenshot_dir("desktop-1440x1000") / "test-failed-1.png"
    _write_png(screenshot, metadata={"Comment": "SYNTHETIC_QUERY_SECRET SYNTHETIC_RESPONSE_BODY"})
    monkeypatch.setattr(module, "_sanitize_failure_screenshots", lambda _root: None)

    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


def test_near_match_screenshot_directory_is_ignored_and_exact_directory_remains_eligible(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    raw.mkdir()
    secret = _write_secret(tmp_path / "password")
    _write_png(raw / "test-results" / _screenshot_dir("tablet-820x1180") / "test-failed-1.png")
    _write_png(raw / "test-results" / (_screenshot_dir("tablet-820x1180") + "-spoof") / "test-failed-1.png")

    assert module.count_allowlisted_failure_screenshots(raw) == 1


def test_malformed_or_oversized_allowlisted_png_fails_closed(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    for payload in (b"not a PNG",):
        raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
        _seed_raw_reports(raw, diagnostic_viewport="tablet-820x1180")
        screenshot = raw / "test-results" / _screenshot_dir("tablet-820x1180") / "test-failed-1.png"
        screenshot.write_bytes(payload)
        secret = _write_secret(tmp_path / "password")
        with pytest.raises(RuntimeError, match="upload withheld"):
            module.publish_verified_reports(raw, published, secret)
        assert list(published.iterdir()) == []
        shutil.rmtree(raw)
        shutil.rmtree(published)

    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    _seed_raw_reports(raw, diagnostic_viewport="mobile-390x844")
    screenshot = raw / "test-results" / _screenshot_dir("mobile-390x844") / "test-failed-1.png"
    _write_png(screenshot)
    screenshot.write_bytes(b"x" * (module.MAX_SCREENSHOT_BYTES + 1))
    secret = _write_secret(tmp_path / "password")
    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []

    raw, published = tmp_path / "raw-dimensions", tmp_path / "published-dimensions"
    _seed_raw_reports(raw, diagnostic_viewport="mobile-390x844")
    screenshot = raw / "test-results" / _screenshot_dir("mobile-390x844") / "test-failed-1.png"
    _write_png(screenshot)
    Image.new("RGB", (module.MAX_SCREENSHOT_WIDTH + 1, 1)).save(screenshot, format="PNG")
    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


def test_nonallowlisted_png_in_staging_is_rejected_by_final_leak_gate(tmp_path):
    artifacts = tmp_path / "artifacts"
    secret = _write_secret(tmp_path / "password")
    _write_png(artifacts / "unknown" / "failure.png")
    with pytest.raises(RuntimeError, match="non-allowlisted PNG"):
        module.verify_artifact_redaction(artifacts, secret)


def test_allowlisted_screenshot_symlink_fails_closed(tmp_path, monkeypatch):
    _enable_current_linux_browser_run(monkeypatch)
    raw, published = tmp_path / "raw", tmp_path / "artifacts-sanitized"
    _seed_raw_reports(raw, diagnostic_viewport="mobile-390x844")
    outside = tmp_path / "outside.png"
    _write_png(outside)
    target = raw / "test-results" / _screenshot_dir("mobile-390x844") / "test-failed-1.png"
    target.symlink_to(outside)
    secret = _write_secret(tmp_path / "password")

    with pytest.raises(RuntimeError, match="upload withheld"):
        module.publish_verified_reports(raw, published, secret)
    assert list(published.iterdir()) == []


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
