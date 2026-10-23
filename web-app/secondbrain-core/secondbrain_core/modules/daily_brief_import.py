"""Core persistence primitives for the frozen, manually approved Brief write."""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import secrets
import stat
import threading
import time
from datetime import date, datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .daily_brief_store import (
    _MAX_RECORD_BYTES,
    _MAX_SOURCE_REFS,
    _unique_object,
    _open_dir_chain,
    _validate_record,
)


_IDEMPOTENCY_LOCKS = tuple(threading.RLock() for _ in range(64))
_MAX_IDEMPOTENCY_OPERATIONS = 2000
_MAX_IMPORT_ROOT_ENTRIES = 5000


class BriefImportRejected(ValueError):
    """Candidate rejected before persistence; message contains no source data."""


class BriefImportForbidden(BriefImportRejected):
    """A required source permission is no longer available."""


class BriefImportStale(BriefImportRejected):
    """A selected source no longer resolves to the submitted version."""


class BriefImportConflict(RuntimeError):
    """A different record already owns the requested calendar date."""


class BriefImportUnavailable(RuntimeError):
    """The private record root cannot safely persist this candidate."""


class BriefAuditUnavailable(OSError):
    """Audit append failed; published marks a complete atomic log replacement."""

    def __init__(self, message, *, published=False):
        super().__init__(message)
        self.published = published


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _open_lock_at(root_fd, name, *, label):
    """Retry the bounded first-create race seen with concurrent openat(O_CREAT)."""
    for attempt in range(32):
        try:
            return os.open(name, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                           0o600, dir_fd=root_fd)
        except FileNotFoundError:
            if attempt == 31:
                raise
            info = os.fstat(root_fd)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077):
                raise BriefImportUnavailable(f"{label} root unavailable")
            time.sleep(min(0.01, 0.001 * (attempt + 1)))
    raise BriefImportUnavailable(f"{label} lock unavailable")


