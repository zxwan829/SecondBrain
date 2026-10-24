"""Bounded, read-only projection of the existing Promote audit ledger.

This is an internal source adapter only. It intentionally does not register an
HTTP route or define an Activity response contract.
"""
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone

from .worker import _open_dir_chain, _REQUEST_ID, _SAFE_NAME, _SHA256


MAX_AUDIT_BYTES = 1024 * 1024
MAX_AUDIT_ROWS = 5000
_MAX_FIELD = 2048
_FIELDS = frozenset({
    "event", "request_id", "approver_subject", "approved_at", "recorded_at",
    "review_path", "review_sha256", "target_filename", "output_sha256",
})
_REVIEW_ACTIVITY_STATUSES = frozenset({"pending", "deferred", "approved", "promoting", "promoted", "failed"})
_REVIEW_ACTIVITY_MAX_FILES = 2000
_REVIEW_ACTIVITY_MAX_BYTES = 2 * 1024 * 1024
_REVIEW_ACTIVITY_MAX_FILE_BYTES = 64 * 1024
_REVIEW_ACTIVITY_MAX_DEPTH = 16


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _timestamp(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _record(value):
    if not isinstance(value, dict) or set(value) != _FIELDS or value.get("event") != "promoted":
        return None
    if not isinstance(value.get("request_id"), str) or not _REQUEST_ID.fullmatch(value["request_id"]):
        return None
    if not isinstance(value.get("approver_subject"), str) or not value["approver_subject"] or \
            len(value["approver_subject"]) > _MAX_FIELD:
        return None
    if not _timestamp(value.get("approved_at")) or not _timestamp(value.get("recorded_at")):
        return None
    if not isinstance(value.get("review_path"), str) or not value["review_path"] or \
            len(value["review_path"]) > _MAX_FIELD:
        return None
    if not isinstance(value.get("target_filename"), str) or not _SAFE_NAME.fullmatch(value["target_filename"]):
        return None
    if not isinstance(value.get("review_sha256"), str) or not _SHA256.fullmatch(value["review_sha256"]):
        return None
    if not isinstance(value.get("output_sha256"), str) or not _SHA256.fullmatch(value["output_sha256"]):
        return None
    # Never pass paths, target names, approver identity or content digests to
    # Activity consumers. The opaque ID binds the existing immutable event.
    identity = "\0".join((value["request_id"], value["recorded_at"], value["output_sha256"]))
    return {
        "activity_id": hashlib.sha256(("promote\0" + identity).encode("utf-8")).hexdigest()[:32],
        "kind": "promote",
        "status": "promoted",
        "occurred_at": value["recorded_at"],
    }


class PromoteAuditActivityReadStore:
    """Read at most the newest 1 MiB / 5000 rows without creating files."""

    def __init__(self, audit_path):
        if audit_path:
            absolute = os.path.abspath(audit_path)
            # Resolve directory aliases such as macOS /private -> /var while
            # preserving the final component for O_NOFOLLOW validation.
            self.audit_path = os.path.join(os.path.realpath(os.path.dirname(absolute)),
                                           os.path.basename(absolute))
        else:
            self.audit_path = None

    def read(self):
        """Return ``(safe_rows, complete)``; uncertainty never claims complete."""
        if not self.audit_path:
            return [], False
        directory_fd = None
        fd = None
        try:
            directory = os.path.dirname(self.audit_path)
            basename = os.path.basename(self.audit_path)
            directory_fd = _open_dir_chain(directory)
            directory_before = os.fstat(directory_fd)
            try:
                fd = os.open(basename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                             getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                # A configured parent that disappeared is an incomplete source,
                # not an empty audit ledger. Only an absent leaf in the same
                # still-present directory represents the known empty state.
                try:
                    current_directory_fd = _open_dir_chain(directory)
                    try:
                        current_directory = os.fstat(current_directory_fd)
                        try:
                            os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
                            leaf_still_missing = False
                        except FileNotFoundError:
                            leaf_still_missing = True
                        same_directory = (directory_before.st_dev, directory_before.st_ino) == \
                                         (current_directory.st_dev, current_directory.st_ino)
                        if same_directory and leaf_still_missing:
                            return [], True
                    finally:
                        os.close(current_directory_fd)
                except OSError:
                    pass
                return [], False
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or
                    stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
                return [], False
            offset = max(0, before.st_size - MAX_AUDIT_BYTES)
            os.lseek(fd, offset, os.SEEK_SET)
            chunks = []
            remaining = min(before.st_size, MAX_AUDIT_BYTES)
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    return [], False
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(fd)
            try:
                entry = os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
                directory_after = os.fstat(directory_fd)
            except OSError:
                return [], False
            same_file = (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) == \
                        (entry.st_dev, entry.st_ino)
            same_directory = (directory_before.st_dev, directory_before.st_ino) == \
                             (directory_after.st_dev, directory_after.st_ino)
            stable_metadata = before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
            if not same_file or not same_directory or not stable_metadata or not stat.S_ISREG(entry.st_mode):
                return [], False

            complete = offset == 0
            if payload and offset:
                first_newline = payload.find(b"\n")
                if first_newline < 0:
                    return [], False
                payload = payload[first_newline + 1:]
                complete = False
            if payload and not payload.endswith(b"\n"):
                payload = payload[:payload.rfind(b"\n") + 1] if b"\n" in payload else b""
                complete = False
            lines = payload.splitlines()
            if len(lines) > MAX_AUDIT_ROWS:
                lines = lines[-MAX_AUDIT_ROWS:]
                complete = False
            rows = []
            for line in lines:
                try:
                    value = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
                    row = _record(value)
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                    complete = False
                    continue
                if row is None:
                    complete = False
                    continue
                rows.append(row)
            # Parsing may take time. Recheck the pathname and opened inode
            # after parsing so replacement or in-place mutation during that
            # interval cannot be reported as a stable snapshot.
            final_fd = os.fstat(fd)
            try:
                final_entry = os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
                final_directory_fd = _open_dir_chain(directory)
            except OSError:
                return [], False
            try:
                final_directory = os.fstat(final_directory_fd)
                stable_parent = (directory_before.st_dev, directory_before.st_ino) == \
                                (final_directory.st_dev, final_directory.st_ino)
                stable_file = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == \
                              (final_fd.st_dev, final_fd.st_ino, final_fd.st_size, final_fd.st_mtime_ns)
                same_entry = (before.st_dev, before.st_ino) == (final_entry.st_dev, final_entry.st_ino)
                if (not stable_parent or not stable_file or not same_entry or
                        not stat.S_ISREG(final_entry.st_mode)):
                    return [], False
            finally:
                os.close(final_directory_fd)
            return rows, complete
        except (OSError, ValueError, TypeError):
            return [], False
        finally:
            if fd is not None:
                os.close(fd)
            if directory_fd is not None:
                os.close(directory_fd)


class ReviewActivityReadStore:
    """Bounded metadata-only projection of Core-owned Review Markdown files."""

    def __init__(self, review_root):
        self.review_root = os.path.abspath(review_root) if review_root else None

    @staticmethod
    def _metadata(payload):
        try:
            lines = payload.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            return None
        if not lines or lines[0].strip() != "---":
            return None
        status = None
        captured_at = None
        closed = False
        for line in lines[1:256]:
            if line.strip() == "---":
                closed = True
                break
            match = re.match(r"^(review_status|status):\s*['\"]?([^'\"]+)['\"]?\s*$", line)
            if match:
                status = match.group(2).strip()
            match = re.match(r"^captured_at:\s*(.*?)\s*$", line)
            if match:
                captured_at = match.group(1).strip()
                if captured_at.startswith('"'):
                    try:
                        captured_at = json.loads(captured_at)
                    except (ValueError, TypeError):
                        return None
        if (not closed or status not in _REVIEW_ACTIVITY_STATUSES
                or not isinstance(captured_at, str)):
            return None
        return status, captured_at

    def read(self, start, end, zone):
        """Return minimal rows and completeness; never expose paths or content."""
        if not self.review_root:
            return [], False
        root_fd = None
        rows = []
        complete = True
        files_read = 0
        bytes_read = 0

        def visit(directory_fd, relative_parts, depth):
            nonlocal complete, files_read, bytes_read
            if depth > _REVIEW_ACTIVITY_MAX_DEPTH:
                complete = False
                return
            try:
                names = sorted(os.listdir(directory_fd))
            except OSError:
                complete = False
                return
            for name in names:
                try:
                    entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError:
                    complete = False
                    continue
                if stat.S_ISLNK(entry.st_mode):
                    complete = False
                    continue
                if stat.S_ISDIR(entry.st_mode):
                    if name.startswith("."):
                        complete = False
                        continue
                    try:
                        child_fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                           getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
                    except OSError:
                        complete = False
                        continue
                    try:
                        child = os.fstat(child_fd)
                        if child.st_uid != os.geteuid() or child.st_mode & 0o077:
                            complete = False
                            continue
                        visit(child_fd, (*relative_parts, name), depth + 1)
                    finally:
                        os.close(child_fd)
                    continue
                if not name.lower().endswith(".md"):
                    continue
                files_read += 1
                if files_read > _REVIEW_ACTIVITY_MAX_FILES:
                    complete = False
                    return
                if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.geteuid()
                        or entry.st_mode & 0o077 or entry.st_nlink != 1
                        or entry.st_size > _REVIEW_ACTIVITY_MAX_FILE_BYTES
                        or bytes_read + entry.st_size > _REVIEW_ACTIVITY_MAX_BYTES):
                    complete = False
                    continue
                try:
                    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                                 getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
                    try:
                        before = os.fstat(fd)
                        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                                or before.st_mode & 0o077 or before.st_nlink != 1
                                or before.st_size > _REVIEW_ACTIVITY_MAX_FILE_BYTES):
                            raise OSError("Review entry changed to an unsafe file")
                        payload = bytearray()
                        while len(payload) <= _REVIEW_ACTIVITY_MAX_FILE_BYTES:
                            chunk = os.read(fd, min(8192, _REVIEW_ACTIVITY_MAX_FILE_BYTES + 1 - len(payload)))
                            if not chunk:
                                break
                            payload.extend(chunk)
                        after = os.fstat(fd)
                    finally:
                        os.close(fd)
                except OSError:
                    complete = False
                    continue
                try:
                    current_entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError:
                    complete = False
                    continue
                if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                        or (before.st_dev, before.st_ino) !=
                        (current_entry.st_dev, current_entry.st_ino)
                        or not stat.S_ISREG(current_entry.st_mode)
                        or stat.S_ISLNK(current_entry.st_mode)
                        or len(payload) != before.st_size or len(payload) > _REVIEW_ACTIVITY_MAX_FILE_BYTES):
                    complete = False
                    continue
                bytes_read += len(payload)
                metadata = self._metadata(bytes(payload))
                if metadata is None:
                    complete = False
                    continue
                status, captured_at = metadata
                try:
                    stamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    complete = False
                    continue
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=zone)
                stamp = stamp.astimezone(timezone.utc)
                if not (start <= stamp.astimezone(zone).date() <= end):
                    continue
                relative = "/".join((*relative_parts, name))
                digest = hashlib.sha256(payload).hexdigest()
                activity_id = hashlib.sha256(
                    f"secondbrain-activity-v1\0review\0{relative}\0{digest}".encode("utf-8")
                ).hexdigest()[:32]
                rows.append({
                    "activity_id": activity_id,
                    "kind": "review",
                    "status": status,
                    "occurred_at": stamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                })

        try:
            root_fd = _open_dir_chain(self.review_root)
            root_info = os.fstat(root_fd)
            if root_info.st_uid != os.geteuid() or root_info.st_mode & 0o077:
                return [], False
            visit(root_fd, (), 0)
        except (OSError, ValueError, TypeError):
            return [], False
        finally:
            if root_fd is not None:
                os.close(root_fd)
        return rows, complete
