"""Read-only verifier for the immutable evidence behind a promoted note.

It accepts a source link only when the Knowledge bytes, approval, version Claim,
durable decision, Review bytes, and one exact promotion Audit row all agree.
It reads one Review path pinned by that evidence and never scans Raw or Private.
"""
import hashlib
import json
import os
import re
import stat

from .approval import ApprovalFileStore, ReviewDecisionStore
from .worker import _open_dir_chain, _validate_relative_review_path, render_promoted_markdown


_MARKER = re.compile(
    rb"^<!-- secondbrain-promote request_id=([A-Za-z0-9][A-Za-z0-9._-]{0,127}) "
    rb"review_sha256=([0-9a-f]{64}) -->\n"
)
MAX_AUDIT_BYTES = 4 * 1024 * 1024
MAX_REVIEW_BYTES = 2 * 1024 * 1024


class PromoteProvenanceVerifier:
    def __init__(self, review_root, approvals_root, audit_path, operations_root=None):
        self.review_root = os.path.abspath(review_root)
        self.approvals = ApprovalFileStore(os.path.abspath(approvals_root))
        self.decisions = ReviewDecisionStore(os.path.abspath(approvals_root))
        self.audit_path = os.path.abspath(audit_path)
        self.operations_root = os.path.abspath(operations_root) if operations_root else None

    def _confirmed_output(self, request_id, approval, review, content, output_sha256):
        """Rebuild approved bytes and bind B1b to its durable confirmation."""
        try:
            output = render_promoted_markdown(
                request_id, approval["review_sha256"], approval["approved_at"], review,
            )
        except Exception:
            return False
        expected = hashlib.sha256(output).hexdigest()
        if output != content or expected != output_sha256:
            return False
        if not request_id.startswith("b1b-"):
            # Legacy B1a approvals have no B1b operation record; reconstructed
            # canonical bytes still bind them to the durable approval and audit.
            return True
        if not self.operations_root:
            return False
        try:
            from .b1b import OperationStore
            operation = OperationStore(self.operations_root).get(request_id)
        except Exception:
            return False
        if not operation:
            return False
        try:
            from datetime import datetime
            confirmed_at = datetime.fromisoformat(operation["confirmed_at"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError):
            return False
        return bool(
            confirmed_at.tzinfo
            and operation.get("status") in {"promoted", "already_promoted"}
            and operation.get("confirm_intent") == "promote_exact_preview"
            and isinstance(operation.get("preview_id"), str)
            and re.fullmatch(r"[A-Za-z0-9_-]{32,80}", operation["preview_id"])
            and isinstance(operation.get("session_binding"), str)
            and re.fullmatch(r"[0-9a-f]{64}", operation["session_binding"])
            and operation.get("request_id") == request_id
            and operation.get("review_path") == approval.get("review_path")
            and operation.get("review_sha256") == approval.get("review_sha256")
            and operation.get("target_filename") == approval.get("target_filename")
            and operation.get("approved_at") == approval.get("approved_at")
            and operation.get("approver_subject") == approval.get("approver_subject")
            and operation.get("output_sha256") == expected
        )

    def _audit_for(self, request_id):
        directory_fd = _open_dir_chain(os.path.dirname(self.audit_path))
        try:
            fd = os.open(os.path.basename(self.audit_path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_NONBLOCK", 0),
                         dir_fd=directory_fd)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_size > MAX_AUDIT_BYTES):
                    return []
                chunks = []
                remaining = MAX_AUDIT_BYTES + 1
                while remaining:
                    chunk = os.read(fd, min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                payload = b"".join(chunks)
                if len(payload) > MAX_AUDIT_BYTES or (payload and not payload.endswith(b"\n")):
                    return []
                rows = []
                for line in payload.splitlines():
                    value = json.loads(line.decode("utf-8"))
                    if not isinstance(value, dict):
                        return []
                    if value.get("request_id") == request_id:
                        rows.append(value)
                return rows
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)

    def _read_review(self, review_path):
        parts = _validate_relative_review_path(review_path)
        root_fd = _open_dir_chain(self.review_root)
        current_fd = os.dup(root_fd)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd)
                os.close(current_fd)
                current_fd = child
            fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_NONBLOCK", 0), dir_fd=current_fd)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_size > MAX_REVIEW_BYTES):
                    return None
                chunks = []
                remaining = MAX_REVIEW_BYTES + 1
                while remaining:
                    chunk = os.read(fd, min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                payload = b"".join(chunks)
                if len(payload) > MAX_REVIEW_BYTES:
                    return None
                return payload
            finally:
                os.close(fd)
        finally:
            os.close(current_fd)
            os.close(root_fd)

    def verify(self, knowledge_path, content, output_sha256):
        if (not isinstance(knowledge_path, str) or "/" in knowledge_path
                or not re.fullmatch(r"[^/\\\x00-\x1f\x7f:]{1,180}\.md", knowledge_path)):
            return None
        if hashlib.sha256(content).hexdigest() != output_sha256:
            return None
        marker = _MARKER.match(content)
        if not marker:
            return None
        request_id, review_sha256 = marker.group(1).decode("ascii"), marker.group(2).decode("ascii")
        approval = self.approvals.read(request_id)
        if not approval:
            return None
        review_path = approval.get("review_path")
        target_filename = approval.get("target_filename")
        if (approval.get("request_id") != request_id or approval.get("status") != "approved"
                or approval.get("review_sha256") != review_sha256
                or target_filename != knowledge_path):
            return None
        claim = self.decisions.read_claim(review_path, review_sha256)
        decision = self.decisions.get(review_path, review_sha256)
        if (not claim or decision.get("status") != "promoted"
                or any(claim.get(key) != approval.get(key) for key in (
                    "request_id", "review_path", "review_sha256", "target_filename",
                    "approver_subject", "approved_at"))
                or any(decision.get(key) != approval.get(key) for key in (
                    "request_id", "target_filename", "approver_subject", "review_path", "review_sha256"))):
            return None
        rows = self._audit_for(request_id)
        if len(rows) != 1:
            return None
        row = rows[0]
        if (row.get("event") != "promoted"
                or any(row.get(key) != approval.get(key) for key in (
                    "request_id", "approver_subject", "approved_at", "review_path",
                    "review_sha256", "target_filename"))
                or row.get("output_sha256") != output_sha256):
            return None
        review = self._read_review(review_path)
        if review is None:
            return None
        if hashlib.sha256(review).hexdigest() != review_sha256:
            return None
        if not self._confirmed_output(request_id, approval, review, content, output_sha256):
            return None
        return {"kind": "review", "ref": review_path, "sha256": review_sha256,
                "request_id": request_id}