class DailyBriefImportStore:
    """Create-only persistence primitive for a verified, explicitly supplied brief.

    ``source_verifier`` must resolve each exact ref through an authoritative
    Core verifier. It is called before and after the atomic create. The normal
    GET path must still revalidate refs on every read.
    """

    def __init__(self, root: str, *, max_record_bytes=_MAX_RECORD_BYTES,
                 max_source_refs=_MAX_SOURCE_REFS, clock: Callable | None = None,
                 id_factory: Callable[[], str] | None = None):
        self.root = root if isinstance(root, str) and os.path.isabs(root) else ""
        self.configured = bool(root)
        self.max_record_bytes = max_record_bytes
        self.max_source_refs = max_source_refs
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.id_factory = id_factory or (lambda: "brief-" + secrets.token_hex(16))

    def _validate_candidate(self, candidate, *, brief_id=None, generated_at=None):
        fields = {"date", "timezone", "categories", "summary", "source_refs"}
        if not isinstance(candidate, dict) or set(candidate) != fields:
            raise BriefImportRejected("invalid brief candidate")
        day, timezone_name = candidate["date"], candidate["timezone"]
        try:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                raise ValueError
            if not isinstance(timezone_name, str) or not timezone_name or len(timezone_name) > 64:
                raise ValueError
            zone = ZoneInfo(timezone_name)
        except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
            raise BriefImportRejected("invalid brief candidate") from exc
        refs = candidate["source_refs"]
        if (not isinstance(refs, list) or not refs or len(refs) > self.max_source_refs
                or any(not isinstance(ref, dict) or ref.get("kind") not in {"task", "project", "journal"}
                       for ref in refs)):
            raise BriefImportRejected("invalid brief candidate")
        record = {
            "brief_id": brief_id or self.id_factory(),
            "date": day,
            "timezone": timezone_name,
            "generated_at": generated_at or self.clock().astimezone(zone).isoformat(timespec="seconds"),
            "generation_status": "generated",
            "categories": candidate["categories"],
            "summary": candidate["summary"],
            "source_refs": refs,
        }
        if not _validate_record(record, day, timezone_name, zone, self.max_source_refs):
            raise BriefImportRejected("invalid brief candidate")
        return record

    @staticmethod
    def _verify(refs, verifier):
        if not callable(verifier):
            raise BriefImportRejected("source verification unavailable")
        try:
            for ref in refs:
                result = verifier(dict(ref))
                if result is not True and result != "verified":
                    if result == "forbidden":
                        raise BriefImportForbidden("source permission denied")
                    if result in {"missing", "stale"}:
                        raise BriefImportStale("source selection is stale")
                    if result in {"unavailable", "failed"}:
                        raise BriefImportUnavailable("source verification unavailable")
                    raise BriefImportRejected("source verification failed")
        except (BriefImportRejected, BriefImportUnavailable):
            raise
        except Exception as exc:
            raise BriefImportRejected("source verification failed") from exc

    @staticmethod
    def _resolve_verifier(source_verifier, source_verifier_factory):
        try:
            return source_verifier_factory() if source_verifier_factory else source_verifier
        except (BriefImportRejected, BriefImportUnavailable):
            raise
        except Exception as exc:
            raise BriefImportRejected("source verification unavailable") from exc

    @staticmethod
    def _read_existing(root_fd, name, limit):
        deadline = time.monotonic() + 0.5
        while True:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077 or info.st_size < 0 or info.st_size > limit):
                    raise BriefImportUnavailable("existing record is not private and bounded")
                if info.st_nlink != 1:
                    if time.monotonic() < deadline:
                        time.sleep(0.001)
                        continue
                    raise BriefImportUnavailable("existing record link count is unsafe")
                parts = []
                remaining = limit + 1
                while remaining:
                    chunk = os.read(fd, min(65536, remaining))
                    if not chunk:
                        break
                    parts.append(chunk)
                    remaining -= len(chunk)
                payload = b"".join(parts)
                if len(payload) != info.st_size or len(payload) > limit:
                    raise BriefImportUnavailable("existing record is changing")
                return payload, (info.st_dev, info.st_ino)
            finally:
                os.close(fd)

    def import_record(self, candidate, *, source_verifier=None, source_verifier_factory=None,
                      brief_id=None, generated_at=None, allow_duplicate=True):
        if not self.configured or not self.root:
            raise BriefImportUnavailable("record root unavailable")
        record = self._validate_candidate(candidate, brief_id=brief_id, generated_at=generated_at)
        verifier = self._resolve_verifier(source_verifier, source_verifier_factory)
        self._verify(record["source_refs"], verifier)
        payload = _canonical(record)
        if len(payload) > self.max_record_bytes:
            raise BriefImportRejected("brief exceeds persistence budget")
        try:
            root_fd = _open_dir_chain(self.root)
        except OSError as exc:
            raise BriefImportUnavailable("record root unavailable") from exc
        temp_name = ".brief-tmp-" + secrets.token_hex(16)
        final_name = record["date"] + ".json"
        try:
            root_info = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                    or root_info.st_mode & 0o077):
                raise BriefImportUnavailable("record root is not private")
            fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                # Hard-link publication is atomic and create-only; it cannot replace a date.
                os.link(temp_name, final_name, src_dir_fd=root_fd, dst_dir_fd=root_fd,
                        follow_symlinks=False)
                created = True
                # Remove the temporary name before validation so the published
                # record has the single-link invariant required by the reader.
                os.unlink(temp_name, dir_fd=root_fd)
            except FileExistsError:
                created = False
                if not allow_duplicate:
                    raise BriefImportConflict("date already has a record")
                old_payload, _old_identity = self._read_existing(
                    root_fd, final_name, self.max_record_bytes)
                try:
                    old = json.loads(old_payload.decode("utf-8"), object_pairs_hook=_unique_object)
                    old_zone = ZoneInfo(record["timezone"])
                    if not _validate_record(old, record["date"], record["timezone"],
                                            old_zone, self.max_source_refs):
                        raise ValueError("existing record schema invalid")
                except Exception:
                    raise BriefImportConflict("date already has a record")
                # Idempotent content comparison deliberately ignores generated ID/time.
                comparable = {k: old.get(k) for k in ("date", "timezone", "categories", "summary", "source_refs")}
                wanted = {k: record[k] for k in comparable}
                if comparable != wanted:
                    raise BriefImportConflict("date already has a different record")
                record = old
            os.fsync(root_fd)
            # Recheck immediately after publication; GET will independently recheck later.
            try:
                verifier = self._resolve_verifier(source_verifier, source_verifier_factory)
                self._verify(record["source_refs"], verifier)
            except BriefImportRejected:
                if created:
                    try:
                        current, identity = self._read_existing(root_fd, final_name, self.max_record_bytes)
                        if identity and hashlib.sha256(current).digest() == hashlib.sha256(payload).digest():
                            os.unlink(final_name, dir_fd=root_fd)
                            os.fsync(root_fd)
                    except (OSError, BriefImportUnavailable):
                        pass
                raise
            return {"status": "created" if created else "duplicate",
                    "brief_id": record["brief_id"], "date": record["date"],
                    "timezone": record["timezone"],
                    "record_sha256": hashlib.sha256(_canonical(record)).hexdigest()}
        except BriefImportRejected:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise BriefImportUnavailable("record persistence failed") from exc
        finally:
            try:
                os.unlink(temp_name, dir_fd=root_fd)
            except OSError:
                pass
            os.close(root_fd)

    @staticmethod
    def _read_operation(root_fd, name):
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 4096):
                raise BriefImportUnavailable("idempotency metadata unavailable")
            payload = os.read(fd, 4097)
            if len(payload) != info.st_size or len(payload) > 4096:
                raise BriefImportUnavailable("idempotency state incomplete")
        finally:
            os.close(fd)
        try:
            value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except Exception as exc:
            raise BriefImportUnavailable("idempotency state malformed") from exc
        expected = {"request_sha256", "actor_sha256", "date", "timezone", "brief_id", "operation_id",
                    "generated_at", "state", "record_sha256"}
        if (not isinstance(value, dict) or set(value) != expected
                or value["state"] not in {"pending", "committed"}):
            raise BriefImportUnavailable("idempotency state invalid")
        return value

    @staticmethod
    def _pending_name(day):
        if (not isinstance(day, str) or len(day) != 10
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)):
            raise BriefImportUnavailable("pending state date invalid")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except ValueError as exc:
            raise BriefImportUnavailable("pending state date invalid") from exc
        return f".pending-{day}.json"

    @staticmethod
    def _read_pending_marker(root_fd, day):
        name = DailyBriefImportStore._pending_name(day)
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or info.st_size < 0 or info.st_size > 4096):
                raise BriefImportUnavailable("pending state unavailable")
            payload = os.read(fd, 4097)
            if len(payload) != info.st_size or len(payload) > 4096:
                raise BriefImportUnavailable("pending state incomplete")
        finally:
            os.close(fd)
        try:
            value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except Exception as exc:
            raise BriefImportUnavailable("pending state malformed") from exc
        expected = {"actor_sha256", "date", "key_sha256", "operation_id", "request_sha256"}
        if (not isinstance(value, dict) or set(value) != expected or value["date"] != day
                or not all(isinstance(value[key], str) and re.fullmatch(r"[a-f0-9]{64}", value[key])
                           for key in ("actor_sha256", "key_sha256", "request_sha256"))
                or not isinstance(value["operation_id"], str)
                or not re.fullmatch(r"dbi-[a-f0-9]{64}", value["operation_id"])):
            raise BriefImportUnavailable("pending state invalid")
        return value

    @staticmethod
    def _remove_pending_marker(root_fd, day, operation_id):
        name = DailyBriefImportStore._pending_name(day)
        marker = DailyBriefImportStore._read_pending_marker(root_fd, day)
        if marker is not None and marker["operation_id"] == operation_id:
            os.unlink(name, dir_fd=root_fd)
            os.fsync(root_fd)

    def has_pending_for_date(self, day):
        """Fail closed using one exact date marker; never enumerate Brief history."""
        if not self.configured:
            return False
        if not self.root:
            raise BriefImportUnavailable("idempotency state unavailable")
        root_fd = _open_dir_chain(self.root)
        try:
            return self._read_pending_marker(root_fd, day) is not None
        except OSError as exc:
            raise BriefImportUnavailable("idempotency state unavailable") from exc
        finally:
            os.close(root_fd)

    @staticmethod
    def _write_operation(root_fd, name, operation, *, replace):
        payload = _canonical(operation)
        temp = ".op-tmp-" + secrets.token_hex(16)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            if replace:
                os.replace(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            else:
                os.link(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)
                os.unlink(temp, dir_fd=root_fd)
            os.fsync(root_fd)
        finally:
            try:
                os.unlink(temp, dir_fd=root_fd)
            except OSError:
                pass

    def import_idempotent(self, candidate, *, source_verifier_factory, idempotency_key,
                          actor, request_sha256, before_commit=None):
        if isinstance(idempotency_key, str):
            stripe = hashlib.sha256(idempotency_key.encode("utf-8")).digest()[0] % len(_IDEMPOTENCY_LOCKS)
            with _IDEMPOTENCY_LOCKS[stripe]:
                return self._import_idempotent_locked(
                    candidate, source_verifier_factory=source_verifier_factory,
                    idempotency_key=idempotency_key, actor=actor,
                    request_sha256=request_sha256, before_commit=before_commit,
                )
        return self._import_idempotent_locked(
            candidate, source_verifier_factory=source_verifier_factory,
            idempotency_key=idempotency_key, actor=actor,
            request_sha256=request_sha256, before_commit=before_commit,
        )

    def _import_idempotent_locked(self, candidate, *, source_verifier_factory,
                                  idempotency_key, actor, request_sha256, before_commit=None):
        """Persist a private replay marker before the date record; recover pending commits."""
        if (not isinstance(idempotency_key, str) or not 16 <= len(idempotency_key) <= 128
                or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key)
                or not isinstance(actor, str) or not actor
                or not isinstance(request_sha256, str) or len(request_sha256) != 64):
            raise BriefImportRejected("invalid idempotency request")
        record = self._validate_candidate(candidate)
        key_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        actor_hash = hashlib.sha256(actor.encode("utf-8")).hexdigest()
        operation_id = "dbi-" + hashlib.sha256(_canonical({
            "key_sha256": key_hash, "actor_sha256": actor_hash,
            "request_sha256": request_sha256,
        })).hexdigest()
        operation_name = ".op-" + key_hash + ".json"
        lock_name = ".op-lock-" + key_hash
        try:
            root_fd = _open_dir_chain(self.root)
        except OSError as exc:
            raise BriefImportUnavailable("record root unavailable") from exc
        try:
            info = os.fstat(root_fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise BriefImportUnavailable("record root is not private")
            lock_fd = _open_lock_at(root_fd, lock_name, label="record")
            try:
                lock_info = os.fstat(lock_fd)
                if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                        or lock_info.st_mode & 0o077 or lock_info.st_nlink != 1):
                    raise BriefImportUnavailable("idempotency state unavailable")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                date_lock_fd = _open_lock_at(
                    root_fd, f".date-lock-{record['date']}", label="record",
                )
                try:
                    date_lock_info = os.fstat(date_lock_fd)
                    if (not stat.S_ISREG(date_lock_info.st_mode)
                            or date_lock_info.st_uid != os.geteuid()
                            or date_lock_info.st_mode & 0o077 or date_lock_info.st_nlink != 1):
                        raise BriefImportUnavailable("date transaction state unavailable")
                    fcntl.flock(date_lock_fd, fcntl.LOCK_EX)
                    operation = self._read_operation(root_fd, operation_name)
                    pending = self._read_pending_marker(root_fd, record["date"])
                    if pending is not None and (
                            operation is None or pending["operation_id"] != operation["operation_id"]):
                        raise BriefImportUnavailable("date transaction requires recovery")
                    if operation is not None:
                        if (operation["request_sha256"] != request_sha256
                                or operation["actor_sha256"] != actor_hash
                                or operation["date"] != record["date"]
                                or operation["timezone"] != record["timezone"]):
                            raise BriefImportConflict("idempotency key conflicts")
                        record["brief_id"] = operation["brief_id"]
                        record["generated_at"] = operation["generated_at"]
                        operation_id = operation["operation_id"]
                        if operation["state"] == "committed":
                            existing, _ = self._read_existing(
                                root_fd, record["date"] + ".json", self.max_record_bytes)
                            if hashlib.sha256(existing).hexdigest() != operation["record_sha256"]:
                                raise BriefImportUnavailable("idempotency record inconsistent")
                            verifier = self._resolve_verifier(None, source_verifier_factory)
                            self._verify(record["source_refs"], verifier)
                            self._remove_pending_marker(root_fd, record["date"], operation_id)
                            return {"status": "duplicate", "brief_id": record["brief_id"],
                                    "date": record["date"], "timezone": record["timezone"],
                                    "record_sha256": operation["record_sha256"],
                                    "operation_id": operation_id}
                        try:
                            existing, _ = self._read_existing(
                                root_fd, record["date"] + ".json", self.max_record_bytes)
                        except FileNotFoundError:
                            existing = None
                        if existing is not None:
                            expected = hashlib.sha256(_canonical(record)).hexdigest()
                            if hashlib.sha256(existing).hexdigest() != expected:
                                self._remove_pending_operation(root_fd, operation_name)
                                self._remove_pending_marker(root_fd, record["date"], operation_id)
                                raise BriefImportConflict("date already has a different record")
                            verifier = self._resolve_verifier(None, source_verifier_factory)
                            self._verify(record["source_refs"], verifier)
                            recovered = {"status": "created", "brief_id": record["brief_id"],
                                         "date": record["date"], "timezone": record["timezone"],
                                         "record_sha256": expected}
                            try:
                                if before_commit is not None:
                                    before_commit(recovered)
                            except Exception as exc:
                                if not getattr(exc, "published", False):
                                    self._rollback_pending_record(
                                        root_fd, operation_name, record["date"], expected)
                                raise BriefImportUnavailable("audit commit unavailable") from exc
                            operation["state"] = "committed"
                            operation["record_sha256"] = expected
                            self._write_operation(root_fd, operation_name, operation, replace=True)
                            self._remove_pending_marker(root_fd, record["date"], operation_id)
                            return {"status": "duplicate", "brief_id": record["brief_id"],
                                    "date": record["date"], "timezone": record["timezone"],
                                    "record_sha256": expected, "operation_id": operation_id}
                    else:
                        names = os.listdir(root_fd)
                        if len(names) > _MAX_IMPORT_ROOT_ENTRIES:
                            raise BriefImportUnavailable("idempotency state budget exceeded")
                        operation_count = sum(
                            name.startswith(".op-") and name.endswith(".json") for name in names)
                        if operation_count >= _MAX_IDEMPOTENCY_OPERATIONS:
                            raise BriefImportUnavailable("idempotency state budget exceeded")
                        operation = {
                            "request_sha256": request_sha256,
                            "actor_sha256": actor_hash,
                            "date": record["date"],
                            "timezone": record["timezone"],
                            "brief_id": record["brief_id"],
                            "operation_id": operation_id,
                            "generated_at": record["generated_at"],
                            "state": "pending",
                            "record_sha256": hashlib.sha256(_canonical(record)).hexdigest(),
                        }
                        self._write_operation(root_fd, operation_name, operation, replace=False)

                    if pending is None:
                        pending = {
                            "actor_sha256": actor_hash,
                            "date": record["date"],
                            "key_sha256": key_hash,
                            "operation_id": operation_id,
                            "request_sha256": request_sha256,
                        }
                        self._write_operation(
                            root_fd, self._pending_name(record["date"]), pending, replace=False)
                    try:
                        result = self.import_record(
                            candidate, source_verifier_factory=source_verifier_factory,
                            brief_id=operation["brief_id"], generated_at=operation["generated_at"],
                            allow_duplicate=False,
                        )
                    except (BriefImportConflict, BriefImportRejected):
                        self._remove_pending_operation(root_fd, operation_name)
                        self._remove_pending_marker(root_fd, record["date"], operation_id)
                        raise
                    try:
                        if before_commit is not None:
                            before_commit(result)
                    except Exception as exc:
                        if not getattr(exc, "published", False):
                            self._rollback_pending_record(root_fd, operation_name, record["date"],
                                                          result["record_sha256"])
                        raise BriefImportUnavailable("audit commit unavailable") from exc
                    operation["state"] = "committed"
                    operation["record_sha256"] = result["record_sha256"]
                    self._write_operation(root_fd, operation_name, operation, replace=True)
                    self._remove_pending_marker(root_fd, record["date"], operation_id)
                    result["operation_id"] = operation_id
                    return result
                finally:
                    os.close(date_lock_fd)
            finally:
                os.close(lock_fd)
        except FileExistsError as exc:
            raise BriefImportConflict("idempotency key conflicts") from exc
        except OSError as exc:
            raise BriefImportUnavailable("idempotency state unavailable") from exc
        finally:
            os.close(root_fd)

    def _rollback_pending_record(self, root_fd, operation_name, day, expected_sha256):
        """Remove only this uncommitted create after its required audit fails."""
        operation = self._read_operation(root_fd, operation_name)
        if operation is None or operation["state"] != "pending":
            return
        try:
            current, _identity = self._read_existing(root_fd, day + ".json", self.max_record_bytes)
        except FileNotFoundError:
            current = None
        if current is not None:
            if hashlib.sha256(current).hexdigest() != expected_sha256:
                # An unexpected target must retain its recovery marker.
                return
            os.unlink(day + ".json", dir_fd=root_fd)
            os.fsync(root_fd)
        os.unlink(operation_name, dir_fd=root_fd)
        os.fsync(root_fd)
        self._remove_pending_marker(root_fd, day, operation["operation_id"])

    @staticmethod
    def _remove_pending_operation(root_fd, operation_name):
        operation = DailyBriefImportStore._read_operation(root_fd, operation_name)
        if operation is not None and operation["state"] == "pending":
            os.unlink(operation_name, dir_fd=root_fd)
            os.fsync(root_fd)


