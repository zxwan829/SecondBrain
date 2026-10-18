"""Short-lived B1b preview tickets and durable, output-bound confirmations."""
import hashlib
import json
import os
import re
import secrets
import stat
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .approval import ApprovalRequestError, _read_review, _TARGET
from .worker import _open_dir_chain, render_promoted_markdown


_REQUEST_ID = re.compile(r"^b1b-[0-9a-f]{32}$")
_PREVIEW_ID = re.compile(r"^[A-Za-z0-9_-]{32,80}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPERATION_STATES = {
    "confirmed", "claimed", "promoting", "promoted", "already_promoted",
    "recovery_required", "failed",
}
_MAX_OPERATION_RECORDS = 10000


class OperationStore:
    """Private synthetic/live Core state for confirmed B1b operations."""

    def __init__(self, directory):
        if not os.path.isabs(directory):
            raise ValueError("Operation state path must be absolute")
        self.directory = os.path.abspath(directory)
        os.makedirs(self.directory, mode=0o700, exist_ok=True)
        info = os.stat(self.directory, follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError("Operation state directory permissions are unsafe")
        self._lock = threading.RLock()

    def _path(self, request_id):
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ApprovalRequestError("Invalid operation ID")
        return os.path.join(self.directory, request_id + ".json")

    @staticmethod
    def _read_file(path):
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 131072):
                raise ApprovalRequestError("Operation record permissions or size are unsafe")
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            record = json.loads(b"".join(chunks).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise ApprovalRequestError("Operation record is unreadable; recovery required") from exc
        finally:
            os.close(fd)
        if (not isinstance(record, dict) or record.get("status") not in _OPERATION_STATES or
                not isinstance(record.get("request_id"), str) or
                not _REQUEST_ID.fullmatch(record["request_id"]) or
                not isinstance(record.get("review_sha256"), str) or
                not _SHA256.fullmatch(record["review_sha256"]) or
                not isinstance(record.get("output_sha256"), str) or
                not _SHA256.fullmatch(record["output_sha256"])):
            raise ApprovalRequestError("Operation record identity is invalid; recovery required")
        return record

    def get(self, request_id):
        path = self._path(request_id)
        try:
            record = self._read_file(path)
        except FileNotFoundError:
            return None
        if record.get("request_id") != request_id:
            raise ApprovalRequestError("Operation record identity mismatch; recovery required")
        return record

    def find_for_version(self, review_path, review_sha256):
        """Find an existing confirmed operation; fail closed at a fixed scan bound."""
        directory_fd = _open_dir_chain(self.directory)
        try:
            names = [name for name in os.listdir(directory_fd) if name.endswith(".json")]
            if len(names) > _MAX_OPERATION_RECORDS:
                raise ApprovalRequestError("Operation inventory exceeds the safe lookup limit")
            for name in names:
                record = self._read_file(os.path.join(self.directory, name))
                if (record.get("review_path") == review_path and
                        record.get("review_sha256") == review_sha256):
                    return record
            return None
        finally:
            os.close(directory_fd)

    def create_confirmed(self, record):
        path = self._path(record.get("request_id"))
        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                existing = self.get(record["request_id"])
                bound = ("request_id", "preview_id", "session_binding", "review_path",
                         "review_sha256", "target_filename", "approved_at", "output_sha256")
                if existing and all(existing.get(key) == record.get(key) for key in bound):
                    return existing
                raise ApprovalRequestError("Operation ID is already bound; recovery required")
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
                os.fsync(fd)
            except Exception:
                os.close(fd)
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise
            os.close(fd)
            directory_fd = _open_dir_chain(self.directory)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return record

    def update(self, request_id, status, **fields):
        if status not in _OPERATION_STATES:
            raise ApprovalRequestError("Unsupported operation state")
        path = self._path(request_id)
        with self._lock:
            current = self.get(request_id)
            if current is None:
                raise ApprovalRequestError("Confirmed operation is missing; recovery required")
            updated = {**current, **fields, "status": status,
                       "updated_at": datetime.now(timezone.utc).isoformat()}
            temp = os.path.join(self.directory, ".operation-" + secrets.token_hex(16))
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                payload = (json.dumps(updated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temp, path)
            directory_fd = _open_dir_chain(self.directory)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return updated


class B1bPromoteFlow:
    """A one-process ticket cache; durable confirmations survive for recovery."""

    def __init__(self, service, review_root, knowledge_root, operations_root,
                 auth, *, promote_enabled=False, ticket_ttl=600):
        self.service = service
        self.review_root = os.path.abspath(review_root)
        self.knowledge_root = os.path.abspath(knowledge_root)
        self.auth = auth
        self.promote_enabled = bool(promote_enabled)
        self.ticket_ttl = min(max(int(ticket_ttl), 1), 600)
        self.operations = OperationStore(operations_root)
        self._tickets = {}
        self._lock = threading.RLock()

    def _target_is_free(self, target_filename):
        if not isinstance(target_filename, str) or not _TARGET.fullmatch(target_filename):
            raise HTTPException(status_code=409, detail={"code": "target_invalid"})
        root_fd = _open_dir_chain(self.knowledge_root)
        try:
            try:
                fd = os.open(target_filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            except FileNotFoundError:
                return
            else:
                os.close(fd)
                raise HTTPException(status_code=409, detail={"code": "target_occupied"})
        except OSError as exc:
            raise HTTPException(status_code=409, detail={"code": "target_unavailable"}) from exc
        finally:
            os.close(root_fd)

    def preview(self, request, body):
        binding = self.auth.require_app(request)
        if not isinstance(body, dict):
            raise HTTPException(status_code=409, detail={"code": "preview_invalid"})
        try:
            review_path = self.service.decisions.canonical_review_path(body.get("review_path"))
            supplied_digest = body.get("review_sha256")
            if not isinstance(supplied_digest, str) or not _SHA256.fullmatch(supplied_digest):
                raise ApprovalRequestError("invalid digest")
            source = _read_review(self.review_root, review_path)
            digest = hashlib.sha256(source).hexdigest()
            if digest != supplied_digest:
                raise HTTPException(status_code=409, detail={"code": "source_stale"})
            try:
                existing_operation = self.operations.find_for_version(review_path, digest)
            except (ApprovalRequestError, OSError) as exc:
                raise HTTPException(status_code=503, detail={"code": "operation_state_invalid"}) from exc
            if existing_operation is not None:
                raise HTTPException(status_code=409, detail={"code": "operation_recovery_required"})
            source_markdown = source.decode("utf-8")
            target_filename = body.get("target_filename")
            self._target_is_free(target_filename)
            request_id = "b1b-" + secrets.token_hex(16)
            preview_id = secrets.token_urlsafe(32)
            approved_at = datetime.now(timezone.utc).isoformat()
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ticket_ttl)
            output = render_promoted_markdown(request_id, digest, approved_at, source)
            projected_markdown = output.decode("utf-8")
            ticket = {"preview_id": preview_id, "request_id": request_id,
                      "session_binding": binding, "review_path": review_path,
                      "review_sha256": digest, "target_filename": target_filename,
                      "source_markdown": source_markdown, "source_bytes": source,
                      "projected_markdown": projected_markdown,
                      "approved_at": approved_at,
                      "output_sha256": hashlib.sha256(output).hexdigest(),
                      "expires_at": expires_at.timestamp(),
                      "expires_at_iso": expires_at.isoformat()}
            with self._lock:
                self._purge_expired()
                self._tickets[preview_id] = ticket
            return {key: ticket[key] for key in (
                "preview_id", "request_id", "review_path",
                "target_filename", "source_markdown", "projected_markdown", "output_sha256",
            )} | {"source_sha256": digest, "expires_at": ticket["expires_at_iso"],
                 "target_precondition": {"exists": False},
                 "change_summary": [
                     "The server converts Review type/status fields to the Knowledge schema and preserves other fields and body.",
                     "The server adds the approval timestamp and Promote request marker.",
                     "The target must remain absent; existing files are never overwritten.",
                 ]}
        except HTTPException:
            raise
        except (ApprovalRequestError, UnicodeDecodeError, OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "preview_invalid"}) from exc

    def _purge_expired(self):
        now = time.time()
        for key in [key for key, item in self._tickets.items() if item["expires_at"] <= now]:
            del self._tickets[key]

    def confirm(self, request, body):
        self.auth.require_owner(request)
        binding = self.auth.require_app(request)
        if not self.promote_enabled:
            raise HTTPException(status_code=423, detail={"code": "promote_disabled"})
        if (not isinstance(body, dict) or body.get("confirm_intent") != "promote_exact_preview" or
                not isinstance(body.get("preview_id"), str) or
                not _PREVIEW_ID.fullmatch(body["preview_id"])):
            raise HTTPException(status_code=409, detail={"code": "confirmation_invalid"})
        preview_id = body["preview_id"]
        with self._lock:
            ticket = self._tickets.get(preview_id)
            if not ticket:
                raise HTTPException(status_code=410, detail={"code": "preview_expired"})
            if ticket["expires_at"] <= time.time():
                self._tickets.pop(preview_id, None)
                raise HTTPException(status_code=410, detail={"code": "preview_expired"})
            if not secrets.compare_digest(ticket["session_binding"], binding):
                raise HTTPException(status_code=401, detail={"code": "preview_session_mismatch"})
            try:
                source = _read_review(self.review_root, ticket["review_path"])
            except ApprovalRequestError as exc:
                raise HTTPException(status_code=409, detail={"code": "source_unavailable"}) from exc
            if hashlib.sha256(source).hexdigest() != ticket["review_sha256"] or source != ticket["source_bytes"]:
                raise HTTPException(status_code=409, detail={"code": "source_stale"})
            output = render_promoted_markdown(ticket["request_id"], ticket["review_sha256"],
                                               ticket["approved_at"], source)
            output_digest = hashlib.sha256(output).hexdigest()
            if output_digest != ticket["output_sha256"]:
                raise HTTPException(status_code=409, detail={"code": "preview_output_changed"})
            try:
                existing_operation = self.operations.get(ticket["request_id"])
            except ApprovalRequestError as exc:
                raise HTTPException(status_code=503, detail={"code": "operation_state_invalid"}) from exc
            if existing_operation is not None:
                bound_fields = ("preview_id", "session_binding", "review_path", "review_sha256",
                                "target_filename", "approved_at", "output_sha256")
                if any(existing_operation.get(key) != ticket.get(key) for key in bound_fields):
                    raise HTTPException(status_code=409, detail={"code": "operation_binding_conflict"})
                try:
                    existing_output = self._read_target(ticket["target_filename"])
                except FileNotFoundError:
                    existing_output = None
                except OSError as exc:
                    raise HTTPException(status_code=409, detail={"code": "target_unavailable"}) from exc
                if existing_output is not None and hashlib.sha256(existing_output).hexdigest() != output_digest:
                    raise HTTPException(status_code=409, detail={"code": "target_occupied"})
                if existing_output is None:
                    self._target_is_free(ticket["target_filename"])
            else:
                self._target_is_free(ticket["target_filename"])
            now = datetime.now(timezone.utc).isoformat()
            record = {"request_id": ticket["request_id"], "preview_id": preview_id,
                      "session_binding": binding, "review_path": ticket["review_path"],
                      "review_sha256": ticket["review_sha256"],
                      "target_filename": ticket["target_filename"],
                      "approved_at": ticket["approved_at"], "confirmed_at": now,
                      "approver_subject": "owner", "output_sha256": output_digest,
                      "status": "confirmed"}
            try:
                self.operations.create_confirmed(record)
            except (ApprovalRequestError, OSError) as exc:
                raise HTTPException(status_code=503, detail={"code": "confirmation_not_durable"}) from exc

            def operation_callback(status):
                self.operations.update(ticket["request_id"], status)

            try:
                result = self.service.approve_and_promote_as(
                    "owner", {"request_id": ticket["request_id"],
                              "review_path": ticket["review_path"],
                              "review_sha256": ticket["review_sha256"],
                              "target_filename": ticket["target_filename"]},
                    self.review_root, approved_at=ticket["approved_at"],
                    operation_callback=operation_callback,
                )
                state = "promoted" if result.get("status") == "promoted" else "already_promoted"
                self.operations.update(ticket["request_id"], state)
                return {"status": state, "request_id": ticket["request_id"],
                        "target_filename": ticket["target_filename"],
                        "output_sha256": output_digest}
            except ApprovalRequestError as exc:
                # Exceptions are mapped to fixed codes; filesystem details never cross HTTP.
                state = "recovery_required" if "recovery" in str(exc).lower() else "failed"
                try:
                    self.operations.update(ticket["request_id"], state,
                                           error_code="operation_recovery_required" if state == "recovery_required"
                                           else "operation_failed")
                except Exception:
                    pass
                raise HTTPException(status_code=503 if state == "recovery_required" else 409,
                                    detail={"code": "operation_recovery_required" if state == "recovery_required"
                                            else "operation_failed"}) from exc

    def status(self, request, request_id):
        self.auth.require_owner(request, allow_originless_same_origin=True)
        try:
            record = self.operations.get(request_id)
        except ApprovalRequestError as exc:
            raise HTTPException(status_code=503, detail={"code": "operation_state_invalid"}) from exc
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "operation_not_found"})
        try:
            source = _read_review(self.review_root, record["review_path"])
            current_digest = hashlib.sha256(source).hexdigest()
            if current_digest != record["review_sha256"]:
                raise HTTPException(status_code=409, detail={"code": "operation_source_changed"})
            decision = self.service.get_decision(record["review_path"], record["review_sha256"])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"code": "operation_recovery_required"}) from exc
        state = record["status"]
        try:
            claim = self.service.decisions.read_claim(record["review_path"], record["review_sha256"])
            actual = self._read_target(record["target_filename"])
            actual_hash = hashlib.sha256(actual).hexdigest()
            audit = self._read_audit()
        except FileNotFoundError:
            claim = None
            actual_hash = None
            audit = []
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"code": "operation_recovery_required"}) from exc
        claim_matches = bool(claim and claim.get("request_id") == request_id and
                             claim.get("target_filename") == record["target_filename"] and
                             claim.get("approved_at") == record["approved_at"] and
                             claim.get("review_path") == record["review_path"] and
                             claim.get("review_sha256") == record["review_sha256"] and
                             claim.get("approver_subject") == record["approver_subject"])
        audit_matches = any(event.get("request_id") == request_id and
                            event.get("event") == "promoted" and
                            event.get("review_path") == record["review_path"] and
                            event.get("review_sha256") == record["review_sha256"] and
                            event.get("target_filename") == record["target_filename"] and
                            event.get("approved_at") == record["approved_at"] and
                            event.get("output_sha256") == record["output_sha256"]
                            for event in audit)
        if claim_matches and audit_matches and actual_hash == record["output_sha256"]:
            state = "promoted"
        elif (state in {"confirmed", "claimed", "promoting", "promoted", "already_promoted"} or
              decision.get("status") in {"approved", "promoting", "promoted", "failed"}):
            state = "recovery_required"
        if state != record["status"]:
            try:
                record = self.operations.update(request_id, state)
            except Exception as exc:
                raise HTTPException(status_code=503, detail={"code": "operation_recovery_required"}) from exc
        result = {"status": record["status"], "request_id": request_id,
                "review_path": record["review_path"], "review_sha256": record["review_sha256"],
                "target_filename": record["target_filename"], "output_sha256": record["output_sha256"],
                "confirmed_at": record["confirmed_at"]}
        if record.get("error_code"):
            result["error_code"] = record["error_code"]
        return result

    def _read_target(self, target_filename):
        root_fd = _open_dir_chain(self.knowledge_root)
        try:
            fd = os.open(target_filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("target is not regular")
                chunks = []
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        return b"".join(chunks)
                    chunks.append(chunk)
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)

    def _read_audit(self):
        path = self.service.worker.audit_path
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return []
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise OSError("audit permissions unsafe")
            data = bytearray()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                data.extend(chunk)
            if data and not data.endswith(b"\n"):
                raise OSError("audit tail incomplete")
            return [json.loads(line.decode("utf-8")) for line in data.splitlines()]
        finally:
            os.close(fd)
