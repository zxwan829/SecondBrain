import asyncio
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from secondbrain_core.modules.siliconflow_eval_run import (
    ALLOWED_MODEL_IDS,
    PersistentBenchmarkRun,
)


def synthetic_result():
    return {"http_status": 200, "elapsed_ms": 12.3, "trace_id": "synthetic-trace-1",
            "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50,
                      "reasoning_tokens": 5, "model": ALLOWED_MODEL_IDS[0]},
            "drafts": [{"category": "todo", "title": "合成事项", "source_quotes": []}]}


class PersistentBenchmarkRunTests(unittest.TestCase):
    def make_run(self, directory):
        return PersistentBenchmarkRun.create(directory, model_ids=ALLOWED_MODEL_IDS[:1])

    def test_slow_call_is_single_flight_and_duplicate_start_does_not_invoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp))
            entered = asyncio.Event()
            release = asyncio.Event()
            calls = 0

            async def slow_call():
                nonlocal calls
                calls += 1
                entered.set()
                await release.wait()
                return synthetic_result()

            async def exercise():
                task = asyncio.create_task(run.run_once(ALLOWED_MODEL_IDS[0], slow_call))
                await entered.wait()
                second_process = PersistentBenchmarkRun.open(Path(tmp), run.run_id)
                duplicate = await second_process.run_once(ALLOWED_MODEL_IDS[0], slow_call)
                self.assertEqual(duplicate["state"], "started")
                self.assertTrue(duplicate["active"])
                self.assertEqual(calls, 1)
                release.set()
                completed = await task
                self.assertEqual(completed["state"], "completed")

            asyncio.run(exercise())
            self.assertEqual(calls, 1)

    def test_interrupted_started_state_recovers_to_unknown_and_never_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp))
            self.assertTrue(run.claim(ALLOWED_MODEL_IDS[0]))
            # The persisted started state only means the slot was reserved; it does not prove dispatch.
            reopened = PersistentBenchmarkRun.open(Path(tmp), run.run_id)
            row = reopened.status()["models"][ALLOWED_MODEL_IDS[0]]
            self.assertEqual(row["state"], "unknown")
            self.assertEqual(row["error_code"], "interrupted_after_started_state")
            calls = 0

            async def must_not_run():
                nonlocal calls
                calls += 1
                return synthetic_result()

            row = asyncio.run(reopened.run_once(ALLOWED_MODEL_IDS[0], must_not_run))
            self.assertEqual(row["state"], "unknown")
            self.assertEqual(calls, 0)

    def test_completed_run_survives_restart_and_is_not_sent_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp))
            calls = 0

            async def call_once():
                nonlocal calls
                calls += 1
                await asyncio.sleep(0.01)
                return synthetic_result()

            first = asyncio.run(run.run_once(ALLOWED_MODEL_IDS[0], call_once))
            run.annotate(ALLOWED_MODEL_IDS[0],
                         evaluation={"json_valid": True, "categories": {"journal": 1, "work_idea": 1, "todo": 1},
                                     "hallucinations": 0, "duplicate_drafts": 0},
                         estimated_cost={"currency": "CNY", "amount": 0.01,
                                         "basis": "synthetic test rate", "priced_at": "2026-10-15"})
            reopened = PersistentBenchmarkRun.open(Path(tmp), run.run_id)
            second = asyncio.run(reopened.run_once(ALLOWED_MODEL_IDS[0], call_once))
            self.assertEqual(first["state"], "completed")
            self.assertEqual(second["state"], "completed")
            self.assertEqual(calls, 1)
            self.assertEqual(second["result"]["usage"]["reasoning_tokens"], 5)
            self.assertTrue(second["evaluation"]["json_valid"])
            self.assertEqual(second["estimated_cost"]["amount"], 0.01)

    def test_cancelled_execution_becomes_unknown_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp))
            entered = asyncio.Event()

            async def slow_call():
                entered.set()
                await asyncio.Event().wait()

            async def exercise():
                task = asyncio.create_task(run.run_once(ALLOWED_MODEL_IDS[0], slow_call))
                await entered.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            asyncio.run(exercise())
            reopened = PersistentBenchmarkRun.open(Path(tmp), run.run_id)
            self.assertEqual(reopened.status()["models"][ALLOWED_MODEL_IDS[0]]["state"], "unknown")

    def test_known_http_failure_is_recorded_without_fabricated_usage_or_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp))
            calls = 0

            async def rate_limited():
                nonlocal calls
                calls += 1
                error = RuntimeError("sanitized")
                error.status_code = 429
                error.code = "provider_rate_limited"
                error.trace_id = "synthetic-trace-429"
                raise error

            with self.assertRaises(RuntimeError):
                asyncio.run(run.run_once(ALLOWED_MODEL_IDS[0], rate_limited))
            row = run.status()["models"][ALLOWED_MODEL_IDS[0]]
            self.assertEqual(row["state"], "completed")
            self.assertEqual(row["result"]["http_status"], 429)
            self.assertNotIn("usage", row["result"])
            repeated = asyncio.run(run.run_once(ALLOWED_MODEL_IDS[0], rate_limited))
            self.assertEqual(repeated["state"], "completed")
            self.assertEqual(calls, 1)

    def test_ledger_is_private_and_contains_no_request_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(Path(tmp))
            file_info = run.path.stat()
            self.assertEqual(stat.S_IMODE(file_info.st_mode), 0o600)
            self.assertEqual(file_info.st_uid, os.geteuid())
            asyncio.run(run.run_once(ALLOWED_MODEL_IDS[0], lambda: asyncio.sleep(0, result=synthetic_result())))
            raw = run.path.read_text(encoding="utf-8")
            doc = json.loads(raw)
            self.assertNotIn("Authorization", raw)
            self.assertNotIn("api_key", raw.lower())
            self.assertEqual(doc["models"][ALLOWED_MODEL_IDS[0]]["state"], "completed")


if __name__ == "__main__":
    unittest.main()
