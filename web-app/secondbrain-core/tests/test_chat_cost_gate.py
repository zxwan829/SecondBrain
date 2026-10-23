import concurrent.futures
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from secondbrain_core.modules.chat_cost_gate import ChatCostGate, ChatCostPolicy
from secondbrain_core.modules.organizer_engine import OrganizerState


def policy(**overrides):
    value = {
        "policy_id": "synthetic-v1",
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
        "passive_daily_microcny": 1000,
        "passive_monthly_microcny": 1000,
        "active_daily_microcny": 3000,
        "active_monthly_microcny": 3000,
    }
    value.update(overrides)
    return ChatCostPolicy.parse(value)


class ChatCostGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = OrganizerState(self.temp.name)
        self.gate = ChatCostGate(self.state, policy())
        self.now = datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc)
        self.body = {"input": "synthetic prompt", "session_id": "session-1"}

    def tearDown(self):
        self.temp.cleanup()

    def reserve(self, key, *, request_class="passive", body=None):
        return self.gate.reserve(owner="owner", session_id="session-1", idempotency_key=key,
                                 run_body=body or self.body, request_class=request_class, now=self.now)

    def test_unknown_hermes_capability_fails_closed(self):
        for value in ({}, {"features": {"run_cost_envelope": {"version": 1, "enforced": True}}},
                      {"features": {"run_cost_envelope": {
                          "version": 1, "enforced": True, "max_input_tokens": 100,
                          "max_output_tokens": 50, "max_model_calls": 2,
                          "route_allowlist_enforced": False}}}):
            with self.assertRaises(HTTPException) as error:
                self.gate.require_hermes_envelope(value)
            self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.state.read().get("budget", {}).get("chat_runs", {}), {})

    def test_idempotent_replay_fails_closed_after_hermes_retention_window(self):
        first = self.reserve("old-key")
        def age(state):
            row = next(iter(state["budget"]["chat_runs"].values()))
            row["created_at"] = "2026-10-21T00:00:00Z"
        self.state.update(age)
        replay = self.reserve("old-key")
        self.assertTrue(replay["replay"])
        with self.assertRaises(HTTPException) as error:
            self.gate.require_replay_window(replay, now=self.now)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(first["reservation_id"], replay["reservation_id"])

    def test_reservation_uses_highest_fallback_rate_and_replay_is_exact(self):
        first = self.reserve("same-key")
        replay = self.reserve("same-key")
        self.assertEqual(first["reserved_microcny"], 700)
        self.assertTrue(replay["replay"])
        self.assertEqual(replay["reservation_id"], first["reservation_id"])
        self.assertEqual(len(self.gate.rows()), 1)
        with self.assertRaises(HTTPException) as error:
            self.reserve("same-key", body={"input": "changed", "session_id": "session-1"})
        self.assertEqual(error.exception.status_code, 409)

    def test_passive_and_active_pools_are_separate_and_overage_blocks(self):
        self.reserve("passive-1")
        with self.assertRaises(HTTPException) as error:
            self.reserve("passive-2")
        self.assertEqual(error.exception.status_code, 429)
        active = self.reserve("active-1", request_class="active")
        self.assertEqual(active["request_class"], "active")
        self.assertEqual(len(self.gate.rows()), 2)

    def test_concurrent_reservations_do_not_oversell(self):
        limits = {"passive_daily_microcny": 700, "passive_monthly_microcny": 700}
        gate = ChatCostGate(self.state, policy(**limits))
        def attempt(index):
            try:
                return gate.reserve(owner="owner", session_id="session-1",
                                    idempotency_key=f"parallel-{index}", run_body=self.body,
                                    now=self.now)["status"]
            except HTTPException as exc:
                return exc.status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(outcomes.count("reserved"), 1)
        self.assertEqual(outcomes.count(429), 7)
        self.assertEqual(len(gate.rows()), 1)

    def test_unknown_holds_reservation_and_trusted_usage_settles_after_restart(self):
        reservation = self.reserve("reconcile-key")
        self.gate.attach_run(reservation["reservation_id"], "run-1")
        self.gate.mark_unknown("run-1")
        restarted = ChatCostGate(OrganizerState(self.temp.name), policy())
        row = restarted.rows()[0]
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["accounted_microcny"], reservation["reserved_microcny"])
        self.assertFalse(restarted.settle_completed("run-1", {
            "event": "run.completed", "runtime": {"provider": "unknown", "model": "route"},
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }))
        self.assertEqual(restarted.rows()[0]["status"], "unknown")
        self.assertTrue(restarted.settle_completed("run-1", {
            "event": "run.completed", "runtime": {"provider": "synthetic", "model": "bounded/model"},
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }))
        settled = restarted.rows()[0]
        self.assertEqual(settled["status"], "settled")
        self.assertEqual(settled["actual_microcny"], 40)
        self.assertFalse(settled["over_reservation"])

    def test_expired_price_policy_is_rejected_before_reservation(self):
        expired = ChatCostGate(self.state, policy(price_valid_until="2020-01-01T00:00:00Z"))
        with self.assertRaises(HTTPException) as error:
            expired.require_hermes_envelope({
                "features": {"run_cost_envelope": {
                    "version": 1, "enforced": True, "route_allowlist_enforced": True,
                    "max_input_tokens": 100, "max_output_tokens": 50, "max_model_calls": 2,
                }},
            })
        self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
