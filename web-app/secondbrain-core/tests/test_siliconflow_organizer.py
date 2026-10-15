import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi import HTTPException

from secondbrain_core.modules.organizer_engine import OrganizerRunner
from secondbrain_core.modules.siliconflow_organizer import (
    ENDPOINT,
    OrganizerAdapterError,
    SiliconFlowOrganizerModel,
    _bounded_messages,
    read_private_secret,
)


def response(body, status=200):
    return httpx.Response(status, json=body)


def good_body(*, text=None, completion_tokens=20):
    return {"model": "synthetic/model", "choices": [{"finish_reason": "stop", "message": {
        "content": text if text is not None else json.dumps({"drafts": []})}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": completion_tokens,
                  "total_tokens": 100 + completion_tokens}}


class SiliconFlowAdapterTests(unittest.TestCase):
    def make_adapter(self, handler, *, timeout=0.2):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
        return SiliconFlowOrganizerModel("synthetic-only-secret", client=client, timeout_seconds=timeout), client

    def test_request_is_single_non_streaming_text_call_without_tools_and_returns_usage(self):
        seen = []

        async def handler(request):
            seen.append(request)
            return response(good_body())

        adapter, client = self.make_adapter(handler)
        try:
            result = asyncio.run(adapter.extract({"job_id": "job-1", "task": "extract",
                                                  "new_user_messages": [], "context_only": {},
                                                  "output_schema": {"drafts": []}},
                                                 max_input_tokens=6000, max_output_tokens=300))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(result["drafts"], [])
        self.assertEqual(result["usage"]["total_tokens"], 120)
        self.assertEqual(len(seen), 1)
        self.assertEqual(str(seen[0].url), ENDPOINT)
        self.assertEqual(seen[0].headers["authorization"], "Bearer synthetic-only-secret")
        body = json.loads(seen[0].content)
        self.assertEqual(body["max_tokens"], 300)
        self.assertFalse(body["stream"])
        self.assertTrue(seen[0].headers.get("x-trace-id"))
        self.assertNotIn("enable_thinking", body)
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)
        self.assertNotIn("parallel_tool_calls", body)
        self.assertEqual(adapter.capabilities["hard_cost_budget"], False)
        self.assertNotIn("synthetic-only-secret", repr(adapter))

    def test_three_model_ids_receive_the_same_offline_comparison_request(self):
        model_ids = ["deepseek-ai/DeepSeek-V4-Flash", "zai-org/GLM-4.5-Air",
                     "Qwen/Qwen3.5-35B-A3B"]
        seen = []
        payload = {"job_id": "synthetic-eval-20261015", "task": "按分类提炼明确表达的用户事实；过滤普通问答和闲聊。",
                   "new_user_messages": [
                       {"session_id": "synthetic-life", "message_id": "life-001",
                        "timestamp": "2026-10-15T09:00:00Z", "text": "今天陪家人去公园，感觉轻松。"},
                       {"session_id": "synthetic-work-a", "message_id": "idea-followup-002",
                        "timestamp": "2026-10-15T10:10:00Z", "text": "我还可以从最近一个月的高频问题开始。"},
                       {"session_id": "synthetic-work-b", "message_id": "idea-duplicate-003",
                        "timestamp": "2026-10-15T10:12:00Z", "text": "先把客服高频问题整理成知识卡片。"},
                       {"session_id": "synthetic-life", "message_id": "todo-004",
                        "timestamp": "2026-10-15T10:15:00Z", "text": "周五前把试点计划发给小林。"},
                       {"session_id": "synthetic-life", "message_id": "smalltalk-005",
                        "timestamp": "2026-10-15T10:16:00Z", "text": "谢谢，收到。"},
                       {"session_id": "synthetic-life", "message_id": "qa-006",
                        "timestamp": "2026-10-15T10:17:00Z", "text": "月球距离地球的平均距离大约是多少？"},
                   ],
                   "context_only": {"synthetic-work-a": [{"message_id": "idea-original-001",
                       "role": "user", "timestamp": "2026-10-15T10:00:00Z",
                       "text": "下季度把客服问题整理成知识卡片，减少重复排查。"}]},
                   "output_schema": {"drafts": [{"category": "journal|work_idea|todo|knowledge_candidate",
                       "title": "string", "summary": "string", "source_quotes": []}]}}

        async def handler(request):
            seen.append(json.loads(request.content))
            return response(good_body())

        async def run_all():
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
            try:
                for model_id in model_ids:
                    adapter = SiliconFlowOrganizerModel("synthetic-only-secret", model=model_id,
                                                        client=client, timeout_seconds=1)
                    result = await adapter.extract(payload,
                                                   max_input_tokens=6000, max_output_tokens=1200)
                    self.assertEqual(result["drafts"], [])
            finally:
                await client.aclose()

        asyncio.run(run_all())
        self.assertEqual([body["model"] for body in seen], model_ids)
        normalized = [{key: value for key, value in body.items() if key != "model"} for body in seen]
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[1], normalized[2])
        self.assertEqual(normalized[0]["max_tokens"], 1200)
        self.assertEqual(normalized[0]["temperature"], 0)
        self.assertEqual(normalized[0]["n"], 1)
        self.assertFalse(normalized[0]["stream"])
        self.assertNotIn("enable_thinking", normalized[0])
        self.assertNotIn("tools", normalized[0])
        self.assertNotIn("tool_choice", normalized[0])

    def test_prompt_is_truncated_to_a_deterministic_byte_ceiling(self):
        original = {"task": "x", "new_user_messages": [{
            "session_id": "s", "message_id": "m", "timestamp": "2026-10-15T00:00:00Z",
            "text": "中文内容" * 8000}], "context_only": {}, "output_schema": {}}
        messages = _bounded_messages(original, 6000)
        self.assertLessEqual(len(messages[1]["content"].encode("utf-8")), 4500)
        self.assertIn("[已截断]", messages[1]["content"])
        self.assertEqual(len(original["new_user_messages"][0]["text"]), 32000)

    def test_429_is_sanitized_and_never_retried(self):
        count = 0

        async def handler(request):
            nonlocal count
            count += 1
            return response({"message": "sensitive provider detail"}, status=429)

        adapter, client = self.make_adapter(handler)
        try:
            with self.assertRaises(OrganizerAdapterError) as raised:
                asyncio.run(adapter.extract({"task": "x", "new_user_messages": [], "context_only": {},
                                              "output_schema": {}}, max_input_tokens=6000, max_output_tokens=300))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(raised.exception.code, "provider_rate_limited")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertTrue(raised.exception.trace_id)
        self.assertNotIn("sensitive provider detail", str(raised.exception))
        self.assertEqual(count, 1)

    def test_timeout_is_bounded(self):
        async def handler(request):
            await asyncio.sleep(0.2)
            return response(good_body())

        adapter, client = self.make_adapter(handler, timeout=0.03)
        try:
            with self.assertRaises(OrganizerAdapterError) as raised:
                asyncio.run(adapter.extract({"task": "x", "new_user_messages": [], "context_only": {},
                                              "output_schema": {}}, max_input_tokens=6000, max_output_tokens=300))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(raised.exception.code, "provider_timeout")

    def test_malformed_json_and_non_json_provider_content_fail_closed(self):
        async def handler(request):
            return response(good_body(text="not JSON"))

        adapter, client = self.make_adapter(handler)
        try:
            with self.assertRaises(OrganizerAdapterError) as raised:
                asyncio.run(adapter.extract({"task": "x", "new_user_messages": [], "context_only": {},
                                              "output_schema": {}}, max_input_tokens=6000, max_output_tokens=300))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(raised.exception.code, "provider_response_invalid")
        self.assertEqual(raised.exception.status_code, 200)
        self.assertTrue(raised.exception.trace_id)

    def test_reasoning_tokens_above_final_reply_cap_are_reported(self):
        async def handler(request):
            body = good_body(completion_tokens=1301)
            body["usage"]["completion_tokens_details"] = {"reasoning_tokens": 1101}
            return response(body)

        adapter, client = self.make_adapter(handler)
        try:
            result = asyncio.run(adapter.extract({"task": "x", "new_user_messages": [], "context_only": {},
                                                  "output_schema": {}}, max_input_tokens=6000, max_output_tokens=300))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(result["usage"]["completion_tokens"], 1301)
        self.assertEqual(result["usage"]["reasoning_tokens"], 1101)
        self.assertEqual(result["http_status"], 200)
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertTrue(result["trace_id"])
        self.assertFalse(SiliconFlowOrganizerModel.capabilities["hard_output_token_limit"])

    def test_output_budget_exhaustion_is_rejected_before_network(self):
        count = 0

        async def handler(request):
            nonlocal count
            count += 1
            return response(good_body())

        adapter, client = self.make_adapter(handler)
        try:
            with self.assertRaises(OrganizerAdapterError) as raised:
                asyncio.run(adapter.extract({"task": "x", "new_user_messages": [], "context_only": {},
                                              "output_schema": {}}, max_input_tokens=6000, max_output_tokens=5000))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(raised.exception.code, "output_budget_exceeded")
        self.assertEqual(count, 0)

    def test_secret_file_requires_private_owned_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret"
            path.write_text("synthetic-secret\n", encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(read_private_secret(path), "synthetic-secret")
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                read_private_secret(path)

    def test_runner_stays_blocked_for_adapter_without_hard_cost_and_token_attestation(self):
        class Source:
            async def get_session(self, session_id):
                return {"message_count": 0}

            async def list_messages(self, *args, **kwargs):
                return {"messages": []}

        requests = []
        adapter = SiliconFlowOrganizerModel("synthetic-only-secret", client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: requests.append(request) or response(good_body()))))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            root.mkdir(mode=0o700)
            review = Path(directory) / "review"
            review.mkdir(mode=0o700)
            runner = OrganizerRunner(root, review, Source(), adapter)
            self.assertFalse(runner.status()["execution_available"])
            self.assertIn("hard_input_token_limit", runner.status()["blocked_reason"])
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(runner.run())
            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(requests, [], "the configured adapter must not be called until it clears the hard gate")
        asyncio.run(adapter._client.aclose())


if __name__ == "__main__":
    unittest.main()
