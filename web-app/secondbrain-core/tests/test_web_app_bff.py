import hashlib
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from secondbrain_core.app import create_app
from secondbrain_core.modules.hermes_api import HermesAPI
from secondbrain_core.modules.auto_organize import OrganizeSettingsStore, next_scheduled_at
from datetime import datetime, timezone


class WebAppBffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.review = self.root / "review"
        self.knowledge = self.root / "knowledge"
        self.raw = self.root / "raw"
        self.state = self.root / "state"
        for path in (self.review, self.knowledge, self.raw, self.state):
            path.mkdir(mode=0o700)
        self.review_content = b"---\ntype: review\nstatus: pending\n---\n# Review title\nReal Review content.\n"
        (self.review / "candidate.md").write_bytes(self.review_content)
        (self.knowledge / "known.md").write_text("# Existing knowledge\nReal file.\n", encoding="utf-8")
        self.password_file = self.root / "app.password"
        self.password_file.write_text("one-owner-test-password", encoding="utf-8")
        self.password_file.chmod(0o600)
        self.static = self.root / "static"
        (self.static / "assets").mkdir(parents=True)
        (self.static / "index.html").write_text('<div id="root">App shell</div>', encoding="utf-8")
        (self.static / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
        self.approvals = self.state / "approvals"
        self.approvals.mkdir(mode=0o700)
        self.calls = []

        def handler(request):
            self.calls.append(request)
            if request.url.path == "/v1/capabilities":
                return httpx.Response(200, json={"features": {"session_api": True}})
            if request.url.path == "/api/sessions":
                if request.method == "POST":
                    return httpx.Response(201, json={"object": "hermes.session", "session": {"id": "session-2", "title": "New session"}})
                return httpx.Response(200, json={"object": "list", "data": [{"id": "session-1", "title": "Existing"}], "limit": 50, "offset": 0})
            if request.url.path == "/api/sessions/session-1/fork":
                return httpx.Response(201, json={"object": "hermes.session", "session": {"id": "session-3", "title": "Forked"}})
            if request.url.path.endswith("/messages"):
                return httpx.Response(200, json={"object": "list", "session_id": "session-1", "data": [{"id": "message-1", "session_id": "session-1", "role": "user", "timestamp": "2026-10-15T01:02:03Z", "content": [{"type": "text", "text": "hello"}]}], "pagination": {"limit": 100, "offset": 50, "order": "oldest", "returned": 1}})
            if request.url.path == "/v1/runs":
                return httpx.Response(202, json={"run_id": "run-1", "status": "started"})
            if request.url.path == "/v1/runs/run-1":
                return httpx.Response(200, json={"run_id": "run-1", "status": "completed", "output": "done"})
            if request.url.path == "/v1/runs/run-1/events":
                return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                      content=b"data: {\"event\":\"tool.started\",\"tool\":\"search_files\",\"preview\":\"query\"}\n\ndata: {\"event\":\"message.delta\",\"delta\":\"done\"}\n\ndata: {\"event\":\"run.completed\",\"output\":\"done\"}\n\n")
            if request.url.path == "/v1/runs/run-1/stop":
                return httpx.Response(200, json={"status": "stopping"})
            return httpx.Response(404, json={"detail": "not found"})

        self.transport = httpx.MockTransport(handler)
        self.hermes = HermesAPI("http://hermes.internal", "server-only-test-key", self.transport)
        self.env = {
            "SB_REVIEW_ROOT": str(self.review),
            "SB_CAPTURE_RAW_ROOT": str(self.raw),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge),
            "SB_PROMOTE_STATE_ROOT": str(self.state),
            "SB_DASHBOARD_ORIGINS": "http://testserver,https://testserver",
            "SB_CORE_ALLOWED_HOSTS": "testserver",
            "SB_APP_PASSWORD_FILE": str(self.password_file),
            "SB_HERMES_API_URL": "http://hermes.internal",
            "SB_HERMES_API_KEY": "unused-placeholder",
            "SB_PROMOTE_ENABLED": "false",
            "SB_STATIC_ROOT": str(self.static),
        }
        with patch.dict(os.environ, self.env), patch("secondbrain_core.app.HermesAPI", return_value=self.hermes):
            self.app = create_app()
        self.client = TestClient(self.app, base_url="https://testserver")

    def tearDown(self):
        self.client.close()
        self.transport.close()
        self.temp.cleanup()

    def login(self):
        return self.client.post("/api/auth/login", json={"password": "one-owner-test-password"},
                                headers={"Origin": "https://testserver"})

    def test_login_origin_session_and_promote_fail_closed(self):
        self.assertEqual(self.client.get("/api/home").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"password": "one-owner-test-password"},
                                          headers={"Origin": "https://evil.invalid"}).status_code, 403)
        login = self.login()
        self.assertEqual(login.status_code, 200)
        self.assertIn("httponly", login.headers["set-cookie"].lower())
        self.assertIn("samesite=strict", login.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/auth/session").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/session").status_code, 200)  # same cookie survives page refresh
        logout = self.client.post("/api/auth/logout", json={}, headers={"Origin": "https://testserver"})
        self.assertIn("; secure", logout.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/auth/session").status_code, 401)
        self.login()
        forged = TestClient(self.app, base_url="https://testserver")
        self.assertEqual(forged.post("/api/promote/review/approve", json={"approved": True},
                                     headers={"Origin": "https://testserver"}).status_code, 401)
        forged.close()
        self.assertEqual(self.client.post("/api/promote/review/approve", json={"approved": True},
                                          headers={"Origin": "https://evil.invalid"}).status_code, 403)
        item = self.client.get("/api/promote/review/items").json()["items"][0]
        response = self.client.post("/api/promote/review/approve", json={
            "request_id": "blocked-approve", "review_path": item["review_path"],
            "review_sha256": item["review_sha256"], "target_filename": "approved.md",
        }, headers={"Origin": "https://testserver"})
        self.assertEqual(response.status_code, 423)
        self.assertEqual(list(self.approvals.iterdir()), [])

    def test_home_and_review_are_real_file_backed_data_and_defer_is_persisted(self):
        self.login()
        home = self.client.get("/api/home").json()
        self.assertEqual(home["status"], "ok")
        self.assertEqual(home["review"]["pending_count"], 1)
        self.assertEqual(home["knowledge"]["items"][0]["title"], "Existing knowledge")
        self.assertEqual(home["agent"]["source"], "hermes-runtime")
        item = self.client.get("/api/promote/review/items").json()["items"][0]
        self.assertEqual(item["review_sha256"], hashlib.sha256(self.review_content).hexdigest())
        deferred = self.client.post("/api/promote/review/defer", json={
            "review_path": item["review_path"], "review_sha256": item["review_sha256"],
        }, headers={"Origin": "https://testserver"})
        self.assertEqual(deferred.status_code, 200, deferred.text)
        self.assertEqual(deferred.json()["status"], "deferred")
        refreshed = self.client.get("/api/promote/review/items").json()["items"][0]
        self.assertEqual(refreshed["decision"]["status"], "deferred")

    def test_sessions_runs_sse_and_stop_are_server_side_authenticated(self):
        self.login()
        sessions = self.client.get("/api/chat/sessions").json()
        self.assertEqual(sessions["sessions"][0], {"session_id": "session-1", "title": "Existing", "updated_at": None})
        created = self.client.post("/api/chat/sessions", json={}, headers={"Origin": "https://testserver"})
        self.assertEqual(created.json()["session_id"], "session-2")
        forked = self.client.post("/api/chat/sessions/session-1/fork", json={}, headers={"Origin": "https://testserver"})
        self.assertEqual(forked.json()["session_id"], "session-3")
        messages = self.client.get("/api/chat/sessions/session-1/messages").json()
        self.assertEqual(messages["messages"][0], {"id": "message-1", "session_id": "session-1", "role": "user",
                                                     "timestamp": "2026-10-15T01:02:03Z", "text": "hello"})
        started = self.client.post("/api/chat/sessions/session-1/runs", json={"input": "hello"},
                                   headers={"Origin": "https://testserver", "Idempotency-Key": "test-run-1"})
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["run_id"], "run-1")
        events = self.client.get("/api/chat/runs/run-1/events")
        self.assertEqual(events.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertIn(b"tool.started", events.content)
        self.assertIn(b"message.delta", events.content)
        self.assertEqual(self.client.get("/api/chat/runs/run-1").json()["status"], "completed")
        stopped = self.client.post("/api/chat/runs/run-1/stop", json={}, headers={"Origin": "https://testserver"})
        self.assertEqual(stopped.json()["status"], "stopping")
        self.assertTrue(self.calls)
        self.assertTrue(all(call.headers.get("authorization") == "Bearer server-only-test-key" for call in self.calls))

    def test_cookie_scheme_and_exact_proxy_trust(self):
        self.assertIn("secure", self.login().headers["set-cookie"].lower())
        http_client = TestClient(self.app, base_url="http://testserver")
        response = http_client.post("/api/auth/login", json={"password": "one-owner-test-password"},
                                    headers={"Origin": "http://testserver"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("; secure", response.headers["set-cookie"].lower())

        async def capture(scope, receive, send):
            seen.append(scope["scheme"])

        proxy = ProxyHeadersMiddleware(capture, trusted_hosts="192.0.2.10")
        seen = []
        async def scheme_for(peer):
            scope = {"type": "http", "scheme": "http", "client": (peer, 1234), "headers": [(b"x-forwarded-proto", b"https")]}
            async def receive(): return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message): pass
            await proxy(scope, receive, send)
        asyncio.run(scheme_for("192.0.2.10"))
        asyncio.run(scheme_for("192.0.2.11"))
        self.assertEqual(seen, ["https", "http"])
        http_client.close()

        trusted_client = TestClient(ProxyHeadersMiddleware(self.app, trusted_hosts="testclient"),
                                    base_url="http://testserver")
        forwarded = trusted_client.post("/api/auth/login", json={"password": "one-owner-test-password"},
                                        headers={"Origin": "https://testserver", "X-Forwarded-Proto": "https"})
        self.assertEqual(forwarded.status_code, 200, forwarded.text)
        self.assertIn("; secure", forwarded.headers["set-cookie"].lower())
        trusted_client.close()

    def test_run_failure_and_interruption_frames_remain_machine_readable(self):
        for source, expected in (
            ('data: {"event":"run.failed","error":"provider unavailable"}', "run.failed"),
            ('data: {"event":"run.interrupted","error":"worker stopped"}', "run.interrupted"),
            ('event: run.cancelled\ndata: {"status":"cancelled"}', "run.cancelled"),
        ):
            normalized = HermesAPI._normalize_event_frame(source)
            payload = json.loads(normalized.removeprefix("data: ").strip())
            self.assertEqual(payload["event"], expected)

    def test_same_origin_spa_fallback_serves_assets_and_keeps_unknown_api_404(self):
        page = self.client.get("/chat")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        self.assertIn("App shell", page.text)
        asset = self.client.get("/assets/app.js")
        self.assertEqual(asset.status_code, 200)
        self.assertIn("javascript", asset.headers["content-type"])

    def test_persistent_message_adapter_preserves_source_ids_timestamps_and_page(self):
        result = asyncio.run(self.hermes.list_messages("session-1", limit=100, offset=50, order="oldest"))
        self.assertEqual(result["messages"][0]["id"], "message-1")
        self.assertEqual(result["messages"][0]["session_id"], "session-1")
        self.assertEqual(result["messages"][0]["timestamp"], "2026-10-15T01:02:03Z")
        self.assertEqual(result["pagination"]["offset"], 50)
        request = self.calls[-1]
        self.assertEqual(request.url.params["limit"], "100")
        self.assertEqual(request.url.params["offset"], "50")

    def test_automation_settings_persist_and_execution_fails_closed(self):
        self.login()
        settings = self.client.get("/api/automation/organize/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json()["mode"], "interval")
        self.assertEqual(settings.json()["interval_hours"], 4)
        changed = {**settings.json(), "mode": "fixed_time", "daily_time": "06:45", "timezone": "Asia/Shanghai"}
        saved = self.client.put("/api/automation/organize/settings", json=changed,
                                headers={"Origin": "https://testserver"})
        self.assertEqual(saved.status_code, 200)
        store = OrganizeSettingsStore(self.state / "ai-organize")
        self.assertEqual(store.read()["daily_time"], "06:45")
        self.assertEqual(self.client.get("/api/automation/organize/status").json()["execution_available"], False)
        run = self.client.post("/api/automation/organize/run", json={}, headers={"Origin": "https://testserver"})
        self.assertEqual(run.status_code, 503)
        self.assertEqual(run.json()["detail"]["code"], "organizer_unavailable")

    def test_automation_settings_validation_and_auth(self):
        self.assertEqual(self.client.get("/api/automation/organize/settings").status_code, 401)
        self.login()
        invalid = self.client.put("/api/automation/organize/settings",
                                  json={"enabled": True, "mode": "interval", "interval_hours": 5},
                                  headers={"Origin": "https://testserver"})
        self.assertEqual(invalid.status_code, 422)
        cross_origin = self.client.put("/api/automation/organize/settings",
                                       json={"enabled": False, "mode": "interval", "interval_hours": 4},
                                       headers={"Origin": "https://evil.invalid"})
        self.assertEqual(cross_origin.status_code, 403)

    def test_scheduler_time_calculation_uses_zone_and_persisted_interval_anchor(self):
        now = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
        interval = {"enabled": True, "mode": "interval", "interval_hours": 4,
                    "daily_time": "00:30", "timezone": "Asia/Shanghai"}
        anchor = datetime(2026, 10, 14, 22, 0, tzinfo=timezone.utc)
        self.assertEqual(next_scheduled_at(interval, now=now, interval_anchor=anchor), datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc))
        fixed = {"enabled": True, "mode": "fixed_time", "interval_hours": 4,
                 "daily_time": "00:30", "timezone": "Asia/Shanghai"}
        self.assertEqual(next_scheduled_at(fixed, now=now), datetime(2026, 10, 15, 16, 30, tzinfo=timezone.utc))
        self.assertEqual(self.client.get("/api/does-not-exist").status_code, 404)


if __name__ == "__main__":
    unittest.main()
