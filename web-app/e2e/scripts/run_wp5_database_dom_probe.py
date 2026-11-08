#!/usr/bin/env python3
"""Start isolated synthetic Core/Vite and run the standalone WP5 DOM probe."""
from __future__ import annotations

import importlib.util
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[3]
CORE = ROOT / "web-app" / "secondbrain-core"
FRONTEND = ROOT / "web-app" / "secondbrain-frontend"
E2E = ROOT / "web-app" / "e2e"
RUNNER = E2E / "scripts" / "run_synthetic_ci.py"
spec = importlib.util.spec_from_file_location("wp5_harness", RUNNER)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load isolated Core/Vite harness helpers")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="wp5-database-dom-probe-")).resolve()
    os.chmod(root, 0o700)
    names = ("raw", "review", "state", "knowledge", "journal", "task", "projects", "briefs", "notes")
    dirs = {name: root / name for name in names}
    processes: list[subprocess.Popen] = []
    try:
        for path in dirs.values():
            path.mkdir(mode=0o700)
        harness.seed_notes_safety_fixtures(dirs["notes"])
        harness.seed_daily_brief_sources(dirs)

        core_port = port()
        web_port = port()
        while web_port == core_port:
            web_port = port()
        core_url = f"http://127.0.0.1:{core_port}"
        web_url = f"http://127.0.0.1:{web_port}"
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
            "SB_DASHBOARD_ORIGINS": web_url,
            "SB_CORE_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "SB_PROMOTE_ENABLED": "false",
            "SB_HERMES_API_URL": "",
            "SB_PERSONAL_MEMORY_ENABLED": "false",
            "SB_PERSONAL_LEARNING_ENABLED": "false",
            "VITE_ENABLE_NOTES": "true",
            "SB_E2E_BASE_URL": web_url,
            "SB_CORE_PROXY_TARGET": core_url,
            "SB_E2E_PASSWORD_FILE": str(password_path),
            "CI": "true",
        })
        core = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "secondbrain_core.app:create_app", "--factory",
            "--host", "127.0.0.1", "--port", str(core_port),
        ], cwd=CORE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        processes.append(core)
        harness.wait_http(core_url + "/health", core, "Core")
        web = subprocess.Popen([
            "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort",
        ], cwd=FRONTEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        processes.append(web)
        harness.wait_http(web_url + "/chat/blank", web, "Vite")
        probe_env = env | {"SB_WP5_DOM_PROBE_URL": web_url}
        probe = subprocess.run(["node", str(E2E / "scripts" / "wp5_database_dom_probe.mjs")],
                               cwd=E2E, env=probe_env, check=False)
        return probe.returncode
    finally:
        for process in reversed(processes):
            harness.stop(process)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
