"""Private, version-bound Knowledge recall metadata for Chat runs.

Document bytes are used only while constructing the upstream Run request. The
durable ledger stores no document text and never accepts references from the
browser or Hermes output.
"""
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import uuid
from pathlib import Path

from fastapi import HTTPException


MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_RUNS = 1000
MAX_CITATIONS = 3
MAX_ITEM_BYTES = 8 * 1024
MAX_TOTAL_BYTES = 16 * 1024
MAX_QUERY_CHARS = 200
RECALL_TIMEOUT_SECONDS = 0.75


class ChatKnowledgeCitationStore:
    def __init__(self, root, knowledge_store):
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("Chat Knowledge citation root must be absolute")
        try:
            os.mkdir(self.root, 0o700)
        except FileExistsError:
            pass
        self._verify_root()
        self.path = self.root / "citations.json"
        self.lock_path = self.root / ".citations.lock"
        self.knowledge_store = knowledge_store

    def _verify_root(self):
        info = self.root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or not os.access(self.root, os.W_OK)):
            raise ValueError("Chat Knowledge citation root must be private and owned by Core")

    def _lock(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise HTTPException(status_code=503, detail="Chat citation state unavailable")
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _read_unlocked(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Chat citation state unavailable") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=503, detail="Chat citation state unavailable")
            if info.st_size > MAX_LEDGER_BYTES:
                raise HTTPException(status_code=503, detail="Chat citation state unavailable")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                value = json.load(stream)
            if (not isinstance(value, dict) or len(value) > MAX_RUNS
                    or any(not self._valid_record(run_id, record) for run_id, record in value.items())):
                raise ValueError("invalid citation ledger")
            return value
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Chat citation state unavailable") from exc
        finally:
            os.close(fd)

    @staticmethod
    def _valid_record(run_id, record):
        if (not isinstance(run_id, str) or not run_id or not isinstance(record, dict)
                or not isinstance(record.get("session_id"), str) or not record["session_id"]
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("input_sha256", "")))
                or record.get("status") not in {"available", "none", "partial", "unavailable"}
                or not isinstance(record.get("identity"), list)
                or not isinstance(record.get("citations"), list)
                or len(record["citations"]) > MAX_CITATIONS):
            return False
        for item in record["identity"]:
            if (not isinstance(item, dict) or set(item) != {"relative_path", "sha256", "title"}
                    or not isinstance(item["relative_path"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"]))
                    or not isinstance(item["title"], str) or len(item["title"]) > 200):
                return False
        for item in record["citations"]:
            if (not isinstance(item, dict)
                    or set(item) != {"citation_id", "relative_path", "title", "sha256",
                                     "knowledge_status", "provenance_status"}
                    or not isinstance(item["citation_id"], str) or not item["citation_id"]
                    or not isinstance(item["relative_path"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"]))
                    or not isinstance(item["title"], str) or len(item["title"]) > 200
                    or item["knowledge_status"] != "version_verified"
                    or item["provenance_status"] != "verified"):
                return False
        return True

    def _write_unlocked(self, rows):
        if len(rows) > MAX_RUNS:
            # Retain only the most recently inserted bounded run bindings.
            rows = dict(list(rows.items())[-MAX_RUNS:])
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(payload) > MAX_LEDGER_BYTES:
            raise HTTPException(status_code=503, detail="Chat citation state unavailable")
        temporary = self.root / (".citations-" + uuid.uuid4().hex + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(fd)
            os.replace(temporary, self.path)
            directory_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                   getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(status_code=503, detail="Chat citation state unavailable") from exc
        finally:
            os.close(fd)

    @staticmethod
    def _identity(items):
        return [{"relative_path": item["relative_path"], "sha256": item["sha256"],
                 "title": item["title"]} for item in items]

    def bind(self, run_id, session_id, input_text, recall):
        if not isinstance(run_id, str) or not run_id or not isinstance(session_id, str) or not session_id:
            return None
        items = recall.get("items", []) if isinstance(recall, dict) else []
        items = [item for item in items[:MAX_CITATIONS]
                 if isinstance(item, dict) and item.get("provenance_status") == "verified"]
        input_sha256 = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        fd = self._lock()
        try:
            rows = self._read_unlocked()
            prior = rows.get(run_id)
            identity = self._identity(items)
            if prior:
                if (prior.get("session_id") != session_id or prior.get("input_sha256") != input_sha256
                        or prior.get("identity") != identity):
                    # Preserve the original binding metadata but invalidate its
                    # public projection so a same-run conflict cannot replay a
                    # previously trusted reference.
                    prior["status"] = "unavailable"
                    prior["citations"] = []
                    self._write_unlocked(rows)
                    return None
                return self._project(prior, run_id)
            citations = [{
                "citation_id": secrets.token_urlsafe(18), "relative_path": item["relative_path"],
                "title": "".join(char for char in str(item["title"])[:200]
                                 if char >= " " and char not in {"\u007f", "\u2028", "\u2029"}),
                "sha256": item["sha256"],
                "knowledge_status": "version_verified", "provenance_status": "verified",
            } for item in items]
            status = recall.get("status", "none") if isinstance(recall, dict) else "unavailable"
            if status not in {"available", "none", "partial", "unavailable"}:
                status = "unavailable"
            if citations:
                status = "partial" if status == "partial" else "available"
            else:
                status = status if status in {"partial", "unavailable"} else "none"
            record = {"session_id": session_id, "input_sha256": input_sha256,
                      "identity": identity, "status": status, "citations": citations}
            rows[run_id] = record
            self._write_unlocked(rows)
            return self._project(record, run_id)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _project(record, run_id=None):
        return {"event": "knowledge.citations", "version": 1,
                "run_id": run_id or record.get("run_id"),
                "session_id": record["session_id"], "status": record["status"],
                "citations": [{key: citation[key] for key in
                               ("citation_id", "title", "sha256", "knowledge_status", "provenance_status")}
                              for citation in record["citations"]]}

    def read_for_session(self, session_id, run_id):
        fd = self._lock()
        try:
            record = self._read_unlocked().get(run_id)
            if not record or record.get("session_id") != session_id:
                raise HTTPException(status_code=404, detail="Chat citations not found")
            projected = self._project(record, run_id)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        if not record["citations"]:
            return projected
        try:
            valid = all(self.knowledge_store.verify_chat_reference(
                citation["relative_path"], citation["sha256"]) for citation in record["citations"])
        except HTTPException:
            projected["status"] = "unavailable"
            projected["citations"] = []
            return projected
        if not valid:
            projected["status"] = "stale"
            projected["citations"] = []
        return projected

    def read_for_run(self, run_id):
        fd = self._lock()
        try:
            record = self._read_unlocked().get(run_id)
            if not record:
                return None
            session_id = record["session_id"]
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return self.read_for_session(session_id, run_id)


def recall_query(text):
    return " ".join(text.split())[:MAX_QUERY_CHARS].strip()