class DailyBriefAuditStore:
    """Append only the frozen allowlisted audit fields; never content or refs."""

    _FIELDS = {"event_type", "request_id", "brief_id", "date", "timezone",
               "source_kind_counts", "outcome", "recorded_at", "actor"}
    MAX_BYTES = 16 * 1024 * 1024

    def __init__(self, path):
        self.path = path if isinstance(path, str) and os.path.isabs(path) else ""

    def append(self, event):
        if not self.path or not isinstance(event, dict) or set(event) != self._FIELDS:
            raise OSError("audit unavailable")
        if (event["event_type"] != "daily_brief_import"
                or event["outcome"] not in {"created", "duplicate", "rejected", "failed"}
                or not isinstance(event["source_kind_counts"], dict)
                or set(event["source_kind_counts"]) - {"task", "project", "journal"}):
            raise OSError("audit event invalid")
        payload = _canonical(event) + b"\n"
        if len(payload) > 4096:
            raise OSError("audit event exceeds budget")
        parent, name = os.path.split(self.path)
        root_fd = _open_dir_chain(parent)
        lock_fd = temp_fd = None
        temp_name = ".daily-brief-audit-tmp-" + secrets.token_hex(16)
        published = False
        try:
            root_info = os.fstat(root_fd)
            if root_info.st_uid != os.geteuid() or root_info.st_mode & 0o077:
                raise BriefAuditUnavailable("audit root unavailable")
            lock_fd = _open_lock_at(root_fd, ".daily-brief-audit.lock", label="audit")
            lock_info = os.fstat(lock_fd)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                    or lock_info.st_mode & 0o077 or lock_info.st_nlink != 1):
                raise BriefAuditUnavailable("audit lock unavailable")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            try:
                audit_fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                                   dir_fd=root_fd)
            except FileNotFoundError:
                old_payload = b""
            else:
                try:
                    audit_info = os.fstat(audit_fd)
                    if (not stat.S_ISREG(audit_info.st_mode) or audit_info.st_uid != os.geteuid()
                            or audit_info.st_mode & 0o077 or audit_info.st_nlink != 1
                            or audit_info.st_size < 0 or audit_info.st_size > self.MAX_BYTES):
                        raise BriefAuditUnavailable("audit file unavailable")
                    chunks = []
                    remaining = self.MAX_BYTES + 1
                    while remaining:
                        chunk = os.read(audit_fd, min(65536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    old_payload = b"".join(chunks)
                    if len(old_payload) != audit_info.st_size or len(old_payload) > self.MAX_BYTES:
                        raise BriefAuditUnavailable("audit file changed")
                finally:
                    os.close(audit_fd)

            if event["outcome"] == "created" and event["brief_id"]:
                for line in old_payload.splitlines():
                    if not line:
                        continue
                    try:
                        prior = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
                    except Exception as exc:
                        raise BriefAuditUnavailable("audit file is invalid") from exc
                    if not isinstance(prior, dict) or set(prior) != self._FIELDS:
                        raise BriefAuditUnavailable("audit file is invalid")
                    if (prior.get("event_type") == event["event_type"]
                            and prior.get("outcome") == "created"
                            and prior.get("brief_id") == event["brief_id"]
                            and prior.get("date") == event["date"]
                            and prior.get("timezone") == event["timezone"]
                            and prior.get("actor") == event["actor"]):
                        return
            new_payload = old_payload + payload
            if len(new_payload) > self.MAX_BYTES:
                raise BriefAuditUnavailable("audit budget exhausted")
            temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
            view = memoryview(new_payload)
            while view:
                written = os.write(temp_fd, view)
                if written <= 0:
                    raise BriefAuditUnavailable("audit short write")
                view = view[written:]
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = None
            os.replace(temp_name, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            published = True
            try:
                os.fsync(root_fd)
            except OSError as exc:
                raise BriefAuditUnavailable("audit directory sync unavailable", published=True) from exc
        except BriefAuditUnavailable:
            raise
        except OSError as exc:
            raise BriefAuditUnavailable("audit persistence unavailable", published=published) from exc
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
            if not published:
                try:
                    os.unlink(temp_name, dir_fd=root_fd)
                except OSError:
                    pass
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(root_fd)
