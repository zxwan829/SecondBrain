#!/usr/bin/env python3
"""Run the focused WP5 Notes Chromium journey without the formal report runner."""
from __future__ import annotations

import argparse
import json
import re
import math
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "web-app" / "secondbrain-core"
FRONTEND = ROOT / "web-app" / "secondbrain-frontend"
E2E = ROOT / "web-app" / "e2e"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, process: subprocess.Popen[bytes], label: str) -> None:
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} stopped before readiness")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"{label} readiness timed out")


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def sanitize_png(source: Path, target: Path, *, mobile: bool = False) -> tuple[int, int]:
    from PIL import Image

    with Image.open(source) as image:
        if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
            raise RuntimeError("browser evidence screenshot is not a single PNG")
        width, height = image.size
        min_width, max_width = (320, 700) if mobile else (1000, 2048)
        if width < min_width or width > max_width or height <= 0 or height > 1600 or width * height > 3_200_000:
            raise RuntimeError("browser evidence screenshot dimensions rejected")
        image.load()
        mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
        pixels = image.convert(mode)
        clean = Image.frombytes(mode, pixels.size, pixels.tobytes())
        clean.save(target, format="PNG", optimize=False)
    os.chmod(target, 0o600)
    with Image.open(target) as clean:
        if clean.info:
            raise RuntimeError("browser evidence screenshot metadata remains")
    return width, height


