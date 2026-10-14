import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from secondbrain_core.app import create_app
from secondbrain_core.modules.hermes_api import HermesAPI


class WebAppBffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.review = self.root / "review"
        self.knowledge = self.root / "knowledge"
        self.state = self.root / "state"
        for path in (self.review, self.knowledge, self.state):
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
                    return httpx.Response(201, json={"session_id": "session-2", "title": "New session"})
                return httpx.Response(200, json={"sessions": [{"session_id": "session-1", "title": "Existing"}]})
            if request.url.path.endswith("/messages"):
                return httpx.Response(200, json={"messages": [{"role": "user", "content": "hello"}]})
            if request.url.path == "/v1/runs":
                return httpx.Response(202, json={"run_id": "run-1", "status": "started"})
            if request.url.path == "/v1/runs/run-1/events":
                return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                      content=b"event: tool.started\ndata: {\"tool_name\":\"search_files\"}\n\nevent: run.completed\ndata: {\"output\":\"done\"}\n\n")
            if request.url.path == "/v1/runs/run-1/stop":
                return httpx.Response(200, json={"status": "stopping"})
            return httpx.Response(404, json={"detail": "not found"})

        self.transport = httpx.MockTransport(handler)
        self.hermes = HermesAPI("http://hermes.internal", "server-only-test-key", self.transport)
        self.env = {
            "SB_REVIEW_ROOT": str(self.review),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge),
            "SB_PROMOTE_STATE_ROOT": str(self.state),
            "SB_DASHBOARD_ORIGINS": "https://testserver",
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
        self.assertEqual(self.client.get("/api/chat/sessions").json()["sessions"][0]["session_id"], "session-1")
        messages = self.client.get("/api/chat/sessions/session-1/messages").json()
        self.assertEqual(messages["messages"][0]["content"], "hello")
        started = self.client.post("/api/chat/sessions/session-1/runs", json={"input": "hello"},
                                   headers={"Origin": "https://testserver", "Idempotency-Key": "test-run-1"})
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["run_id"], "run-1")
        events = self.client.get("/api/chat/runs/run-1/events")
        self.assertEqual(events.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertIn(b"tool.started", events.content)
        stopped = self.client.post("/api/chat/runs/run-1/stop", json={}, headers={"Origin": "https://testserver"})
        self.assertEqual(stopped.json()["status"], "stopping")
        self.assertTrue(self.calls)
        self.assertTrue(all(call.headers.get("authorization") == "Bearer server-only-test-key" for call in self.calls))

    def test_same_origin_spa_fallback_serves_assets_and_keeps_unknown_api_404(self):
        page = self.client.get("/chat")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        self.assertIn("App shell", page.text)
        asset = self.client.get("/assets/app.js")
        self.assertEqual(asset.status_code, 200)
        self.assertIn("javascript", asset.headers["content-type"])
        self.assertEqual(self.client.get("/api/does-not-exist").status_code, 404)


if __name__ == "__main__":
    unittest.main()
