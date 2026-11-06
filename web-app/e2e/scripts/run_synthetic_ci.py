#!/usr/bin/env python3
"""Run an isolated Core + Vite + Playwright acceptance and clean its temp state."""
from __future__ import annotations

import json
import hashlib
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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "web-app" / "secondbrain-core"
FRONTEND = ROOT / "web-app" / "secondbrain-frontend"
E2E = Path(__file__).resolve().parents[1]
ARTIFACTS = E2E / "artifacts-sanitized"
CORE_URL = ""
WEB_URL = ""
OPAQUE_ID = __import__("re").compile(r"(?i)\b(?:[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}|[0-9a-f]{32})\b")
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
FAILURE_JUNIT_TESTCASE_VIEWPORTS = {
    ("inbox-browser.spec.ts", "explicit Inbox capture, retry, conflict and source protection at desktop-1440x1000"): "desktop-1440x1000",
    ("inbox-browser.spec.ts", "explicit Inbox capture, retry, conflict and source protection at tablet-820x1180"): "tablet-820x1180",
    ("inbox-browser.spec.ts", "explicit Inbox capture, retry, conflict and source protection at mobile-390x844"): "mobile-390x844",
}
FAILURE_DIAGNOSTIC_STAGES = {
    "test_setup", "login", "session", "first_submit", "retry", "conflict",
    "ordinary_chat", "source_protection", "daily_brief_read", "daily_brief_sources",
    "daily_brief_journal", "daily_brief_preview", "daily_brief_confirm",
    "daily_brief_readback", "permission_revocation", "post_revocation_navigation",
    "agent_health", "today", "journal", "calendar", "notes_navigation",
    "notes_create", "notes_edit_save", "notes_reopen", "notes_frontmatter_seed",
    "notes_frontmatter_reopen", "notes_blocksuite_open",
    "notes_blocksuite_edit", "notes_blocksuite_reopen", "viewport_layout",
}
FAILURE_DIAGNOSTIC_CODES = {"assertion_failed", "timeout", "test_error"}
FAILURE_DIAGNOSTIC_ASSERTIONS = {
    "test_setup", "home_to_projects", "projects_heading", "home_after_projects",
    "home_to_activity", "activity_heading", "activity_get_response",
    "activity_get_status_200", "home_after_activity", "home_after_revocation",
    "agent_health_heading", "home_after_agent_health", "today_heading", "home_after_today",
    "journal_heading", "home_after_journal", "calendar_heading", "layout_no_horizontal_overflow",
    "projects_navigation", "projects_api_response", "activity_navigation",
    "agent_health_navigation", "agent_health_api_response", "today_navigation",
    "today_api_response", "journal_navigation", "journal_api_response", "journal_append",
    "journal_saved_readback", "journal_refresh_readback",
    "calendar_navigation", "calendar_api_response", "home_api_response",
    "layout_home", "layout_projects", "layout_activity", "layout_agent_health",
    "layout_today", "layout_journal", "layout_calendar", "chat_session",
    "chat_context_preview", "chat_preview_button_visible", "chat_preview_button_enabled",
    "chat_preview_button_in_viewport", "chat_preview_request", "chat_preview_result_status",
    "chat_preview_result_source",
    "chat_grounding", "chat_planning", "chat_attachment",
    "chat_composer", "chat_run", "chat_run_waiting", "chat_run_completed", "chat_run_status_count",
    "chat_run_candidates", "chat_run_citations", "chat_run_citation_panel", "chat_run_citation_content",
    "chat_composer_reset", "chat_reload",
    "notes_navigation", "notes_navigation_link", "notes_collections", "notes_create", "notes_save",
    "notes_readback", "notes_readback_payload", "notes_readback_editor_missing",
    "notes_frontmatter_seed", "notes_frontmatter_reopen",
    "notes_blocksuite_button_click", "notes_blocksuite_canvas_visible", "notes_blocksuite_save_status",
    "notes_blocksuite_body_visible", "notes_blocksuite_enabled", "notes_blocksuite_contenteditable",
    "notes_blocksuite_simple_open",
    "notes_blocksuite_open", "notes_blocksuite_edit", "notes_blocksuite_reopen",
    "layout_notes", "layout_chat",
    "daily_brief_navigation", "daily_brief_heading", "daily_brief_saved_readback",
    "daily_brief_open_prepare", "daily_brief_task_source", "daily_brief_project_source",
    "daily_brief_project_count", "daily_brief_project_label", "daily_brief_project_visible",
    "daily_brief_project_click", "daily_brief_project_checked",
    "daily_brief_sources", "daily_brief_journal_action",
    "daily_brief_journal_source", "daily_brief_preview",
    "activity_revocation_denial", "activity_revocation_empty", "activity_revocation_status_403",
    "calendar_api_requests",
}
MAX_FAILURE_DIAGNOSTIC_BYTES = 2048
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
               "journal_source_fixture_files", "journal_mutated_files", "brief_files",
               "brief_file_set_verified", "notes_files", "python", "node",
               "html_report_uploaded", "screenshots_uploaded"}
    path.write_text(json.dumps({key: summary[key] for key in allowed if key in summary}, indent=2) + "\n",
                    encoding="utf-8")