def verify_evidence(source: Path, target: Path) -> dict:
    evidence = json.loads(source.read_text(encoding="utf-8"))
    if evidence.get("viewport") != "1440x1000":
        raise RuntimeError("browser evidence viewport mismatch")
    enter = evidence.get("enter", {})
    if enter.get("contenteditable") != "true" or not enter.get("selectionInsideEditor"):
        raise RuntimeError("browser evidence focus/selection check failed")
    blocks = enter.get("blocks", [])
    texts = [item.get("text", "") for item in blocks]
    if not any("First line after title" in value for value in texts):
        raise RuntimeError("browser evidence first line missing from Yjs")
    if not any("Second paragraph after Enter" in value for value in texts):
        raise RuntimeError("browser evidence second paragraph missing from Yjs")
    first = evidence.get("firstOpen", {})
    warm = evidence.get("warmOpen", {})
    refresh = evidence.get("refreshOpen", {})
    if any(item.get("viewport") != "1440x1000" for item in (first, warm, refresh)):
        raise RuntimeError("browser evidence performance viewport mismatch")
    if not all(isinstance(item.get("durationMs"), (int, float)) and not isinstance(item.get("durationMs"), bool)
               and math.isfinite(item["durationMs"]) and 0 <= item["durationMs"] <= 1_000_000
               for item in (first, warm, refresh)):
        raise RuntimeError("browser evidence click-to-editable performance measurement missing")
    creation = evidence.get("creationTimings", {})
    first_create = creation.get("firstCreate", {}) if isinstance(creation, dict) else {}
    refresh_state = creation.get("refresh", {}) if isinstance(creation, dict) else {}
    edgeless_state = creation.get("edgelessRefresh", {}) if isinstance(creation, dict) else {}
    repeated = evidence.get("repeatedCreation", {})
    required_stages = {"draftPost", "resourcePost", "markdownReferencePut", "resourceReceiptPut"}
    stages = first_create.get("apiStages", {}) if isinstance(first_create, dict) else {}
    if (not isinstance(creation, dict) or creation.get("viewport") != "1440x1000"
            or not isinstance(creation.get("coldNotesNavigationMs"), (int, float))
            or not isinstance(first_create.get("clickToVisibleFeedbackMs"), (int, float))
            or not isinstance(first_create.get("clickToInputReadyMs"), (int, float))
            or first_create.get("realCaretInputVerified") is not True
            or type(first_create.get("temporaryMarkdownEditorMounts")) is not int
            or first_create.get("temporaryMarkdownEditorMounts") != 0
            or not isinstance(stages, dict) or set(stages) != required_stages
            or any(not isinstance(stages.get(stage), (int, float)) for stage in required_stages)
            or any(status != 200 for status in first_create.get("apiStatuses", []))
            or not isinstance(refresh_state.get("cleanExitPrompt"), bool)
            or refresh_state.get("cleanExitPrompt") is not False
            or refresh_state.get("status") == "有未保存的资源修改"
            or not isinstance(refresh_state.get("openMs"), (int, float))
            or not isinstance(edgeless_state.get("cleanExitPrompt"), bool)
            or not isinstance(edgeless_state.get("status"), str)
            or edgeless_state.get("cleanExitPrompt") is not False
            or edgeless_state.get("status") == "有未保存的资源修改"
            or not isinstance(repeated, dict) or repeated.get("warmSampleCount") != 20
            or len(repeated.get("samples", [])) != 21
            or any(not isinstance(repeated.get(key), (int, float)) for key in
                   ("clickToVisibleFeedbackP95Ms", "clickToInputReadyP95Ms"))
            or type(repeated.get("cleanExitPromptCount")) is not int):
        raise RuntimeError("browser evidence Notes creation/refresh timing measurement missing or invalid")
    required_internal_stages = {"notes-create", "blocksuite-payload-module-load", "blocksuite-module-load", "resource-payload-init", "resource-create",
                                "markdown-save", "resource-receipt-save", "yjs-hydration", "editor-mount"}
    internal_stages = first_create.get("internalStages", [])
    api_waterfall = first_create.get("apiWaterfall", [])
    script_resources = first_create.get("scriptResources", {})
    pre_create_long_tasks = first_create.get("longTasksStartedBeforeCreate", [])
    long_tasks = first_create.get("longTasksStartedDuringCreate", [])
    valid_nonnegative_number = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1_000_000
    valid_byte_count = lambda value: isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000
    valid_asset_name = lambda value: isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,120}\.js", value) is not None
    valid_resource_entry = lambda item: isinstance(item, dict) and valid_asset_name(item.get("name")) \
        and valid_nonnegative_number(item.get("durationMs")) \
        and all(valid_byte_count(item.get(key)) for key in ("transferSize", "decodedBodySize"))
    api_statuses = first_create.get("apiStatuses", [])
    if (not isinstance(internal_stages, list) or len(internal_stages) != len(required_internal_stages)
            or {item.get("stage") for item in internal_stages if isinstance(item, dict)} != required_internal_stages
            or any(not valid_nonnegative_number(item.get("durationMs"))
                   or ("elapsedMs" in item and not valid_nonnegative_number(item.get("elapsedMs"))) for item in internal_stages)
            or not isinstance(api_waterfall, list) or len(api_waterfall) != 4
            or {item.get("stage") for item in api_waterfall if isinstance(item, dict)} != required_stages
            or any(item.get("stage") not in {"draftPost", "resourcePost", "markdownReferencePut", "resourceReceiptPut"}
                   or not valid_nonnegative_number(item.get("requestElapsedMs"))
                   or not valid_nonnegative_number(item.get("durationMs")) or item.get("status") != 200 for item in api_waterfall)
            or not isinstance(api_statuses, list) or len(api_statuses) != 4
            or any(type(status) is not int or status != 200 for status in api_statuses)
            or not isinstance(script_resources, dict)
            or any(type(script_resources.get(key)) is not int or script_resources[key] < 0
                   for key in ("initiatedBeforeCreateCount", "completedBeforeCreateCount", "inFlightAtCreateStartCount",
                               "requestCount", "duplicateUrlCount"))
            or script_resources.get("duplicateUrlCount", 0) > script_resources.get("initiatedBeforeCreateCount", 0)
                + script_resources.get("requestCount", 0)
            or script_resources.get("completedBeforeCreateCount", 0) + script_resources.get("inFlightAtCreateStartCount", 0)
                != script_resources.get("initiatedBeforeCreateCount", -1)
            or not isinstance(script_resources.get("initiatedBeforeCreate"), list)
            or len(script_resources["initiatedBeforeCreate"]) != script_resources["initiatedBeforeCreateCount"]
            or any(not valid_resource_entry(item) or not valid_nonnegative_number(item.get("startTimeMs"))
                   or not valid_nonnegative_number(item.get("responseEndMs")) for item in script_resources["initiatedBeforeCreate"])
            or not isinstance(script_resources.get("requests"), list)
            or any(not valid_resource_entry(item) for item in script_resources.get("requests", []))
            or not isinstance(pre_create_long_tasks, list)
            or any(not isinstance(item, dict) or not valid_nonnegative_number(item.get("startTime"))
                   or not valid_nonnegative_number(item.get("duration")) for item in pre_create_long_tasks)
            or not isinstance(long_tasks, list)
            or any(not isinstance(item, dict) or not valid_nonnegative_number(item.get("startTime"))
                   or not valid_nonnegative_number(item.get("duration")) for item in long_tasks)):
        raise RuntimeError("browser evidence Notes creation stage diagnostics missing or invalid")
    target_values = {
        "clickToVisibleFeedbackMs": first_create["clickToVisibleFeedbackMs"],
        "coldClickToInputReadyMs": first_create["clickToInputReadyMs"],
        "warmInputReadyP95Ms": repeated["clickToInputReadyP95Ms"],
        "warmVisibleFeedbackP95Ms": repeated["clickToVisibleFeedbackP95Ms"],
    }
    if any(not valid_nonnegative_number(value) for value in target_values.values()):
        raise RuntimeError("browser evidence performance target timing is invalid")
    performance_targets = {key: round(value, 1) for key, value in target_values.items()}
    performance_targets["status"] = "PASS" if (
        target_values["clickToVisibleFeedbackMs"] <= 100
        and target_values["coldClickToInputReadyMs"] <= 1000
        and target_values["warmInputReadyP95Ms"] <= 500
        and target_values["warmVisibleFeedbackP95Ms"] <= 100
    ) else "PARTIAL"
    boundary = evidence.get("titleBoundary", {})
    if boundary.get("title") != "WP5 Native Probe" or boundary.get("firstBody", {}).get("text") != "First line after title":
        raise RuntimeError("browser evidence title/backspace boundary check failed")
    if boundary.get("firstBody", {}).get("id") == boundary.get("titleBlockId"):
        raise RuntimeError("browser evidence paragraph merged into the title block")
    title_state = evidence.get("titleAndBody", {})
    if len(title_state.get("visibleTitleHeadings", [])) != 1 or title_state.get("hiddenTitleDisplay") != "none":
        raise RuntimeError("browser evidence title de-duplication check failed")
    if title_state.get("modalEditorCount") != 0 or not title_state.get("inlineEditor"):
        raise RuntimeError("browser evidence editor placement check failed")
    controls = evidence.get("blockControls", [])
    if {item.get("kind") for item in controls} != {"grip", "plus"} or not all(item.get("visible") for item in controls):
        raise RuntimeError("browser evidence block control visibility check failed")
    mobile = evidence.get("mobileLayout", {})
    if mobile.get("viewportWidth") != 390 or mobile.get("documentWidth", 0) > 390 or mobile.get("notesWidth", 0) > 390:
        raise RuntimeError("browser evidence mobile layout overflow check failed")
    if not mobile.get("controlsVisible") or not all(item.get("visibleAndWithinViewport") for item in mobile["controlsVisible"]):
        raise RuntimeError("browser evidence mobile control visibility check failed")
    if not mobile.get("plusVisible") or not mobile.get("gripVisible"):
        raise RuntimeError("browser evidence mobile block control visibility check failed")
    formatted_drag = evidence.get("formattedHeadingDrag", {})
    formatted_state = formatted_drag.get("formattedState", {})
    routing = formatted_drag.get("routing", {})
    if formatted_state != {"type": "h1", "textAlign": "center", "bold": True}:
        raise RuntimeError("browser evidence formatted heading state check failed")
    if routing != {"anchorIsSource": True, "dragSourceIsSource": True, "hitIsDropTarget": True,
                   "dropTargetIsDropTarget": True, "dropBefore": False, "pointerCaptured": True}:
        raise RuntimeError("browser evidence formatted heading pointer routing check failed")
    handle_gap = formatted_drag.get("handleGapPx")
    if not isinstance(handle_gap, (int, float)) or abs(handle_gap - 64) >= 2:
        raise RuntimeError("browser evidence centered heading handle alignment check failed")
    if not (formatted_drag.get("sourceBefore", -1) < formatted_drag.get("targetBefore", -1)
            and formatted_drag.get("sourceAfterDrop", -1) > formatted_drag.get("targetAfterDrop", -1)
            and formatted_drag.get("sourceAfterReturn", -1) < formatted_drag.get("targetAfterReturn", -1)):
        raise RuntimeError("browser evidence formatted heading Yjs order check failed")
    safe_text = lambda value: value if value in {"WP5 Native Probe", "新建笔记", "First line after title",
        "Second paragraph after Enter", "中文输入法内容"} else "backspace probe" if value.startswith(" backspace-") \
        else "undo probe" if value.startswith(" undo-") else "[redacted]"
    safe = {
        "scope": "synthetic Notes UI only",
        "viewport": evidence["viewport"],
        "clickToEditableMs": {"firstCreate": round(first["durationMs"], 1),
                               "samePageReopen": round(warm["durationMs"], 1),
                               "refreshRestore": round(refresh["durationMs"], 1)},
        "creationTimings": {
            "coldNotesNavigationMs": round(creation["coldNotesNavigationMs"], 1),
            "firstCreate": {"clickToVisibleFeedbackMs": round(first_create["clickToVisibleFeedbackMs"], 1),
                            "apiResponseElapsedMs": {stage: round(stages[stage], 1) for stage in sorted(required_stages)},
                            "apiStatuses": first_create["apiStatuses"],
                            "apiWaterfall": [{"stage": item["stage"], "requestElapsedMs": round(item["requestElapsedMs"], 1),
                                              "durationMs": round(item["durationMs"], 1), "status": item["status"]}
                                             for item in api_waterfall],
                            "internalStages": [{"stage": item["stage"],
                                                **({"elapsedMs": round(item["elapsedMs"], 1)} if isinstance(item.get("elapsedMs"), (int, float)) else {}),
                                                "durationMs": round(item["durationMs"], 1)} for item in internal_stages],
                            "scriptResources": {"initiatedBeforeCreateCount": script_resources["initiatedBeforeCreateCount"],
                                                "completedBeforeCreateCount": script_resources["completedBeforeCreateCount"],
                                                "inFlightAtCreateStartCount": script_resources["inFlightAtCreateStartCount"],
                                                "initiatedBeforeCreate": [{"name": Path(item["name"]).name,
                                                                           "startTimeMs": item["startTimeMs"],
                                                                           "responseEndMs": item["responseEndMs"],
                                                                           "durationMs": item["durationMs"],
                                                                  "transferSize": item["transferSize"],
                                                                  "decodedBodySize": item["decodedBodySize"]}
                                                                 for item in script_resources["initiatedBeforeCreate"]],
                                                "requestCount": script_resources["requestCount"],
                                                "duplicateUrlCount": script_resources["duplicateUrlCount"],
                                                "requests": [{"name": Path(item["name"]).name, "durationMs": item["durationMs"],
                                                              "transferSize": item["transferSize"],
                                                              "decodedBodySize": item["decodedBodySize"]}
                                                             for item in script_resources["requests"]]},
                            "longTasksStartedBeforeCreate": [{"startTime": round(item["startTime"], 1), "duration": round(item["duration"], 1)}
                                                    for item in pre_create_long_tasks],
                            "longTasksStartedDuringCreate": [{"startTime": round(item["startTime"], 1), "duration": round(item["duration"], 1)}
                                          for item in long_tasks],
                            "clickToInputReadyMs": round(first_create["clickToInputReadyMs"], 1),
                            "realCaretInputVerified": first_create["realCaretInputVerified"],
                            "temporaryMarkdownEditorMounts": first_create["temporaryMarkdownEditorMounts"]},
            "refresh": {"openMs": round(refresh_state["openMs"], 1),
                        "status": refresh_state.get("status") if refresh_state.get("status") in {
                            "笔记已就绪", "BlockSuite 资源已保存", "有未保存的资源修改"} else "other",
                        "cleanExitPrompt": refresh_state["cleanExitPrompt"]},
            "edgelessRefresh": {"status": edgeless_state["status"] if edgeless_state["status"] in {
                "笔记已就绪", "BlockSuite 资源已保存", "有未保存的资源修改"} else "other",
                "cleanExitPrompt": edgeless_state["cleanExitPrompt"]},
        },
        "repeatedCreation": {"warmSampleCount": repeated["warmSampleCount"],
                             "clickToVisibleFeedbackP95Ms": round(repeated["clickToVisibleFeedbackP95Ms"], 1),
                             "clickToInputReadyP95Ms": round(repeated["clickToInputReadyP95Ms"], 1),
                             "cleanExitPromptCount": repeated["cleanExitPromptCount"]},
        "performanceTargets": performance_targets,
        "focus": {"contenteditable": enter["contenteditable"], "selectionInsideEditor": enter["selectionInsideEditor"],
                  "selectionOffset": enter.get("anchorOffset")},
        "yjsParagraphTexts": [safe_text(value) for value in texts if value.strip()],
        "visibleTitleCount": len(title_state["visibleTitleHeadings"]),
        "editorPlacement": "inline, no modal",
        "blockControls": controls,
        "titleBackspaceBoundary": {"titleRetained": boundary.get("title") == "WP5 Native Probe",
                                   "firstParagraphRetained": boundary.get("firstBody", {}).get("text") == "First line after title",
                                   "distinctBlock": boundary.get("firstBody", {}).get("id") != boundary.get("titleBlockId")},
        "formattedHeadingDrag": {"type": formatted_state["type"], "textAlign": formatted_state["textAlign"],
                                 "bold": formatted_state["bold"], "anchorMatchesSource": routing["anchorIsSource"],
                                 "gripToTextGapPx": round(handle_gap, 1),
                                 "pointerCapture": routing["pointerCaptured"], "hitMatchesTarget": routing["hitIsDropTarget"],
                                 "dropTargetMatches": routing["dropTargetIsDropTarget"],
                                 "dropBefore": routing["dropBefore"],
                                 "sourceOrderBefore": formatted_drag["sourceBefore"],
                                 "targetOrderBefore": formatted_drag["targetBefore"],
                                 "sourceOrderAfterDrop": formatted_drag["sourceAfterDrop"],
                                 "targetOrderAfterDrop": formatted_drag["targetAfterDrop"],
                                 "sourceOrderAfterReturn": formatted_drag["sourceAfterReturn"],
                                 "targetOrderAfterReturn": formatted_drag["targetAfterReturn"]},
        "journey": evidence.get("journey", []),
        "mobileLayout": mobile,
        "result": "PASS",
    }
    target.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return safe


