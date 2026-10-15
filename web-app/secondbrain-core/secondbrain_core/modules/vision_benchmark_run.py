"""Private crash-safe ledger for one-shot SiliconFlow vision comparisons."""
from __future__ import annotations

import asyncio
import copy
import fcntl
import json
import os
import re
import stat
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .vision_benchmark import MODEL_POLICIES, VisionBenchmarkError


VISION_MODEL_ORDER = (
    "Qwen/Qwen3.5-35B-A3B",
    "deepseek-ai/DeepSeek-V4-Flash-Vision-Exp",
    "zai-org/GLM-5V-Turbo",
)
MAX_LEDGER_BYTES = 512_000
RUN_ID_PATTERN = re.compile(r"^[a-f0-9-]{36}$")
TRACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class VisionRunError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _private_dir(path: Path, *, create: bool) -> Path:
    if not path.is_absolute():
        raise VisionRunError("run_directory_must_be_absolute")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise VisionRunError("run_directory_permissions_invalid")
    return path


class PersistentVisionRun:
    """A model may be attempted once; ambiguous outcomes stay terminal unknown."""

    def __init__(self, directory: Path, run_id: str):
        self.directory = _private_dir(directory, create=False)
        self.run_id = run_id
        self.path = directory / f"{run_id}.json"
        self.lock_path = directory / f"{run_id}.lock"
        self.execution_lock_path = directory / f"{run_id}.execution.lock"

    @classmethod
    def create(cls, directory: str | Path) -> "PersistentVisionRun":
        directory = _private_dir(Path(directory), create=True)
        run_id = str(uuid.uuid4())
        instance = cls(directory, run_id)
        instance._write({"schema_version": 1, "run_id": run_id, "created_at": _now(),
                         "models": {model: {"state": "pending", "attempts": 0}
                                    for model in VISION_MODEL_ORDER}}, exclusive=True)
        return instance

    @classmethod
    def open(cls, directory: str | Path, run_id: str) -> "PersistentVisionRun":
        if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
            raise VisionRunError("run_id_invalid")
        instance = cls(Path(directory), run_id)
        with instance._execution_lock() as acquired:
            if acquired:
                with instance._locked():
                    doc = instance._read()
                    changed = False
                    for row in doc["models"].values():
                        if row["state"] == "started":
                            row.update({"state": "unknown", "error_code": "interrupted_after_started",
                                        "finished_at": _now()})
                            changed = True
                    if changed:
                        instance._write(doc)
        return instance

    @contextmanager
    def _locked(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise VisionRunError("lock_permissions_invalid")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @contextmanager
    def _execution_lock(self):
        fd = os.open(self.execution_lock_path,
                     os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        acquired = False
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise VisionRunError("execution_lock_permissions_invalid")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
            yield acquired
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self) -> dict[str, Any]:
        fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_LEDGER_BYTES):
                raise VisionRunError("ledger_permissions_invalid")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                doc = json.load(stream)
        finally:
            os.close(fd)
        valid_states = {"pending", "started", "completed", "failed", "unknown"}
        if (not isinstance(doc, dict) or doc.get("schema_version") != 1
                or doc.get("run_id") != self.run_id or not isinstance(doc.get("models"), dict)):
            raise VisionRunError("ledger_invalid")
        for model, row in doc["models"].items():
            if (model not in MODEL_POLICIES or not isinstance(row, dict)
                    or row.get("state") not in valid_states
                    or type(row.get("attempts")) is not int or row["attempts"] not in (0, 1)):
                raise VisionRunError("ledger_invalid")
        return doc

    def _write(self, doc: dict[str, Any], *, exclusive: bool = False) -> None:
        data = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        if len(data) > MAX_LEDGER_BYTES:
            raise VisionRunError("ledger_too_large")
        temp = self.directory / f".{self.run_id}.{uuid.uuid4().hex}.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive and self.path.exists():
                raise VisionRunError("run_id_collision")
            os.replace(temp, self.path)
            dir_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def status(self) -> dict[str, Any]:
        with self._locked():
            return copy.deepcopy(self._read())

    def _update_row(self, model: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        with self._locked():
            doc = self._read()
            row = doc["models"].get(model)
            if row is None:
                raise VisionRunError("model_not_in_run")
            mutate(row)
            self._write(doc)

    def claim(self, model: str, *, request_metadata: dict[str, Any]) -> bool:
        allowed_metadata = {"fixture_sha256", "prompt_sha256", "image_count", "max_output_tokens",
                            "json_mode", "image_detail"}
        clean_metadata = {k: v for k, v in request_metadata.items() if k in allowed_metadata}
        encoded = json.dumps(clean_metadata, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 4096:
            raise VisionRunError("request_metadata_invalid")
        result = False
        with self._locked():
            doc = self._read()
            row = doc["models"].get(model)
            if row is None:
                raise VisionRunError("model_not_in_run")
            if row["state"] == "pending" and row["attempts"] == 0:
                row.update({"state": "started", "attempts": 1, "started_at": _now(),
                            "request_metadata": clean_metadata})
                result = True
                self._write(doc)
        return result

    def save_result(self, model: str, result: dict[str, Any]) -> None:
        status = result.get("http_status")
        elapsed = result.get("elapsed_ms")
        trace = result.get("trace_id")
        usage = result.get("usage")
        content = result.get("content")
        parsed = result.get("parsed")
        if (type(status) is not int or not 100 <= status <= 599
                or not isinstance(elapsed, (int, float)) or elapsed < 0
                or not isinstance(trace, str) or not TRACE_PATTERN.fullmatch(trace)
                or not isinstance(usage, dict) or not isinstance(content, str)
                or len(content.encode("utf-8")) > 64_000):
            raise VisionRunError("result_invalid")
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if type(usage.get(key)) is not int or usage[key] < 0:
                raise VisionRunError("usage_invalid")
        details = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens",
                                         "reasoning_tokens") if k in usage}
        clean = {"http_status": status, "elapsed_ms": round(float(elapsed), 1),
                 "trace_id": trace, "model": str(result.get("model", ""))[:160],
                 "usage": details, "content": content, "parsed": parsed}
        if len(json.dumps(clean, ensure_ascii=False).encode("utf-8")) > 128_000:
            raise VisionRunError("result_too_large")

        def mutate(row):
            if row["state"] != "started":
                raise VisionRunError("model_not_started")
            row.update({"state": "completed", "finished_at": _now(), "result": clean})
        self._update_row(model, mutate)

    def save_error(self, model: str, error: VisionBenchmarkError) -> None:
        audit = error.audit
        terminal = "failed" if type(audit.get("http_status")) is int else "unknown"
        clean = {k: audit.get(k) for k in ("error_code", "http_status", "elapsed_ms")}
        trace = audit.get("trace_id")
        if isinstance(trace, str) and TRACE_PATTERN.fullmatch(trace):
            clean["trace_id"] = trace
        usage = audit.get("usage")
        if isinstance(usage, dict):
            allowed_usage = {k: v for k, v in usage.items()
                             if k in {"prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"}
                             and type(v) is int and v >= 0}
            if allowed_usage:
                clean["usage"] = allowed_usage

        def mutate(row):
            if row["state"] != "started":
                raise VisionRunError("model_not_started")
            row.update({"state": terminal, "finished_at": _now(), "error": clean})
        self._update_row(model, mutate)

    def may_run_in_order(self, model: str) -> bool:
        try:
            index = VISION_MODEL_ORDER.index(model)
        except ValueError as exc:
            raise VisionRunError("model_not_in_ordered_allowlist") from exc
        states = self.status()["models"]
        return all(states.get(prior, {}).get("state") == "completed"
                   for prior in VISION_MODEL_ORDER[:index])

    async def run_once(self, model: str, *, request_metadata: dict[str, Any],
                       invoke: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
        with self._execution_lock() as acquired:
            if not acquired:
                return {"state": "started", "active": True, "attempts": 1}
            if not self.claim(model, request_metadata=request_metadata):
                return self.status()["models"][model]
            started = time.monotonic()
            try:
                result = await invoke()
            except VisionBenchmarkError as exc:
                audit = dict(exc.audit)
                if audit.get("elapsed_ms") is None:
                    audit["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                exc.audit = audit
                self.save_error(model, exc)
                raise
            except asyncio.CancelledError:
                error = VisionBenchmarkError("execution_cancelled", model=model,
                    elapsed_ms=round((time.monotonic() - started) * 1000))
                self.save_error(model, error)
                raise
            except Exception:
                error = VisionBenchmarkError("execution_outcome_unknown", model=model,
                    elapsed_ms=round((time.monotonic() - started) * 1000))
                self.save_error(model, error)
                raise error from None
            self.save_result(model, result)
            return self.status()["models"][model]
