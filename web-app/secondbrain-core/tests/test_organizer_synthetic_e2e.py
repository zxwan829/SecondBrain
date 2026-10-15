"""Synthetic end-to-end organizer exercise; never reads production Hermes data."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from secondbrain_core.modules.organizer_engine import OrganizerRunner


CAPABILITIES = {
    "no_tools": True,
    "hard_input_token_limit": True,
    "hard_output_token_limit": True,
    "hard_timeout": True,
    "single_concurrency": True,
    "single_request_per_job": True,
    "hard_cost_budget": True,
    "max_input_tokens": 6000,
    "max_output_tokens": 1200,
    "timeout_seconds": 45,
    "max_calls_per_job": 1,
    "max_cost_usd": 0,
}


class SyntheticHermesSource:
    def __init__(self, sessions: dict[str, list[dict]]):
        self.sessions = sessions

    async def get_session(self, session_id: str):
        return {"session_id": session_id, "message_count": len(self.sessions[session_id])}

    async def list_messages(self, session_id: str, limit=500, offset=0, order="oldest"):
        rows = list(self.sessions[session_id])
        if order == "latest":
            rows.reverse()
        page = rows[offset:offset + limit]
        return {"messages": page, "pagination": {"limit": limit, "offset": offset,
                "has_more": offset + len(page) < len(rows)}}


class SyntheticFakeModel:
    capabilities = CAPABILITIES

    def __init__(self, *outputs: dict):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    async def extract(self, payload, *, max_input_tokens, max_output_tokens):
        self.calls.append({"payload": payload, "max_input_tokens": max_input_tokens,
                           "max_output_tokens": max_output_tokens})
        if not self.outputs:
            raise AssertionError("Unexpected synthetic model call")
        return self.outputs.pop(0)


def message(session_id: str, message_id: str, role: str, timestamp: str, text: str) -> dict:
    return {"session_id": session_id, "id": message_id, "role": role,
            "timestamp": timestamp, "text": text}


class OrganizerSyntheticEndToEndTests(unittest.TestCase):
    def test_diary_work_todo_idle_cross_session_duplicate_and_batch_recovery(self):
        diary = "今天下班后我和家人去公园散步，心情放松了很多。"
        work_idea = "下季度把客服问题整理成知识卡片，减少重复排查。"
        todo = "周五前把试点计划发给小林。"
        idle = "谢谢，收到。"
        sessions = {
            "synthetic-diary": [
                message("synthetic-diary", "d-user-001", "user", "2026-10-15T10:00:00Z", diary),
                message("synthetic-diary", "d-assistant-002", "assistant", "2026-10-15T10:00:03Z", "听起来不错。"),
                message("synthetic-diary", "d-user-003", "user", "2026-10-15T10:02:00Z", todo),
                message("synthetic-diary", "d-user-004", "user", "2026-10-15T10:03:00Z", idle),
            ],
            "synthetic-work-a": [
                message("synthetic-work-a", "w-user-001", "user", "2026-10-15T11:00:00Z", work_idea),
            ],
            "synthetic-work-b": [
                message("synthetic-work-b", "dup-user-001", "user", "2026-10-15T11:05:00Z", work_idea),
            ],
        }
        first_output = {"drafts": [
            {"category": "journal", "title": "下班后的公园散步", "summary": "AI 提炼：用户记录了与家人散步后的放松感。",
             "source_quotes": [{"session_id": "synthetic-diary", "message_id": "d-user-001", "excerpt": diary}]},
            {"category": "todo", "title": "发送试点计划", "summary": "AI 提炼：周五前需要把试点计划发给小林。",
             "source_quotes": [{"session_id": "synthetic-diary", "message_id": "d-user-003", "excerpt": todo}]},
            {"category": "work_idea", "title": "将客服问题整理为知识卡片", "summary": "AI 提炼：把重复问题整理成知识卡片以减少重复排查。",
             "source_quotes": [
                 {"session_id": "synthetic-work-a", "message_id": "w-user-001", "excerpt": work_idea},
                 {"session_id": "synthetic-work-b", "message_id": "dup-user-001", "excerpt": work_idea},
             ]},
        ], "usage": {"prompt_tokens": 430, "completion_tokens": 180, "total_tokens": 610,
                    "model": "synthetic/fake"}}
        follow_up = "我还可以先从最近一个月的高频问题开始。"
        second_output = {"drafts": [
            {"category": "work_idea", "title": "知识卡片试点范围补充", "summary": "AI 提炼：建议先从最近一个月的高频客服问题开始。",
             "source_quotes": [{"session_id": "synthetic-work-a", "message_id": "w-user-002", "excerpt": follow_up}]},
        ], "usage": {"prompt_tokens": 210, "completion_tokens": 90, "total_tokens": 300,
                     "model": "synthetic/fake"}}

        with tempfile.TemporaryDirectory(prefix="secondbrain-organizer-synthetic-") as tmp:
            root = Path(tmp) / "isolated-state"
            root.mkdir(mode=0o700)
            review = Path(tmp) / "isolated-review"
            review.mkdir(mode=0o700)
            source = SyntheticHermesSource(sessions)
            model = SyntheticFakeModel(first_output, second_output)
            runner = OrganizerRunner(root, review, source, model)
            for session_id in sessions:
                runner.state.register_session(session_id, baseline_count=0)

            first = asyncio.run(runner.run(reason="synthetic-first-batch"))
            self.assertEqual(first["status"], "completed")
            self.assertEqual(first["draft_count"], 3)
            self.assertEqual(len(model.calls), 1)
            first_job = runner.state.read()["jobs"][first["job_id"]]
            first_payload = model.calls[0]["payload"]
            self.assertEqual(len(first_payload["new_user_messages"]), 5)
            self.assertEqual(len(first_job["artifacts"]), 3)
            self.assertEqual(first_job["usage"]["model"], "synthetic/fake")
            self.assertEqual({row["message_id"] for row in first_payload["new_user_messages"]},
                             {"d-user-001", "d-user-003", "d-user-004", "w-user-001", "dup-user-001"})
            self.assertTrue(all(item["session_id"].startswith("synthetic-") for item in first_payload["new_user_messages"]))
            state_after_first = runner.state.read()
            self.assertEqual(state_after_first["sessions"]["synthetic-diary"]["cursor_count"], 4)
            self.assertEqual(state_after_first["sessions"]["synthetic-work-a"]["cursor_count"], 1)
            self.assertEqual(state_after_first["sessions"]["synthetic-work-b"]["cursor_count"], 1)
            all_reviews = list(review.glob("AI-Organize-*.md"))
            combined = next(path for path in all_reviews if "知识卡片" in path.read_text(encoding="utf-8"))
            combined_text = combined.read_text(encoding="utf-8")
            self.assertIn("w-user-001", combined_text)
            self.assertIn("dup-user-001", combined_text)
            self.assertIn("> " + work_idea, combined_text)
            self.assertTrue(combined.is_relative_to(review))

            sessions["synthetic-work-a"].append(message(
                "synthetic-work-a", "w-user-002", "user", "2026-10-15T12:00:00Z", follow_up))
            import secondbrain_core.modules.organizer_engine as engine_module
            create = engine_module._create_immutable

            def create_then_interrupt(path, content):
                create(path, content)
                raise OSError("synthetic interruption after immutable file creation")

            with patch.object(engine_module, "_create_immutable", side_effect=create_then_interrupt):
                with self.assertRaises(OSError):
                    asyncio.run(runner.run(reason="synthetic-follow-up"))
            followup_payload = model.calls[1]["payload"]
            self.assertEqual([row["message_id"] for row in followup_payload["new_user_messages"]],
                             ["w-user-002"])
            self.assertIn("w-user-001", json.dumps(followup_payload["context_only"], ensure_ascii=False))
            pending = runner.state.read()
            pending_job = pending["jobs"][pending["active_job_id"]]
            self.assertEqual(pending_job["status"], "drafts_pending")
            self.assertEqual(pending["sessions"]["synthetic-work-a"]["cursor_count"], 1)
            self.assertEqual(len(model.calls), 2)

            recovered = asyncio.run(runner.run(reason="synthetic-recovery"))
            self.assertEqual(recovered["status"], "completed")
            self.assertEqual(len(model.calls), 2, "recovery must use persisted model output, not call again")
            self.assertEqual(runner.state.read()["sessions"]["synthetic-work-a"]["cursor_count"], 2)
            recovery_review = next(path for path in review.glob("AI-Organize-*.md")
                                   if "试点范围补充" in path.read_text(encoding="utf-8"))
            self.assertIn("w-user-002", recovery_review.read_text(encoding="utf-8"))
            before = sorted((path.name, path.read_bytes()) for path in review.glob("AI-Organize-*.md"))
            second = asyncio.run(runner.run(reason="synthetic-idempotency-check"))
            after = sorted((path.name, path.read_bytes()) for path in review.glob("AI-Organize-*.md"))
            self.assertEqual(second["status"], "no_new_messages")
            self.assertEqual(before, after)
            self.assertEqual(len(model.calls), 2)
            self.assertEqual(len(after), 4)

            # Preserve a concise, deterministic record in test output for the audit trail.
            print(json.dumps({"isolated_review_root": str(review),
                              "synthetic_sessions": {sid: [row["id"] for row in rows]
                                                     for sid, rows in sessions.items()},
                              "first_batch_drafts": first["draft_count"],
                              "cross_session_duplicate_merged": True,
                              "second_batch_recovery_model_calls": len(model.calls),
                              "final_review_count": len(after),
                              "final_cursor_counts": {sid: row["cursor_count"] for sid, row in
                                                      runner.state.read()["sessions"].items()},
                              "third_run": second["status"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
