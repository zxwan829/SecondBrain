"""Bounded, read-only Knowledge search and exact-item access.

Search and detail read only the configured Knowledge root. An optional,
separately injected verifier may inspect one exact Review path only after a
promoted marker and durable Core evidence pin that path and version. It never
searches Raw or Private; without complete evidence source claims remain
missing/unverified.

Item IDs use a random process-local key and expire after restart. Scans consume
filesystem iterator order up to the strict entry budget; rows are sorted only
within the visited subset. Exhausting the budget reports `truncated`, because
complete coverage cannot be claimed once the bounded prefix ends.
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
from datetime import datetime, timezone
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response


MAX_QUERY_CHARS = 200
MAX_LIMIT = 50
DEFAULT_LIMIT = 20
MAX_SCAN_ENTRIES = 2000
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_SNIPPET_CHARS = 240
MAX_DETAIL_CHARS = MAX_FILE_BYTES
_SOURCE_HINTS = ("source_ref:", "source_sha256:", "source_kind:", "source_id:",
                 "source_type:", "source_version_sha256:", "original_asset:", "capture_context:")


def _open_dir_chain(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise OSError("Knowledge root is not an absolute path")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open("/", flags)
    try:
        for part in path.split("/"):
            if not part:
                continue
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("Knowledge root is not a directory")
        return fd
    except Exception:
        os.close(fd)
        raise


def _validate_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("invalid path")
    if len(value.encode("utf-8")) > 4096:
        raise ValueError("invalid path")
    parts = value.split("/")
    if len(parts) > 32 or any(part in {"", ".", ".."} or len(part.encode("utf-8")) > 255 for part in parts):
        raise ValueError("invalid path")
    lowered = value.lower()
    if re.search(r"%(?:2e|2f|5c|25(?:2e|2f|5c))", lowered):
        # The filesystem lookup never URL-decodes, but reject encoded and
        # double-encoded traversal spellings explicitly as defense in depth.
        raise ValueError("invalid path")
    if PurePosixPath(value).is_absolute() or not value.lower().endswith(".md"):
        raise ValueError("invalid path")
    return parts


def _open_exact(root_fd, relative_path):
    parts = _validate_relative_path(relative_path)
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                            getattr(os, "O_NOFOLLOW", 0), dir_fd=current)
            os.close(current)
            current = child
        fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            os.close(fd)
            raise OSError("Knowledge item is not a regular file")
        return fd, info
    finally:
        os.close(current)


def _read_bounded(fd, max_bytes):
    chunks = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _id_key(secret):
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("Knowledge ID key must contain at least 256 bits")
    return secret


def _token(relative_path, content_sha256, secret):
    payload = json.dumps({"path": relative_path, "sha256": content_sha256},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_id_key(secret), payload, hashlib.sha256).hexdigest()[:32]
    return f"v1.{encoded}.{signature}"


def _decode_token(item_id, secret):
    try:
        if not isinstance(item_id, str) or len(item_id) > 8192:
            raise ValueError
        version, encoded, supplied = item_id.split(".", 2)
        if (version != "v1" or len(supplied) != 32
                or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded)
                or len(encoded) % 4 == 1
                or not re.fullmatch(r"[0-9a-f]{32}", supplied)):
            raise ValueError
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"path", "sha256"}:
            raise ValueError
        relative = payload["path"]
        expected_sha256 = payload["sha256"]
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError
        expected = hmac.new(_id_key(secret), raw, hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(supplied, expected):
            raise ValueError
        _validate_relative_path(relative)
        return relative, expected_sha256
    except (ValueError, UnicodeError, TypeError, binascii.Error, RecursionError):
        raise HTTPException(status_code=404, detail="Knowledge item not found")


def _provenance_status(content):
    # This fallback cannot validate a promoted source. User-editable Markdown
    # and frontmatter can signal a claim but cannot prove it.
    if b"secondbrain-promote request_id=" in content[:512]:
        return "unverified"
    try:
        text = content[:65536].decode("utf-8")
    except UnicodeDecodeError:
        return "unverified"
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "missing"
    end = next((index for index in range(1, min(len(lines), 201)) if lines[index].strip() == "---"), None)
    if end is None:
        return "unverified"
    fields = tuple(hint.split(":", 1)[0] for hint in _SOURCE_HINTS)
    if any(line.split(":", 1)[0].strip().lower() in fields and ":" in line
           for line in lines[1:end]):
        return "unverified"
    return "missing"


def _frontmatter_title(text, fallback):
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:101]:
            if line.strip() == "---":
                break
            if line.lower().startswith("title:"):
                value = line.split(":", 1)[1].strip().strip("'\"")
                if value:
                    return value[:200]
    for line in lines[:200]:
        if line.startswith("# "):
            return line[2:].strip()[:200] or fallback
    return fallback


def _snippet(text, query):
    normalized = " ".join(text.split())
    needle = query.casefold()
    index = normalized.casefold().find(needle)
    if index < 0:
        return normalized[:MAX_SNIPPET_CHARS]
    start = max(0, index - MAX_SNIPPET_CHARS // 3)
    return normalized[start:start + MAX_SNIPPET_CHARS]


class KnowledgeReadStore:
    def __init__(self, knowledge_root, provenance_verifier=None):
        self.root = knowledge_root if isinstance(knowledge_root, str) and os.path.isabs(knowledge_root) else ""
        self.provenance_verifier = provenance_verifier
        # Never derive this key from the App login credential or persist it.
        self._id_secret = secrets.token_bytes(32)

    def _root_fd(self):
        if not self.root:
            raise HTTPException(status_code=503, detail="Knowledge is unavailable")
        try:
            return _open_dir_chain(self.root)
        except OSError:
            raise HTTPException(status_code=503, detail="Knowledge is unavailable")

    def search(self, query, limit):
        if not isinstance(query, str) or not query.strip():
            raise HTTPException(status_code=400, detail="A non-empty query is required")
        query = query.strip()
        if len(query) > MAX_QUERY_CHARS:
            raise HTTPException(status_code=400, detail="Query is too long")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
            raise HTTPException(status_code=400, detail="Invalid result limit")
        root_fd = self._root_fd()
        rows = []
        entries_seen = 0
        bytes_read = 0
        budget_exceeded = False
        invalid_paths_seen = False

        def visit(directory_fd, prefix, depth=0):
            nonlocal entries_seen, bytes_read, budget_exceeded, invalid_paths_seen
            if entries_seen >= MAX_SCAN_ENTRIES or bytes_read >= MAX_TOTAL_BYTES or budget_exceeded:
                return
            try:
                entries = os.scandir(directory_fd)
            except OSError:
                return
            try:
                with entries:
                    iterator = iter(entries)
                    while True:
                        if bytes_read >= MAX_TOTAL_BYTES or budget_exceeded:
                            return
                        try:
                            entry = next(iterator)
                        except StopIteration:
                            break
                        entries_seen += 1
                        if entries_seen >= MAX_SCAN_ENTRIES:
                            budget_exceeded = True
                        name = entry.name
                        if name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
                            continue
                        try:
                            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                        except OSError:
                            continue
                        relative = f"{prefix}/{name}" if prefix else name
                        if stat.S_ISDIR(info.st_mode):
                            if depth >= 32:
                                continue
                            try:
                                child = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                                getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
                            except OSError:
                                continue
                            try:
                                visit(child, relative, depth + 1)
                            finally:
                                os.close(child)
                            continue
                        if (not stat.S_ISREG(info.st_mode) or info.st_nlink > 1
                                or not name.lower().endswith(".md")):
                            continue
                        if info.st_size < 0 or info.st_size > MAX_FILE_BYTES or bytes_read + info.st_size > MAX_TOTAL_BYTES:
                            continue
                        try:
                            fd, opened_info = _open_exact(root_fd, relative)
                        except (ValueError, UnicodeError):
                            # Unsafe names are omitted from Knowledge results;
                            # signal incomplete coverage without relaxing the
                            # exact-item path validation contract.
                            invalid_paths_seen = True
                            continue
                        try:
                            try:
                                allowed_bytes = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - bytes_read)
                                if opened_info.st_size > allowed_bytes:
                                    continue
                                payload = _read_bounded(fd, allowed_bytes)
                                bytes_read += len(payload)
                                if len(payload) > allowed_bytes:
                                    budget_exceeded = True
                                    continue
                            finally:
                                os.close(fd)
                            text = payload.decode("utf-8")
                        except (OSError, UnicodeDecodeError):
                            continue
                        if not text.strip():
                            continue
                        title = _frontmatter_title(text, PurePosixPath(name).stem)
                        searchable = (title + "\n" + text).casefold()
                        if query.casefold() not in searchable:
                            continue
                        rows.append({
                            "id": _token(relative, hashlib.sha256(payload).hexdigest(), self._id_secret),
                            "title": title,
                            "snippet": _snippet(text, query),
                            "match": "title" if query.casefold() in title.casefold() else "content",
                            "updated": datetime.fromtimestamp(opened_info.st_mtime, timezone.utc).isoformat(),
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "provenance_status": _provenance_status(payload),
                        })
            except OSError:
                return

        try:
            visit(root_fd, "")
        finally:
            os.close(root_fd)
        rows.sort(key=lambda row: (row["title"].casefold(), row["id"]))
        return {"items": rows[:limit], "status": "truncated" if invalid_paths_seen or entries_seen >= MAX_SCAN_ENTRIES or bytes_read >= MAX_TOTAL_BYTES or budget_exceeded else "ok"}

    def detail(self, item_id):
        relative, expected_sha256 = _decode_token(item_id, self._id_secret)
        root_fd = self._root_fd()
        try:
            try:
                fd, info = _open_exact(root_fd, relative)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Knowledge item not found")
            except OSError:
                raise HTTPException(status_code=404, detail="Knowledge item unavailable")
            try:
                if info.st_size > MAX_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="Knowledge item is too large")
                payload = _read_bounded(fd, MAX_FILE_BYTES)
                if len(payload) > MAX_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="Knowledge item is too large")
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(status_code=422, detail="Knowledge item is unavailable")
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)
        if len(text) > MAX_DETAIL_CHARS:
            raise HTTPException(status_code=413, detail="Knowledge item is too large")
        digest = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(digest, expected_sha256):
            raise HTTPException(status_code=409, detail="Knowledge item changed; search again")
        return {"id": item_id, "content": text, "sha256": digest,
                "updated": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                "provenance_status": _provenance_status(payload)}

    def source(self, item_id):
        relative, expected_sha256 = _decode_token(item_id, self._id_secret)
        detail = self.detail(item_id)
        content = detail["content"].encode("utf-8")
        verified = self._verified_source(relative, content, expected_sha256)
        if verified:
            return {"status": "available", "provenance_status": "verified", "source": verified}
        status = _provenance_status(content)
        return {"status": "unavailable" if status == "unverified" else "missing",
                "provenance_status": status, "source": None}

    def chat_recall(self, query, *, max_items=3, max_item_bytes=8 * 1024,
                    max_total_bytes=16 * 1024):
        """Build a bounded internal Chat context from exact verified Knowledge.

        This is deliberately separate from the public search response: the
        relative path and content stay server-side and are never accepted from
        a browser. Only documents whose exact current bytes have verified
        provenance are eligible for a reference citation.
        """
        rows = self.search(query, max_items)
        selected = []
        total = 0
        partial = rows["status"] != "ok"
        for row in rows["items"]:
            if len(selected) >= max_items or total >= max_total_bytes:
                partial = True
                break
            try:
                relative, expected_sha256 = _decode_token(row["id"], self._id_secret)
                source = self.source(row["id"])
                if source.get("status") != "available" or source.get("provenance_status") != "verified":
                    continue
                detail = self.detail(row["id"])
                payload = detail["content"].encode("utf-8")
                digest = hashlib.sha256(payload).hexdigest()
                if (not hmac.compare_digest(digest, expected_sha256)
                        or not hmac.compare_digest(digest, detail["sha256"])):
                    partial = True
                    continue
                remaining = max_total_bytes - total
                excerpt = payload[:min(max_item_bytes, remaining)].decode("utf-8", errors="ignore")
                if not excerpt:
                    partial = True
                    continue
                selected.append({"relative_path": relative, "title": row["title"],
                                 "sha256": digest, "content": excerpt,
                                 "provenance_status": "verified"})
                total += len(excerpt.encode("utf-8"))
                if len(payload) > len(excerpt.encode("utf-8")):
                    partial = True
            except HTTPException as exc:
                if exc.status_code in {404, 409, 413, 422, 503}:
                    partial = True
                    continue
                raise
        return {"items": selected,
                "status": "available" if selected and not partial else
                          "partial" if partial else "none"}

    def verify_chat_reference(self, relative_path, expected_sha256):
        """Re-read one stored internal reference without exposing its path."""
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            return False
        root_fd = self._root_fd()
        try:
            try:
                fd, info = _open_exact(root_fd, relative_path)
            except (OSError, ValueError, UnicodeError):
                return False
            try:
                if info.st_size > MAX_FILE_BYTES:
                    return False
                payload = _read_bounded(fd, MAX_FILE_BYTES)
                if len(payload) > MAX_FILE_BYTES:
                    return False
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)
        digest = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(digest, expected_sha256):
            return False
        return self._verified_source(relative_path, payload, digest) is not None

    def _verified_source(self, relative, content, digest):
        if self.provenance_verifier is None:
            return None
        try:
            return self.provenance_verifier.verify(relative, content, digest)
        except Exception:
            # Provenance verification is a read-only enhancement. Corrupt or
            # unavailable evidence must never turn an untrusted claim trusted.
            return None

def create_knowledge_read_router(auth, store):
    router = APIRouter(prefix="/api/knowledge")

    def require(request):
        auth.require_action(request, "knowledge.read")

    @router.get("/search")
    def search(request: Request, response: Response, q: str = "", limit: int = DEFAULT_LIMIT):
        require(request)
        response.headers["Cache-Control"] = "private, no-store"
        return store.search(q, limit)

    @router.get("/items/{knowledge_id}")
    def detail(request: Request, knowledge_id: str, response: Response):
        require(request)
        result = store.detail(knowledge_id)
        response.headers["ETag"] = f'"{result["sha256"]}"'
        response.headers["Cache-Control"] = "private, no-store"
        return result

    @router.get("/items/{knowledge_id}/source")
    def source(request: Request, knowledge_id: str, response: Response):
        require(request)
        response.headers["Cache-Control"] = "private, no-store"
        return store.source(knowledge_id)

    return router
