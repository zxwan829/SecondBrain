"""Crash-safe local ledger for explicitly authorized, one-shot model evaluations.

The ledger never retries a model. A durable ``started`` state is ambiguous after
process loss and is converted to ``unknown`` on reopen, before any caller can
attempt another request.
"""
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


ALLOWED_MODEL_IDS = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "zai-org/GLM-4.5-Air",
    "Qwen/Qwen3.5-35B-A3B",
)
RUN_ID_RE = re.compile(r"^[a-f0-9-]{36}$")
SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
MAX_LEDGER_BYTES = 256_000


class BenchmarkRunError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_run_dir(path: Path, *, create: bool) -> Path:
    if not path.is_absolute():
        raise BenchmarkRunError("run_directory_must_be_absolute")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise BenchmarkRunError("run_directory_permissions_invalid")
    return path


def _sanitize_model_result(value: dict[str, Any]) -> dict[str, Any]:
    """Persist only known, non-secret response fields; never headers/request data."""
    usage = value.get("usage")
    drafts = value.get("drafts")
    if not isinstance(usage, dict) or not isinstance(drafts, list):
        raise BenchmarkRunError("model_result_shape_invalid")
    clean_usage: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
        if key not in usage:
            continue
        item = usage[key]
        if type(item) is not int or item < 0:
            raise BenchmarkRunError("model_usage_invalid")
        clean_usage[key] = item
    if not {"prompt_tokens", "completion_tokens", "total_tokens"}.issubset(clean_usage):
        raise BenchmarkRunError("model_usage_invalid")
    model = usage.get("model")
    if isinstance(model, str):
        clean_usage["model"] = model[:160]
    status = value.get("http_status")
    elapsed = value.get("elapsed_ms")
    trace = value.get("trace_id")
    if type(status) is not int or not 100 <= status <= 599:
        raise BenchmarkRunError("model_status_invalid")
    if not isinstance(elapsed, (int, float)) or elapsed < 0:
        raise BenchmarkRunError("model_elapsed_invalid")
    if not isinstance(trace, str) or len(trace) > 160 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", trace):
        raise BenchmarkRunError("model_trace_invalid")
    clean_drafts = copy.deepcopy(drafts)
    encoded = json.dumps(clean_drafts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 64_000:
        raise BenchmarkRunError("model_result_too_large")
    return {"http_status": status, "elapsed_ms": round(float(elapsed), 1),
            "trace_id": trace, "usage": clean_usage, "drafts": clean_drafts}


class PersistentBenchmarkRun:
    """One-run, per-model exactly-once-attempt state stored outside production data."""

    def __init__(self, directory: Path, run_id: str):
        if not RUN_ID_RE.fullmatch(run_id):
            raise BenchmarkRunError("run_id_invalid")
        self.directory = _safe_run_dir(directory, create=False)
        self.run_id = run_id
        self.path = self.directory / f"{run_id}.json"
        self.lock_path = self.directory / f"{run_id}.lock"
        self.execution_lock_path = self.directory / f"{run_id}.execution.lock"

    @classmethod
    def create(cls, directory: str | Path, model_ids=ALLOWED_MODEL_IDS) -> "PersistentBenchmarkRun":
        directory = _safe_run_dir(Path(directory), create=True)
        models = tuple(model_ids)
        if not models or len(set(models)) != len(models) or any(model not in ALLOWED_MODEL_IDS for model in models):
            raise BenchmarkRunError("model_allowlist_invalid")
        run_id = str(uuid.uuid4())
        instance = cls(directory, run_id)
        doc = {"schema_version": 1, "run_id": run_id, "created_at": _utc_now(),
               "models": {model: {"state": "pending", "attempts": 0} for model in models}}
        with instance._locked():
            if instance.path.exists():
                raise BenchmarkRunError("run_id_collision")
            instance._write_unlocked(doc, exclusive=True)
        return instance

    @classmethod
    def open(cls, directory: str | Path, run_id: str) -> "PersistentBenchmarkRun":
        instance = cls(Path(directory), run_id)
        with instance._execution_lock() as acquired:
            if acquired:
                with instance._locked():
                    doc = instance._read_unlocked()
                    changed = False
                    for row in doc["models"].values():
                        if row.get("state") == "started":
                            row.update({"state": "unknown", "finished_at": _utc_now(),
                                        "error_code": "interrupted_after_started_state"})
                            changed = True
                    if changed:
                        instance._write_unlocked(doc)
        return instance

    @contextmanager
    def _locked(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise BenchmarkRunError("run_lock_permissions_invalid")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
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
                raise BenchmarkRunError("execution_lock_permissions_invalid")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                acquired = False
            yield acquired
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_unlocked(self) -> dict[str, Any]:
        fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > MAX_LEDGER_BYTES):
                raise BenchmarkRunError("run_file_permissions_invalid")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                doc = json.load(stream)
        finally:
            os.close(fd)
        if (not isinstance(doc, dict) or doc.get("schema_version") != 1
                or doc.get("run_id") != self.run_id or not isinstance(doc.get("models"), dict)):
            raise BenchmarkRunError("run_file_invalid")
        for model_id, row in doc["models"].items():
            if (model_id not in ALLOWED_MODEL_IDS or not isinstance(row, dict)
                    or row.get("state") not in {"pending", "started", "completed", "unknown",
                                                "billed_result_unavailable"}
                    or type(row.get("attempts")) is not int or row["attempts"] not in (0, 1)):
                raise BenchmarkRunError("run_file_invalid")
        return doc

    def _write_unlocked(self, doc: dict[str, Any], *, exclusive: bool = False) -> None:
        data = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        if len(data) > MAX_LEDGER_BYTES:
            raise BenchmarkRunError("run_file_too_large")
        temp = self.directory / f".{self.run_id}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive and self.path.exists():
                raise BenchmarkRunError("run_id_collision")
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
            return copy.deepcopy(self._read_unlocked())

    def claim(self, model_id: str) -> bool:
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None:
                raise BenchmarkRunError("model_not_in_run")
            if row.get("state") != "pending" or row.get("attempts") != 0:
                return False
            row.update({"state": "started", "attempts": 1, "started_at": _utc_now()})
            self._write_unlocked(doc)
            return True

    def complete(self, model_id: str, result: dict[str, Any]) -> None:
        clean = _sanitize_model_result(result)
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "started":
                raise BenchmarkRunError("model_not_started")
            row.update({"state": "completed", "finished_at": _utc_now(), "result": clean})
            self._write_unlocked(doc)

    def import_completed(self, model_id: str, result: dict[str, Any], *, source: str) -> None:
        """Reconcile a prior, already observed response without sending a request."""
        if not isinstance(source, str) or not source or len(source) > 120:
            raise BenchmarkRunError("import_source_invalid")
        clean = _sanitize_model_result(result)
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "pending" or row.get("attempts") != 0:
                raise BenchmarkRunError("model_not_pending_for_import")
            row.update({"state": "completed", "attempts": 1, "origin": "reconciled_prior_request",
                        "source": source, "finished_at": _utc_now(), "result": clean})
            self._write_unlocked(doc)

    def import_unknown(self, model_id: str, error_code: str, *, source: str,
                       request_dispatched: bool) -> None:
        """Reserve a past attempt whose outcome cannot be recovered; never retry it."""
        code = error_code if SAFE_CODE_RE.fullmatch(error_code or "") else "prior_result_unknown"
        if not isinstance(source, str) or not source or len(source) > 120 or type(request_dispatched) is not bool:
            raise BenchmarkRunError("import_source_invalid")
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "pending" or row.get("attempts") != 0:
                raise BenchmarkRunError("model_not_pending_for_import")
            row.update({"state": "unknown", "attempts": 1, "origin": "reconciled_prior_request",
                        "source": source, "request_dispatched": request_dispatched,
                        "finished_at": _utc_now(), "error_code": code})
            self._write_unlocked(doc)

    def adjudicate_billed_result_unavailable(self, model_id: str, *, source: str,
                                             input_tokens: int, output_tokens: int,
                                             billed_amount_cny: float,
                                             payable_after_voucher_cny: float,
                                             reason: str) -> None:
        """Record user-authorized billing evidence while keeping response unavailable.

        This is a terminal, non-retryable disposition. It stores no fabricated HTTP
        status, trace ID, model output, or quality score.
        """
        if (not isinstance(source, str) or not source or len(source) > 160
                or not isinstance(reason, str) or not reason or len(reason) > 300
                or type(input_tokens) is not int or input_tokens < 0
                or type(output_tokens) is not int or output_tokens < 0
                or not isinstance(billed_amount_cny, (int, float)) or billed_amount_cny < 0
                or not isinstance(payable_after_voucher_cny, (int, float))
                or payable_after_voucher_cny < 0):
            raise BenchmarkRunError("billing_exception_invalid")
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "unknown" or row.get("attempts") != 1:
                raise BenchmarkRunError("model_not_unknown_for_billing_exception")
            row.update({
                "state": "billed_result_unavailable",
                "finished_at": _utc_now(),
                "billing_evidence": {
                    "source": source,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "billed_amount_cny": round(float(billed_amount_cny), 6),
                    "payable_after_voucher_cny": round(float(payable_after_voucher_cny), 6),
                    "response_usage_recovered": False,
                    "http_status_recovered": False,
                    "trace_id_recovered": False,
                },
                "manual_exception": {
                    "authorized_by": "user",
                    "reason": reason,
                    "recorded_at": _utc_now(),
                    "permits_next_model_only": True,
                    "permits_retry": False,
                },
            })
            self._write_unlocked(doc)

    def may_run_in_order(self, model_id: str) -> bool:
        """Allow only completed predecessors or audited billed-unavailable skips."""
        try:
            index = ALLOWED_MODEL_IDS.index(model_id)
        except ValueError as exc:
            raise BenchmarkRunError("model_not_in_ordered_allowlist") from exc
        states = self.status()["models"]
        for prior_id in ALLOWED_MODEL_IDS[:index]:
            row = states.get(prior_id, {})
            if row.get("state") == "completed":
                continue
            if (row.get("state") == "billed_result_unavailable"
                    and row.get("attempts") == 1
                    and row.get("manual_exception", {}).get("permits_next_model_only") is True
                    and row.get("manual_exception", {}).get("permits_retry") is False
                    and "billing_evidence" in row):
                continue
            return False
        return True

    def complete_error(self, model_id: str, error_code: str, *, status_code: int,
                       elapsed_ms: float, trace_id: str | None = None) -> None:
        code = error_code if SAFE_CODE_RE.fullmatch(error_code or "") else "provider_http_error"
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "started":
                raise BenchmarkRunError("model_not_started")
            result = {"http_status": status_code, "elapsed_ms": round(max(0.0, float(elapsed_ms)), 1),
                      "error_code": code}
            if trace_id and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", trace_id):
                result["trace_id"] = trace_id
            row.update({"state": "completed", "finished_at": _utc_now(), "result": result})
            self._write_unlocked(doc)

    def annotate(self, model_id: str, *, evaluation: dict[str, Any],
                 estimated_cost: dict[str, Any]) -> None:
        """Attach a human score and a sourced estimate after a completed response."""
        if not isinstance(evaluation, dict) or not isinstance(estimated_cost, dict):
            raise BenchmarkRunError("annotation_invalid")
        cost = {"currency": estimated_cost.get("currency"), "amount": estimated_cost.get("amount"),
                "basis": estimated_cost.get("basis"), "priced_at": estimated_cost.get("priced_at")}
        if (cost["currency"] != "CNY" or not isinstance(cost["amount"], (int, float))
                or cost["amount"] < 0 or not isinstance(cost["basis"], str)
                or len(cost["basis"]) > 300 or not isinstance(cost["priced_at"], str)
                or len(cost["priced_at"]) > 80):
            raise BenchmarkRunError("cost_estimate_invalid")
        try:
            clean_evaluation = json.loads(json.dumps(evaluation, ensure_ascii=False, allow_nan=False))
            encoded = json.dumps(clean_evaluation, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise BenchmarkRunError("evaluation_invalid") from exc
        if len(encoded) > 16_000:
            raise BenchmarkRunError("evaluation_too_large")
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "completed" or "result" not in row:
                raise BenchmarkRunError("model_result_not_completed")
            row["evaluation"] = clean_evaluation
            row["estimated_cost"] = cost
            self._write_unlocked(doc)

    def mark_unknown(self, model_id: str, error_code: str, *, status_code: int | None = None,
                     trace_id: str | None = None, elapsed_ms: float | None = None) -> None:
        code = error_code if SAFE_CODE_RE.fullmatch(error_code or "") else "request_outcome_unknown"
        with self._locked():
            doc = self._read_unlocked()
            row = doc["models"].get(model_id)
            if row is None or row.get("state") != "started":
                raise BenchmarkRunError("model_not_started")
            row.update({"state": "unknown", "finished_at": _utc_now(), "error_code": code})
            if status_code is not None and type(status_code) is int and 100 <= status_code <= 599:
                row["http_status"] = status_code
            if trace_id and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", trace_id):
                row["trace_id"] = trace_id
            if isinstance(elapsed_ms, (int, float)) and elapsed_ms >= 0:
                row["elapsed_ms"] = round(float(elapsed_ms), 1)
            self._write_unlocked(doc)

    async def run_once(self, model_id: str,
                       invoke: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
        """Persist started before invocation; ambiguous failures become unknown; never retry."""
        with self._execution_lock() as acquired:
            if not acquired:
                return {"state": "started", "active": True, "attempts": 1}
            if not self.claim(model_id):
                return self.status()["models"][model_id]
            started = time.monotonic()
            try:
                result = await invoke()
            except asyncio.CancelledError:
                self.mark_unknown(model_id, "execution_cancelled",
                                  elapsed_ms=(time.monotonic() - started) * 1000)
                raise
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                trace_id = getattr(exc, "trace_id", None)
                error_code = getattr(exc, "code", "request_outcome_unknown")
                # A known HTTP response is a completed attempt, even if it is an error.
                if type(status_code) is int:
                    self.complete_error(model_id, error_code, status_code=status_code,
                                        elapsed_ms=(time.monotonic() - started) * 1000,
                                        trace_id=trace_id)
                else:
                    self.mark_unknown(model_id, error_code, trace_id=trace_id,
                                      elapsed_ms=(time.monotonic() - started) * 1000)
                raise
            self.complete(model_id, result)
            return self.status()["models"][model_id]