def verify_failure_evidence(source: Path, target: Path) -> dict:
    evidence = json.loads(source.read_text(encoding="utf-8"))
    if evidence.get("result") != "FAIL":
        raise RuntimeError("failure evidence must remain explicitly FAIL")
    viewport = evidence.get("viewport", "unknown")
    if viewport != "unknown" and viewport not in {"1440x1000", "390x844"}:
        viewport = "unknown"
    safe_text_values = {"WP5 Native Probe", "新建笔记", "First line after title",
                        "Second paragraph after Enter", "中文输入法内容",
                        "WP5 Native ProbeFirst line after title"}
    paragraphs = []
    for index, block in enumerate(evidence.get("blocks", [])[:80]):
        value = block.get("text", "")
        text = value if value in safe_text_values else "[redacted]"
        paragraphs.append({"index": index, "idLength": block.get("idLength"),
                           "type": block.get("type") if block.get("type") in {"text", "h1", "h2", "h3", "bulleted", "numbered"} else "other",
                           "text": text})
    safe = {"result": "FAIL", "evidenceType": "independent synthetic DOM afterEach",
            "viewport": viewport, "activeTag": evidence.get("activeTag"),
            "activeRole": evidence.get("activeRole"), "contenteditable": evidence.get("contenteditable"),
            "selectionInsideEditor": bool(evidence.get("selectionInsideEditor")),
            "selectionCollapsed": evidence.get("selectionCollapsed"),
            "selectionOffset": evidence.get("selectionOffset"),
            "titleBlockDisplay": evidence.get("titleBlockDisplay"),
            "editorVisible": bool(evidence.get("editorVisible")),
            "modalCount": evidence.get("modalCount"), "yjsParagraphs": paragraphs}
    target.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return safe


