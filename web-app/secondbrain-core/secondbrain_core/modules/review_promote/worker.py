"""Fail-closed, filesystem-only core for an isolated SecondBrain Promote worker.

The Dashboard approval adapter writes immutable approvals bound to request_id,
review_path, review_sha256, and target_filename. This worker module deliberately
has no HTTP endpoint, CLI approval flag, or secret.
"""
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from datetime import datetime, timezone
from typing import Optional, Protocol

from .review_adapter import ReviewFormatError, adapt_review_markdown


class PromotionError(Exception):
    pass


class ApprovalRecord:
    def __init__(self, request_id, status, approver_subject, approved_at,
                 review_path, review_sha256, target_filename):
        self.request_id = request_id
        self.status = status
        self.approver_subject = approver_subject
        self.approved_at = approved_at
        self.review_path = review_path
        self.review_sha256 = review_sha256
        self.target_filename = target_filename


class ApprovalSource(Protocol):
    def get_approved(self, request_id: str) -> Optional[ApprovalRecord]:
        ...


class NoApprovalSource:
    def get_approved(self, request_id):
        return None


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[^./\\\x00-\x1f\x7f:][^/\\\x00-\x1f\x7f:]{0,179}\.md$")


def _validate_relative_review_path(path):
    if not isinstance(path, str) or not path or path.startswith("/"):
        raise PromotionError("Review path must be relative")
    if "\\" in path or "\x00" in path:
        raise PromotionError("Invalid Review path")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise PromotionError("Review path traversal rejected")
    return parts


