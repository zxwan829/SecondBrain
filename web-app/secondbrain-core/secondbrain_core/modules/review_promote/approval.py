"""Dashboard-authenticated approval spool for the isolated Promote Worker.

The caller supplies an item/version to identify what they reviewed. Authority
comes only from Hermes request.state.session after the host auth gate succeeds.
"""
import hashlib
import json
import os
import re
import secrets
import stat
from datetime import datetime, timezone
from types import SimpleNamespace

from .worker import PromotionError, _open_dir_chain, _validate_relative_review_path


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TARGET = re.compile(r"^[^./\\\x00-\x1f\x7f:][^/\\\x00-\x1f\x7f:]{0,179}\.md$")


class ApprovalRequestError(Exception):
    pass


class DashboardAuthorizationError(ApprovalRequestError):
    pass


def _read_review(review_root, review_path):
    try:
        parts = _validate_relative_review_path(review_path)
    except PromotionError as exc:
        raise ApprovalRequestError(str(exc)) from exc
    root_fd = _open_dir_chain(os.path.abspath(review_root))
    current_fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ApprovalRequestError("Review item must be a regular file")
            chunks = []
            while True:
                chunk = os.read(file_fd, 65536)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise ApprovalRequestError("Review item could not be read safely") from exc
    finally:
        os.close(current_fd)
        os.close(root_fd)


class ApprovalFileStore:
    """Immutable per-request approval files; mount RW in Dashboard, RO in Worker."""
    def __init__(self, directory):
        if not os.path.isabs(directory):
            raise ApprovalRequestError("Approval directory must be an absolute provisioned path")
        self.directory = os.path.abspath(directory)

    def _record_name(self, request_id):
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ApprovalRequestError("Invalid request ID")
        return request_id + ".json"

    def create(self, record):
        name = self._record_name(record["request_id"])
        directory_fd = _open_dir_chain(self.directory)
        temp_name = ".approval-" + secrets.token_hex(16)
        temp_fd = None
        try:
            temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(temp_fd, view)
                view = view[written:]
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = None
            try:
                os.link(temp_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                        follow_symlinks=False)
            except FileExistsError:
                existing = self.read(record["request_id"])
                if all(existing.get(key) == record.get(key) for key in (
                    "request_id", "status", "approver_subject", "review_path",
                    "review_sha256", "target_filename",
                )):
                    return {"status": "already_approved", "request_id": record["request_id"]}
                raise ApprovalRequestError("Request ID already has a different approval")
            os.fsync(directory_fd)
            return {"status": "approved", "request_id": record["request_id"]}
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)

    def read(self, request_id):
        name = self._record_name(request_id)
        directory_fd = _open_dir_chain(self.directory)
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ApprovalRequestError("Approval record must be a regular file")
                chunks = []
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                record = json.loads(b"".join(chunks).decode("utf-8"))
            finally:
                os.close(fd)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise ApprovalRequestError("Approval record is unreadable or malformed") from exc
        finally:
            os.close(directory_fd)
        if record.get("request_id") != request_id or record.get("status") != "approved":
            raise ApprovalRequestError("Approval record identity or state mismatch")
        return record

    def has_version(self, review_path, review_sha256):
        directory_fd = _open_dir_chain(self.directory)
        try:
            for name in os.listdir(directory_fd):
                if not name.endswith(".json"):
                    continue
                record = self.read(name[:-5])
                if record and record.get("review_path") == review_path and record.get("review_sha256") == review_sha256:
                    return True
            return False
        finally:
            os.close(directory_fd)

    def approve_as(self, approver, body, review_root):
        """Create approval only after an upstream/Core auth adapter verifies owner."""
        if not isinstance(approver, str) or not approver:
            raise DashboardAuthorizationError("A verified approver identity is required")
        request_id = body.get("request_id")
        review_path = body.get("review_path")
        review_sha256 = body.get("review_sha256")
        target_filename = body.get("target_filename")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ApprovalRequestError("Invalid request ID")
        if not isinstance(review_sha256, str) or not _SHA256.fullmatch(review_sha256):
            raise ApprovalRequestError("Invalid Review content digest")
        if not isinstance(target_filename, str) or not _TARGET.fullmatch(target_filename):
            raise ApprovalRequestError("Unsafe Knowledge target filename")
        actual = hashlib.sha256(_read_review(review_root, review_path)).hexdigest()
        if actual != review_sha256:
            raise ApprovalRequestError("Review content changed; refresh before approving")
        record = {
            "request_id": request_id,
            "status": "approved",
            "approver_subject": approver,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "review_path": review_path,
            "review_sha256": actual,
            "target_filename": target_filename,
        }
        return self.create(record)


class FileApprovalSource:
    """Read-only Worker adapter for Dashboard-created approval records."""
    def __init__(self, directory):
        self.store = ApprovalFileStore(directory)

    def get_approved(self, request_id):
        record = self.store.read(request_id)
        return SimpleNamespace(**record) if record else None


class ReviewDecisionStore:
    """Durable decisions keyed by the exact Review path and content digest."""
    STATES = {"pending", "deferred", "approved", "promoting", "promoted", "failed"}

    def __init__(self, directory):
        if not os.path.isabs(directory):
            raise ApprovalRequestError("Decision directory must be an absolute provisioned path")
        self.directory = os.path.abspath(directory)

    @staticmethod
    def version_key(review_path, review_sha256):
        if not isinstance(review_sha256, str) or not _SHA256.fullmatch(review_sha256):
            raise ApprovalRequestError("Invalid Review content digest")
        try:
            _validate_relative_review_path(review_path)
        except PromotionError as exc:
            raise ApprovalRequestError(str(exc)) from exc
        return hashlib.sha256((review_path + "\0" + review_sha256).encode("utf-8")).hexdigest()

    def _read_dir_fd(self):
        return _open_dir_chain(self.directory)

    def get(self, review_path, review_sha256):
        key = self.version_key(review_path, review_sha256)
        directory_fd = self._read_dir_fd()
        try:
            try:
                fd = os.open(key + ".json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                return {"status": "pending", "review_path": review_path, "review_sha256": review_sha256}
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ApprovalRequestError("Decision record must be a regular file")
                chunks = []
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                record = json.loads(b"".join(chunks).decode("utf-8"))
            finally:
                os.close(fd)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise ApprovalRequestError("Decision record is unreadable or malformed") from exc
        finally:
            os.close(directory_fd)
        if record.get("review_path") != review_path or record.get("review_sha256") != review_sha256:
            raise ApprovalRequestError("Decision record version mismatch")
        return record

    def set(self, review_path, review_sha256, status, **fields):
        if status not in self.STATES:
            raise ApprovalRequestError("Unsupported Review decision state")
        key = self.version_key(review_path, review_sha256)
        directory_fd = self._read_dir_fd()
        temp_name = ".decision-" + secrets.token_hex(16)
        fd = None
        try:
            current = self.get(review_path, review_sha256)
            updated_at = datetime.now(timezone.utc).isoformat()
            record = {**current, **fields, "review_path": review_path,
                      "review_sha256": review_sha256, "status": status,
                      "updated_at": updated_at}
            history = list(current.get("history", []))
            event = {"status": status, "updated_at": updated_at}
            for field_name in ("request_id", "approver_subject", "decided_by", "error_code"):
                if fields.get(field_name) is not None:
                    event[field_name] = fields[field_name]
            history.append(event)
            record["history"] = history
            fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(temp_name, key + ".json", src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
            return record
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)