def _validate_failure_diagnostics(value) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > MAX_FAILURE_SCREENSHOTS:
        raise RuntimeError("failure diagnostic schema rejected; upload withheld")
    validated = []
    seen_viewports = set()
    for entry in value:
        base_keys = {"viewport", "stage", "code", "assertion_id", "activity_get_statuses"}
        optional_keys = ("notes_collection_statuses", "daily_brief_get_statuses",
                         "notes_item_read_statuses", "notes_readback_failure", "notes_seed_status",
                         "notes_ui_state", "page_error_names", "page_error_categories", "page_error_sources",
                         "blocksuite_module_statuses", "page_error_summaries")
        allowed_shapes = {
            frozenset(base_keys | {key for index, key in enumerate(optional_keys) if mask & (1 << index)})
            for mask in range(1 << len(optional_keys))
        }
        if not isinstance(entry, dict) or frozenset(entry) not in allowed_shapes:
            raise RuntimeError("failure diagnostic fields rejected; upload withheld")
        viewport = entry["viewport"]
        stage = entry["stage"]
        code = entry["code"]
        assertion_id = entry["assertion_id"]
        activity_statuses = entry["activity_get_statuses"]
        notes_statuses = entry.get("notes_collection_statuses", [])
        notes_item_statuses = entry.get("notes_item_read_statuses", [])
        notes_readback_failure = entry.get("notes_readback_failure")
        notes_seed_status = entry.get("notes_seed_status")
        notes_ui_state = entry.get("notes_ui_state")
        page_error_names = entry.get("page_error_names", [])
        page_error_categories = entry.get("page_error_categories", [])
        page_error_sources = entry.get("page_error_sources", [])
        blocksuite_module_statuses = entry.get("blocksuite_module_statuses", [])
        page_error_summaries = entry.get("page_error_summaries", [])
        brief_statuses = entry.get("daily_brief_get_statuses", [])
        if (not isinstance(viewport, str) or viewport not in FAILURE_SCREENSHOT_DIR_VIEWPORTS.values()
                or not isinstance(stage, str) or stage not in FAILURE_DIAGNOSTIC_STAGES
                or not isinstance(code, str) or code not in FAILURE_DIAGNOSTIC_CODES
                or not isinstance(assertion_id, str) or assertion_id not in FAILURE_DIAGNOSTIC_ASSERTIONS
                or not isinstance(activity_statuses, list) or len(activity_statuses) > 4
                or any(status is not None and (type(status) is not int or not 100 <= status <= 599)
                       for status in activity_statuses)
                or not isinstance(notes_statuses, list) or len(notes_statuses) > 4
                or any(status is not None and (type(status) is not int or not 100 <= status <= 599)
                       for status in notes_statuses)
                or not isinstance(notes_item_statuses, list) or len(notes_item_statuses) > 4
                or any(status is not None and (type(status) is not int or not 100 <= status <= 599)
                       for status in notes_item_statuses)
                or (notes_readback_failure is not None and (
                    not isinstance(notes_readback_failure, str) or notes_readback_failure not in {
                        "session_required", "action_not_enabled", "draft_directory_permissions_unsafe",
                        "directory_permissions_unsafe", "note_file_permissions_unsafe", "note_open_rejected",
                        "note_not_found", "other",
                    }))
                or (notes_seed_status is not None
                    and (type(notes_seed_status) is not int or not 100 <= notes_seed_status <= 599))
                or (notes_ui_state is not None and (
                    not isinstance(notes_ui_state, str) or notes_ui_state not in {
                        "vite_error", "fallback_message", "fallback_invalid_frontmatter", "fallback_unsupported_syntax",
                        "fallback_markdown_conversion_error", "fallback_unsafe_roundtrip",
                        "fallback_content_mismatch",
                        "fallback_view_initialization_error", "blocksuite_canvas", "legacy_editor",
                        "app_blank", "canvas_missing", "unavailable",
                    }))
                or not isinstance(page_error_names, list) or len(page_error_names) > 5
                or any(not isinstance(name, str) or name not in {
                    "Error", "TypeError", "ReferenceError", "RangeError", "SyntaxError", "URIError", "unknown",
                }
                       for name in page_error_names)
                or not isinstance(page_error_categories, list) or len(page_error_categories) > 5
                or any(not isinstance(category, str) or category not in {
                    "nullish_property_access", "invalid_runtime_symbol", "custom_element_registration",
                    "module_load_failure", "missing_block_extension", "view_service_error",
                    "block_schema_error", "document_state_error", "react_lazy_error", "other",
                } for category in page_error_categories)
                or not isinstance(page_error_sources, list) or len(page_error_sources) > 5
                or any(not isinstance(source, str) or source not in {
                    "blocksuite_module", "notes_page_module", "react_dom", "vite_runtime", "other_module",
                } for source in page_error_sources)
                or not isinstance(blocksuite_module_statuses, list) or len(blocksuite_module_statuses) > 8
                or any(status is not None and (type(status) is not int or not 100 <= status <= 599)
                       for status in blocksuite_module_statuses)
                or not isinstance(page_error_summaries, list) or len(page_error_summaries) > 5
                or any(not isinstance(summary, str) or len(summary) > 120
                       or not re.fullmatch(r"[A-Za-z0-9 <>._,:()'-]{1,120}", summary)
                       for summary in page_error_summaries)
                or not isinstance(brief_statuses, list) or len(brief_statuses) > 4
                or any(status is not None and (type(status) is not int or not 100 <= status <= 599)
                       for status in brief_statuses)
                or viewport in seen_viewports):
            raise RuntimeError("failure diagnostic value rejected; upload withheld")
        seen_viewports.add(viewport)
        normalized = {"viewport": viewport, "stage": stage, "code": code,
                      "assertion_id": assertion_id, "activity_get_statuses": activity_statuses}
        if "notes_collection_statuses" in entry:
            normalized["notes_collection_statuses"] = notes_statuses
        if "notes_item_read_statuses" in entry:
            normalized["notes_item_read_statuses"] = notes_item_statuses
        if "notes_readback_failure" in entry:
            normalized["notes_readback_failure"] = notes_readback_failure
        if "notes_seed_status" in entry:
            normalized["notes_seed_status"] = notes_seed_status
        if "notes_ui_state" in entry:
            normalized["notes_ui_state"] = notes_ui_state
        if "page_error_names" in entry:
            normalized["page_error_names"] = page_error_names
        if "page_error_categories" in entry:
            normalized["page_error_categories"] = page_error_categories
        if "page_error_sources" in entry:
            normalized["page_error_sources"] = page_error_sources
        if "blocksuite_module_statuses" in entry:
            normalized["blocksuite_module_statuses"] = blocksuite_module_statuses
        if "page_error_summaries" in entry:
            normalized["page_error_summaries"] = page_error_summaries
        if "daily_brief_get_statuses" in entry:
            normalized["daily_brief_get_statuses"] = brief_statuses
        validated.append(normalized)
    return validated