def _open_dir_chain(path):
    if not os.path.isabs(path):
        raise PromotionError("Configured roots must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open("/", flags)
    try:
        for component in path.split("/"):
            if not component:
                continue
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_review_file(review_root_fd, parts):
    current = os.dup(review_root_fd)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        for component in parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            os.close(current)
            current = next_fd
        file_fd = os.open(parts[-1], flags, dir_fd=current)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            os.close(file_fd)
            raise PromotionError("Review source must be a regular file")
        return file_fd
    finally:
        os.close(current)


def _read_all(fd):
    chunks = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_audit(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    entries = []
    payload = _read_all(fd)
    # Preserve incomplete bytes and stop. Automatic truncation could erase the
    # only evidence of a partially durable promotion event.
    if payload and not payload.endswith(b"\n"):
        raise PromotionError("Audit log has an incomplete tail; manual recovery required")
    for line in payload.splitlines():
        try:
            entries.append(json.loads(line.decode("utf-8")))
        except Exception as exc:
            raise PromotionError("Audit log is malformed; refusing promotion") from exc
    return entries


def _append_audit(fd, record):
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    os.lseek(fd, 0, os.SEEK_END)
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short audit write")
        view = view[written:]
    os.fsync(fd)


class PromoteWorker:
    def __init__(self, review_root, knowledge_root, audit_path, approval_source):
        self.review_root = os.path.abspath(review_root)
        self.knowledge_root = os.path.abspath(knowledge_root)
        self.audit_path = os.path.abspath(audit_path)
        self.approval_source = approval_source or NoApprovalSource()
        if self.audit_path == self.knowledge_root or self.audit_path.startswith(self.knowledge_root + os.sep):
            raise PromotionError("Audit log must be outside Knowledge")

    def promote(self, request_id, review_path, review_sha256):
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise PromotionError("Invalid request ID")
        if not isinstance(review_path, str) or not _SHA256.fullmatch(review_sha256 or ""):
            raise PromotionError("Explicit Review item and content version are required")
        approval = self.approval_source.get_approved(request_id)
        if approval is None:
            raise PromotionError("No trusted approval exists")
        if approval.request_id != request_id or approval.status != "approved":
            raise PromotionError("Approval identity or state mismatch")
        if approval.review_path != review_path or approval.review_sha256 != review_sha256:
            raise PromotionError("Requested Review item/version does not match server approval")
        if not approval.approver_subject or not approval.approved_at:
            raise PromotionError("Approval lacks trusted human identity or timestamp")
        if not _SHA256.fullmatch(approval.review_sha256 or ""):
            raise PromotionError("Approval lacks a valid pinned content digest")
        if not _SAFE_NAME.fullmatch(approval.target_filename or ""):
            raise PromotionError("Unsafe Knowledge filename")
        parts = _validate_relative_review_path(review_path)

        review_fd = _open_dir_chain(self.review_root)
        knowledge_fd = _open_dir_chain(self.knowledge_root)
        audit_dir_fd = _open_dir_chain(os.path.dirname(self.audit_path))
        try:
            try:
                audit_fd = os.open(os.path.basename(self.audit_path),
                                   os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                                   0o600, dir_fd=audit_dir_fd)
            except OSError as exc:
                raise PromotionError("Unable to securely open audit log") from exc
            try:
                audit_info = os.fstat(audit_fd)
                if not stat.S_ISREG(audit_info.st_mode) or audit_info.st_uid != os.geteuid() or \
                        stat.S_IMODE(audit_info.st_mode) != 0o600:
                    raise PromotionError("Audit log permissions are unsafe")
                fcntl.flock(audit_fd, fcntl.LOCK_EX)
                entries = _read_audit(audit_fd)
                previous = [e for e in entries if e.get("request_id") == request_id and e.get("event") == "promoted"]
                if previous:
                    existing = previous[-1]
                    if (existing.get("review_sha256") != approval.review_sha256 or
                            existing.get("review_path") != approval.review_path or
                            existing.get("target_filename") != approval.target_filename):
                        raise PromotionError("Request ID is already bound to different approved content")
                    target_fd = os.open(approval.target_filename,
                                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=knowledge_fd)
                    try:
                        current_hash = hashlib.sha256(_read_all(target_fd)).hexdigest()
                    finally:
                        os.close(target_fd)
                    if current_hash != existing.get("output_sha256"):
                        raise PromotionError("Previously promoted output changed")
                    return {"status": "already_promoted", "request_id": request_id,
                            "target_filename": approval.target_filename}

                source_fd = _open_review_file(review_fd, parts)
                try:
                    content = _read_all(source_fd)
                finally:
                    os.close(source_fd)
                digest = hashlib.sha256(content).hexdigest()
                if digest != approval.review_sha256:
                    raise PromotionError("Review content changed; approval is stale")
                try:
                    content = adapt_review_markdown(content, approval.approved_at)
                except ReviewFormatError as exc:
                    raise PromotionError(str(exc)) from exc
                output = ("<!-- secondbrain-promote request_id=" + request_id +
                          " review_sha256=" + digest + " -->\n").encode("utf-8") + content
                output_hash = hashlib.sha256(output).hexdigest()
                try:
                    existing_fd = os.open(approval.target_filename,
                                          os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=knowledge_fd)
                except FileNotFoundError:
                    existing_fd = None
                if existing_fd is not None:
                    try:
                        existing_bytes = _read_all(existing_fd)
                    finally:
                        os.close(existing_fd)
                    if hashlib.sha256(existing_bytes).hexdigest() != output_hash:
                        raise PromotionError("Knowledge target exists; refusing overwrite")
                    _append_audit(audit_fd, self._audit_record(approval, digest, output_hash, "promoted"))
                    return {"status": "already_promoted", "request_id": request_id,
                            "target_filename": approval.target_filename}

                temp_name = ".promote-" + secrets.token_hex(16)
                temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=knowledge_fd)
                try:
                    os.fchmod(temp_fd, 0o640)
                    view = memoryview(output)
                    while view:
                        written = os.write(temp_fd, view)
                        view = view[written:]
                    os.fsync(temp_fd)
                    os.close(temp_fd)
                    temp_fd = -1
                    try:
                        os.link(temp_name, approval.target_filename, src_dir_fd=knowledge_fd,
                                dst_dir_fd=knowledge_fd, follow_symlinks=False)
                    except FileExistsError as exc:
                        raise PromotionError("Knowledge target appeared; refusing overwrite") from exc
                    os.fsync(knowledge_fd)
                    _append_audit(audit_fd, self._audit_record(approval, digest, output_hash, "promoted"))
                finally:
                    if temp_fd >= 0:
                        os.close(temp_fd)
                    try:
                        os.unlink(temp_name, dir_fd=knowledge_fd)
                    except FileNotFoundError:
                        pass
                return {"status": "promoted", "request_id": request_id,
                        "target_filename": approval.target_filename}
            finally:
                os.close(audit_fd)
        finally:
            os.close(review_fd)
            os.close(knowledge_fd)
            os.close(audit_dir_fd)

    @staticmethod
    def _audit_record(approval, review_sha256, output_sha256, event):
        return {"event": event, "request_id": approval.request_id,
                "approver_subject": approval.approver_subject, "approved_at": approval.approved_at,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "review_path": approval.review_path, "review_sha256": review_sha256,
                "target_filename": approval.target_filename, "output_sha256": output_sha256}
