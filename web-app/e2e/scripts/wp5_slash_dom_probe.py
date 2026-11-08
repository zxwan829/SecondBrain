#!/usr/bin/env python3
"""Start isolated synthetic Core + Vite services and run the standalone DOM probe."""
from __future__ import annotations

import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'web-app' / 'secondbrain-core'
FRONTEND = ROOT / 'web-app' / 'secondbrain-frontend'
E2E = ROOT / 'web-app' / 'e2e'
PROBE = E2E / 'scripts' / 'wp5-slash-dom-probe.mjs'


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, process: subprocess.Popen, name: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{name} exited before becoming ready')
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f'{name} did not become ready')


def terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='wp5-slash-dom-probe-') as temporary:
        root = Path(temporary).resolve()
        os.chmod(root, 0o700)
        data = {name: root / name for name in ('raw', 'review', 'state', 'knowledge', 'journal', 'task', 'projects', 'briefs', 'notes')}
        for path in data.values():
            path.mkdir(mode=0o700)
        password_file = root / 'synthetic-password'
        password_file.write_text(secrets.token_urlsafe(32) + '\n', encoding='utf-8')
        os.chmod(password_file, 0o600)
        core_port, web_port = free_port(), free_port()
        while core_port == web_port:
            web_port = free_port()
        core_url, web_url = f'http://127.0.0.1:{core_port}', f'http://127.0.0.1:{web_port}'
        env = os.environ.copy()
        env.update({
            'SB_REVIEW_ROOT': str(data['review']), 'SB_KNOWLEDGE_ROOT': str(data['knowledge']),
            'SB_PROMOTE_STATE_ROOT': str(data['state']), 'SB_CAPTURE_RAW_ROOT': str(data['raw']),
            'SB_JOURNAL_ROOT': str(data['journal']), 'SB_TASK_ROOT': str(data['task']),
            'SB_PROJECTS_INDEX_ROOT': str(data['projects']), 'SB_DAILY_BRIEF_STORE_ROOT': str(data['briefs']),
            'SB_NOTES_DRAFTS_ROOT': str(data['notes']), 'SB_APP_PASSWORD_FILE': str(password_file),
            'SB_DASHBOARD_ORIGINS': web_url, 'SB_CORE_ALLOWED_HOSTS': '127.0.0.1,localhost',
            'SB_PROMOTE_ENABLED': 'false', 'SB_HERMES_API_URL': '', 'SB_PERSONAL_MEMORY_ENABLED': 'false',
            'SB_PERSONAL_LEARNING_ENABLED': 'false', 'SB_CORE_PROXY_TARGET': core_url,
            'VITE_ENABLE_NOTES': 'true', 'WP5_DOM_PROBE_URL': web_url,
            'WP5_DOM_PROBE_PASSWORD_FILE': str(password_file),
        })
        logs = [(root / 'core.log').open('wb'), (root / 'vite.log').open('wb')]
        processes: list[subprocess.Popen] = []
        try:
            core = subprocess.Popen([
                sys.executable, '-m', 'uvicorn', 'secondbrain_core.app:create_app', '--factory',
                '--host', '127.0.0.1', '--port', str(core_port),
            ], cwd=CORE, env=env, stdout=logs[0], stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(core)
            wait_http(core_url + '/health', core, 'synthetic Core')
            web = subprocess.Popen([
                'npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(web_port), '--strictPort',
            ], cwd=FRONTEND, env=env, stdout=logs[1], stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(web)
            wait_http(web_url + '/chat/blank', web, 'synthetic Vite')
            result = subprocess.run(['node', str(PROBE)], cwd=E2E, env=env, check=False)
            return result.returncode
        finally:
            for process in reversed(processes):
                terminate(process)
            for log in logs:
                log.close()


if __name__ == '__main__':
    raise SystemExit(main())
