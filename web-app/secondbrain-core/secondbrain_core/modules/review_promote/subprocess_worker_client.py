"""Narrow Core-to-worker IPC client for synthetic/local Promote validation."""
import json
import os
import subprocess
import sys
from pathlib import Path

from .worker import PromotionError


MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 4096


class SubprocessPromoteWorker:
    """Execute one exact Promote request in a resource-limited child process.

    The child is deliberately given no App credentials or general environment.
    The local candidate does not change OS UID or mounts; deployment isolation
    remains blocked until a separate identity and filesystem ACLs are provisioned.
    """

    def __init__(self, review_root, knowledge_root, audit_path, approval_root, *, timeout=35):
        self.review_root = os.path.abspath(review_root)
        self.knowledge_root = os.path.abspath(knowledge_root)
        self.audit_path = os.path.abspath(audit_path)
        self.approval_root = os.path.abspath(approval_root)
        self.timeout = min(max(float(timeout), 1), 60)
        self.package_root = str(Path(__file__).resolve().parents[3])

    def promote(self, request_id, review_path, review_sha256):
        payload = json.dumps({"review_root": self.review_root,
                              "knowledge_root": self.knowledge_root,
                              "approval_root": self.approval_root,
                              "audit_path": self.audit_path,
                              "request_id": request_id,
                              "review_path": review_path,
                              "review_sha256": review_sha256},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise PromotionError("Worker request exceeds the safe protocol limit")
        env = {"PYTHONNOUSERSITE": "1", "PYTHONPATH": self.package_root,
               "PYTHONUTF8": "1"}
        try:
            result = subprocess.run(
                [sys.executable, "-s", "-m", "secondbrain_core.modules.review_promote.subprocess_worker"],
                input=payload, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=self.package_root, env=env, close_fds=True, timeout=self.timeout,
                check=False, start_new_session=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PromotionError("Isolated worker did not complete safely") from exc
        if len(result.stdout) > MAX_RESPONSE_BYTES or result.returncode != 0:
            raise PromotionError("Isolated worker rejected the operation")
        try:
            response = json.loads(result.stdout.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PromotionError("Isolated worker response is invalid") from exc
        if not isinstance(response, dict) or response.get("status") not in {"promoted", "already_promoted"}:
            raise PromotionError("Isolated worker operation failed")
        if response.get("request_id") != request_id:
            raise PromotionError("Isolated worker response binding is invalid")
        return response