def _collect_failure_diagnostics(raw_root: Path) -> list[dict[str, object]]:
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
    testcase_viewports = []
    failed_viewports = []
    for element in junit.iter():
        if element.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        identity = (element.attrib.get("classname"), element.attrib.get("name"))
        viewport = FAILURE_JUNIT_TESTCASE_VIEWPORTS.get(identity)
        if viewport is None:
            raise RuntimeError("failure diagnostic JUnit testcase identity rejected; upload withheld")
        testcase_viewports.append(viewport)
        if any(child.tag.rsplit("}", 1)[-1] in {"failure", "error"} for child in element):
            failed_viewports.append(viewport)
    if (len(testcase_viewports) != len(FAILURE_JUNIT_TESTCASE_VIEWPORTS)
            or set(testcase_viewports) != set(FAILURE_JUNIT_TESTCASE_VIEWPORTS.values())
            or len(set(testcase_viewports)) != len(testcase_viewports)):
        safe_observed = ",".join(testcase_viewports)
        safe_failed = ",".join(failed_viewports)
        raise RuntimeError(f"failure diagnostic JUnit testcase set rejected; upload withheld; count={len(testcase_viewports)}; observed={safe_observed}; failed={safe_failed}")
    failed_viewport_set = set(failed_viewports)
    if summary_path.exists():
        if summary_path.stat().st_size > 4096 or not summary_path.is_file():
            raise RuntimeError("failure diagnostic run summary rejected; upload withheld")
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
            raise RuntimeError("failure diagnostic run summary rejected; upload withheld") from error
        if not isinstance(summary, dict):
            raise RuntimeError("failure diagnostic run summary rejected; upload withheld")
        if summary.get("result") == "FAIL" and not failed_viewports:
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
            base_keys = {"schema_version", "viewport", "stage", "code", "assertion_id", "activity_get_statuses"}
            optional_keys = ("notes_collection_statuses", "daily_brief_get_statuses",
                             "notes_item_read_statuses", "notes_readback_failure", "notes_seed_status",
                             "notes_ui_state", "page_error_names", "page_error_categories", "page_error_sources",
                             "blocksuite_module_statuses", "page_error_summaries")
            allowed_shapes = {
                frozenset(base_keys | {key for index, key in enumerate(optional_keys) if mask & (1 << index)})
                for mask in range(1 << len(optional_keys))
            }
            if (not isinstance(raw, dict) or frozenset(raw) not in allowed_shapes
                    or type(raw.get("schema_version")) is not int or raw.get("schema_version") != 2
                    or raw.get("viewport") != viewport):
                raise RuntimeError("failure diagnostic source schema rejected; upload withheld")
            diagnostics.append({
                "viewport": viewport, "stage": raw.get("stage"), "code": raw.get("code"),
                "assertion_id": raw.get("assertion_id"),
                "activity_get_statuses": raw.get("activity_get_statuses"),
            })
            if "notes_collection_statuses" in raw:
                diagnostics[-1]["notes_collection_statuses"] = raw["notes_collection_statuses"]
            if "notes_item_read_statuses" in raw:
                diagnostics[-1]["notes_item_read_statuses"] = raw["notes_item_read_statuses"]
            if "notes_readback_failure" in raw:
                diagnostics[-1]["notes_readback_failure"] = raw["notes_readback_failure"]
            if "notes_seed_status" in raw:
                diagnostics[-1]["notes_seed_status"] = raw["notes_seed_status"]
            if "notes_ui_state" in raw:
                diagnostics[-1]["notes_ui_state"] = raw["notes_ui_state"]
            if "page_error_names" in raw:
                diagnostics[-1]["page_error_names"] = raw["page_error_names"]
            if "page_error_categories" in raw:
                diagnostics[-1]["page_error_categories"] = raw["page_error_categories"]
            if "page_error_sources" in raw:
                diagnostics[-1]["page_error_sources"] = raw["page_error_sources"]
            if "blocksuite_module_statuses" in raw:
                diagnostics[-1]["blocksuite_module_statuses"] = raw["blocksuite_module_statuses"]
            if "page_error_summaries" in raw:
                diagnostics[-1]["page_error_summaries"] = raw["page_error_summaries"]
            if "daily_brief_get_statuses" in raw:
                diagnostics[-1]["daily_brief_get_statuses"] = raw["daily_brief_get_statuses"]

    diagnostics = _validate_failure_diagnostics(diagnostics)
    diagnostic_viewports = {entry["viewport"] for entry in diagnostics}
    if not diagnostic_viewports.issubset(failed_viewport_set):
        raise RuntimeError("failure diagnostics do not match failed testcase viewports; upload withheld")
    # JUnit identifies which allowlisted viewport failed, but not why. A
    # missing per-viewport summary is not evidence of browser/test setup
    # failure; withhold the report unless every failed viewport has an
    # explicit, validated diagnostic rather than inventing a stage.
    if diagnostic_viewports != failed_viewport_set:
        raise RuntimeError("failure diagnostics do not cover every failed testcase viewport; upload withheld")
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
        reason = str(error)
        # Surface only a short, path-free validator message so a withheld
        # report can be diagnosed from Actions logs. Never echo arbitrary OS
        # exceptions, paths, or report contents.
        if (type(error) is RuntimeError and re.fullmatch(r"[A-Za-z0-9 _.,:=;()'-]{1,220}", reason)
                and "/" not in reason and "\\" not in reason
                and not any(marker in reason.lower() for marker in ("token", "cookie", "secret", "password", "authorization"))):
            safe_detail = f" ({reason})"
        else:
            safe_detail = f" ({type(error).__name__})"
        raise RuntimeError(f"report validation failed; artifact upload withheld{safe_detail}") from error


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


