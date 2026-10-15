"""Restricted, opt-in SiliconFlow vision benchmark adapter.

This module is intentionally separate from the Organizer text adapter and is
not wired to production routes or scheduling. It accepts only local PNG/JPEG
bytes, sends one non-streaming Chat Completions request, and never retries.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from PIL import Image, UnidentifiedImageError


ENDPOINT = "https://api.siliconflow.cn/v1/chat/completions"
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_TOKENS = 2000
MAX_RESPONSE_BYTES = 128 * 1024
MAX_TIMEOUT_SECONDS = 45.0
MAX_IMAGE_WIDTH = 1600
MAX_IMAGE_HEIGHT = 1600
MAX_IMAGE_PIXELS = 2_560_000


@dataclass(frozen=True)
class ModelPolicy:
    json_mode_supported: bool
    # None means the public model-specific evidence does not justify sending it.
    enable_thinking: bool | None
    image_detail: str


# JSON Mode support follows the project’s previously checked official model
# catalog. Thinking parameters remain omitted until each model is verified.
MODEL_POLICIES: dict[str, ModelPolicy] = {
    "Qwen/Qwen3.5-35B-A3B": ModelPolicy(True, None, "low"),
    "deepseek-ai/DeepSeek-V4-Flash-Vision-Exp": ModelPolicy(True, None, "low"),
    "zai-org/GLM-5V-Turbo": ModelPolicy(False, None, "low"),
}


class VisionBenchmarkError(RuntimeError):
    """Sanitized failure carrying safe audit fields, never response/key data."""

    def __init__(self, code: str, *, model: str | None = None,
                 elapsed_ms: int | None = None, trace_id: str | None = None,
                 http_status: int | None = None, usage: dict[str, Any] | None = None,
                 finish_reason: str | None = None):
        self.code = code
        self.audit = {"ok": False, "model": model, "error_code": code,
                      "elapsed_ms": elapsed_ms, "trace_id": trace_id,
                      "http_status": http_status, "finish_reason": finish_reason}
        if isinstance(usage, dict):
            safe_usage = {key: value for key, value in usage.items()
                          if key in {"prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"}
                          and type(value) is int and value >= 0}
            if safe_usage:
                self.audit["usage"] = safe_usage
        super().__init__(code)


def _validate_image(raw: bytes) -> tuple[str, str]:
    if not isinstance(raw, bytes) or not raw:
        raise VisionBenchmarkError("image_empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise VisionBenchmarkError("image_too_large")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            fmt = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise VisionBenchmarkError("image_invalid") from exc
    if fmt not in {"PNG", "JPEG"}:
        raise VisionBenchmarkError("image_format_unsupported")
    if width < 1 or height < 1 or width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT or width * height > MAX_IMAGE_PIXELS:
        raise VisionBenchmarkError("image_dimensions_exceeded")
    return ("image/png", "png") if fmt == "PNG" else ("image/jpeg", "jpeg")


def build_request(model: str, prompt: str, images: Iterable[bytes], *,
                  max_output_tokens: int = MAX_OUTPUT_TOKENS,
                  json_mode: bool = False) -> dict[str, Any]:
    """Build the exact bounded request; no URL fetching or tool parameters."""
    policy = MODEL_POLICIES.get(model)
    if policy is None:
        raise VisionBenchmarkError("model_not_allowlisted", model=model)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 16_000:
        raise VisionBenchmarkError("prompt_invalid", model=model)
    if type(max_output_tokens) is not int or not 0 < max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise VisionBenchmarkError("output_budget_exceeded", model=model)
    if json_mode and not policy.json_mode_supported:
        raise VisionBenchmarkError("json_mode_unsupported", model=model)
    image_list = []
    for image in images:
        image_list.append(image)
        if len(image_list) > MAX_IMAGES:
            raise VisionBenchmarkError("image_count_exceeded", model=model)
    if not image_list:
        raise VisionBenchmarkError("image_count_exceeded", model=model)

    content: list[dict[str, Any]] = []
    for raw in image_list:
        mime, _ = _validate_image(raw)
        encoded = base64.b64encode(raw).decode("ascii")
        content.append({"type": "image_url", "image_url": {
            "url": f"data:{mime};base64,{encoded}", "detail": policy.image_detail}})
    content.append({"type": "text", "text": prompt})
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "max_tokens": max_output_tokens,
        "temperature": 0,
        "n": 1,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if policy.enable_thinking is not None:
        body["enable_thinking"] = policy.enable_thinking
    if len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
        raise VisionBenchmarkError("request_body_too_large", model=model)
    return body


class VisionBenchmarkAdapter:
    """No-tools, single-flight, no-retry image benchmark adapter."""

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None,
                 timeout_seconds: float = MAX_TIMEOUT_SECONDS):
        if not isinstance(api_key, str) or not api_key or api_key != api_key.strip() or "\n" in api_key or "\r" in api_key:
            raise ValueError("A valid API key is required")
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError("Adapter timeout exceeds the benchmark limit")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(timeout_seconds))
        self._owns_client = client is None
        self._semaphore = asyncio.Semaphore(1)

    def __repr__(self) -> str:
        return "VisionBenchmarkAdapter(api_key=<redacted>)"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def analyze(self, model: str, prompt: str, images: Iterable[bytes], *,
                      max_output_tokens: int = MAX_OUTPUT_TOKENS,
                      json_mode: bool = False) -> dict[str, Any]:
        body = build_request(model, prompt, images, max_output_tokens=max_output_tokens, json_mode=json_mode)
        trace_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            async with self._semaphore:
                response = await asyncio.wait_for(self._client.post(
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json",
                             "X-Trace-Id": trace_id},
                    json=body,
                    timeout=httpx.Timeout(self.timeout_seconds),
                    follow_redirects=False,
                ), timeout=self.timeout_seconds)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            raise VisionBenchmarkError("provider_timeout", model=model,
                                       elapsed_ms=round((time.monotonic() - started) * 1000), trace_id=trace_id) from None
        except httpx.HTTPError:
            raise VisionBenchmarkError("provider_transport_error", model=model,
                                       elapsed_ms=round((time.monotonic() - started) * 1000), trace_id=trace_id) from None

        elapsed_ms = round((time.monotonic() - started) * 1000)
        response_trace = response.headers.get("x-siliconcloud-trace-id") or trace_id
        if response.history or str(response.url) != ENDPOINT:
            raise VisionBenchmarkError("provider_redirect_rejected", model=model, elapsed_ms=elapsed_ms,
                                       trace_id=response_trace, http_status=response.status_code)
        if 300 <= response.status_code < 400:
            raise VisionBenchmarkError("provider_redirect_rejected", model=model, elapsed_ms=elapsed_ms,
                                       trace_id=response_trace, http_status=response.status_code)
        if response.status_code == 429:
            raise VisionBenchmarkError("provider_rate_limited", model=model, elapsed_ms=elapsed_ms,
                                       trace_id=response_trace, http_status=response.status_code)
        if response.status_code >= 400:
            raise VisionBenchmarkError("provider_http_error", model=model, elapsed_ms=elapsed_ms,
                                       trace_id=response_trace, http_status=response.status_code)
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise VisionBenchmarkError("provider_response_too_large", model=model, elapsed_ms=elapsed_ms,
                                       trace_id=response_trace, http_status=response.status_code)
        try:
            data = response.json()
            returned_model = data["model"]
            message = data["choices"][0]["message"]
            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason")
            usage = data["usage"]
            raw_content = message["content"]
            if not isinstance(usage, dict):
                raise ValueError("usage")
            safe_usage = {key: value for key, value in usage.items()
                          if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                          and type(value) is int and value >= 0}
            if len(safe_usage) != 3:
                raise ValueError("usage")
            details = usage.get("completion_tokens_details")
            reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
            if reasoning_tokens is not None:
                if type(reasoning_tokens) is not int or reasoning_tokens < 0:
                    raise ValueError("reasoning_usage")
                safe_usage["reasoning_tokens"] = reasoning_tokens
            if message.get("tool_calls") or choice.get("finish_reason") == "tool_calls":
                raise VisionBenchmarkError("provider_returned_tool_call", model=model,
                                           elapsed_ms=elapsed_ms, trace_id=response_trace,
                                           http_status=response.status_code, usage=safe_usage,
                                           finish_reason=finish_reason)
            if finish_reason == "length":
                raise VisionBenchmarkError("provider_output_truncated", model=model,
                                           elapsed_ms=elapsed_ms, trace_id=response_trace,
                                           http_status=response.status_code, usage=safe_usage,
                                           finish_reason=finish_reason)
            if not isinstance(raw_content, str) or len(raw_content.encode("utf-8")) > max_output_tokens * 32:
                raise VisionBenchmarkError("provider_output_exceeded", model=model,
                                           elapsed_ms=elapsed_ms, trace_id=response_trace,
                                           http_status=response.status_code, usage=safe_usage,
                                           finish_reason=finish_reason)
            parsed = json.loads(raw_content)
            if not isinstance(parsed, (dict, list)):
                raise ValueError("json_shape")
        except VisionBenchmarkError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
            code = "provider_output_invalid_json" if "raw_content" in locals() else "provider_response_invalid"
            raise VisionBenchmarkError(code, model=model, elapsed_ms=elapsed_ms,
                                       trace_id=response_trace,
                                       http_status=response.status_code,
                                       usage=safe_usage if "safe_usage" in locals() else None,
                                       finish_reason=finish_reason if "finish_reason" in locals() else None) from None
        return {"content": raw_content, "parsed": parsed, "model": returned_model,
                "requested_model": model,
                "usage": safe_usage, "elapsed_ms": elapsed_ms, "trace_id": response_trace,
                "http_status": response.status_code, "finish_reason": finish_reason,
                "ok": True, "error_code": None}
