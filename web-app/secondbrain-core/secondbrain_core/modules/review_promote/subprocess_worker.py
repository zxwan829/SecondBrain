"""One-request subprocess entry point for the local Promote isolation candidate.

This creates a process/address-space and a narrow one-operation protocol. It is
not an OS identity or mount sandbox: the caller and child retain the same UID.
"""
import json
import os
import re
import sys

from .approval import FileApprovalSource
from .worker import PromoteWorker


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_RPC_BYTES = 8192


def _run(payload):
    expected = {"review_root", "knowledge_root", "approval_root", "audit_path",
                "request_id", "review_path", "review_sha256"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("invalid worker request")
    roots = (payload["review_root"], payload["knowledge_root"],
             payload["approval_root"], os.path.dirname(payload["audit_path"]))
    if any(not isinstance(path, str) or not os.path.isabs(path) for path in roots):
        raise ValueError("invalid worker roots")
    if not isinstance(payload["request_id"], str) or not _REQUEST_ID.fullmatch(payload["request_id"]):
        raise ValueError("invalid request ID")
    if not isinstance(payload["review_path"], str) or not _SHA256.fullmatch(payload["review_sha256"] or ""):
        raise ValueError("invalid Review binding")
    worker = PromoteWorker(
        payload["review_root"], payload["knowledge_root"], payload["audit_path"],
        FileApprovalSource(payload["approval_root"]),
    )
    return worker.promote(payload["request_id"], payload["review_path"], payload["review_sha256"])


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except (ImportError, OSError, ValueError):
        pass
    raw = sys.stdin.buffer.read(MAX_RPC_BYTES + 1)
    if len(raw) > MAX_RPC_BYTES:
        return 2
    try:
        payload = json.loads(raw.decode("utf-8"))
        result = _run(payload)
        response = {key: result[key] for key in ("status", "request_id", "target_filename") if key in result}
        sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        # Never return paths, source text or exception details over the Core IPC.
        sys.stdout.write('{"error":"worker_operation_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
