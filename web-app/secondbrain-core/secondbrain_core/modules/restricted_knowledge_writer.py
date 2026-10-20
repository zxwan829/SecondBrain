"""Single-purpose, fail-closed local Knowledge writer candidate.

This module is deliberately not registered by the production Core app factory.
Core must authenticate the user, validate the exact Review/version/approval,
render the canonical approved bytes, and then connect over a private Unix socket.
The Writer pins its own Knowledge and receipt roots and accepts no caller paths.
"""
import base64
import errno
import fcntl
import hashlib
import json
import os
import re
import socket
import stat
import struct
import threading
from datetime import datetime, timedelta, timezone


MAX_REQUEST_BYTES = 1_500_000
MAX_OUTPUT_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 2048
MAX_REQUEST_TTL_SECONDS = 600
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TARGET = re.compile(r"^[^./\\\x00-\x1f\x7f:][^/\\\x00-\x1f\x7f:]{0,179}\.md$")
_FIELDS = {"protocol", "request_id", "target_filename", "review_sha256",
           "output_sha256", "output_base64", "expires_at"}


class WriterRejected(Exception):
    """A request was rejected without writing Knowledge."""


class RecoveryRequired(WriterRejected):
    """A prior write has an ambiguous durable state and needs human recovery."""


def _read_all(fd, limit=MAX_OUTPUT_BYTES):
    chunks = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise WriterRejected("target_too_large")
        chunks.append(chunk)


def _write_all(fd, payload):
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _open_pinned_dir(path, *, expected_group=None, expected_mode=0o700):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise WriterRejected("writer_root_unavailable")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open("/", flags)
    try:
        for part in path.split("/"):
            if not part:
                continue
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise WriterRejected("writer_root_permissions_unsafe")
        if expected_group is not None and info.st_gid != expected_group:
            raise WriterRejected("writer_root_permissions_unsafe")
        if stat.S_IMODE(info.st_mode) != expected_mode:
            raise WriterRejected("writer_root_permissions_unsafe")
        return fd
    except Exception:
        os.close(fd)
        raise


def _parse_expiry(value, now):
    if not isinstance(value, str) or len(value) > 64:
        raise WriterRejected("invalid_expiry")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WriterRejected("invalid_expiry") from exc
    if parsed.tzinfo is None or parsed <= now or (parsed - now).total_seconds() > MAX_REQUEST_TTL_SECONDS:
        raise WriterRejected("request_expired")
    return parsed


def _peer_uid(sock):
    """Return a kernel-authenticated Unix peer UID; unsupported platforms fail closed."""
    if not hasattr(socket, "SO_PEERCRED"):
        raise WriterRejected("peer_credentials_unavailable")
    try:
        credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", credentials)
        return uid
    except (OSError, struct.error) as exc:
        raise WriterRejected("peer_credentials_unavailable") from exc


