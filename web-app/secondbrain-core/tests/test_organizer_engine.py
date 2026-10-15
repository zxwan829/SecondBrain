import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from secondbrain_core.modules.organizer_engine import OrganizerRunner


class FakeSource:
    def __init__(self):
        self.sessions = {}
        self.message_requests = []

    async def get_session(self, session_id):
        return {"session_id": session_id, "message_count": len(self.sessions.get(session_id, []))}

    async def list_messages(self, session_id, limit=500, offset=0, order="oldest"):
        self.message_requests.append((session_id, limit, offset, order))
        rows = list(self.sessions.get(session_id, []))
        if order == "latest":
            rows.reverse()
        return {"messages": rows[offset:offset + limit],
                "pagination": {"limit": limit, "offset": offset, "has_more": offset + limit < len(rows)}}


class FakeModel:
    capabilities = {
        "no_tools": True, "hard_input_token_limit": True,
        "hard_output_token_limit": True, "hard_timeout": True,
        "single_concurrency": True, "single_request_per_job": True,
        "hard_cost_budget": True, "max_input_tokens": 6000,
        "max_output_tokens": 1200, "timeout_seconds": 45,
        "max_calls_per_job": 1, "max_cost_usd": 0,
    }

    def __init__(self, result=None, entered=None, release=None, failure=None):
        self.result = result or {"drafts": []}
        self.entered = entered
        self.release = release
        self.failure = failure
        self.calls = []

    async def extract(self, payload, *, max_input_tokens, max_output_tokens):
        self.calls.append((payload, max_input_tokens, max_output_tokens))
        if self.entered:
            self.entered.set()
        if self.release:
            await self.release.wait()
        if self.failure:
            raise self.failure
        return self.result


def row(message_id, role, text, n, session="app-session"):
    return {"id": message_id, "session_id": session, "role": role,
            "timestamp": f"2026-10-15T00:00:{n:02d}Z", "text": text}


class OrganizerEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"
        self.root.mkdir(mode=0o700)
        self.review = Path(self.temp.name) / "review"
        self.review.mkdir(mode=0o700)
        self.source = FakeSource()
        self.model = FakeModel()
        self.runner = OrganizerRunner(self.root, self.review, self.source, self.model)
        self.runner.state.register_session("app-session", baseline_count=0)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_user_message_creates_traceable_review_and_advances_cursor_once(self):
        self.source.sessions["app-session"] = [row("u1", "user", "我想记录每周复盘", 1),
                                                row("a1", "assistant", "可以安排周五", 2)]
        self.model.result = {"drafts": [{"category": "work_idea", "title": "每周复盘",
                                          "summary": "AI 提炼：用户提出每周进行复盘。",
                                          "source_quotes": [{"session_id": "app-session", "message_id": "u1",
                                                             "excerpt": "我想记录每周复盘"}]}]}
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["draft_count"], 1)
        draft = (self.review / result["drafts"][0]["path"]).read_text()
        self.assertIn('source_type: "hermes_auto_organize"', draft)
        self.assertIn("AI 提炼：用户提出每周进行复盘。", draft)
        self.assertIn("> 我想记录每周复盘", draft)
        state = self.runner.state.read()
        self.assertEqual(state["sessions"]["app-session"]["cursor_count"], 2)
        self.assertIn("app-session:u1", state["processed_messages"])
        second = asyncio.run(self.runner.run())
        self.assertEqual(second["status"], "no_new_messages")
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(len(list(self.review.glob("AI-Organize-*.md"))), 1)

    def test_no_new_user_messages_skips_model_but_checkpoints_assistant_tail(self):
        self.source.sessions["app-session"] = [row("a1", "assistant", "hello", 1)]
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "no_new_messages")
        self.assertEqual(self.model.calls, [])
        self.assertEqual(self.runner.state.read()["sessions"]["app-session"]["cursor_count"], 1)

    def test_cross_session_new_messages_share_one_batch_with_exact_sources(self):
        self.runner.state.register_session("second-session", baseline_count=0)
        self.source.sessions["app-session"] = [row("u1", "user", "今天完成了方案", 1)]
        self.source.sessions["second-session"] = [row("u2", "user", "明天继续验证", 1, "second-session")]
        self.model.result = {"drafts": [{"category": "todo", "title": "继续验证方案", "summary": "跨会话待办候选。",
                                          "source_quotes": [
                                              {"session_id": "app-session", "message_id": "u1", "excerpt": "今天完成了方案"},
                                              {"session_id": "second-session", "message_id": "u2", "excerpt": "明天继续验证"},
                                          ]}]}
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.model.calls), 1)
        self.assertIn("app-session:u1", self.runner.state.read()["processed_messages"])
        self.assertIn("second-session:u2", self.runner.state.read()["processed_messages"])

    def test_only_new_user_messages_can_be_quoted(self):
        self.source.sessions["app-session"] = [row("u1", "user", "新消息", 1)]
        self.model.result = {"drafts": [{"category": "journal", "title": "标题", "summary": "摘要",
                                          "source_quotes": [{"session_id": "app-session", "message_id": "old",
                                                             "excerpt": "旧上下文"}]}]}
        with self.assertRaises(ValueError):
            asyncio.run(self.runner.run())
        state = self.runner.state.read()
        self.assertEqual(state["sessions"]["app-session"]["cursor_count"], 0)
        self.assertEqual(state["jobs"][state["active_job_id"]]["status"], "needs_attention")

    def test_review_write_failure_resumes_from_saved_model_output_without_second_call(self):
        self.source.sessions["app-session"] = [row("u1", "user", "周末读书", 1)]
        self.model.result = {"drafts": [{"category": "journal", "title": "读书记录", "summary": "读书。",
                                          "source_quotes": [{"session_id": "app-session", "message_id": "u1",
                                                             "excerpt": "周末读书"}]}]}
        import secondbrain_core.modules.organizer_engine as engine_module
        with patch.object(engine_module, "_create_immutable", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                asyncio.run(self.runner.run())
        self.assertEqual(self.runner.state.read()["jobs"][self.runner.state.read()["active_job_id"]]["status"], "drafts_pending")
        with patch.object(engine_module, "_create_immutable", wraps=engine_module._create_immutable):
            result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(len(list(self.review.glob("AI-Organize-*.md"))), 1)

    def test_recovery_never_overwrites_a_human_edited_review(self):
        self.source.sessions["app-session"] = [row("u1", "user", "周末读书", 1)]
        self.model.result = {"drafts": [{"category": "journal", "title": "读书记录", "summary": "读书。",
                                          "source_quotes": [{"session_id": "app-session", "message_id": "u1",
                                                             "excerpt": "周末读书"}]}]}
        import secondbrain_core.modules.organizer_engine as engine_module
        original_create = engine_module._create_immutable

        def create_then_interrupt(path, content):
            original_create(path, content)
            raise OSError("interrupted after write")

        with patch.object(engine_module, "_create_immutable", side_effect=create_then_interrupt):
            with self.assertRaises(OSError):
                asyncio.run(self.runner.run())
        artifact = next(self.review.glob("AI-Organize-*.md"))
        artifact.write_text("用户手工修改内容\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            asyncio.run(self.runner.run())
        self.assertEqual(artifact.read_text(encoding="utf-8"), "用户手工修改内容\n")
        self.assertEqual(len(self.model.calls), 1)

    def test_model_timeout_or_unknown_failure_is_not_retried_and_cursor_stays(self):
        self.source.sessions["app-session"] = [row("u1", "user", "待处理", 1)]
        self.model.failure = RuntimeError("lost response")
        with self.assertRaises(RuntimeError):
            asyncio.run(self.runner.run())
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(self.runner.run())
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(self.runner.state.read()["sessions"]["app-session"]["cursor_count"], 0)

    def test_concurrent_manual_and_scheduled_run_share_file_lock(self):
        self.source.sessions["app-session"] = [row("u1", "user", "今天完成了目标", 1)]
        entered = asyncio.Event()
        release = asyncio.Event()
        self.runner.model = FakeModel(entered=entered, release=release)

        async def scenario():
            first = asyncio.create_task(self.runner.run(reason="manual"))
            await entered.wait()
            second = await self.runner.run(reason="scheduled")
            release.set()
            await first
            return second
        result = asyncio.run(scenario())
        self.assertEqual(result["status"], "already_running")
        self.assertEqual(len(self.runner.model.calls), 1)

    def test_history_discontinuity_quarantines_only_that_session(self):
        self.source.sessions["app-session"] = [row("u1", "user", "旧消息", 1),
                                                row("a1", "assistant", "回复", 2)]
        self.runner.state.update(lambda state: state["sessions"]["app-session"].update(
            {"cursor_count": 1, "cursor_message_id": "different"}))
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "no_new_messages")
        self.assertEqual(self.runner.state.read()["sessions"]["app-session"]["source_status"], "history_discontinuous")
        self.assertEqual(self.model.calls, [])

    def test_context_is_bounded_and_never_becomes_candidate_input(self):
        self.source.sessions["app-session"] = [row("old-1", "user", "A" * 3000, 1),
                                                row("old-2", "assistant", "B" * 3000, 2)]
        self.runner.state.update(lambda state: state["sessions"].update({"app-session": {
            "registered_at": "2026-10-15T00:00:00Z", "cursor_count": 2,
            "cursor_message_id": "old-2", "source_status": "active"}}))
        self.source.sessions["app-session"].append(row("new-1", "user", "新消息", 3))
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "no_candidates")
        payload = self.model.calls[0][0]
        self.assertEqual([item["message_id"] for item in payload["new_user_messages"]], ["new-1"])
        self.assertLessEqual(sum(len(item["text"]) for rows in payload["context_only"].values() for item in rows), 4000)

    def test_large_session_history_is_paginated_and_resumed_by_cursor(self):
        rows = []
        for index in range(120):
            role = ("user" if index % 2 == 0 else "assistant") if index < 78 else ("assistant" if index < 110 else "user")
            rows.append(row(f"m{index}", role, f"message-{index}", index + 1))
        self.source.sessions["app-session"] = rows
        first = asyncio.run(self.runner.run())
        self.assertEqual(first["status"], "no_candidates")
        first_cursor = self.runner.state.read()["sessions"]["app-session"]["cursor_count"]
        self.assertEqual(first_cursor, 111)
        second = asyncio.run(self.runner.run())
        self.assertEqual(second["status"], "no_candidates")
        self.assertEqual(self.runner.state.read()["sessions"]["app-session"]["cursor_count"], 120)
        self.assertEqual(len(self.runner.state.read()["processed_messages"]), 49)
        self.assertIn(("app-session", 20, 100, "oldest"), self.source.message_requests)

    def test_scheduler_persists_exponential_backoff_without_leaking_source_errors(self):
        now = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
        self.runner.update_settings({"enabled": True, "mode": "interval", "interval_hours": 4,
                                     "daily_time": "00:30", "timezone": "Asia/Shanghai"})
        self.runner._record_scheduler_failure(now=now)
        state = self.runner.state.read()
        self.assertEqual(state["scheduler_failures"], 1)
        self.assertEqual(state["last_error"]["code"], "scheduler_failed")
        self.assertNotIn("source", state["last_error"]["message"])
        due = datetime.fromisoformat(state["next_run_at"].replace("Z", "+00:00"))
        self.assertGreaterEqual((due - now).total_seconds(), 4 * 3600)

    def test_settings_disabled_blocks_schedule_but_not_manual_run(self):
        self.runner.update_settings({"enabled": False, "mode": "interval", "interval_hours": 4,
                                     "daily_time": "00:30", "timezone": "Asia/Shanghai"})
        self.assertEqual(asyncio.run(self.runner.tick())["status"], "disabled")
        self.assertFalse(self.runner.status()["execution_available"] is False)
        self.source.sessions["app-session"] = [row("u1", "user", "手动内容", 1)]
        self.assertEqual(asyncio.run(self.runner.run(reason="manual"))["status"], "no_candidates")

    def test_scheduler_due_time_survives_runner_recreation_and_catches_up_once(self):
        now = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
        self.runner.update_settings({"enabled": True, "mode": "interval", "interval_hours": 4,
                                     "daily_time": "00:30", "timezone": "Asia/Shanghai"})
        first_due = self.runner.state.read()["next_run_at"]
        self.assertIsNotNone(first_due)
        runner_after_restart = OrganizerRunner(self.root, self.review, self.source, self.model)
        self.assertEqual(runner_after_restart.state.read()["next_run_at"], first_due)
        self.source.sessions["app-session"] = []
        result = asyncio.run(runner_after_restart.tick(now=datetime.fromisoformat(first_due.replace("Z", "+00:00"))))
        self.assertEqual(result["status"], "no_new_messages")
        self.assertNotEqual(runner_after_restart.state.read()["next_run_at"], first_due)

    def test_input_budget_does_not_advance_cursor(self):
        self.source.sessions["app-session"] = [row("u1", "user", "超长" * 13000, 1)]
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(self.runner.run())
        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(self.runner.state.read()["sessions"]["app-session"]["cursor_count"], 0)
        self.assertEqual(self.model.calls, [])

    def test_oversized_model_capability_is_rejected_before_call(self):
        self.runner.model = FakeModel()
        self.runner.model.capabilities = {**FakeModel.capabilities, "max_output_tokens": 9000}
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(self.runner.run())
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(self.model.calls, [])

    def test_inconsistent_zero_model_budget_is_rejected_before_call(self):
        self.runner.model = FakeModel()
        self.runner.model.capabilities = {**FakeModel.capabilities, "max_input_tokens": 0}
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(self.runner.run())
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(self.model.calls, [])

    def test_adapter_budget_is_never_exceeded_by_core_request(self):
        self.runner.model = FakeModel()
        self.runner.model.capabilities = {**FakeModel.capabilities, "max_input_tokens": 3000,
                                           "max_output_tokens": 600}
        self.source.sessions["app-session"] = [row("u1", "user", "新消息", 1)]
        asyncio.run(self.runner.run())
        _, max_input, max_output = self.runner.model.calls[0]
        self.assertEqual((max_input, max_output), (3000, 600))

    def test_app_session_registration_uses_baseline_so_old_history_is_not_replayed(self):
        self.source.sessions["existing"] = [row("old-u", "user", "既有内容", 1, "existing"),
                                              row("old-a", "assistant", "回复", 2, "existing")]
        asyncio.run(self.runner.baseline_session("existing"))
        self.assertEqual(self.runner.state.read()["sessions"]["existing"]["cursor_count"], 2)
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "no_new_messages")
        self.assertEqual(self.model.calls, [])

    def test_deleted_session_is_retained_as_unavailable_and_not_silently_removed(self):
        self.runner.state.mark_session_deleted("app-session")
        result = asyncio.run(self.runner.run())
        self.assertEqual(result["status"], "no_new_messages")
        self.assertIn("app-session", self.runner.state.read()["sessions"])
        self.assertEqual(self.runner.state.read()["sessions"]["app-session"]["source_status"], "deleted_or_unavailable")


if __name__ == "__main__":
    unittest.main()