def seed_daily_brief_sources(dirs: dict[str, Path]) -> dict[str, bytes]:
    """Seed one synthetic row in each frozen Brief source; never use external data."""
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    task = {
        "id": uuid.uuid4().hex,
        "title": "Synthetic brief task source",
        "due_date": day,
        "status": "open",
        "created_at": stamp,
        "updated_at": stamp,
        "source": "web_app_explicit_task",
        "original_command": "synthetic fixture only",
        "operation_id": "synthetic-brief-fixture-task",
        "session_id": "synthetic-brief-fixture-session",
        "history": [],
    }
    (dirs["task"] / "tasks.json").write_text(
        json.dumps({"tasks": [task], "idempotency": {}}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(dirs["task"] / "tasks.json", 0o600)

    project = {"id": "synthetic-brief-project", "title": "Synthetic brief project source", "status": "active"}
    (dirs["projects"] / "synthetic-brief-project.json").write_text(
        json.dumps(project, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8",
    )
    os.chmod(dirs["projects"] / "synthetic-brief-project.json", 0o600)

    journal_record = {
        "id": hashlib.sha256(f"synthetic-journal-source:{uuid.uuid4()}".encode()).hexdigest(),
        "operation_id": "synthetic-brief-fixture-journal",
        "session_id": "synthetic-brief-fixture-session",
        "date": day,
        "created_at": now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "source": "web_app_explicit_intent",
        "original_text": "Synthetic Journal source fixture; never read or published by the UI.",
    }
    journal_file = dirs["journal"] / f"{day}.jsonl"
    journal_file.write_text(json.dumps(journal_record, ensure_ascii=False, separators=(",", ":")) + "\n",
                            encoding="utf-8")
    os.chmod(journal_file, 0o600)
    return {item.name: item.read_bytes() for item in dirs["journal"].iterdir() if item.is_file()}


def seed_notes_safety_fixtures(notes_root: Path) -> None:
    """Create only synthetic Draft files for unsupported syntax/fallback checks."""
    fixtures = {
        "wp5-unsafe-markdown.md": (
            "# WP5 unsafe Markdown fixture\n\n[[Synthetic Wiki Target]]\n"
            "![[synthetic-embed.png]]\n\n<details><summary>unknown block</summary></details>\n"
        ),
        "wp5-attachment-fallback.md": (
            "# WP5 attachment fallback fixture\n\n"
            "![synthetic attachment](attachments/synthetic-attachment.png)\n"
        ),
    }
    for name, content in fixtures.items():
        target = notes_root / name
        target.write_text(content, encoding="utf-8", newline="")
        os.chmod(target, 0o600)


def assert_journal_fixture_unchanged(root: Path, baseline: dict[str, bytes], *,
                                     expected_browser_appends: int = 0) -> None:
    current = _read_regular_file_snapshot(root)
    if expected_browser_appends == 0:
        if current != baseline:
            raise RuntimeError("synthetic Journal source changed during Brief acceptance")
        return
    if len(baseline) != 1 or len(current) != 3 or not set(baseline).issubset(current):
        raise RuntimeError("synthetic Journal file set changed during browser acceptance")
    name = next(iter(baseline))
    expected_locks = {".operations.lock", f".{name[:-6]}.lock"}
    if set(current) != set(baseline) | expected_locks:
        raise RuntimeError("synthetic Journal lock file set changed unexpectedly")
    for lock_name in expected_locks:
        lock_path = root / lock_name
        if lock_path.stat().st_mode & 0o777 != 0o600 or current[lock_name] != b"":
            raise RuntimeError("synthetic Journal lock file permissions or contents are unsafe")
    before = baseline[name]
    after = current[name]
    if not after.startswith(before) or not before.endswith(b"\n"):
        raise RuntimeError("pre-existing synthetic Journal entry was changed or removed")
    appended = after[len(before):].splitlines()
    if len(appended) != expected_browser_appends:
        raise RuntimeError("unexpected synthetic Journal append count")
    operations = set()
    for line in appended:
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RuntimeError("synthetic Journal append is not valid JSONL") from error
        if (not isinstance(row, dict) or row.get("source") != "web_app_explicit_intent"
                or not isinstance(row.get("original_text"), str)
                or not row["original_text"].startswith("记一下：合成浏览器追加 ")
                or not isinstance(row.get("operation_id"), str) or not row["operation_id"]
                or row["operation_id"] in operations or row.get("date") != name[:-6]):
            raise RuntimeError("synthetic Journal append was outside the browser test allowlist")
        operations.add(row["operation_id"])


def _read_regular_file_snapshot(root: Path) -> dict[str, bytes]:
    snapshot = {}
    for item in root.iterdir():
        if item.is_symlink() or not item.is_file():
            raise RuntimeError("synthetic data directory contains a non-regular entry")
        snapshot[item.name] = item.read_bytes()
    return snapshot


def _assert_exact_brief_file_set(root: Path, date_file_name: str) -> int:
    names = set()
    for item in root.iterdir():
        if item.is_symlink() or not item.is_file():
            raise RuntimeError("synthetic Daily Brief directory contains a non-regular entry")
        names.add(item.name)
    operation_hashes = {
        match.group(1) for name in names
        if (match := re.fullmatch(r"\.op-([a-f0-9]{64})\.json", name)) is not None
    }
    lock_hashes = {
        match.group(1) for name in names
        if (match := re.fullmatch(r"\.op-lock-([a-f0-9]{64})", name)) is not None
    }
    date_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.json", date_file_name)
    date_lock = f".date-lock-{date_match.group(1)}" if date_match else None
    expected_shape = (date_lock is not None and date_file_name in names
                      and date_lock in names and len(operation_hashes) == 1
                      and operation_hashes == lock_hashes and len(names) == 4)
    if not expected_shape:
        raise RuntimeError("synthetic Daily Brief directory file set mismatch")
    return len(names)


def http_smoke(password_path: Path) -> list[dict]:
    """Exercise real Core HTTP through Vite without launching a browser."""
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_log: list[dict] = []

    def request(method: str, path: str, body: dict | None = None, *, headers: dict[str, str] | None = None,
                opener=client, origin=WEB_URL):
        started = time.monotonic()
        data = json.dumps(body).encode() if body is not None else None
        request_headers = {"Origin": origin}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
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

    status, collections, _ = request("GET", "/api/notes")
    if status != 200 or collections != {"collections": [{"id": "drafts", "kind": "drafts"}]}:
        raise RuntimeError("synthetic Notes collections read did not return the private Drafts collection")
    initial_note = "# Synthetic HTTP note\n\nInitial body.\n"
    status, note, _ = request("POST", "/api/notes", {"content": initial_note})
    if (status != 200 or not isinstance(note, dict) or note.get("collection") != "drafts"
            or not isinstance(note.get("path"), str) or not __import__("re").fullmatch(r"[0-9a-f-]{36}", note["path"])
            or note.get("content") != initial_note or not isinstance(note.get("etag"), str)):
        raise RuntimeError("synthetic Notes Draft creation receipt did not match the request")
    note_path = f"/api/notes/drafts/{note['path']}"
    status, read_note, _ = request("GET", note_path)
    if status != 200 or not isinstance(read_note, dict) or read_note.get("content") != initial_note:
        raise RuntimeError("synthetic Notes Draft initial readback did not match the created content")
    updated_note_content = "# Synthetic HTTP note\n\nUpdated body.\n"
    status, updated_note, _ = request("PUT", note_path, {"content": updated_note_content},
                                      headers={"If-Match": f'"{note["etag"]}"'})
    if status != 200 or not isinstance(updated_note, dict) or updated_note.get("content") != updated_note_content:
        raise RuntimeError("synthetic Notes Draft update did not return the saved content")
    stale_status, _, _ = request("PUT", note_path, {"content": "# Synthetic HTTP note\n\nStale body.\n"},
                                 headers={"If-Match": f'"{note["etag"]}"'})
    status, persisted_note, _ = request("GET", note_path)
    if (stale_status != 412 or status != 200 or not isinstance(persisted_note, dict)
            or persisted_note.get("content") != updated_note_content):
        raise RuntimeError("synthetic Notes stale ETag did not preserve the latest saved content")

    day = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    status, tasks, _ = request("GET", "/api/tasks?status=all")
    if status != 200 or not isinstance(tasks, dict):
        raise RuntimeError("synthetic Task source did not return HTTP 200")
    task_rows = tasks.get("tasks")
    if not isinstance(task_rows, list) or len(task_rows) != 1:
        raise RuntimeError("synthetic Task source fixture was not uniquely available")
    task = task_rows[0]
    task_fields = ("id", "title", "due_date", "status", "created_at", "updated_at", "source")
    if task.get("title") != "Synthetic brief task source":
        raise RuntimeError("Task source did not match the synthetic fixture")
    task_canonical = {key: task[key] for key in task_fields}
    task_version = hashlib.sha256(json.dumps(
        task_canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    task_ref = {"kind": "task", "id": task["id"], "version": task_version}

    status, projects, _ = request("GET", "/api/projects?limit=50&offset=0")
    if status != 200 or not isinstance(projects, dict) or projects.get("status") != "real":
        safe_status = projects.get("status") if isinstance(projects, dict) else "invalid-response"
        raise RuntimeError(f"synthetic Project source was not real (HTTP {status}, status={safe_status})")
    project_rows = projects.get("items")
    if not isinstance(project_rows, list) or len(project_rows) != 1:
        raise RuntimeError("synthetic Project source fixture was not uniquely available")
    project = project_rows[0]
    if project.get("id") != "synthetic-brief-project":
        raise RuntimeError("Project source did not match the synthetic fixture")
    project_ref = {"kind": "project", **project["source_ref"]}

    status, journals, _ = request(
        "GET", f"/api/daily-brief/source-options/journal?date={day}"
    )
    if status != 200 or not isinstance(journals, dict) or journals.get("status") != "real":
        raise RuntimeError("synthetic Journal source did not return HTTP 200 real data")
    journal_rows = journals.get("items")
    if not isinstance(journal_rows, list) or len(journal_rows) != 1:
        raise RuntimeError("synthetic Journal source fixture was not uniquely available")
    journal_row = journal_rows[0]
    if journal_row.get("date") != day or journal_row.get("kind") != "journal":
        raise RuntimeError("Journal source did not match the expected synthetic day")
    journal_ref = {"kind": "journal", "id": journal_row["id"],
                   "version": journal_row["version"]}

    brief_path = f"/api/daily-brief?date={day}&timezone=Asia%2FShanghai"
    status, current, _ = request("GET", brief_path)
    if status != 200 or not isinstance(current, dict) or current.get("status") != "empty":
        raise RuntimeError("Daily Brief did not start in the expected empty state")
    brief_payload = {
        "mode": "manual_generate", "date": day, "timezone": "Asia/Shanghai",
        "idempotency_key": f"synthetic-a96-{uuid.uuid4().hex}",
        "categories": ["synthetic"],
        "summary": "Synthetic local-only Daily Brief integration result.",
        "source_refs": [task_ref, project_ref, journal_ref], "approved": True,
    }
    status, receipt, _ = request("POST", "/api/daily-brief", brief_payload)
    receipt_fields = {"status", "brief_id", "date", "timezone", "record_version", "operation_id"}
    if status != 201 or not isinstance(receipt, dict) or set(receipt) != receipt_fields:
        raise RuntimeError("Daily Brief manual POST did not return the exact HTTP 201 receipt")
    if receipt.get("status") != "created" or receipt.get("date") != day:
        raise RuntimeError("Daily Brief POST receipt did not confirm the requested synthetic day")
    status, readback, _ = request("GET", brief_path)
    if status != 200 or not isinstance(readback, dict) or readback.get("status") != "real":
        raise RuntimeError("Daily Brief exact GET did not return the created record")
    brief_rows = readback.get("items")
    if not isinstance(brief_rows, list) or len(brief_rows) != 1:
        raise RuntimeError("Daily Brief GET did not return exactly one synthetic record")
    brief = brief_rows[0]
    if brief.get("brief_id") != receipt["brief_id"] or brief.get("summary") != brief_payload["summary"]:
        raise RuntimeError("Daily Brief GET did not match the exact POST receipt and request")
    if brief.get("source_refs") != brief_payload["source_refs"]:
        raise RuntimeError("Daily Brief GET source references did not match the verified inputs")
    duplicate_status, duplicate, _ = request("POST", "/api/daily-brief", brief_payload)
    if duplicate_status != 200 or not isinstance(duplicate, dict) or duplicate.get("status") != "duplicate":
        raise RuntimeError("Daily Brief exact retry was not idempotently acknowledged")
    if duplicate.get("brief_id") != receipt["brief_id"] or duplicate.get("operation_id") != receipt["operation_id"]:
        raise RuntimeError("Daily Brief idempotent retry did not preserve the original receipt")
    conflict_payload = {**brief_payload, "summary": brief_payload["summary"] + " changed"}
    conflict_status, _, _ = request("POST", "/api/daily-brief", conflict_payload)
    if conflict_status != 409:
        raise RuntimeError("Daily Brief changed payload with the same key did not return HTTP 409")
    invalid_import_status, invalid_import, invalid_import_raw = request("POST", "/api/daily-brief", {
        **brief_payload, "mode": "approved_import",
        "import_ref": {"kind": "existing_brief", "id": "synthetic-import", "version": "a" * 64},
    })
    if (invalid_import_status != 422 or not isinstance(invalid_import, dict)
            or invalid_import.get("detail") != "invalid request"
            or b"synthetic-import" in invalid_import_raw):
        raise RuntimeError("malformed approved_import reference was not safely rejected with HTTP 422")

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
    allowed_source_paths = {
        "/api/tasks?status=all", "/api/projects?limit=50&offset=0",
        f"/api/daily-brief/source-options/journal?date={day}", brief_path,
        "/api/daily-brief",
    }
    if any(entry["path"].startswith(("/api/journal/entries", "/api/knowledge", "/api/capture"))
           for entry in request_log):
        raise RuntimeError("HTTP smoke unexpectedly called a protected target API")
    if any(entry["path"].startswith(("/api/tasks", "/api/projects", "/api/daily-brief"))
           and entry["path"] not in allowed_source_paths for entry in request_log):
        raise RuntimeError("HTTP smoke called an unapproved source or Brief endpoint")
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
    # Core opens every configured data root with O_NOFOLLOW from /. macOS
    # commonly returns a /var/folders temporary path whose /var parent is a
    # symlink; canonicalize the harness-owned root before passing its children
    # to Core so only these temporary directories are opened.
    root = Path(tempfile.mkdtemp(prefix="secondbrain-a-web-e2e-")).resolve()
    os.chmod(root, 0o700)
    raw_artifacts = root / "playwright-raw"
    raw_artifacts.mkdir(mode=0o700)
    processes: list[subprocess.Popen] = []
    log_files = []
    result = 1
    try:
        dirs = {name: root / name for name in ("raw", "review", "state", "knowledge", "journal", "task", "projects", "briefs", "notes")}
        for path in dirs.values():
            path.mkdir(mode=0o700)
        seed_notes_safety_fixtures(dirs["notes"])
        journal_fixture = seed_daily_brief_sources(dirs)
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
            "SB_PROJECTS_INDEX_ROOT": str(dirs["projects"]),
            "SB_DAILY_BRIEF_STORE_ROOT": str(dirs["briefs"]),
            "SB_NOTES_DRAFTS_ROOT": str(dirs["notes"]),
            "SB_APP_PASSWORD_FILE": str(password_path),
            "SB_DASHBOARD_ORIGINS": WEB_URL,
            "SB_CORE_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "SB_PROMOTE_ENABLED": "false",
            "SB_HERMES_API_URL": "",
            "SB_PERSONAL_MEMORY_ENABLED": "false",
            "SB_PERSONAL_LEARNING_ENABLED": "false",
            "VITE_ENABLE_NOTES": "true",
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
        journal_after = _read_regular_file_snapshot(dirs["journal"])
        journal_mutated_files = sum(
            name not in journal_after or journal_after.get(name) != contents for name, contents in journal_fixture.items()
        ) + sum(name not in journal_fixture for name in journal_after)
        today_brief_name = datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat() + ".json"
        brief_file_set_verified = False
        if test_returncode == 0:
            expected_raw = 1 if options.http_smoke_only else 3
            if len(raw_files) != expected_raw:
                raise RuntimeError(f"expected one Raw record per viewport; found {len(raw_files)}")
            assert_no_business_files(dirs["knowledge"], "Knowledge root")
            expected_journal_appends = 0 if options.http_smoke_only else len(FAILURE_SCREENSHOT_DIR_VIEWPORTS)
            assert_journal_fixture_unchanged(
                dirs["journal"], journal_fixture, expected_browser_appends=expected_journal_appends,
            )
            _assert_exact_brief_file_set(dirs["briefs"], today_brief_name)
            brief_file_set_verified = True
        brief_directory_files = sum(
            1 for path in dirs["briefs"].iterdir() if path.is_file() and not path.is_symlink()
        )
        screenshot_count = count_allowlisted_failure_screenshots(raw_artifacts)
        summary = {
            "result": "PASS" if test_returncode == 0 else "FAIL",
            "core": "real localhost HTTP",
            "web": "local Vite",
            "browser": "NOT RUN (local stop gate)" if options.http_smoke_only else "Playwright Linux Chromium (workflow runner only)",
            "promote_enabled": False,
            "hermes": "fixture-only Chat endpoints; no Hermes service or credentials",
            "raw_record_count": len(raw_files),
            # Report actual source files separately from any mutations.
            "journal_files": len(journal_after),
            "journal_source_fixture_files": len(journal_fixture),
            "journal_mutated_files": journal_mutated_files,
            "brief_files": brief_directory_files,
            "brief_file_set_verified": brief_file_set_verified,
            "notes_files": sum(1 for path in dirs["notes"].rglob("*") if path.is_file() and not path.is_symlink()),
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
