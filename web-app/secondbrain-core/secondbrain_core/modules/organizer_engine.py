"""Fail-closed, file-backed organizer pipeline.

The production model adapter is intentionally absent until Hermes can prove a
tool-free, hard-budgeted inference path. The engine is injectable so its durable
state, replay rules, and Review writes can be exercised with synthetic fixtures.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from fastapi import HTTPException

from .auto_organize import DEFAULT_SETTINGS, OrganizeSettingsStore, next_scheduled_at


MAX_INPUT_MESSAGES = 40
MAX_INPUT_CHARS = 24_000
MAX_OUTPUT_TOKENS = 1_200
MAX_INPUT_TOKENS = 6_000
MAX_CONTEXT_CHARS = 4_000
MODEL_TIMEOUT_SECONDS = 45
MAX_MODEL_CALLS_PER_JOB = 1
MAX_SESSION_SCAN_ROWS = 2_000
MAX_CANDIDATES = 12
MAX_SCHEDULER_BACKOFF_SECONDS = 21_600
CATEGORIES = {"journal", "work_idea", "todo", "knowledge_candidate"}
SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class MessageSource(Protocol):
    async def get_session(self, session_id: str) -> dict[str, Any]: ...
    async def list_messages(self, session_id: str, limit: int = 500, offset: int = 0,
                            order: str = "oldest") -> dict[str, Any]: ...


class OrganizerModel(Protocol):
    """Adapters must attest enforceable limits; prompt instructions alone do not count."""
    capabilities: dict[str, Any]

    async def extract(self, payload: dict[str, Any], *, max_input_tokens: int,
                      max_output_tokens: int) -> dict[str, Any]: ...


class OrganizerState:
    def __init__(self, root: str | Path):
        self.root = Path(root) / "ai-organize"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise RuntimeError("Organizer state root must be a real directory")
        info = self.root.stat(follow_symlinks=False)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError("Organizer state root must be private and owned by the App UID")
        self.path = self.root / "state.json"
        self.lock_path = self.root / "state.lock"
        self._thread_lock = threading.RLock()

    @staticmethod
    def empty() -> dict[str, Any]:
        return {"version": 1, "sessions": {}, "jobs": {}, "processed_messages": {},
                "active_job_id": None, "next_run_at": None, "last_run_at": None,
                "last_draft_count": None, "last_error": None}

    def read(self) -> dict[str, Any]:
        with self._thread_lock:
            if not self.path.exists():
                return self.empty()
            if self.path.is_symlink() or not self.path.is_file():
                raise RuntimeError("Organizer state must be a regular file")
            info = self.path.stat(follow_symlinks=False)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise RuntimeError("Organizer state file must be private and owned by the App UID")
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") != 1:
                raise RuntimeError("Unsupported organizer state version")
            return value

    def update(self, mutate):
        with self._thread_lock:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                os.fchmod(fd, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                state = self.read()
                result = mutate(state)
                payload = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                tmp_fd, tmp_path = tempfile.mkstemp(prefix=".state-", dir=self.root)
                try:
                    os.fchmod(tmp_fd, 0o600)
                    with os.fdopen(tmp_fd, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(tmp_path, self.path)
                    dir_fd = os.open(self.root, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except FileNotFoundError:
                        pass
                return result
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def register_session(self, session_id: str, *, baseline_count: int = 0,
                         last_message_id: str | None = None) -> bool:
        if not isinstance(session_id, str) or not SAFE_SESSION_ID.fullmatch(session_id):
            raise ValueError("Invalid Hermes session identifier")
        if type(baseline_count) is not int or baseline_count < 0:
            raise ValueError("Invalid session baseline")

        def mutate(state):
            if session_id in state["sessions"]:
                return False
            state["sessions"][session_id] = {
                "registered_at": iso(), "cursor_count": baseline_count,
                "cursor_message_id": last_message_id, "source_status": "active",
            }
            return True
        return self.update(mutate)

    def mark_session_deleted(self, session_id: str):
        def mutate(state):
            row = state["sessions"].get(session_id)
            if row:
                row["source_status"] = "deleted_or_unavailable"
                row["updated_at"] = iso()
        self.update(mutate)


def _valid_model(model: OrganizerModel | None) -> tuple[bool, str]:
    if model is None:
        return False, "尚无已验证的无工具模型适配器；自动整理仅保存设置，尚未运行。"
    caps = getattr(model, "capabilities", {})
    requirements = {
        "no_tools": True, "hard_input_token_limit": True,
        "hard_output_token_limit": True, "hard_timeout": True,
        "single_concurrency": True, "single_request_per_job": True,
        "hard_cost_budget": True,
    }
    for key, expected in requirements.items():
        if caps.get(key) is not expected:
            return False, f"模型适配器未证明安全能力：{key}。"
    input_limit = caps.get("max_input_tokens")
    output_limit = caps.get("max_output_tokens")
    timeout = caps.get("timeout_seconds")
    calls = caps.get("max_calls_per_job")
    if type(input_limit) is not int or not 0 < input_limit <= MAX_INPUT_TOKENS:
        return False, "模型适配器输入 Token 上限无效或超过 Core 限额。"
    if type(output_limit) is not int or not 0 < output_limit <= MAX_OUTPUT_TOKENS:
        return False, "模型适配器输出 Token 上限无效或超过 Core 限额。"
    if type(timeout) not in {int, float} or not 0 < timeout <= MODEL_TIMEOUT_SECONDS:
        return False, "模型适配器请求超时上限无效或超过 Core 限额。"
    if calls != MAX_MODEL_CALLS_PER_JOB:
        return False, "模型适配器单作业请求次数必须严格等于 Core 限额。"
    max_cost = caps.get("max_cost_usd")
    if type(max_cost) not in {int, float} or max_cost != 0:
        return False, "未批准付费模型预算；当前只允许零成本模型适配器。"
    return True, ""


class OrganizerRunner:
    def __init__(self, state_root: str | Path, review_root: str | Path,
                 source: MessageSource, model: OrganizerModel | None = None):
        self.state = OrganizerState(state_root)
        self.settings = OrganizeSettingsStore(Path(state_root) / "ai-organize")
        self.review_root = Path(review_root)
        self.source = source
        self.model = model
        self.lock_path = self.state.root / "run.lock"
        self._scheduler_task: asyncio.Task | None = None

    async def baseline_session(self, session_id: str, metadata: dict[str, Any] | None = None):
        """Admit an App-visible session; skip its old history and retain a stable tail anchor."""
        if session_id in self.state.read()["sessions"]:
            return
        session = metadata or {}
        if type(session.get("message_count")) is not int:
            session = await self.source.get_session(session_id)
        count = session.get("message_count", 0)
        if type(count) is not int or count < 0:
            raise RuntimeError("Hermes session has no verifiable message count")
        last_id = None
        if count:
            page = await self.source.list_messages(session_id, limit=1, offset=0, order="latest")
            rows = page.get("messages", [])
            if not rows or not rows[0].get("id"):
                raise RuntimeError("Hermes session tail has no stable message ID")
            last_id = str(rows[0]["id"])
        self.state.register_session(session_id, baseline_count=count, last_message_id=last_id)

    def status(self) -> dict[str, Any]:
        settings = self.settings.read()
        state = self.state.read()
        available, reason = _valid_model(self.model)
        active = state.get("jobs", {}).get(state.get("active_job_id") or "")
        if active and active.get("status") == "needs_attention":
            run_state = "needs_attention"
        elif active:
            run_state = "running"
        elif not settings["enabled"]:
            run_state = "disabled"
        else:
            run_state = "blocked" if not available else "scheduled"
        configured_due = state.get("next_run_at")
        if configured_due is None:
            estimate_now = utc_now()
            estimated = next_scheduled_at(settings, now=estimate_now, interval_anchor=estimate_now)
            configured_due = iso(estimated) if estimated else None
        warnings = [{"session_id": session_id, "state": row.get("source_status")}
                    for session_id, row in state["sessions"].items()
                    if row.get("source_status") != "active"]
        return {"execution_available": available,
                "state": run_state,
                "last_run_at": state.get("last_run_at"),
                "next_run_at": state.get("next_run_at") if available and settings["enabled"] else None,
                "configured_next_run_at": configured_due,
                "last_draft_count": state.get("last_draft_count"),
                "last_error": state.get("last_error"),
                "coverage_warnings": warnings,
                "blocked_reason": reason if not available else "",
                "settings_only": not available}

    def update_settings(self, value: dict) -> dict[str, Any]:
        saved = self.settings.write(value)
        due = next_scheduled_at(saved, now=utc_now(), interval_anchor=utc_now())
        self.state.update(lambda state: state.update({"next_run_at": iso(due) if due else None}))
        return saved

    async def run(self, *, reason: str = "manual", now: datetime | None = None) -> dict[str, Any]:
        available, blocked_reason = _valid_model(self.model)
        if not available:
            raise HTTPException(status_code=503, detail={"code": "organizer_unavailable", "message": blocked_reason})
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "already_running", "draft_count": 0}
            return await self._run_locked(reason=reason, now=now or utc_now())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    async def _run_locked(self, *, reason: str, now: datetime):
        state = self.state.read()
        active_id = state.get("active_job_id")
        if active_id:
            job = state["jobs"].get(active_id)
            if not job:
                raise HTTPException(status_code=409, detail="Organizer state has an orphan active-job pointer")
            if job["status"] == "model_started":
                self._set_error(job["job_id"], "model_result_unknown", "模型请求中断，结果未知；为避免重复调用，已暂停自动重试。")
                raise HTTPException(status_code=409, detail={"code": "model_result_unknown", "message": "模型请求结果未知，需先核对作业状态。"})
            if job["status"] in {"drafts_pending", "model_complete"}:
                return self._finish_drafts(job)
            if job["status"] == "collecting":
                return await self._invoke_model(job)
            raise HTTPException(status_code=409, detail={"code": "organizer_needs_attention",
                                                         "message": "存在需要核对的中断作业；不会自动重复调用模型。"})

        snapshot = await self._collect_new_messages(state)
        # Cursors for sessions containing only assistant/system rows can advance without model work.
        empty_updates = {sid: cursor for sid, cursor in snapshot["cursor_updates"].items()
                         if sid not in snapshot["user_sessions"]}
        self._commit_empty_session_cursors(empty_updates)
        if not snapshot["new_messages"]:
            due = next_scheduled_at(self.settings.read(), now=now, interval_anchor=now)
            self.state.update(lambda value: value.update({"last_run_at": iso(now), "last_draft_count": 0,
                                                          "last_error": None, "active_job_id": None,
                                                          "next_run_at": iso(due) if due else None}))
            return {"status": "no_new_messages", "draft_count": 0}

        job_id = uuid.uuid4().hex
        job = {"job_id": job_id, "reason": reason, "status": "collecting", "created_at": iso(now),
               "cursor_updates": snapshot["cursor_updates"], "new_messages": snapshot["new_messages"],
               "context": snapshot["context"], "attempts": 0, "drafts": []}
        def begin(value):
            value["jobs"][job_id] = job
            value["active_job_id"] = job_id
        self.state.update(begin)
        return await self._invoke_model(job)

    async def _collect_new_messages(self, state):
        new_messages: list[dict[str, Any]] = []
        contexts: dict[str, list[dict[str, Any]]] = {}
        updates: dict[str, dict[str, Any]] = {}
        total_chars = 0
        for session_id, cursor in sorted(state["sessions"].items()):
            if cursor.get("source_status") != "active":
                continue
            try:
                metadata = await self.source.get_session(session_id)
            except HTTPException as exc:
                if exc.status_code == 404:
                    self.state.mark_session_deleted(session_id)
                    continue
                raise
            total = metadata.get("message_count")
            if type(total) is not int or total < 0:
                raise RuntimeError(f"Hermes session {session_id} has no verifiable message count")
            start = int(cursor.get("cursor_count", 0))
            expected_id = cursor.get("cursor_message_id")
            if total < start:
                self.state.update(lambda value, sid=session_id: value["sessions"][sid].update({"source_status": "history_discontinuous"}))
                continue
            if total == start:
                continue
            if start and expected_id:
                anchor = await self.source.list_messages(session_id, limit=1, offset=start - 1, order="oldest")
                rows = anchor.get("messages", [])
                if not rows or str(rows[0].get("id", "")) != expected_id:
                    self.state.update(lambda value, sid=session_id: value["sessions"][sid].update({"source_status": "history_discontinuous"}))
                    continue
            context_start = max(0, start - 2)
            if start:
                context_page = await self.source.list_messages(session_id, limit=min(2, start), offset=context_start, order="oldest")
                contexts[session_id] = context_page.get("messages", [])
            offset = start
            consumed_rows: list[dict[str, Any]] = []
            row_limit = min(total, start + MAX_SESSION_SCAN_ROWS)
            budget_stop = False
            while offset < row_limit and len(new_messages) < MAX_INPUT_MESSAGES:
                page = await self.source.list_messages(session_id, limit=min(100, row_limit - offset), offset=offset, order="oldest")
                rows = page.get("messages", [])
                if not rows:
                    break
                for row in rows:
                    message_id = str(row.get("id", ""))
                    role = row.get("role")
                    if not message_id or str(row.get("session_id", session_id)) != session_id:
                        raise RuntimeError("Hermes history row is missing a stable ID or has a session mismatch")
                    text = row.get("text", "")
                    if not isinstance(text, str):
                        raise RuntimeError("Hermes history row has invalid content")
                    if role == "user":
                        if not row.get("timestamp"):
                            raise RuntimeError("Hermes user message is missing its source timestamp")
                        if len(text) > MAX_INPUT_CHARS:
                            raise HTTPException(status_code=413, detail={"code": "message_too_large", "message": "单条新消息超过整理输入上限，未推进游标。"})
                        if len(new_messages) >= MAX_INPUT_MESSAGES or total_chars + len(text) > MAX_INPUT_CHARS:
                            budget_stop = True
                            break
                        new_messages.append({"session_id": session_id, "message_id": message_id,
                                             "timestamp": row["timestamp"], "text": text})
                        total_chars += len(text)
                    consumed_rows.append(row)
                # Do not advance past a user message omitted due to the bounded batch.
                offset = start + len(consumed_rows)
                if budget_stop or len(new_messages) >= MAX_INPUT_MESSAGES or total_chars >= MAX_INPUT_CHARS:
                    break
                if len(rows) == 0:
                    break
            if consumed_rows:
                last = consumed_rows[-1]
                updates[session_id] = {"cursor_count": start + len(consumed_rows),
                                       "cursor_message_id": str(last["id"]), "updated_at": iso()}
            if offset < total and len(consumed_rows) >= MAX_SESSION_SCAN_ROWS:
                # This bounded batch can make progress; the remaining tail is picked up next run.
                pass
        # Keep only two context rows and never allow the model to treat context as new candidates.
        payload_context = {}
        context_chars = 0
        candidate_sessions = {message["session_id"] for message in new_messages}
        for session_id in sorted(candidate_sessions):
            rows = contexts.get(session_id, [])
            selected = []
            for row in rows[-2:]:
                text = str(row.get("text", ""))[:min(2000, MAX_CONTEXT_CHARS - context_chars)]
                if not text:
                    break
                selected.append({"message_id": str(row.get("id", "")), "role": row.get("role"),
                                 "timestamp": row.get("timestamp"), "text": text})
                context_chars += len(text)
                if context_chars >= MAX_CONTEXT_CHARS:
                    break
            if selected:
                payload_context[session_id] = selected
            if context_chars >= MAX_CONTEXT_CHARS:
                break
        return {"new_messages": new_messages, "context": payload_context, "cursor_updates": updates,
                "user_sessions": {message["session_id"] for message in new_messages}}

    async def _invoke_model(self, job: dict[str, Any]):
        job["attempts"] = int(job.get("attempts", 0)) + 1
        if job["attempts"] > 1:
            raise HTTPException(status_code=409, detail={"code": "model_retry_budget_exhausted", "message": "该作业的模型调用预算已用完。"})
        job["status"] = "model_started"
        self._save_job(job)
        payload = {"task": "提取值得保存的用户原始经历、工作灵感、待办或知识候选；不把助手建议写成用户事实。",
                   "new_user_messages": job["new_messages"], "context_only": job["context"],
                   "output_schema": {"drafts": [{"category": "journal|work_idea|todo|knowledge_candidate",
                                                   "title": "string", "summary": "string",
                                                   "source_quotes": [{"session_id": "string", "message_id": "string",
                                                                      "excerpt": "原文连续片段"}]}]}}
        try:
            capabilities = self.model.capabilities
            result = await asyncio.wait_for(self.model.extract(
                                                payload,
                                                max_input_tokens=min(MAX_INPUT_TOKENS, capabilities["max_input_tokens"]),
                                                max_output_tokens=min(MAX_OUTPUT_TOKENS, capabilities["max_output_tokens"])),
                                            timeout=MODEL_TIMEOUT_SECONDS)
            drafts = _validate_drafts(result, job["new_messages"])
        except asyncio.TimeoutError:
            self._set_error(job["job_id"], "model_result_unknown", "模型请求超时，远端是否完成未知；为避免重复调用已暂停。")
            raise HTTPException(status_code=504, detail={"code": "model_result_unknown", "message": "整理请求超时且结果未知，已暂停自动重试。"})
        except Exception:
            self._set_error(job["job_id"], "model_result_unknown",
                            "模型请求失败或响应无法核验；远端结果可能未知，已暂停自动重试。")
            raise
        job["drafts"] = drafts
        job["status"] = "drafts_pending"
        job["model_completed_at"] = iso()
        self._save_job(job)
        return self._finish_drafts(job)

    def _finish_drafts(self, job: dict[str, Any]):
        self.review_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.review_root.is_symlink() or not self.review_root.is_dir():
            raise RuntimeError("Review root must be a real directory")
        created = []
        for index, draft in enumerate(job.get("drafts", [])):
            content = _render_draft(job, draft, index)
            digest = hashlib.sha256(content).hexdigest()
            name = f"AI-Organize-{job['job_id']}-{index + 1:02d}-{digest[:10]}.md"
            path = self.review_root / name
            _create_immutable(path, content)
            created.append({"path": name, "sha256": digest})
        def commit(state):
            saved_job = state["jobs"][job["job_id"]]
            for session_id, cursor in job["cursor_updates"].items():
                state["sessions"][session_id].update(cursor)
            draft_by_message: dict[str, list[str]] = {}
            for draft, artifact in zip(job.get("drafts", []), created):
                for quote in draft["source_quotes"]:
                    key = f"{quote['session_id']}:{quote['message_id']}"
                    draft_by_message.setdefault(key, []).append(artifact["path"])
            for message in job["new_messages"]:
                key = f"{message['session_id']}:{message['message_id']}"
                state["processed_messages"][key] = {"processed_at": iso(), "job_id": job["job_id"],
                                                       "draft_paths": draft_by_message.get(key, [])}
            saved_job["artifacts"] = created
            saved_job["status"] = "completed"
            saved_job["completed_at"] = iso()
            state["active_job_id"] = None
            state["last_run_at"] = saved_job["completed_at"]
            state["last_draft_count"] = len(created)
            state["last_error"] = None
            settings = self.settings.read()
            due = next_scheduled_at(settings, now=utc_now(), interval_anchor=utc_now())
            state["next_run_at"] = iso(due) if due else None
        self.state.update(commit)
        return {"status": "completed" if created else "no_candidates", "draft_count": len(created), "job_id": job["job_id"], "drafts": created}

    def _commit_empty_session_cursors(self, updates):
        if not updates:
            return
        def commit(state):
            for session_id, cursor in updates.items():
                if session_id in state["sessions"]:
                    state["sessions"][session_id].update(cursor)
        self.state.update(commit)

    def _save_job(self, job):
        def save(state):
            state["jobs"][job["job_id"]] = job
            state["active_job_id"] = job["job_id"]
        self.state.update(save)

    def _set_error(self, job_id, code, message):
        def save(state):
            job = state["jobs"].get(job_id)
            if job:
                job["status"] = "needs_attention" if code == "model_result_unknown" else "failed"
                job["error_code"] = code
                job["error"] = message[:500]
            state["last_error"] = {"code": code, "message": message[:500], "at": iso()}
            if code != "model_result_unknown":
                state["active_job_id"] = None
        self.state.update(save)

    async def tick(self, *, now: datetime | None = None):
        """One scheduler tick; tests inject time. Production loop is not started without a safe model."""
        available, _ = _valid_model(self.model)
        if not available:
            return {"status": "blocked"}
        settings = self.settings.read()
        if not settings["enabled"]:
            return {"status": "disabled"}
        state = self.state.read()
        now = now or utc_now()
        due_value = state.get("next_run_at")
        if not due_value:
            due = next_scheduled_at(settings, now=now, interval_anchor=now)
            self.state.update(lambda value: value.update({"next_run_at": iso(due) if due else None}))
            return {"status": "scheduled", "next_run_at": iso(due) if due else None}
        due = datetime.fromisoformat(due_value.replace("Z", "+00:00"))
        if now < due:
            return {"status": "not_due", "next_run_at": due_value}
        return await self.run(reason="scheduled", now=now)

    def _record_scheduler_failure(self, *, now: datetime | None = None):
        now = now or utc_now()
        settings = self.settings.read()
        state = self.state.read()
        failures = min(int(state.get("scheduler_failures", 0)) + 1, 16)
        delay = min(60 * (2 ** (failures - 1)), MAX_SCHEDULER_BACKOFF_SECONDS)
        due = next_scheduled_at(settings, now=now + timedelta(seconds=delay), interval_anchor=now)

        def save(value):
            value["scheduler_failures"] = failures
            value["next_run_at"] = iso(due) if due else None
            active = value.get("jobs", {}).get(value.get("active_job_id") or "")
            if not active or active.get("status") != "needs_attention":
                value["last_error"] = {"code": "scheduler_failed",
                                        "message": "自动整理执行失败；系统将在退避后重试。", "at": iso(now)}
        self.state.update(save)

    def start_scheduler(self):
        available, _ = _valid_model(self.model)
        if not available or (self._scheduler_task and not self._scheduler_task.done()):
            return False
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        return True

    async def _scheduler_loop(self):
        while True:
            try:
                result = await self.tick()
            except Exception:
                # Do not log source contents or upstream errors; persist a bounded backoff.
                self._record_scheduler_failure()
            else:
                if result.get("status") in {"completed", "no_candidates", "no_new_messages"}:
                    state = self.state.read()
                    if state.get("scheduler_failures"):
                        self.state.update(lambda value: value.update({"scheduler_failures": 0}))
            await asyncio.sleep(30)


def _validate_drafts(result: Any, new_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not isinstance(result.get("drafts"), list):
        raise ValueError("Model output must contain a drafts array")
    if len(result["drafts"]) > MAX_CANDIDATES:
        raise ValueError("Model output exceeds the draft count limit")
    allowed = {(message["session_id"], message["message_id"]): message for message in new_messages}
    drafts = []
    for candidate in result["drafts"]:
        if not isinstance(candidate, dict) or candidate.get("category") not in CATEGORIES:
            raise ValueError("Model output contains an invalid category")
        title, summary = candidate.get("title"), candidate.get("summary")
        quotes = candidate.get("source_quotes")
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            raise ValueError("Model output contains an invalid title")
        if not isinstance(summary, str) or len(summary) > 4000 or not isinstance(quotes, list) or not quotes or len(quotes) > 10:
            raise ValueError("Model output is missing bounded summary/source quotes")
        normalized = []
        for quote in quotes:
            if not isinstance(quote, dict):
                raise ValueError("Invalid source quote")
            message_id = quote.get("message_id")
            session_id = quote.get("session_id")
            excerpt = quote.get("excerpt")
            source = allowed.get((session_id, message_id))
            if not source or not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 1200 or excerpt not in source["text"]:
                raise ValueError("Model output quote does not match a new user message")
            normalized.append({"session_id": source["session_id"], "message_id": message_id,
                               "timestamp": source["timestamp"], "excerpt": excerpt})
        drafts.append({"category": candidate["category"], "title": title.strip(),
                       "summary": summary.strip(), "source_quotes": normalized})
    return drafts


def _yaml(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_draft(job: dict[str, Any], draft: dict[str, Any], index: int) -> bytes:
    generated_at = job["created_at"]
    meta = {"type": "review", "status": "pending", "source_type": "hermes_auto_organize",
            "captured_at": generated_at, "original_asset": "", "capture_context": "",
            "tags": ["ai-organize", draft["category"]], "review_status": "pending",
            "organizer_job_id": job["job_id"], "organizer_category": draft["category"],
            "source_refs": draft["source_quotes"]}
    frontmatter = "---\n" + "".join(f"{key}: {_yaml(value)}\n" for key, value in meta.items()) + "---\n"
    lines = [f"# {draft['title']}", "", "> AI 整理草稿，请核对后再决定是否保留。", "",
             "## AI 提炼（非原文）", "", draft["summary"], "", "## 用户原始表达", ""]
    for quote in draft["source_quotes"]:
        lines.append(f"> {quote['excerpt'].replace(chr(10), chr(10) + '> ')}")
        lines.append(f"> 来源消息：`{quote['message_id']}` · {quote['timestamp']}")
        lines.append("")
    return (frontmatter + "\n".join(lines).rstrip() + "\n").encode("utf-8")


def _create_immutable(path: Path, content: bytes):
    if path.parent.is_symlink():
        raise RuntimeError("Review directory cannot be a symlink")
    fd, temp_path = tempfile.mkstemp(prefix=".organizer-draft-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, path, follow_symlinks=False)
            os.chmod(path, 0o600, follow_symlinks=False)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise RuntimeError("Immutable Review filename is already occupied by different content")
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
