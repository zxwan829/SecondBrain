import asyncio
import tempfile
import unittest
from pathlib import Path

from secondbrain_core.modules.vision_benchmark import VisionBenchmarkError
from secondbrain_core.modules.vision_benchmark_run import (
    VISION_MODEL_ORDER,
    PersistentVisionRun,
    VisionRunError,
)


def result():
    return {
        "http_status": 200,
        "elapsed_ms": 1234,
        "trace_id": "synthetic-vision-trace",
        "model": VISION_MODEL_ORDER[0],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100,
                  "total_tokens": 1100, "reasoning_tokens": 20},
        "content": '{"images": []}',
        "parsed": {"images": []},
        "finish_reason": "stop",
    }


class PersistentVisionRunTests(unittest.TestCase):
    def test_order_success_recovery_and_duplicate_do_not_invoke_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = PersistentVisionRun.create(Path(tmp))
            self.assertEqual(tuple(run.status()["model_order"]), VISION_MODEL_ORDER)
            self.assertTrue(run.may_run_in_order(VISION_MODEL_ORDER[0]))
            self.assertFalse(run.may_run_in_order(VISION_MODEL_ORDER[1]))
            calls = 0

            async def fake_slow_call():
                nonlocal calls
                calls += 1
                await asyncio.sleep(0.01)
                return result()

            row = asyncio.run(run.run_once(
                VISION_MODEL_ORDER[0], request_metadata={"image_count": 3,
                    "fixture_sha256": ["a" * 64], "max_output_tokens": 800}, invoke=fake_slow_call))
            self.assertEqual(row["state"], "completed")
            reopened = PersistentVisionRun.open(Path(tmp), run.run_id)
            repeated = asyncio.run(reopened.run_once(
                VISION_MODEL_ORDER[0], request_metadata={}, invoke=fake_slow_call))
            self.assertEqual(repeated["state"], "completed")
            self.assertEqual(calls, 1)
            self.assertEqual(repeated["result"]["usage"]["reasoning_tokens"], 20)
            self.assertTrue(reopened.may_run_in_order(VISION_MODEL_ORDER[1]))

    def test_interrupted_started_and_timeout_are_unknown_and_block_following_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = PersistentVisionRun.create(Path(tmp))
            self.assertTrue(run.claim(VISION_MODEL_ORDER[0], request_metadata={"image_count": 3}))
            reopened = PersistentVisionRun.open(Path(tmp), run.run_id)
            self.assertEqual(reopened.status()["models"][VISION_MODEL_ORDER[0]]["state"], "unknown")
            self.assertFalse(reopened.may_run_in_order(VISION_MODEL_ORDER[1]))

        with tempfile.TemporaryDirectory() as tmp:
            run = PersistentVisionRun.create(Path(tmp))

            async def timeout():
                raise VisionBenchmarkError("provider_timeout", model=VISION_MODEL_ORDER[0],
                    elapsed_ms=45_000, trace_id="client-trace-timeout")

            with self.assertRaises(VisionBenchmarkError):
                asyncio.run(run.run_once(VISION_MODEL_ORDER[0], request_metadata={}, invoke=timeout))
            row = run.status()["models"][VISION_MODEL_ORDER[0]]
            self.assertEqual(row["state"], "unknown")
            self.assertEqual(row["attempts"], 1)
            self.assertEqual(row["error"]["trace_id"], "client-trace-timeout")
            self.assertFalse(run.may_run_in_order(VISION_MODEL_ORDER[1]))

    def test_http_error_is_failed_and_stops_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = PersistentVisionRun.create(Path(tmp))

            async def rate_limited():
                raise VisionBenchmarkError("provider_rate_limited", model=VISION_MODEL_ORDER[0],
                    elapsed_ms=10, trace_id="client-trace-429", http_status=429)

            with self.assertRaises(VisionBenchmarkError):
                asyncio.run(run.run_once(VISION_MODEL_ORDER[0], request_metadata={}, invoke=rate_limited))
            row = run.status()["models"][VISION_MODEL_ORDER[0]]
            self.assertEqual(row["state"], "failed")
            self.assertEqual(row["error"]["http_status"], 429)
            self.assertFalse(run.may_run_in_order(VISION_MODEL_ORDER[1]))

    def test_http_error_saves_whitelisted_provider_diagnostics_without_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = PersistentVisionRun.create(Path(tmp), model_order=VISION_MODEL_ORDER[1:])
            model = VISION_MODEL_ORDER[1]
            error = VisionBenchmarkError("provider_http_error", model=model, elapsed_ms=90,
                http_status=400, trace_id="safe-trace", provider_diagnostics={
                    "provider_error_type": "invalid_request_error",
                    "provider_error_code": "image_payload_invalid",
                    "provider_error_param": "detail",
                })

            async def failed():
                raise error

            with self.assertRaises(VisionBenchmarkError):
                asyncio.run(run.run_once(model, request_metadata={}, invoke=failed))
            row = run.status()["models"][model]
            self.assertEqual(row["error"]["provider_error_code"], "image_payload_invalid")
            self.assertEqual(row["error"]["provider_error_param"], "detail")
            self.assertNotIn("message", row["error"])
            self.assertNotIn("response_body", row["error"])

    def test_truncated_http_200_usage_is_persisted_without_partial_json_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = PersistentVisionRun.create(Path(tmp))

            async def truncated():
                raise VisionBenchmarkError("provider_output_truncated", model=VISION_MODEL_ORDER[0],
                    elapsed_ms=100, trace_id="trace-truncated", http_status=200,
                    usage={"prompt_tokens": 300, "completion_tokens": 800,
                           "total_tokens": 1100, "reasoning_tokens": 450}, finish_reason="length")

            with self.assertRaises(VisionBenchmarkError):
                asyncio.run(run.run_once(VISION_MODEL_ORDER[0], request_metadata={}, invoke=truncated))
            row = run.status()["models"][VISION_MODEL_ORDER[0]]
            self.assertEqual(row["state"], "failed")
            self.assertEqual(row["error"]["http_status"], 200)
            self.assertEqual(row["error"]["usage"]["reasoning_tokens"], 450)
            self.assertEqual(row["error"]["finish_reason"], "length")
            self.assertNotIn("result", row)
            self.assertFalse(run.may_run_in_order(VISION_MODEL_ORDER[1]))

    def test_remaining_models_run_in_own_order_and_evaluation_is_saved_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            remaining = VISION_MODEL_ORDER[1:]
            run = PersistentVisionRun.create(Path(tmp), model_order=remaining)
            self.assertEqual(tuple(run.status()["model_order"]), remaining)
            self.assertTrue(run.may_run_in_order(remaining[0]))
            self.assertFalse(run.may_run_in_order(remaining[1]))
            asyncio.run(run.run_once(remaining[0], request_metadata={}, invoke=lambda: _async_result(remaining[0])))
            run.annotate(remaining[0], evaluation={"recognition": 4, "key_numbers": 5,
                "ui_facts": 4, "source_evidence": 5, "hallucinations": 5,
                "json_valid": True, "score_notes": "合成测试评分"},
                estimated_cost_usd=0.002, pricing_as_of="2026-10-15")
            reopened = PersistentVisionRun.open(Path(tmp), run.run_id)
            row = reopened.status()["models"][remaining[0]]
            self.assertEqual(row["result"]["finish_reason"], "stop")
            self.assertEqual(row["evaluation"]["estimated_cost_usd"], 0.002)
            with self.assertRaisesRegex(VisionRunError, "evaluation_already_saved"):
                reopened.annotate(remaining[0], evaluation={"recognition": 4, "key_numbers": 5,
                    "ui_facts": 4, "source_evidence": 5, "hallucinations": 5,
                    "json_valid": True, "score_notes": "不得覆盖"},
                    estimated_cost_usd=0.002, pricing_as_of="2026-10-15")
            self.assertTrue(reopened.may_run_in_order(remaining[1]))


async def _async_result(model):
    value = result()
    value["model"] = model
    return value


if __name__ == "__main__":
    unittest.main()
