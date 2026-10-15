"""Bounded, tool-free SiliconFlow Chat Completions adapter for Organizer.

This adapter is deliberately not wired into the production app. SiliconFlow's
public API accepts an output-token ceiling and returns usage, but the current
provider documentation does not establish a per-key, per-job hard spend cap or
a server-enforced input-token ceiling. Its capabilities therefore fail the
Organizer's activation gate until those limits are independently attested.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


ENDPOINT = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_DEFAULT = "deepseek-ai/DeepSeek-V4-Flash"
MAX_RESPONSE_BYTES = 128_000
MAX_PROMPT_BYTES = 4_500
MAX_OUTPUT_TOKENS = 1_200
TIMEOUT_SECONDS = 45


class OrganizerAdapterError(RuntimeError):
    """Sanitized adapter failure; provider response bodies are never included."""

    def __init__(self, code: str, *, status_code: int | None = None, trace_id: str | None = None):
        self.code = code
        self.status_code = status_code
        self.trace_id = trace_id
        super().__init__(code)


def read_private_secret(path: str | Path) -> str:
    """Read only a dedicated, private credential file; never follow symlinks."""
    secret_path = Path(path)
    if not secret_path.is_absolute():
        raise RuntimeError("Organizer API key file must be an absolute regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(secret_path, flags)
    except OSError as exc:
        raise RuntimeError("Organizer API key file must be a private regular file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError("Organizer API key file must be private and owned by the Core UID")
        if info.st_size > 4096:
            raise RuntimeError("Organizer API key file exceeds the allowed size")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            secret = stream.read(4097)
    finally:
        os.close(fd)
    if secret.endswith("\n"):
        secret = secret[:-1]
        if secret.endswith("\r"):
            secret = secret[:-1]
    if len(secret.encode("utf-8")) > 4096:
        raise RuntimeError("Organizer API key file exceeds the allowed size")
    if not secret or "\n" in secret or "\r" in secret:
        raise RuntimeError("Organizer API key file is empty or malformed")
    if secret != secret.strip():
        raise RuntimeError("Organizer API key file contains surrounding whitespace")
    return secret


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _truncate_utf8(value: str, max_bytes: int) -> str:
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    suffix = "…[已截断]"
    allowance = max(0, max_bytes - len(suffix.encode("utf-8")))
    prefix = data[:allowance].decode("utf-8", errors="ignore")
    return prefix + (suffix if max_bytes >= len(suffix.encode("utf-8")) else "")


def _bounded_messages(payload: dict[str, Any], max_input_tokens: int) -> list[dict[str, str]]:
    """Conservatively cap prompt bytes; exact tokenization is provider/model-specific."""
    model_payload = {
        "task": payload.get("task", ""),
        "new_user_messages": copy.deepcopy(payload.get("new_user_messages", [])),
        "context_only": copy.deepcopy(payload.get("context_only", {})),
        "output_schema": copy.deepcopy(payload.get("output_schema", {})),
    }
    # Leave a substantial allowance for chat framing and system instructions.
    if max_input_tokens <= 512:
        raise OrganizerAdapterError("input_budget_exceeded")
    budget = min(MAX_PROMPT_BYTES, max_input_tokens - 512)
    while len(_json_bytes(model_payload)) > budget:
        contexts = model_payload.get("context_only", {})
        context_rows = next((rows for rows in contexts.values() if rows), None) if isinstance(contexts, dict) else None
        if context_rows:
            context_rows.pop(0)
            continue
        messages = model_payload.get("new_user_messages", [])
        target = max((len(row.get("text", "")) for row in messages if isinstance(row, dict)), default=0)
        if not target:
            raise OrganizerAdapterError("input_budget_exceeded")
        # Deterministic geometric truncation, preserving each source ID/timestamp.
        for row in messages:
            if isinstance(row, dict) and len(row.get("text", "")) == target:
                row["text"] = _truncate_utf8(row["text"], max(0, len(row["text"].encode("utf-8")) // 2))
        if all(not row.get("text") for row in messages if isinstance(row, dict)) and len(_json_bytes(model_payload)) > budget:
            raise OrganizerAdapterError("input_budget_exceeded")
    content = _json_bytes(model_payload).decode("utf-8")
    return [
        {"role": "system", "content": "你是 SecondBrain 整理器。只提炼用户明确表达的事实；不得把助手建议写成用户事实。仅返回符合给定 schema 的 JSON。"},
        {"role": "user", "content": content},
    ]


class SiliconFlowOrganizerModel:
    """Single-request OpenAI-compatible text adapter; never sends tools or streams."""

    capabilities = {
        "no_tools": True,
        "hard_input_token_limit": False,  # byte-bounded locally; tokenizer limit is not provider-attested
        "hard_output_token_limit": False,  # provider max_tokens excludes reasoning tokens
        "hard_timeout": True,
        "single_concurrency": True,
        "single_request_per_job": True,
        "hard_cost_budget": False,  # fail closed: account monthly limit is not a proven per-job cap
        "max_input_tokens": 6_000,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_calls_per_job": 1,
        "max_cost_usd": None,
    }

    @classmethod
    def from_secret_file(cls, secret_path: str | Path, **kwargs):
        """Construct inside Core from a dedicated private secret mount."""
        return cls(read_private_secret(secret_path), **kwargs)

    def __init__(self, api_key: str, *, model: str = MODEL_DEFAULT,
                 client: httpx.AsyncClient | None = None, timeout_seconds: float = TIMEOUT_SECONDS):
        if (not isinstance(api_key, str) or not api_key or api_key != api_key.strip()
                or "\n" in api_key or "\r" in api_key):
            raise ValueError("A valid API key is required")
        if not isinstance(model, str) or not model.strip() or len(model) > 160:
            raise ValueError("A valid model identifier is required")
        if not 0 < timeout_seconds <= TIMEOUT_SECONDS:
            raise ValueError("Adapter timeout exceeds the Core limit")
        self._api_key = api_key
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(timeout_seconds))
        self._owns_client = client is None
        self._semaphore = asyncio.Semaphore(1)

    def __repr__(self) -> str:
        return f"SiliconFlowOrganizerModel(model={self.model!r}, api_key=<redacted>)"

    async def aclose(self):
        if self._owns_client:
            await self._client.aclose()

    async def extract(self, payload: dict[str, Any], *, max_input_tokens: int,
                      max_output_tokens: int) -> dict[str, Any]:
        if not 0 < max_input_tokens <= self.capabilities["max_input_tokens"]:
            raise OrganizerAdapterError("input_budget_exceeded")
        if not 0 < max_output_tokens <= MAX_OUTPUT_TOKENS:
            raise OrganizerAdapterError("output_budget_exceeded")
        request_body = {
            "model": self.model,
            "messages": _bounded_messages(payload, max_input_tokens),
            "stream": False,
            "max_tokens": max_output_tokens,
            "temperature": 0,
            "n": 1,
        }
        request_trace_id = uuid.uuid4().hex
        async with self._semaphore:
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self._client.post(
                        ENDPOINT,
                        headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json",
                                 "X-Trace-Id": request_trace_id},
                        json=request_body,
                    ),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise OrganizerAdapterError("provider_timeout", trace_id=request_trace_id) from exc
            except httpx.HTTPError as exc:
                raise OrganizerAdapterError("provider_transport_error", trace_id=request_trace_id) from exc
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        trace_id = response.headers.get("x-siliconcloud-trace-id", request_trace_id)
        if response.history or str(response.url) != ENDPOINT:
            raise OrganizerAdapterError("provider_redirect_rejected", status_code=response.status_code,
                                        trace_id=trace_id)
        if response.status_code == 429:
            raise OrganizerAdapterError("provider_rate_limited", status_code=429, trace_id=trace_id)
        if response.status_code >= 400:
            raise OrganizerAdapterError("provider_http_error", status_code=response.status_code,
                                        trace_id=trace_id)
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise OrganizerAdapterError("provider_response_too_large", status_code=response.status_code,
                                        trace_id=trace_id)
        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            if message.get("tool_calls") or choice.get("finish_reason") == "tool_calls":
                raise OrganizerAdapterError("provider_returned_tool_call", status_code=response.status_code,
                                            trace_id=trace_id)
            if choice.get("finish_reason") == "length":
                raise OrganizerAdapterError("provider_output_truncated", status_code=response.status_code,
                                            trace_id=trace_id)
            raw_content = message["content"]
            usage = body["usage"]
            completion_tokens = usage["completion_tokens"]
            if type(completion_tokens) is not int or completion_tokens < 0:
                raise OrganizerAdapterError("provider_usage_invalid", status_code=response.status_code,
                                            trace_id=trace_id)
            if not isinstance(raw_content, str) or len(raw_content.encode("utf-8")) > max_output_tokens * 32:
                raise OrganizerAdapterError("provider_output_exceeded", status_code=response.status_code,
                                            trace_id=trace_id)
            result = json.loads(raw_content)
            if not isinstance(result, dict) or set(result) != {"drafts"} or not isinstance(result["drafts"], list):
                raise OrganizerAdapterError("provider_output_schema_invalid", status_code=response.status_code,
                                            trace_id=trace_id)
            clean_usage = {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if type(value) is not int or value < 0:
                    raise OrganizerAdapterError("provider_usage_invalid", status_code=response.status_code,
                                                trace_id=trace_id)
                clean_usage[key] = value
            details = usage.get("completion_tokens_details")
            reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
            if reasoning_tokens is not None:
                if type(reasoning_tokens) is not int or reasoning_tokens < 0:
                    raise OrganizerAdapterError("provider_usage_invalid", status_code=response.status_code,
                                                trace_id=trace_id)
                clean_usage["reasoning_tokens"] = reasoning_tokens
            clean_usage["model"] = str(body.get("model", self.model))[:160]
            return {"drafts": result["drafts"], "usage": clean_usage,
                    "http_status": response.status_code, "elapsed_ms": elapsed_ms,
                    "trace_id": trace_id}
        except OrganizerAdapterError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OrganizerAdapterError("provider_response_invalid", status_code=response.status_code,
                                        trace_id=trace_id) from exc
