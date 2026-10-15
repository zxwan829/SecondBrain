#!/usr/bin/env python3
"""Explicit, resumable runner for the three synthetic D076 text benchmarks.

Importing this module or preparing/inspecting a run never makes a network call.
Each `run` requires an existing run ID, one exact model, a private key-file path,
and an explicit confirmation flag. A missing outcome is never retried.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from secondbrain_core.modules.siliconflow_eval_run import (  # noqa: E402
    ALLOWED_MODEL_IDS,
    PersistentBenchmarkRun,
)
from secondbrain_core.modules.siliconflow_organizer import (  # noqa: E402
    SiliconFlowOrganizerModel,
)


DEFAULT_STATE_DIR = Path.home() / ".local/state/secondbrain/d076-text-benchmark"
PAYLOAD = {
    "job_id": "synthetic-eval-20261015",
    "task": "按分类提炼明确表达的用户事实；过滤普通问答和闲聊。返回 JSON：drafts 数组，每项含 category (journal/work_idea/todo/knowledge_candidate)、title、summary、source_quotes（session_id、message_id、timestamp、excerpt）。只引用给定原文，跨会话同主题合并，不把助手建议当成用户事实。",
    "new_user_messages": [
        {"session_id": "synthetic-life", "message_id": "life-001", "timestamp": "2026-10-15T09:00:00Z", "text": "今天陪家人去公园，感觉轻松。"},
        {"session_id": "synthetic-work-a", "message_id": "idea-followup-002", "timestamp": "2026-10-15T10:10:00Z", "text": "我还可以从最近一个月的高频问题开始。"},
        {"session_id": "synthetic-work-b", "message_id": "idea-duplicate-003", "timestamp": "2026-10-15T10:12:00Z", "text": "先把客服高频问题整理成知识卡片。"},
        {"session_id": "synthetic-life", "message_id": "todo-004", "timestamp": "2026-10-15T10:15:00Z", "text": "周五前把试点计划发给小林。"},
        {"session_id": "synthetic-life", "message_id": "smalltalk-005", "timestamp": "2026-10-15T10:16:00Z", "text": "谢谢，收到。"},
        {"session_id": "synthetic-life", "message_id": "qa-006", "timestamp": "2026-10-15T10:17:00Z", "text": "月球距离地球的平均距离大约是多少？"},
    ],
    "context_only": {"synthetic-work-a": [{
        "message_id": "idea-original-001", "role": "user", "timestamp": "2026-10-15T10:00:00Z",
        "text": "下季度把客服问题整理成知识卡片，减少重复排查。",
    }]},
    "output_schema": {"drafts": [{
        "category": "journal|work_idea|todo|knowledge_candidate", "title": "string", "summary": "string",
        "source_quotes": [{"session_id": "string", "message_id": "string", "timestamp": "ISO-8601 UTC",
                           "excerpt": "verbatim contiguous source text"}],
    }]},
}


def _print(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


async def _run(args, run):
    model = args.model
    states = run.status()["models"]
    if not run.may_run_in_order(model):
        _print({"run_id": run.run_id, "model_id": model, "state": states[model]["state"],
                "error_code": "prior_model_gate_not_satisfied_no_request_sent"})
        return 2
    if not args.confirm_real_request:
        _print({"run_id": run.run_id, "model_id": model, "state": states[model]["state"],
                "error_code": "explicit_confirmation_required_no_request_sent"})
        return 2
    adapter = SiliconFlowOrganizerModel.from_secret_file(args.secret_file, model=model, timeout_seconds=45)
    try:
        try:
            row = await run.run_once(model, lambda: adapter.extract(
                PAYLOAD, max_input_tokens=6000, max_output_tokens=1200))
        except Exception:
            row = run.status()["models"][model]
            _print({"run_id": run.run_id, "model_id": model, **row})
            return 2
        _print({"run_id": run.run_id, "model_id": model, **row})
        return 0 if row.get("state") == "completed" else 2
    finally:
        await adapter.aclose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="create a new private run ledger; does not call any model")
    status = commands.add_parser("status", help="inspect/resume-check an existing ledger; does not call any model")
    status.add_argument("--run-id", required=True)
    run_parser = commands.add_parser("run", help="attempt one pending model once; never retries")
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--model", choices=ALLOWED_MODEL_IDS, required=True)
    run_parser.add_argument("--secret-file", type=Path, required=True,
                            help="path to a private file; never pass the key as an argument")
    run_parser.add_argument("--confirm-real-request", action="store_true",
                            help="explicitly authorize this single model request")
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare":
            run = PersistentBenchmarkRun.create(args.state_dir)
            _print({"run_id": run.run_id, "state_dir": str(args.state_dir),
                    "models": list(ALLOWED_MODEL_IDS), "state": "prepared_no_requests_sent"})
            return 0
        run = PersistentBenchmarkRun.open(args.state_dir, args.run_id)
        if args.command == "status":
            _print(run.status())
            return 0
        return asyncio.run(_run(args, run))
    except Exception as exc:
        # Keep file paths, secret contents, headers, provider bodies and exception text out of output.
        _print({"state": "local_error", "error_code": getattr(exc, "code", type(exc).__name__)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
