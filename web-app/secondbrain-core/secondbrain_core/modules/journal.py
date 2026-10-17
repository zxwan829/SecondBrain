"""Append-only Journal storage and the explicitly invoked Journal API."""
import fcntl
import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request


_INTENT = re.compile(r"^\s*(?:记一下|记下来|写日记|记录一下)(?:[：:,，\s]+|$)")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_ENTRY_BYTES = 16_384


class JournalStore:
    """Write one JSONL record per explicit request under a dedicated private root."""

    def __init__(self, root):
        path = Path(root)
        if not path.is_absolute():
            raise ValueError("Journal root must be absolute")
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or not os.access(path, os.W_OK)):
            raise ValueError("Journal root must be a private writable directory owned by the Core UID")
        self.root = path

    @staticmethod
    def today():
        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    def _path(self, day):
        if not isinstance(day, str) or not _DATE.fullmatch(day):
            raise HTTPException(status_code=400, detail="Date must use YYYY-MM-DD")
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date") from exc
        return self.root / f"{day}.jsonl"

    def append(self, day, text, idempotency_key):
        path = self._path(day)
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(status_code=400, detail="An explicit Journal phrase and text are required")
        if not _INTENT.match(text):
            raise HTTPException(status_code=422, detail="Use an explicit phrase such as 记一下 or 写日记")
        if len(text.encode("utf-8")) > _MAX_ENTRY_BYTES:
            raise HTTPException(status_code=413, detail="Journal entry is too long")
        if (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 255
                or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key)):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")

        key_hash = hashlib.sha256(idempotency_key.encode("ascii")).hexdigest()
        record = {"id": key_hash, "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
                  "source": "web_app_explicit_intent", "original_text": text}
        encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        lock_path = self.root / f".{day}.lock"
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            lock_stat = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.geteuid() or lock_stat.st_mode & 0o077:
                raise HTTPException(status_code=500, detail="Journal lock file is not private")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                read_fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            except FileNotFoundError:
                existing = []
            else:
                try:
                    info = os.fstat(read_fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise HTTPException(status_code=500, detail="Journal file is not private")
                    with os.fdopen(read_fd, "r", encoding="utf-8", closefd=False) as stream:
                        existing = [json.loads(line) for line in stream if line.strip()]
                finally:
                    os.close(read_fd)
            prior = next((item for item in existing if item.get("id") == key_hash), None)
            if prior is not None:
                if prior.get("original_text") != text:
                    raise HTTPException(status_code=409, detail="Idempotency-Key was already used with different Journal text")
                return {"status": "duplicate", "date": day, "entry": prior}
            write_fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                info = os.fstat(write_fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise HTTPException(status_code=500, detail="Journal file is not private")
                old_size = info.st_size
                try:
                    written = os.write(write_fd, encoded)
                    if written != len(encoded):
                        raise OSError("Incomplete Journal append")
                except OSError:
                    # The exclusive file lock makes rollback of a partial append safe.
                    if os.fstat(write_fd).st_size > old_size:
                        os.ftruncate(write_fd, old_size)
                        os.fsync(write_fd)
                    raise
                os.fsync(write_fd)
            finally:
                os.close(write_fd)
            return {"status": "created", "date": day, "entry": record}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="Journal append failed safely") from exc
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def read(self, day):
        path = self._path(day)
        lock_fd = os.open(self.root / f".{day}.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            lock_stat = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.geteuid() or lock_stat.st_mode & 0o077:
                raise HTTPException(status_code=500, detail="Journal lock file is not private")
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            try:
                try:
                    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                except FileNotFoundError:
                    return {"date": day, "entries": []}
                except OSError as exc:
                    raise HTTPException(status_code=500, detail="Journal file could not be opened safely") from exc
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise HTTPException(status_code=500, detail="Journal file is not private")
                    with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                        entries = [json.loads(line) for line in stream if line.strip()]
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise HTTPException(status_code=500, detail="Journal file could not be read safely") from exc
                finally:
                    os.close(fd)
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Journal file could not be read safely") from exc
        finally:
            os.close(lock_fd)
        return {"date": day, "entries": entries}


def create_journal_router(auth, store):
    router = APIRouter(prefix="/api/journal")

    @router.get("/{day}")
    def read_journal(request: Request, day: str):
        auth.require_action(request, "journal.read")
        if store is None:
            raise HTTPException(status_code=503, detail="Journal is not enabled")
        return store.read(day)

    @router.post("/entries")
    def append_journal(request: Request, body: dict):
        auth.require_action(request, "journal.append")
        if store is None:
            raise HTTPException(status_code=503, detail="Journal is not enabled")
        return store.append(body.get("date") or store.today(), body.get("text"), request.headers.get("idempotency-key", ""))

    return router
