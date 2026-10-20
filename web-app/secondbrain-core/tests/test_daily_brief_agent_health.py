import hashlib
import os
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.daily_brief_agent_health import create_daily_brief_agent_health_router
from secondbrain_core.modules.hermes_api import HermesAPI


class FakeHermes:
    def __init__(self, configured=True, payload=None, error=None):
        self.configured = configured
        self.payload = payload or {"features": {"session_api": True}}
        self.error = error
        self.calls = 0

    async def capabilities(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.payload


def make_client(tmp_path, hermes):
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-password-value\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    token = "synthetic-app-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 600
    app = FastAPI()
    app.include_router(create_daily_brief_agent_health_router(auth, hermes))
    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    return client


def test_daily_brief_is_authenticated_and_explicitly_not_configured(tmp_path):
    hermes = FakeHermes()
    client = make_client(tmp_path, hermes)
    response = client.get("/api/daily-brief?date=2026-10-20&timezone=Asia%2FShanghai")
    assert response.status_code == 200
    assert response.json() == {"status": "not_configured", "items": [], "source": None}
    assert hermes.calls == 0

    client.cookies.clear()
    assert client.get("/api/daily-brief?date=2026-10-20").status_code == 401


def test_daily_brief_rejects_invalid_date_and_timezone(tmp_path):
    client = make_client(tmp_path, FakeHermes())
    assert client.get("/api/daily-brief?date=2026-02-30").status_code == 400
    assert client.get("/api/daily-brief?date=2026-10-20&timezone=NoSuch/Zone").status_code == 400


def test_agent_health_filters_hermes_payload_to_allowlisted_capability(tmp_path):
    hermes = FakeHermes(payload={
        "features": {"session_api": True, "message_api": True, "private_mode": False},
        "session_count": 999, "provider": "synthetic-provider", "api_key": "must-not-escape",
    })
    response = make_client(tmp_path, hermes).get("/api/agent/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "source", "checked_at"}
    assert body["status"] == "online"
    assert body["source"] == "hermes-runtime"
    assert body["checked_at"].endswith("Z")
    assert "session_count" not in response.text
    assert "provider" not in response.text
    assert "api_key" not in response.text
    assert "message_api" not in response.text


def test_agent_health_reports_not_configured_and_unavailable(tmp_path):
    unconfigured = FakeHermes(configured=False)
    response = make_client(tmp_path, unconfigured).get("/api/agent/health")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"
    assert response.json()["source"] is None
    assert unconfigured.calls == 0

    unavailable = FakeHermes(error=HTTPException(status_code=502, detail="synthetic unavailable"))
    failed = make_client(tmp_path, unavailable).get("/api/agent/health")
    assert failed.status_code == 200
    assert failed.json()["status"] == "unavailable"


def test_agent_health_requires_app_session(tmp_path):
    client = make_client(tmp_path, FakeHermes())
    client.cookies.clear()
    assert client.get("/api/agent/health").status_code == 401


def test_agent_health_maps_real_hermes_transport_timeout_to_unavailable(tmp_path):
    def timeout(_request):
        raise httpx.ReadTimeout("synthetic Hermes timeout")

    hermes = HermesAPI(base_url="https://hermes.test", api_key="synthetic-key",
                       transport=httpx.MockTransport(timeout))
    response = make_client(tmp_path, hermes).get("/api/agent/health")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["source"] == "hermes-runtime"
    assert set(response.json()) == {"status", "source", "checked_at"}
    assert "synthetic Hermes timeout" not in response.text
