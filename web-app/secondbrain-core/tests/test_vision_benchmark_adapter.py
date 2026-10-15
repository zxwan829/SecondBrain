import asyncio
import base64
import json
import unittest
from io import BytesIO
from unittest.mock import patch

import httpx
from PIL import Image

from secondbrain_core.modules import vision_benchmark as vision


MODELS = [
    "Qwen/Qwen3.5-35B-A3B",
    "deepseek-ai/DeepSeek-V4-Flash-Vision-Exp",
    "zai-org/GLM-5V-Turbo",
]


def png_bytes(color=(25, 80, 180)):
    stream = BytesIO()
    Image.new("RGB", (32, 24), color).save(stream, format="PNG")
    return stream.getvalue()


def jpeg_bytes():
    stream = BytesIO()
    Image.new("RGB", (32, 24), (40, 90, 120)).save(stream, format="JPEG")
    return stream.getvalue()


def completion(content='{"text":"synthetic"}', *, model=None, usage=None):
    return {"model": model or MODELS[0], "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": content}}],
            "usage": usage or {"prompt_tokens": 22, "completion_tokens": 5, "total_tokens": 27}}


class VisionBenchmarkAdapterTests(unittest.TestCase):
    def client(self, handler):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)

    def test_sends_bounded_base64_chat_completion_and_sanitized_usage(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(200, json=completion(), headers={"x-siliconcloud-trace-id": "trace-safe"})

        client = self.client(handler)
        adapter = vision.VisionBenchmarkAdapter("synthetic-test-key", client=client)
        try:
            result = asyncio.run(adapter.analyze(MODELS[0], "读取图中文字并描述画面", [png_bytes(), jpeg_bytes()]))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(len(requests), 1)
        req = requests[0]
        self.assertEqual(str(req.url), vision.ENDPOINT)
        self.assertNotEqual(req.headers["x-trace-id"], "")
        self.assertEqual(result["trace_id"], "trace-safe")
        payload = json.loads(req.content)
        self.assertEqual(payload["model"], MODELS[0])
        self.assertEqual(payload["max_tokens"], vision.MAX_OUTPUT_TOKENS)
        self.assertFalse(payload["stream"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)
        self.assertNotIn("enable_thinking", payload)
        self.assertNotIn("response_format", payload)
        parts = payload["messages"][0]["content"]
        self.assertEqual([p["type"] for p in parts], ["image_url", "image_url", "text"])
        self.assertEqual(parts[0]["image_url"]["url"],
                         "data:image/png;base64," + base64.b64encode(png_bytes()).decode("ascii"))
        self.assertEqual(parts[1]["image_url"]["url"],
                         "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes()).decode("ascii"))
        self.assertEqual(result["usage"], {"prompt_tokens": 22, "completion_tokens": 5, "total_tokens": 27})
        self.assertEqual(result["trace_id"], "trace-safe")
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertNotIn("synthetic-test-key", repr(adapter))
        self.assertNotIn(base64.b64encode(png_bytes()).decode("ascii"), repr(result))

    def test_allowlist_and_per_model_parameter_compatibility_are_explicit(self):
        for model in MODELS:
            body = vision.build_request(model, "test", [png_bytes()])
            self.assertEqual(body["model"], model)
            self.assertNotIn("enable_thinking", body)
            self.assertNotIn("response_format", body)
        for model in MODELS[:2]:
            self.assertEqual(vision.build_request(model, "test", [png_bytes()], json_mode=True)
                             ["response_format"], {"type": "json_object"})
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "json_mode_unsupported"):
            vision.build_request(MODELS[2], "test", [png_bytes()], json_mode=True)
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "model_not_allowlisted"):
            vision.build_request("other/model", "test", [png_bytes()])

    def test_rejects_non_image_unsupported_format_and_oversized_inputs(self):
        for raw, code in [(b"not an image", "image_invalid"), (b"", "image_empty")]:
            with self.subTest(code=code), self.assertRaisesRegex(vision.VisionBenchmarkError, code):
                vision.build_request(MODELS[0], "test", [raw])
        webp = BytesIO()
        Image.new("RGB", (4, 4)).save(webp, format="WEBP")
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "image_format_unsupported"):
            vision.build_request(MODELS[0], "test", [webp.getvalue()])
        oversized_dimensions = BytesIO()
        Image.new("RGB", (vision.MAX_IMAGE_WIDTH + 1, 1)).save(oversized_dimensions, format="PNG")
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "image_dimensions_exceeded"):
            vision.build_request(MODELS[0], "test", [oversized_dimensions.getvalue()])
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "image_too_large"):
            vision.build_request(MODELS[0], "test", [b"x" * (vision.MAX_IMAGE_BYTES + 1)])
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "image_count_exceeded"):
            vision.build_request(MODELS[0], "test", [])
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "image_count_exceeded"):
            vision.build_request(MODELS[0], "test", [png_bytes()] * (vision.MAX_IMAGES + 1))
        with self.assertRaisesRegex(vision.VisionBenchmarkError, "output_budget_exceeded"):
            vision.build_request(MODELS[0], "test", [png_bytes()], max_output_tokens=vision.MAX_OUTPUT_TOKENS + 1)

    def test_rejects_total_request_body_over_limit_before_network(self):
        with patch.object(vision, "MAX_REQUEST_BODY_BYTES", 200):
            with self.assertRaisesRegex(vision.VisionBenchmarkError, "request_body_too_large"):
                vision.build_request(MODELS[0], "test", [png_bytes()])

    def test_429_is_sanitized_and_never_retried(self):
        calls = []

        async def handler(request):
            calls.append(request)
            return httpx.Response(429, json={"message": "secret-looking provider detail"})

        client = self.client(handler)
        adapter = vision.VisionBenchmarkAdapter("synthetic-key", client=client)
        try:
            with self.assertRaises(vision.VisionBenchmarkError) as caught:
                asyncio.run(adapter.analyze(MODELS[0], "test", [png_bytes()]))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(caught.exception.code, "provider_rate_limited")
        self.assertEqual(caught.exception.audit["error_code"], "provider_rate_limited")
        self.assertEqual(caught.exception.audit["http_status"], 429)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("secret-looking", str(caught.exception))

    def test_timeout_is_sanitized_and_single_request(self):
        calls = []

        async def handler(request):
            calls.append(request)
            await asyncio.sleep(0.08)
            return httpx.Response(200, json=completion())

        client = self.client(handler)
        adapter = vision.VisionBenchmarkAdapter("synthetic-key", client=client, timeout_seconds=0.02)
        try:
            with self.assertRaises(vision.VisionBenchmarkError) as caught:
                asyncio.run(adapter.analyze(MODELS[0], "test", [png_bytes()]))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(caught.exception.code, "provider_timeout")
        self.assertEqual(len(calls), 1)

    def test_invalid_json_and_bad_provider_response_are_sanitized(self):
        for body, expected in [
            (completion("not-json"), "provider_output_invalid_json"),
            ({"choices": []}, "provider_response_invalid"),
            (completion(usage={"prompt_tokens": 10, "completion_tokens": vision.MAX_OUTPUT_TOKENS + 1,
                               "total_tokens": vision.MAX_OUTPUT_TOKENS + 11}), "provider_output_exceeded"),
        ]:
            async def handler(request, body=body):
                return httpx.Response(200, json=body)

            client = self.client(handler)
            adapter = vision.VisionBenchmarkAdapter("synthetic-key", client=client)
            try:
                with self.assertRaises(vision.VisionBenchmarkError) as caught:
                    asyncio.run(adapter.analyze(MODELS[0], "test", [png_bytes()]))
            finally:
                asyncio.run(client.aclose())
            self.assertEqual(caught.exception.code, expected)

        async def malformed_json_handler(request):
            return httpx.Response(200, content=b"{not-json", headers={"content-type": "application/json"})

        client = self.client(malformed_json_handler)
        adapter = vision.VisionBenchmarkAdapter("synthetic-key", client=client)
        try:
            with self.assertRaises(vision.VisionBenchmarkError) as caught:
                asyncio.run(adapter.analyze(MODELS[0], "test", [png_bytes()]))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(caught.exception.code, "provider_response_invalid")

    def test_redirect_is_rejected_without_following(self):
        seen = []

        async def handler(request):
            seen.append(request)
            return httpx.Response(307, headers={"location": "https://attacker.invalid/collect"})

        client = self.client(handler)
        adapter = vision.VisionBenchmarkAdapter("synthetic-key", client=client)
        try:
            with self.assertRaises(vision.VisionBenchmarkError) as caught:
                asyncio.run(adapter.analyze(MODELS[0], "test", [png_bytes()]))
        finally:
            asyncio.run(client.aclose())
        self.assertEqual(caught.exception.code, "provider_redirect_rejected")
        self.assertEqual(len(seen), 1)
        self.assertEqual(str(seen[0].url), vision.ENDPOINT)


if __name__ == "__main__":
    unittest.main()
