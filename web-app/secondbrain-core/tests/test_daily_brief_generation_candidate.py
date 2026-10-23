"""Synthetic only: no Hermes, provider, Web mock, or production data."""
import os
import tempfile
import unittest
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from secondbrain_core.modules.chat_cost_gate import ChatCostGate, ChatCostPolicy
from secondbrain_core.modules.daily_brief_generation import DailyBriefGenerationCandidate
from secondbrain_core.modules.daily_brief_import import DailyBriefImportStore
from secondbrain_core.modules.daily_brief_store import DailyBriefRecordReadStore
from secondbrain_core.modules.organizer_engine import OrganizerState
from secondbrain_core.modules.source_reference_authority import SourceReferenceAuthority
from secondbrain_core.modules.tasks import TaskStore, task_source_version


class TaskProjection:
    def __init__(self, row):
        self.row = row
        self.calls = 0

    def list_for_projection(self):
        self.calls += 1
        return {"tasks": [dict(self.row)]}


class SyntheticModel:
    synthetic_only = True

    def __init__(self):
        self.calls = 0
        self.contexts = []
        self.before_return = lambda: None

    def generate(self, context):
        self.calls += 1
        self.contexts.append(context)
        self.before_return()
        run_id = f"synthetic-{self.calls}"
        return {"run_id": run_id, "categories": ["任务"], "summary": "合成任务简报",
                "terminal": {"event": "run.completed", "run_id": run_id,
                             "runtime": {"provider": "synthetic", "model": "fixture"},
                             "usage": {"input_tokens": 40, "output_tokens": 20,
                                       "model_calls": 1}}}


class BriefGenerationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = os.path.realpath(self.temp.name)
        for name in ("budget", "briefs"):
            os.mkdir(os.path.join(self.root, name), 0o700)
        self.row = {"id": "a" * 32, "title": "合成任务", "status": "open",
                    "due_date": "2026-10-23", "created_at": "2026-10-23T00:00:00Z",
                    "updated_at": "2026-10-23T00:00:00Z", "source": "web_app_explicit_task"}
        self.task = TaskProjection(self.row)
        self.ref = {"kind": "task", "id": self.row["id"], "version": task_source_version(self.row)}
        self.read_allowed = True
        self.write_allowed = True
        self.model = SyntheticModel()
        policy = ChatCostPolicy.parse({
            "policy_id": "synthetic-brief", "primary_route": {"provider": "synthetic", "model": "fixture"},
            "allowed_routes": [{"provider": "synthetic", "model": "fixture",
                                "input_microcny_per_million": 1_000_000,
                                "output_microcny_per_million": 1_000_000}],
            "price_source": "synthetic fixture", "price_version": "fixture-1",
            "price_valid_until": "2099-01-01T00:00:00Z", "max_input_tokens": 4096,
            "max_output_tokens": 100, "max_model_calls": 1,
            "passive_daily_microcny": 10000, "passive_monthly_microcny": 10000,
            "active_daily_microcny": 10000, "active_monthly_microcny": 10000,
        })
        self.gate = ChatCostGate(OrganizerState(os.path.join(self.root, "budget")), policy)
        self.store = DailyBriefImportStore(os.path.join(self.root, "briefs"))

    def candidate(self, *, enabled=True):
        def check():
            if not self.write_allowed or not self.read_allowed:
                raise HTTPException(403, "denied")
        return DailyBriefGenerationCandidate(
            authority_factory=lambda: SourceReferenceAuthority(
                task_store=self.task, permission_checks={"task": lambda: check()}),
            store=self.store, cost_gate=self.gate, model=self.model,
            permission_preflight=check, enabled=enabled)

    def generate(self, candidate=None, key="synthetic-key-123456"):
        return (candidate or self.candidate()).generate(
            day="2026-10-23", timezone="Asia/Shanghai", refs=[self.ref],
            actor="synthetic-user", session_id="synthetic-session",
            idempotency_key=key, confirmed=True)

    def test_default_off_and_revocation_zero_source_io(self):
        with self.assertRaises(HTTPException) as error:
            self.generate(self.candidate(enabled=False))
        self.assertEqual(error.exception.status_code, 503)
        self.read_allowed = False
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.task.calls, 0)
        self.assertEqual(self.model.calls, 0)

    def test_budget_exhaustion_zero_model_calls(self):
        self.gate.policy = replace(self.gate.policy, active_daily_microcny=0)
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.model.calls, 0)

    def test_generated_record_readback_and_replay_no_second_call(self):
        result = self.generate()
        self.assertEqual(result["status"], "created")
        self.assertEqual(self.model.contexts[0]["untrusted_sources"][0]["content"]["title"], "合成任务")
        snapshot = DailyBriefRecordReadStore(os.path.join(self.root, "briefs")).read(
            "2026-10-23", "Asia/Shanghai",
            source_verifier=self.candidate().authority_factory().verify)
        self.assertTrue(snapshot.found)
        self.assertEqual(snapshot.record["summary"], "合成任务简报")
        replay = self.generate()
        self.assertEqual(replay["status"], "duplicate")
        self.assertEqual(replay["brief_id"], result["brief_id"])
        self.assertEqual(self.model.calls, 1)

    def test_real_task_store_to_brief_persistent_readback(self):
        task_root = os.path.join(self.root, "tasks")
        os.mkdir(task_root, 0o700)
        self.task = TaskStore(task_root)
        created = self.task.create("真实 Core 合成任务", "2026-10-23", "task-key-123456")
        task = created["task"]
        self.ref = {"kind": "task", "id": task["id"], "version": task_source_version(task)}
        result = self.generate()
        self.assertEqual(result["status"], "created")
        self.assertEqual(self.model.contexts[0]["untrusted_sources"][0]["content"]["title"],
                         "真实 Core 合成任务")
        snapshot = DailyBriefRecordReadStore(os.path.join(self.root, "briefs")).read(
            "2026-10-23", "Asia/Shanghai",
            source_verifier=self.candidate().authority_factory().verify)
        self.assertEqual(snapshot.source_verification, "verified")
        self.assertEqual(snapshot.record["summary"], "合成任务简报")

    def test_stale_source_rejected_before_model_or_budget(self):
        self.row["title"] = "已改变"
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.gate.rows(), [])

    def test_source_drift_during_generation_fails_closed(self):
        self.model.before_return = lambda: self.row.__setitem__("title", "生成期间变更")
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.task.calls, 2)
        self.assertFalse(os.path.exists(os.path.join(self.root, "briefs", "2026-10-23.json")))
        with self.assertRaises(HTTPException):
            self.generate()
        self.assertEqual(self.model.calls, 1)

    def test_revocation_during_generation_blocks_commit(self):
        self.model.before_return = lambda: setattr(self, "read_allowed", False)
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.task.calls, 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "briefs", "2026-10-23.json")))

    def test_concurrent_active_reservations_do_not_oversell(self):
        one = self.gate.policy.reservation_microcny
        self.gate.policy = replace(self.gate.policy, active_daily_microcny=one,
                                   active_monthly_microcny=one)
        def attempt(key):
            try:
                self.generate(key=key)
                return 201
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(attempt, ("synthetic-key-aaaa", "synthetic-key-bbbb")))
        self.assertIn(429, statuses)
        self.assertEqual(self.model.calls, 1)

    def test_restart_preserves_replay_and_prevents_second_call(self):
        self.generate()
        self.gate = ChatCostGate(OrganizerState(os.path.join(self.root, "budget")),
                                 self.gate.policy)
        replay = self.generate()
        self.assertEqual(replay["status"], "duplicate")
        self.assertEqual(self.model.calls, 1)

    def test_model_failure_preserves_unknown_reservation(self):
        def fail():
            raise TimeoutError("synthetic timeout")
        self.model.before_return = fail
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.gate.rows()[0]["status"], "unknown")
        self.model.before_return = lambda: None
        with self.assertRaises(HTTPException) as replay:
            self.generate()
        self.assertEqual(replay.exception.status_code, 409)
        self.assertEqual(self.model.calls, 1)

    def test_published_record_without_cost_receipt_requires_recovery(self):
        update = self.gate.state.update
        def fail_receipt(fn):
            if fn.__name__ == "save_receipt":
                raise OSError("synthetic ledger interruption")
            return update(fn)
        self.gate.state.update = fail_receipt
        with self.assertRaises(HTTPException) as error:
            self.generate()
        self.assertEqual(error.exception.status_code, 503)
        self.assertTrue(os.path.exists(os.path.join(self.root, "briefs", "2026-10-23.json")))
        with self.assertRaises(HTTPException) as replay:
            self.generate()
        self.assertEqual(replay.exception.status_code, 409)
        self.assertEqual(self.model.calls, 1)


if __name__ == "__main__":
    unittest.main()
