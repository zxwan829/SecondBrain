import hashlib
import os
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth


def test_daily_brief_write_is_explicitly_registered_and_unknown_actions_default_deny(tmp_path):
    password_file = tmp_path / "password"
    password_file.write_bytes(b"synthetic-password\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    token = "synthetic-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 60
    app = FastAPI()

    @app.post("/known")
    def known(request: Request):
        auth.require_action(request, "daily_brief.write")
        return {"ok": True}

    @app.post("/unknown")
    def unknown(request: Request):
        auth.require_action(request, "daily_brief.typo")
        return {"ok": True}

    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    headers = {"Origin": "https://app.test"}
    assert client.post("/known", headers=headers).status_code == 200
    denied = client.post("/unknown", headers=headers)
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Action is not enabled"}


def test_supported_action_registry_covers_existing_literal_and_dynamic_families():
    expected = {
        "activity.read", "agent.health.read", "auth.logout", "auth.session",
        "automation.run", "automation.settings.read", "automation.settings.write",
        "automation.status.read", "calendar.read", "capture.read", "capture.write",
        "chat.approve_tool", "chat.manage", "chat.read", "chat.run", "chat.stop",
        "chat.write", "daily_brief.read", "daily_brief.write", "home.read",
        "inbox.read", "journal.append", "journal.read", "knowledge.read", "notes.read",
        "notes.create", "notes.write", "personal_memory.read", "personal_memory.write",
        "projects.read", "promote.read", "review.defer",
        "review.read", "task.read", "task.write", "vocabulary.read", "vocabulary.write",
        "inbox.proposals.read", "inbox.proposals.write", "planning.read", "planning.write",
    }
    assert AppSessionAuth.SUPPORTED_ACTIONS == expected
