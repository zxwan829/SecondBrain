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
import fcntl
from contextlib import contextmanager
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


def _read_fd(fd):
    chunks = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _write_all(fd, payload):
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


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

    def _open_private_dir(self):
        try:
            fd = _open_dir_chain(self.directory)
        except OSError as exc:
            raise ApprovalRequestError("Private approval state is unavailable") from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(fd)
            raise ApprovalRequestError("Private approval state permissions are unsafe")
        return fd

    def _record_name(self, request_id):
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id) or \
                re.fullmatch(r"[0-9a-f]{64}", request_id):
            raise ApprovalRequestError("Invalid request ID")
        return request_id + ".json"

    def create(self, record):
        name = self._record_name(record["request_id"])
        directory_fd = self._open_private_dir()
        temp_name = ".approval-" + secrets.token_hex(16)
        temp_fd = None
        try:
            temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            _write_all(temp_fd, payload)
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
                    "approved_at", "review_sha256", "target_filename",
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
        directory_fd = self._open_private_dir()
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or \
                        stat.S_IMODE(info.st_mode) != 0o600:
                    raise ApprovalRequestError("Approval record must be a regular file")
                record = json.loads(_read_fd(fd).decode("utf-8"))
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
        return bool(self.records_for_version(review_path, review_sha256))

    def records_for_version(self, review_path, review_sha256):
        directory_fd = self._open_private_dir()
        records = []
        try:
            for name in os.listdir(directory_fd):
                if not name.endswith(".json"):
                    continue
                # ReviewDecisionStore keeps one 64-hex version-key JSON beside
                # request-ID approval files. It is a distinct record namespace.
                if re.fullmatch(r"[0-9a-f]{64}\.json", name):
                    continue
                record = self.read(name[:-5])
                if record and record.get("review_path") == review_path and record.get("review_sha256") == review_sha256:
                    records.append(record)
            return records
        finally:
            os.close(directory_fd)

    def approve_as(self, approver, body, review_root, approved_at=None):
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
            "approved_at": approved_at or datetime.now(timezone.utc).isoformat(),
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
            parts = _validate_relative_review_path(review_path)
        except PromotionError as exc:
            raise ApprovalRequestError(str(exc)) from exc
        canonical_path = "/".join(parts)
        return hashlib.sha256((canonical_path + "\0" + review_sha256).encode("utf-8")).hexdigest()

    @staticmethod
    def canonical_review_path(review_path):
        try:
            return "/".join(_validate_relative_review_path(review_path))
        except PromotionError as exc:
            raise ApprovalRequestError(str(exc)) from exc

    def _read_dir_fd(self):
        try:
            fd = _open_dir_chain(self.directory)
        except OSError as exc:
            raise ApprovalRequestError("Private approval state is unavailable") from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(fd)
            raise ApprovalRequestError("Private approval state permissions are unsafe")
        return fd

    @contextmanager
    def lock_version(self, review_path, review_sha256):
        """Serialize every mutation for one canonical Review version across processes."""
        key = self.version_key(review_path, review_sha256)
        directory_fd = self._read_dir_fd()
        lock_fd = None
        try:
            try:
                try:
                    lock_fd = os.open(key + ".lock", os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                                      dir_fd=directory_fd)
                except FileNotFoundError:
                    try:
                        lock_fd = os.open(key + ".lock", os.O_RDWR | os.O_CREAT | os.O_EXCL |
                                          getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
                    except FileExistsError:
                        lock_fd = os.open(key + ".lock", os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                                          dir_fd=directory_fd)
            except OSError as exc:
                raise ApprovalRequestError("Review version lock is unavailable or unsafe") from exc
            info = os.fstat(lock_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ApprovalRequestError("Review version lock permissions are unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield key
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def read_claim(self, review_path, review_sha256):
        key = self.version_key(review_path, review_sha256)
        directory_fd = self._read_dir_fd()
        try:
            try:
                fd = os.open(key + ".claim", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                return None
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                    raise ApprovalRequestError("Review version claim permissions are unsafe")
                record = json.loads(_read_fd(fd).decode("utf-8"))
            finally:
                os.close(fd)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise ApprovalRequestError("Review version claim is unreadable or malformed; recovery required") from exc
        finally:
            os.close(directory_fd)
        if not isinstance(record, dict) or record.get("version") != 1 or \
                not isinstance(record.get("request_id"), str) or \
                not _REQUEST_ID.fullmatch(record["request_id"]) or \
                not isinstance(record.get("target_filename"), str) or \
                not _TARGET.fullmatch(record["target_filename"]) or \
                not isinstance(record.get("approver_subject"), str) or not record["approver_subject"] or \
                not isinstance(record.get("approved_at"), str):
            raise ApprovalRequestError("Review version claim is inconsistent; recovery required")
        try:
            datetime.fromisoformat(record["approved_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApprovalRequestError("Review version claim is inconsistent; recovery required") from exc
        expected = self.version_key(record.get("review_path"), record.get("review_sha256"))
        if expected != key or record.get("version_key") != key:
            raise ApprovalRequestError("Review version claim identity mismatch; recovery required")
        return record

    def create_claim(self, review_path, review_sha256, request_id, target_filename, approver_subject):
        """Create one immutable, durable request/target binding without clobbering."""
        key = self.version_key(review_path, review_sha256)
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id) or \
                re.fullmatch(r"[0-9a-f]{64}", request_id):
            raise ApprovalRequestError("Invalid request ID")
        if not isinstance(target_filename, str) or not _TARGET.fullmatch(target_filename):
            raise ApprovalRequestError("Unsafe Knowledge target filename")
        if not isinstance(approver_subject, str) or not approver_subject:
            raise DashboardAuthorizationError("A verified approver identity is required")
        directory_fd = self._read_dir_fd()
        temp_name = ".claim-" + secrets.token_hex(16)
        temp_fd = None
        try:
            claim = {"version": 1, "version_key": key, "review_path": self.canonical_review_path(review_path),
                     "review_sha256": review_sha256, "request_id": request_id,
                     "target_filename": target_filename, "approver_subject": approver_subject,
                     "approved_at": datetime.now(timezone.utc).isoformat()}
            payload = (json.dumps(claim, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            _write_all(temp_fd, payload)
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = None
            try:
                os.link(temp_name, key + ".claim", src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                        follow_symlinks=False)
            except FileExistsError:
                existing = self.read_claim(review_path, review_sha256)
                if existing is None:
                    raise ApprovalRequestError("Review version claim changed; recovery required")
                if any(existing.get(field) != claim.get(field) for field in (
                    "request_id", "target_filename", "approver_subject", "review_path", "review_sha256",
                )):
                    raise ApprovalRequestError("Review version is already claimed; recovery required")
                return existing
            os.fsync(directory_fd)
            return claim
        except OSError as exc:
            raise ApprovalRequestError("Review version claim could not be persisted safely") from exc
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)

    def get(self, review_path, review_sha256):
        key = self.version_key(review_path, review_sha256)
        directory_fd = self._read_dir_fd()
        try:
            try:
                fd = os.open(key + ".json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                return {"status": "pending", "review_path": review_path, "review_sha256": review_sha256}
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or \
                        stat.S_IMODE(info.st_mode) != 0o600:
                    raise ApprovalRequestError("Decision record must be a regular file")
                record = json.loads(_read_fd(fd).decode("utf-8"))
            finally:
                os.close(fd)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise ApprovalRequestError("Decision record is unreadable or malformed") from exc
        finally:
            os.close(directory_fd)
        if not isinstance(record, dict) or record.get("status") not in self.STATES or \
                not isinstance(record.get("history", []), list) or \
                record.get("review_path") != review_path or record.get("review_sha256") != review_sha256:
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
            _write_all(fd, payload)
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