def verify_canvas_open_failure_evidence(source: Path, target: Path) -> dict:
    evidence = json.loads(source.read_text(encoding="utf-8"))
    state = evidence.get("canvasOpenState")
    expected_keys = {"galleryExpanded", "canvasCardCount", "openButtonCount", "openButtonsEnabled",
                     "resourceDialogVisible", "nestedEditorVisible"}
    if (evidence.get("result") != "FAIL" or evidence.get("scope") != "independent synthetic canvas-open repro"
            or evidence.get("viewport") != "1440x1000" or not isinstance(state, dict)
            or set(state) != expected_keys
            or any(type(state.get(key)) is not bool for key in
                   ("galleryExpanded", "resourceDialogVisible", "nestedEditorVisible"))
            or any(type(state.get(key)) is not int or not 0 <= state[key] <= 12
                   for key in ("canvasCardCount", "openButtonCount", "openButtonsEnabled"))
            or state["openButtonsEnabled"] > state["openButtonCount"]):
        raise RuntimeError("canvas open failure evidence rejected")
    safe = {"result": "FAIL", "scope": "independent synthetic canvas-open repro",
            "viewport": "1440x1000", "canvasOpenState": state}
    target.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return safe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--undo-minimal-repro", action="store_true",
                        help="run an independent fresh-page undo/redo observation, without pass/fail assertions")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.is_symlink():
        raise RuntimeError("evidence output directory cannot be a symlink")
    with tempfile.TemporaryDirectory(prefix="wp5-notes-native-ux-") as temporary:
        temp = Path(temporary)
        os.chmod(temp, 0o700)
        roots = {name: temp / name for name in ("review", "state", "knowledge", "raw", "journal", "task", "projects", "briefs", "notes")}
        for directory in roots.values():
            directory.mkdir(mode=0o700)
        password_file = temp / "app-password"
        password_file.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        os.chmod(password_file, 0o600)
        core_port, web_port = free_port(), free_port()
        core_url, web_url = f"http://127.0.0.1:{core_port}", f"http://127.0.0.1:{web_port}"
        raw_artifacts = temp / "playwright-raw"
        raw_artifacts.mkdir(mode=0o700)
        source_screenshot = temp / "wp5-notes-native.png"
        source_mobile_screenshot = temp / "wp5-notes-native-mobile.png"
        source_evidence = temp / "wp5-notes-native-dom.json"
        source_failure_evidence = temp / "wp5-notes-native-failure.json"
        source_mobile_diagnostic = temp / "wp5-notes-native-mobile-diagnostic.json"
        source_canvas_open_screenshot = temp / "wp5-notes-native-canvas-open.png"
        source_canvas_open_evidence = temp / "wp5-notes-native-canvas-open.json"
        source_canvas_open_failure_screenshot = temp / "wp5-notes-native-canvas-open-failure.png"
        source_canvas_open_failure_evidence = temp / "wp5-notes-native-canvas-open-failure.json"
        source_undo_screenshot = temp / "wp5-undo-minimal.png"
        source_undo_evidence = temp / "wp5-undo-minimal.json"
        env = os.environ.copy()
        env.update({
            "SB_REVIEW_ROOT": str(roots["review"]), "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
            "SB_PROMOTE_STATE_ROOT": str(roots["state"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
            "SB_JOURNAL_ROOT": str(roots["journal"]), "SB_TASK_ROOT": str(roots["task"]),
            "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]), "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
            "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]), "SB_APP_PASSWORD_FILE": str(password_file),
            "SB_DASHBOARD_ORIGINS": web_url, "SB_CORE_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "SB_PROMOTE_ENABLED": "false", "SB_HERMES_API_URL": "", "SB_PERSONAL_MEMORY_ENABLED": "false",
            "SB_PERSONAL_LEARNING_ENABLED": "false", "SB_WEIXIN_INBOX_ENABLED": "false",
            "SB_CORE_PROXY_TARGET": core_url, "SB_E2E_BASE_URL": web_url,
            "SB_E2E_PASSWORD_FILE": str(password_file), "SB_E2E_RAW_ARTIFACTS": str(raw_artifacts),
            "PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(raw_artifacts / "junit.xml"),
            "PLAYWRIGHT_HTML_OUTPUT_DIR": str(raw_artifacts / "html"),
            "SB_E2E_WP5_ARCHIVE_UX_ONLY": "true", "SB_E2E_DESKTOP_ONLY": "true",
            "SB_E2E_PRODUCTION_BUILD": "true", "SB_WP5_NATIVE_SCREENSHOT_PATH": str(source_screenshot),
            "SB_WP5_NATIVE_DOM_EVIDENCE_PATH": str(source_evidence),
            "SB_WP5_NATIVE_FAILURE_EVIDENCE_PATH": str(source_failure_evidence),
            "SB_WP5_NATIVE_MOBILE_DIAGNOSTIC_PATH": str(source_mobile_diagnostic),
            "SB_WP5_NATIVE_MOBILE_SCREENSHOT_PATH": str(source_mobile_screenshot),
            "SB_WP5_NATIVE_CANVAS_OPEN_SCREENSHOT_PATH": str(source_canvas_open_screenshot),
            "SB_WP5_NATIVE_CANVAS_OPEN_EVIDENCE_PATH": str(source_canvas_open_evidence),
            "SB_WP5_NATIVE_CANVAS_OPEN_FAILURE_SCREENSHOT_PATH": str(source_canvas_open_failure_screenshot),
            "SB_WP5_NATIVE_CANVAS_OPEN_FAILURE_EVIDENCE_PATH": str(source_canvas_open_failure_evidence),
            "SB_WP5_NATIVE_UX_PROBE_ONLY": "true", "VITE_ENABLE_NOTES": "true",
            "SB_WP5_UNDO_REPRO_SCREENSHOT_PATH": str(source_undo_screenshot),
            "SB_WP5_UNDO_REPRO_JSON_PATH": str(source_undo_evidence),
            "CI": "true",
        })
        processes: list[subprocess.Popen[bytes]] = []
        logs = []
        try:
            core_log = (temp / "core.log").open("wb")
            logs.append(core_log)
            core = subprocess.Popen([sys.executable, "-m", "uvicorn", "secondbrain_core.app:create_app", "--factory",
                                     "--host", "127.0.0.1", "--port", str(core_port)], cwd=CORE, env=env,
                                    stdout=core_log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(core)
            wait_http(core_url + "/health", core, "Core")
            with urlopen(core_url + "/health", timeout=5) as response:
                health = json.loads(response.read())
            if health.get("promote_enabled") is not False or health.get("hermes_configured") is not False:
                raise RuntimeError("isolated Core security settings rejected")
            web_log = (temp / "vite.log").open("wb")
            logs.append(web_log)
            web = subprocess.Popen(["npx", "--no-install", "vite", "preview", "--host", "127.0.0.1",
                                    "--port", str(web_port), "--strictPort"], cwd=FRONTEND, env=env,
                                   stdout=web_log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(web)
            wait_http(web_url + "/chat/blank", web, "Web preview")
            command = (["node", "scripts/wp5-undo-minimal-repro.mjs"] if args.undo_minimal_repro else
                       ["npx", "--no-install", "playwright", "test", "--config=playwright.wp5-notes-native-ux.config.ts"])
            result = subprocess.run(command, cwd=E2E, env=env, check=False)
            if result.returncode:
                if source_mobile_diagnostic.is_file():
                    mobile_diagnostic = json.loads(source_mobile_diagnostic.read_text(encoding="utf-8"))
                    print(f"WP5_NATIVE_MOBILE_DIAGNOSTIC {json.dumps(mobile_diagnostic, ensure_ascii=False)}")
                failure_target = output / "wp5-notes-native-failure-evidence.json"
                if source_failure_evidence.is_file():
                    failure = verify_failure_evidence(source_failure_evidence, failure_target)
                    if source_screenshot.is_file():
                        from PIL import Image
                        with Image.open(source_screenshot) as failed_image:
                            image_width = 390 <= failed_image.width <= 700
                        sanitize_png(source_screenshot, output / ("wp5-notes-native-failure-mobile.png" if image_width
                                                                        else "wp5-notes-native-failure-desktop.png"),
                                     mobile=image_width)
                    print(json.dumps(failure, ensure_ascii=False))
                if source_canvas_open_failure_evidence.is_file():
                    canvas_failure_target = output / "wp5-notes-native-canvas-open-failure-evidence.json"
                    canvas_failure = verify_canvas_open_failure_evidence(source_canvas_open_failure_evidence,
                                                                          canvas_failure_target)
                    if source_canvas_open_failure_screenshot.is_file():
                        sanitize_png(source_canvas_open_failure_screenshot,
                                     output / "wp5-notes-native-canvas-open-failure-1440x1000.png")
                    print(json.dumps(canvas_failure, ensure_ascii=False))
                return result.returncode
            if args.undo_minimal_repro:
                if not source_undo_screenshot.is_file() or not source_undo_evidence.is_file():
                    raise RuntimeError("independent undo reproduction did not produce evidence")
                screenshot_target = output / "wp5-undo-minimal-1440x1000.png"
                evidence_target = output / "wp5-undo-minimal-evidence.json"
                dimensions = sanitize_png(source_undo_screenshot, screenshot_target)
                evidence = json.loads(source_undo_evidence.read_text(encoding="utf-8"))
                if evidence.get("scope") != "synthetic isolated Notes page":
                    raise RuntimeError("undo reproduction scope rejected")
                evidence_target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                os.chmod(evidence_target, 0o600)
                print(json.dumps({"result": "OBSERVED", "screenshot": screenshot_target.name,
                                  "screenshot_dimensions": dimensions, "sequence": evidence["sequence"],
                                  "undoRemovedTypedText": evidence["undoRemovedTypedText"],
                                  "redoRestoredTypedText": evidence["redoRestoredTypedText"]}, ensure_ascii=False))
                return 0
            if not source_screenshot.is_file() or not source_mobile_screenshot.is_file() or not source_evidence.is_file():
                raise RuntimeError("focused Chromium journey did not produce its evidence files")
            if not source_canvas_open_screenshot.is_file() or not source_canvas_open_evidence.is_file():
                raise RuntimeError("independent nested canvas open repro did not produce its evidence files")
            canvas_open = json.loads(source_canvas_open_evidence.read_text(encoding="utf-8"))
            canvas_layout = canvas_open.get("canvasLayout") if isinstance(canvas_open, dict) else None
            if (not isinstance(canvas_open, dict)
                    or set(canvas_open) != {"result", "scope", "resourceReadStatus", "dialogVisible",
                                            "nestedEditorVisible", "canvasLayout"}
                    or canvas_open.get("result") != "PASS"
                    or canvas_open.get("scope") != "independent synthetic canvas-open repro"
                    or type(canvas_open.get("resourceReadStatus")) is not int or canvas_open["resourceReadStatus"] != 200
                    or canvas_open.get("dialogVisible") is not True
                    or canvas_open.get("nestedEditorVisible") is not True
                    or not isinstance(canvas_layout, dict)
                    or set(canvas_layout) != {"paragraphCount", "hostBottom", "galleryTop", "lastParagraphBottom", "noOverlap"}
                    or type(canvas_layout.get("paragraphCount")) is not int or canvas_layout["paragraphCount"] != 13
                    or any(type(canvas_layout.get(key)) not in (int, float) or not math.isfinite(canvas_layout[key])
                           or abs(canvas_layout[key]) > 100000
                           for key in ("hostBottom", "galleryTop", "lastParagraphBottom"))
                    or canvas_layout.get("noOverlap") is not True
                    or canvas_layout["galleryTop"] < canvas_layout["hostBottom"] - 1
                    or canvas_layout["galleryTop"] < canvas_layout["lastParagraphBottom"] - 1):
                raise RuntimeError("independent nested canvas open evidence rejected")
            screenshot_target = output / "wp5-notes-native-1440x1000.png"
            mobile_screenshot_target = output / "wp5-notes-native-390x844.png"
            canvas_open_screenshot_target = output / "wp5-notes-native-canvas-open-1440x1000.png"
            evidence_target = output / "wp5-notes-native-evidence.json"
            dimensions = sanitize_png(source_screenshot, screenshot_target)
            mobile_dimensions = sanitize_png(source_mobile_screenshot, mobile_screenshot_target, mobile=True)
            canvas_open_dimensions = sanitize_png(source_canvas_open_screenshot, canvas_open_screenshot_target)
            evidence = verify_evidence(source_evidence, evidence_target)
            canvas_open_target = output / "wp5-notes-native-canvas-open-evidence.json"
            canvas_open_target.write_text(json.dumps(canvas_open, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.chmod(canvas_open_target, 0o600)
            print(json.dumps({"result": "PASS", "screenshot": screenshot_target.name,
                              "screenshot_dimensions": dimensions, "click_to_editable_ms": evidence["clickToEditableMs"],
                              "mobile_screenshot": mobile_screenshot_target.name, "mobile_dimensions": mobile_dimensions,
                              "canvas_open_screenshot": canvas_open_screenshot_target.name,
                              "canvas_open_dimensions": canvas_open_dimensions,
                              "viewport": evidence["viewport"]}, ensure_ascii=False))
            return 0
        finally:
            for process in reversed(processes):
                stop_process(process)
            for stream in logs:
                stream.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"WP5 native Notes probe failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
