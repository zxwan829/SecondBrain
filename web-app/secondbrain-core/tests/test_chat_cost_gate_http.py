import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from secondbrain_core.app import create_app
from secondbrain_core.modules.hermes_api import HermesAPI


class ChatCostGateHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.review, self.raw, self.knowledge, self.state = (
            root / "review", root / "raw", root / "knowledge", root / "state")
        self.journal, self.tasks = root / "journal", root / "tasks"
        self.static = root / "static"
        for path in (self.review, self.raw, self.knowledge, self.state, self.journal, self.tasks, self.static):
            path.mkdir(mode=0o700)
        (self.static / "index.html").write_text("synthetic app shell", encoding="utf-8")
        self.password_file = root / "app.password"
        self.password_file.write_text("synthetic-chat-cost-password", encoding="utf-8")
        self.password_file.chmod(0o600)
        self.policy_file = root / "chat-cost-policy.json"
        self.policy_file.write_text(json.dumps({
            "policy_id": "http-fixture-v1",
            "primary_route": {"provider": "synthetic", "model": "bounded/model"},
            "allowed_routes": [
                {"provider": "synthetic", "model": "bounded/model",
                 "input_microcny_per_million": 1_000_000,
                 "output_microcny_per_million": 2_000_000},
                {"provider": "synthetic-fallback", "model": "bounded/model",
                 "input_microcny_per_million": 2_000_000,
                 "output_microcny_per_million": 3_000_000},
            ],
            "price_source": "synthetic fixture",
            "price_version": "fixture-1",
            "price_valid_until": "2099-01-01T00:00:00Z",
            "max_input_tokens": 100,
            "max_output_tokens": 50,
            "max_model_calls": 2,
            "passive_daily_microcny": 700,
            "passive_monthly_microcny": 700,
            "active_daily_microcny": 3000,
            "active_monthly_microcny": 3000,
        }), encoding="utf-8")
        self.policy_file.chmod(0o600)
        self.allow_envelope = False
        self.event = {"event": "run.completed", "runtime": {"provider": "unknown", "model": "unknown"},
                      "usage": {"input_tokens": 1, "output_tokens": 1, "model_calls": 1}}
        self.calls = []
        self.logical_runs = {}
        self.run_posts = 0
        self.fail_after_create = False

        def handler(request):
            self.calls.append(request)
            if request.url.path == "/v1/capabilities":
                features = {"session_api": True}
                if self.allow_envelope:
                    features["run_cost_envelope"] = {
                        "version": 1, "enforced": True, "route_allowlist_enforced": True,
                        "max_input_tokens": 100, "max_output_tokens": 50, "max_model_calls": 2,
                    }
                return httpx.Response(200, json={"features": features})
            if request.url.path == "/api/sessions/session-1":
                return httpx.Response(200, json={"session": {"id": "session-1", "message_count": 0}})
            if request.url.path == "/api/sessions/session-1/messages":
                return httpx.Response(200, json={"data": [], "pagination": {"limit": 500, "offset": 0}})
            if request.url.path == "/v1/runs":
                self.run_posts += 1
                key = request.headers.get("Idempotency-Key")
                run_id = self.logical_runs.setdefault(key, f"run-{len(self.logical_runs) + 1}")
                if self.fail_after_create:
                    self.fail_after_create = False
                    raise httpx.ReadTimeout("synthetic response lost after accepted request")
                return httpx.Response(202, json={"run_id": run_id, "status": "started"})
            if request.url.path.endswith("/events"):
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"},
                    content=("data: " + json.dumps(self.event) + "\n\n").encode("utf-8"),
                )
            return httpx.Response(404, json={"detail": "not found"})

        self.transport = httpx.MockTransport(handler)
        self.hermes = HermesAPI("http://hermes.synthetic", "synthetic-only-key", self.transport)
        env = {
            "SB_REVIEW_ROOT": str(self.review),
            "SB_CAPTURE_RAW_ROOT": str(self.raw),
            "SB_JOURNAL_ROOT": str(self.journal),
            "SB_TASK_ROOT": str(self.tasks),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge),
            "SB_PROMOTE_STATE_ROOT": str(self.state),
            "SB_DASHBOARD_ORIGINS": "https://testserver",
            "SB_CORE_ALLOWED_HOSTS": "testserver",
            "SB_APP_PASSWORD_FILE": str(self.password_file),
            "SB_HERMES_API_URL": "http://hermes.synthetic",
            "SB_HERMES_API_KEY": "synthetic-only-key",
            "SB_PROMOTE_ENABLED": "false",
            "SB_STATIC_ROOT": str(self.static),
            "SB_CHAT_COST_GATE_ENABLED": "true",
            "SB_CHAT_COST_POLICY_FILE": str(self.policy_file),
        }
        with patch.dict(os.environ, env), patch("secondbrain_core.app.HermesAPI", return_value=self.hermes):
            self.app = create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        login = self.client.post("/api/auth/login", json={"password": "synthetic-chat-cost-password"},
                                 headers={"Origin": "https://testserver"})
        self.assertEqual(login.status_code, 200, login.text)
        self.calls.clear()

    def tearDown(self):
        self.client.close()
        self.transport.close()
        self.temp.cleanup()

    def run_once(self, key):
        return self.client.post("/api/chat/sessions/session-1/runs", json={"input": "synthetic prompt"},
                                headers={"Origin": "https://testserver", "Idempotency-Key": key})

    def ledger_rows(self):
        state_path = self.state / "ai-organize" / "state.json"
        if not state_path.exists():
            return []
        return json.loads(state_path.read_text(encoding="utf-8")).get("budget", {}).get("chat_runs", {}).values()

    def test_real_core_route_fails_closed_without_hermes_envelope_and_never_posts_run(self):
        response = self.run_once("cost-no-envelope")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "chat_cost_envelope_unavailable")
        self.assertFalse(any(call.url.path == "/v1/runs" for call in self.calls))
        self.assertEqual(list(self.ledger_rows()), [])

    def test_opt_in_route_reserves_replays_and_recovers_unknown_using_synthetic_usage(self):
        self.allow_envelope = True
        start = self.run_once("cost-replay-key")
        self.assertEqual(start.status_code, 200, start.text)
        run_id = start.json()["run_id"]
        post = next(call for call in self.calls if call.url.path == "/v1/runs")
        body = json.loads(post.content)
        self.assertEqual((body["provider"], body["model"]), ("synthetic", "bounded/model"))
        self.assertEqual(body["cost_envelope"]["allowed_routes"][1]["provider"], "synthetic-fallback")
        self.assertEqual(post.headers["Idempotency-Key"], "cost-replay-key")

        unknown = self.client.get(f"/api/chat/runs/{run_id}/events")
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(list(self.ledger_rows())[0]["status"], "unknown")

        self.event = {
            "event": "run.completed",
            "runtime": {"provider": "synthetic-fallback", "model": "bounded/model"},
            "usage": {"input_tokens": 20, "output_tokens": 10, "model_calls": 1},
        }
        replay = self.run_once("cost-replay-key")
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["run_id"], run_id)
        settled = self.client.get(f"/api/chat/runs/{run_id}/events")
        self.assertEqual(settled.status_code, 200)
        self.assertEqual(self.run_posts, 2)  # explicit retry, same Hermes key and same run
        rows = list(self.ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["request_class"], "passive")
        self.assertEqual(rows[0]["status"], "settled")
        self.assertEqual(rows[0]["actual_microcny"], 70)
        self.assertIn("not an invoice", rows[0]["estimate_basis"])

        blocked = self.run_once("second-cost-key")
        self.assertEqual(blocked.status_code, 429, blocked.text)
        self.assertEqual(self.run_posts, 2)

    def test_non_success_sse_terminals_hold_reservation_with_reported_usage(self):
        self.allow_envelope = True
        start = self.run_once("failed-sse-terminal")
        self.assertEqual(start.status_code, 200)
        run_id = start.json()["run_id"]
        for terminal in ("run.failed", "run.cancelled", "run.interrupted"):
            with self.subTest(terminal=terminal):
                self.event = {
                    "event": terminal,
                    "runtime": {"provider": "synthetic", "model": "bounded/model"},
                    "usage": {"input_tokens": 20, "output_tokens": 10, "model_calls": 1},
                }
                response = self.client.get(f"/api/chat/runs/{run_id}/events")
                self.assertEqual(response.status_code, 200)
                row = next(row for row in self.ledger_rows() if row.get("run_id") == run_id)
                self.assertEqual(row["status"], "unknown")
                self.assertEqual(row["accounted_microcny"], row["reserved_microcny"])

    def test_ambiguous_start_failure_keeps_reservation_until_explicit_same_key_replay(self):
        self.allow_envelope = True
        self.fail_after_create = True
        failed = self.run_once("ambiguous-start-key")
        self.assertEqual(failed.status_code, 502)
        rows = list(self.ledger_rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "unknown")
        self.assertEqual(self.run_posts, 1)  # no automatic retry

        replay = self.run_once("ambiguous-start-key")
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["run_id"], "run-1")
        self.assertEqual(self.run_posts, 2)  # explicit same key; Hermes returns the original logical Run
        self.assertEqual(len(list(self.ledger_rows())), 1)


if __name__ == "__main__":
    unittest.main()
