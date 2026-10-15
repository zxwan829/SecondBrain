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
    "请分别分析这三张合成图片，并严格返回 JSON 对象，结构为："
    "{\"images\":[{\"index\":1,\"readable_text\":[{\"text\":\"\",\"evidence\":\"\"}],"
    "\"facts\":[{\"label\":\"\",\"value\":\"\",\"evidence\":\"\"}],"
    "\"description\":\"\"}]}。第一张是仿真软件界面，第二张是图表，第三张是扫描页。"
    "仅记录图中清楚可见的文字、数字和画面内容；证据须为图中文字的原样短引。"
    "不推测缺失信息。文字识别与画面描述分开。"
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
    body = build_request(model, PROMPT, images, max_output_tokens=800, json_mode=False)
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
                invoke=lambda: adapter.analyze(model, PROMPT, images, max_output_tokens=800, json_mode=False),
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
    commands.add_parser("prepare", help="create private ledger; no network")
    status = commands.add_parser("status", help="inspect ledger; no network")
    status.add_argument("--run-id", required=True)
    run_cmd = commands.add_parser("run", help="one authorized model request, no retry")
    run_cmd.add_argument("--run-id", required=True)
    run_cmd.add_argument("--model", choices=VISION_MODEL_ORDER, required=True)
    run_cmd.add_argument("--secret-file", type=Path, required=True)
    run_cmd.add_argument("--confirm-real-request", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            run = PersistentVisionRun.create(args.state_dir)
            _print({"run_id": run.run_id, "state": "prepared_no_requests_sent",
                    "model_order": list(VISION_MODEL_ORDER)})
            return 0
        run = PersistentVisionRun.open(args.state_dir, args.run_id)
        if args.command == "status":
            _print(run.status())
            return 0
        return asyncio.run(_run(args, run))
    except Exception as exc:
        # No exception body, request headers, credential contents, or fixture bytes are emitted.
        _print({"state": "local_error", "error_code": getattr(exc, "code", type(exc).__name__)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
