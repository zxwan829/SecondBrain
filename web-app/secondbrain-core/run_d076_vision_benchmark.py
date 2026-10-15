#!/usr/bin/env python3
"""Explicit one-model-at-a-time runner for the synthetic D076 vision benchmark."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIXTURES = REPO / "docs/benchmarks/d076-siliconflow-multimodal/fixtures"
DEFAULT_STATE_DIR = Path.home() / ".local/state/secondbrain/d076-vision-benchmark"
IMAGES = (
    FIXTURES / "03-simulated-software-ui.png",
    FIXTURES / "04-synthetic-chart.png",
    FIXTURES / "07-synthetic-scan-page.png",
)
PROMPT = (
    "分析随附的3张合成图片，只输出紧凑、合法的JSON对象，不要Markdown围栏或解释段落。"
    "格式：{\"images\":[{\"image_index\":1,\"text\":[\"可见原文\"],"
    "\"key_facts\":[{\"label\":\"字段\",\"value\":\"值\",\"evidence\":\"最短可核对依据\"}],"
    "\"ui_info\":[\"重要界面状态或元素\"]}]}。每张图最多列10条文字、8条事实、5条界面信息；"
    "只记录清晰可见内容，数字原样抄录，不推测、不重复、不写长篇描述。"
    "所有事实须对应正确图片编号，证据用简短原文或图表位置说明。"
)

sys.path.insert(0, str(HERE))
from secondbrain_core.modules.siliconflow_organizer import read_private_secret  # noqa: E402
from secondbrain_core.modules.vision_benchmark import (  # noqa: E402
    MODEL_POLICIES,
    VisionBenchmarkAdapter,
    build_request,
)
from secondbrain_core.modules.vision_benchmark_run import (  # noqa: E402
    VISION_MODEL_ORDER,
    PersistentVisionRun,
)


def _print(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _inputs():
    paths = []
    raw_images = []
    for path in IMAGES:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("synthetic_fixture_unavailable")
        paths.append(path)
        raw_images.append(path.read_bytes())
    return paths, raw_images


async def _run(args, run):
    model = args.model
    status = run.status()["models"]
    target = status.get(model, {})
    if not run.may_run_in_order(model):
        _print({"run_id": run.run_id, "model_id": model, "state": target.get("state"),
                "error_code": "prior_vision_model_not_completed_no_request_sent"})
        return 2
    if target.get("state") != "pending" or target.get("attempts") != 0:
        _print({"run_id": run.run_id, "model_id": model, **target,
                "error_code": "model_already_attempted_no_request_sent"})
        return 2
    if not args.confirm_real_request:
        _print({"run_id": run.run_id, "model_id": model, "state": "pending",
                "error_code": "explicit_confirmation_required_no_request_sent"})
        return 2
    # Validate the dedicated secret's ownership/permissions before reserving an attempt.
    api_key = read_private_secret(args.secret_file)
    paths, images = _inputs()
    body = build_request(model, PROMPT, images, max_output_tokens=2000, json_mode=False)
    metadata = {
        "fixture_sha256": [hashlib.sha256(raw).hexdigest() for raw in images],
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "image_count": len(images),
        "max_output_tokens": body["max_tokens"],
        "json_mode": False,
        "image_detail": MODEL_POLICIES[model].image_detail,
    }
    adapter = VisionBenchmarkAdapter(api_key, timeout_seconds=45)
    del api_key
    try:
        try:
            row = await run.run_once(
                model, request_metadata=metadata,
                invoke=lambda: adapter.analyze(model, PROMPT, images, max_output_tokens=2000, json_mode=False),
            )
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
    prepare = commands.add_parser("prepare", help="create private ledger; no network")
    prepare.add_argument("--models", nargs="+", choices=VISION_MODEL_ORDER,
                         help="optional ordered subset for an independent run")
    status = commands.add_parser("status", help="inspect ledger; no network")
    status.add_argument("--run-id", required=True)
    run_cmd = commands.add_parser("run", help="one authorized model request, no retry")
    run_cmd.add_argument("--run-id", required=True)
    run_cmd.add_argument("--model", choices=VISION_MODEL_ORDER, required=True)
    run_cmd.add_argument("--secret-file", type=Path, required=True)
    run_cmd.add_argument("--confirm-real-request", action="store_true")
    annotate = commands.add_parser("annotate", help="persist offline human evaluation; no network")
    annotate.add_argument("--run-id", required=True)
    annotate.add_argument("--model", choices=VISION_MODEL_ORDER, required=True)
    annotate.add_argument("--evaluation-json", type=Path, required=True)
    annotate.add_argument("--estimated-cost-usd", type=float, required=True)
    annotate.add_argument("--pricing-as-of", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            model_order = tuple(args.models) if args.models else VISION_MODEL_ORDER
            run = PersistentVisionRun.create(args.state_dir, model_order=model_order)
            _print({"run_id": run.run_id, "state": "prepared_no_requests_sent",
                    "model_order": list(model_order)})
            return 0
        run = PersistentVisionRun.open(args.state_dir, args.run_id)
        if args.command == "status":
            _print(run.status())
            return 0
        if args.command == "annotate":
            evaluation = json.loads(args.evaluation_json.read_text(encoding="utf-8"))
            run.annotate(args.model, evaluation=evaluation,
                         estimated_cost_usd=args.estimated_cost_usd,
                         pricing_as_of=args.pricing_as_of)
            _print({"run_id": run.run_id, "model_id": args.model,
                    "state": run.status()["models"][args.model]["state"],
                    "evaluation_saved": True})
            return 0
        return asyncio.run(_run(args, run))
    except Exception as exc:
        # No exception body, request headers, credential contents, or fixture bytes are emitted.
        _print({"state": "local_error", "error_code": getattr(exc, "code", type(exc).__name__)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