class RestrictedKnowledgeWriter:
    """Accept one authorized exact-byte create-only request per request_id.

    ``expected_core_uid`` and the kernel peer credential adapter are environment
    claims until validated under an independently provisioned OS identity. Unit
    tests inject a synthetic credential function and never imply that isolation
    exists in this same-UID development environment.
    """

    def __init__(self, knowledge_root, receipt_root, expected_core_uid, *, expected_core_gid=None,
                 peer_uid_reader=_peer_uid):
        self.knowledge_root = os.path.abspath(knowledge_root)
        self.receipt_root = os.path.abspath(receipt_root)
        if self.knowledge_root == self.receipt_root or self.knowledge_root.startswith(self.receipt_root + os.sep) or self.receipt_root.startswith(self.knowledge_root + os.sep):
            raise ValueError("Knowledge and Writer receipt roots must be separate")
        if not isinstance(expected_core_uid, int) or expected_core_uid < 0:
            raise ValueError("A specific expected Core UID is required")
        if not isinstance(expected_core_gid, int) or expected_core_gid < 0:
            raise ValueError("A specific expected Core GID is required")
        self.expected_core_uid = expected_core_uid
        self.expected_core_gid = expected_core_gid
        self.peer_uid_reader = peer_uid_reader
        self._thread_lock = threading.Lock()
        self._knowledge_fd = _open_pinned_dir(
            self.knowledge_root, expected_group=self.expected_core_gid, expected_mode=0o750,
        )
        try:
            self._receipts_fd = _open_pinned_dir(self.receipt_root)
            self._lock_fd = os.open(".writer.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                                    0o600, dir_fd=self._receipts_fd)
            lock_info = os.fstat(self._lock_fd)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                    or lock_info.st_nlink != 1 or lock_info.st_mode & 0o077):
                raise WriterRejected("receipt_lock_unsafe")
        except Exception:
            if hasattr(self, "_lock_fd"):
                os.close(self._lock_fd)
            if hasattr(self, "_receipts_fd"):
                os.close(self._receipts_fd)
            os.close(self._knowledge_fd)
            raise

    def close(self):
        for name in ("_lock_fd", "_receipts_fd", "_knowledge_fd"):
            fd = getattr(self, name, None)
            if fd is not None:
                setattr(self, name, None)
                os.close(fd)

    def _validated(self, payload, peer_uid):
        if peer_uid != self.expected_core_uid:
            raise WriterRejected("peer_rejected")
        if not isinstance(payload, dict) or set(payload) != _FIELDS or payload.get("protocol") != 1:
            raise WriterRejected("invalid_protocol")
        request_id = payload.get("request_id")
        target = payload.get("target_filename")
        review_sha = payload.get("review_sha256")
        output_sha = payload.get("output_sha256")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise WriterRejected("invalid_request_id")
        if not isinstance(target, str) or not _TARGET.fullmatch(target):
            raise WriterRejected("invalid_target")
        if not isinstance(review_sha, str) or not _SHA256.fullmatch(review_sha):
            raise WriterRejected("invalid_review_digest")
        if not isinstance(output_sha, str) or not _SHA256.fullmatch(output_sha):
            raise WriterRejected("invalid_output_digest")
        _parse_expiry(payload.get("expires_at"), datetime.now(timezone.utc))
        encoded = payload.get("output_base64")
        if not isinstance(encoded, str) or len(encoded) > ((MAX_OUTPUT_BYTES + 2) // 3) * 4:
            raise WriterRejected("output_too_large")
        try:
            output = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise WriterRejected("invalid_output_encoding") from exc
        if not output or len(output) > MAX_OUTPUT_BYTES or hashlib.sha256(output).hexdigest() != output_sha:
            raise WriterRejected("output_digest_mismatch")
        try:
            output.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WriterRejected("output_not_utf8") from exc
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(canonical) > MAX_REQUEST_BYTES:
            raise WriterRejected("request_too_large")
        return request_id, target, review_sha, output_sha, output

    @staticmethod
    def _read_record(receipts_fd, name):
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=receipts_fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 8192:
                raise RecoveryRequired("receipt_state_unsafe")
            record = json.loads(_read_all(fd, 8192).decode("utf-8"))
            if (not isinstance(record, dict)
                    or set(record) != {"request_id", "target_filename", "review_sha256", "output_sha256", "state"}
                    or record.get("state") not in {"writing", "written"}):
                raise ValueError("invalid record")
            return record
        except (OSError, ValueError, UnicodeError) as exc:
            raise RecoveryRequired("receipt_state_invalid") from exc
        finally:
            os.close(fd)

    @staticmethod
    def _write_record(receipts_fd, name, record, *, create_only):
        temporary = ".receipt-" + hashlib.sha256(os.urandom(32)).hexdigest()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, 0o600, dir_fd=receipts_fd)
        try:
            _write_all(fd, (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            if create_only:
                os.link(temporary, name, src_dir_fd=receipts_fd, dst_dir_fd=receipts_fd, follow_symlinks=False)
            else:
                os.replace(temporary, name, src_dir_fd=receipts_fd, dst_dir_fd=receipts_fd)
            os.fsync(receipts_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=receipts_fd)
            except FileNotFoundError:
                pass

    def handle(self, payload, peer_uid):
        request_id, target, review_sha, output_sha, output = self._validated(payload, peer_uid)
        with self._thread_lock:
            if self._lock_fd is None or self._knowledge_fd is None or self._receipts_fd is None:
                raise RecoveryRequired("writer_closed")
            return self._handle_locked(request_id, target, review_sha, output_sha, output)

    def _handle_locked(self, request_id, target, review_sha, output_sha, output):
        knowledge_fd = self._knowledge_fd
        receipts_fd = self._receipts_fd
        lock_fd = self._lock_fd
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            record_name = request_id + ".json"
            fingerprint = {"request_id": request_id, "target_filename": target,
                           "review_sha256": review_sha, "output_sha256": output_sha}
            prior = self._read_record(receipts_fd, record_name)
            if prior:
                if any(prior.get(key) != value for key, value in fingerprint.items()):
                    raise WriterRejected("request_replay_conflict")
                if prior.get("state") == "writing":
                    raise RecoveryRequired("recovery_required")
                if prior.get("state") != "written":
                    raise RecoveryRequired("recovery_required")
                existing_fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=knowledge_fd)
                try:
                    existing_info = os.fstat(existing_fd)
                    existing = _read_all(existing_fd)
                    if not stat.S_ISREG(existing_info.st_mode) or existing_info.st_nlink != 1 or hashlib.sha256(existing).hexdigest() != output_sha:
                        raise RecoveryRequired("recovery_required")
                finally:
                    os.close(existing_fd)
                return {"status": "already_written", "request_id": request_id, "output_sha256": output_sha}

            try:
                os.stat(target, dir_fd=knowledge_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise WriterRejected("target_exists")
            self._write_record(receipts_fd, record_name, {**fingerprint, "state": "writing"}, create_only=True)
            file_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o640, dir_fd=knowledge_fd)
            try:
                file_info = os.fstat(file_fd)
                if not stat.S_ISREG(file_info.st_mode) or file_info.st_nlink != 1:
                    raise RecoveryRequired("recovery_required")
                os.fchmod(file_fd, 0o640)
                _write_all(file_fd, output)
                os.fsync(file_fd)
            finally:
                os.close(file_fd)
            os.fsync(knowledge_fd)
            self._write_record(receipts_fd, record_name, {**fingerprint, "state": "written"}, create_only=False)
            return {"status": "written", "request_id": request_id, "output_sha256": output_sha}
        except FileExistsError as exc:
            raise RecoveryRequired("target_race_recovery_required") from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EEXIST}:
                raise RecoveryRequired("recovery_required") from exc
            raise RecoveryRequired("writer_io_recovery_required") from exc
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def handle_socket(self, conn):
        """Serve one bounded JSON-line request over an already accepted Unix socket."""
        try:
            peer_uid = self.peer_uid_reader(conn)
            raw = bytearray()
            while len(raw) <= MAX_REQUEST_BYTES:
                chunk = conn.recv(min(65536, MAX_REQUEST_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if b"\n" in chunk:
                    break
            if len(raw) > MAX_REQUEST_BYTES or raw.count(b"\n") != 1 or not raw.endswith(b"\n"):
                raise WriterRejected("request_too_large_or_framing_invalid")
            payload = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=_unique_json_object)
            response = self.handle(payload, peer_uid)
        except RecoveryRequired:
            response = {"status": "recovery_required"}
        except (WriterRejected, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            response = {"status": "rejected"}
        except OSError:
            response = {"status": "rejected"}
        try:
            encoded = (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
            if len(encoded) <= MAX_RESPONSE_BYTES:
                conn.sendall(encoded)
        except OSError:
            pass


def serve_unix_socket(writer, socket_path, stop_event):
    """Serve one request at a time on a pre-provisioned local socket path.

    This is a library candidate only; the production Core factory does not
    import or start it. The socket parent and group membership must be created
    by a separately authorized OS provisioning step. This function refuses to
    replace any existing path and removes only the socket inode it created.
    """
    if not isinstance(socket_path, str) or not os.path.isabs(socket_path) or len(socket_path.encode()) >= 104:
        raise ValueError("An absolute short Unix socket path is required")
    parent = os.path.dirname(socket_path)
    parent_info = os.stat(parent, follow_symlinks=False)
    if (not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.geteuid()
            or parent_info.st_gid != writer.expected_core_gid
            or stat.S_IMODE(parent_info.st_mode) != 0o710):
        raise WriterRejected("socket_parent_permissions_unsafe")
    if writer.expected_core_gid is None or parent_info.st_gid != writer.expected_core_gid or os.getegid() != writer.expected_core_gid:
        raise WriterRejected("socket_group_unverified")
    try:
        os.lstat(socket_path)
    except FileNotFoundError:
        pass
    else:
        raise WriterRejected("socket_path_exists")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    created = False
    try:
        listener.bind(socket_path)
        created = True
        os.chmod(socket_path, 0o660, follow_symlinks=False)
        socket_info = os.stat(socket_path, follow_symlinks=False)
        if (not stat.S_ISSOCK(socket_info.st_mode) or socket_info.st_uid != os.geteuid()
                or socket_info.st_gid != writer.expected_core_gid or stat.S_IMODE(socket_info.st_mode) != 0o660):
            raise WriterRejected("socket_permissions_unsafe")
        listener.listen(8)
        listener.settimeout(0.2)
        while not stop_event.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(2)
                writer.handle_socket(connection)
    finally:
        listener.close()
        if created:
            try:
                info = os.stat(socket_path, follow_symlinks=False)
                if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.geteuid():
                    os.unlink(socket_path)
            except FileNotFoundError:
                pass


class RestrictedWriterIPCClient:
    """Core-side client for exact approved output bytes; never accepts a root path.

    Call only after the Core auth/approval/Review/version checks and canonical
    rendering have succeeded. The client is not wired into the production app.
    """

    def __init__(self, socket_path, *, timeout=2):
        if not isinstance(socket_path, str) or not os.path.isabs(socket_path) or len(socket_path.encode()) >= 104:
            raise ValueError("An absolute short Writer socket path is required")
        self.socket_path = socket_path
        self.timeout = min(max(float(timeout), 0.1), 10)

    def write_approved(self, request_id, target_filename, review_sha256, output_bytes, *, ttl_seconds=300):
        if not isinstance(output_bytes, bytes) or not 1 <= len(output_bytes) <= MAX_OUTPUT_BYTES:
            raise WriterRejected("output_too_large")
        if not 1 <= ttl_seconds <= MAX_REQUEST_TTL_SECONDS:
            raise WriterRejected("invalid_expiry")
        payload = {
            "protocol": 1,
            "request_id": request_id,
            "target_filename": target_filename,
            "review_sha256": review_sha256,
            "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "output_base64": base64.b64encode(output_bytes).decode("ascii"),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise WriterRejected("request_too_large")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(self.socket_path)
                client.sendall(encoded)
                client.shutdown(socket.SHUT_WR)
                response = bytearray()
                while len(response) <= MAX_RESPONSE_BYTES:
                    chunk = client.recv(min(1024, MAX_RESPONSE_BYTES + 1 - len(response)))
                    if not chunk:
                        break
                    response.extend(chunk)
                    if b"\n" in chunk:
                        break
                if len(response) > MAX_RESPONSE_BYTES or not response.endswith(b"\n"):
                    raise RecoveryRequired("writer_response_invalid")
                result = json.loads(response[:-1].decode("utf-8"), object_pairs_hook=_unique_json_object)
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RecoveryRequired("writer_response_unavailable") from exc
        if not isinstance(result, dict) or result.get("request_id") not in (None, request_id):
            raise RecoveryRequired("writer_response_binding_invalid")
        if result.get("status") == "recovery_required":
            raise RecoveryRequired("recovery_required")
        if result.get("status") == "rejected":
            raise WriterRejected("writer_rejected")
        if (result.get("status") not in {"written", "already_written"}
                or result.get("request_id") != request_id
                or result.get("output_sha256") != payload["output_sha256"]):
            raise RecoveryRequired("writer_response_binding_invalid")
        return result
