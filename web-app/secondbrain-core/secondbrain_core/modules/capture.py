"""File-backed Universal Capture intake and deterministic processors.

Raw evidence is immutable. The capture status journal lives in Core's private
state directory; Review files reuse the canonical Markdown frontmatter fields.
"""
import hashlib
import fcntl
import http.client
import ipaddress
import json
import os
import re
import socket
import stat
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, UploadFile
from pypdf import PdfReader
from .channel_identity import authenticated_web_identity, validate_trusted_identity


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_CAPTURE_STATE_BYTES = 1024 * 1024
MAX_ACTIVITY_CAPTURE_STATE_FILES = 500
MAX_ACTIVITY_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_DISPLAY_FILENAME_CHARS = 255
MAX_WEB_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 4
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf", ".png", ".jpg", ".jpeg",
                    ".webp", ".gif", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
SUMMARY_STATUSES = {"pending", "prepared", "processing", "completed", "partial_success", "failed"}
SUMMARY_ERROR_CODES = {"processing_interrupted", "processor_unavailable", "processing_failed"}
SUMMARY_SOURCE_TYPES = {"text", "url", "file", "markdown", "pdf", "image", "audio", "capture_context",
                        "inbox_proposal_review"}
SUMMARY_INPUT_TYPES = {"text", "markdown", "url", "txt", "md", "pdf", "png", "jpg", "jpeg", "webp", "gif",
                       "wav", "mp3", "m4a", "aac", "ogg", "flac"}
PREVIEW_MEDIA_TYPES = {
    ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
    ".markdown": "text/plain; charset=utf-8", ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".wav": "audio/wav",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".flac": "audio/flac",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_name(name, suffix):
    raw = Path((name or "capture") .replace("\\", "/")).name
    raw = raw.replace("\x00", "")
    stem = Path(raw).stem[:100] or "capture"
    clean = _SAFE_NAME.sub("-", stem).strip(".-_") or "capture"
    return clean + suffix


def _display_filename(name, suffix):
    """Keep a bounded, human-readable upload name separate from the safe Raw path."""
    raw = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    raw = "".join(char for char in raw if unicodedata.category(char) not in {"Cc", "Cf", "Cs"}).strip()
    if not raw:
        raw = "upload" + suffix
    if len(raw) > MAX_DISPLAY_FILENAME_CHARS:
        extension = Path(raw).suffix
        if len(extension) >= MAX_DISPLAY_FILENAME_CHARS:
            extension = ""
        raw = raw[:MAX_DISPLAY_FILENAME_CHARS - len(extension)] + extension
    return raw


def _valid_signature(suffix, data):
    if suffix == ".pdf":
        return data.startswith(b"%PDF-")
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if suffix == ".wav":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if suffix == ".mp3":
        return data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    if suffix == ".m4a":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if suffix == ".aac":
        return len(data) >= 2 and data[0] == 0xFF and data[1] & 0xF6 == 0xF0
    if suffix == ".ogg":
        return data.startswith(b"OggS")
    if suffix == ".flac":
        return data.startswith(b"fLaC")
    return suffix in {".txt", ".md", ".markdown"}


def _yaml_scalar(value):
    return json.dumps(str(value), ensure_ascii=False)


def _frontmatter(source_type, captured_at, original_asset, capture_context="", status="pending"):
    fields = {
        "type": "review", "status": "pending", "source_type": source_type,
        "captured_at": captured_at, "original_asset": original_asset,
        "capture_context": capture_context, "tags": "[]", "review_status": status,
    }
    return "---\n" + "".join(f"{key}: {_yaml_scalar(value)}\n" for key, value in fields.items()) + "---\n"


class _TextExtractor(HTMLParser):
    BLOCKED = {"script", "style", "noscript", "svg", "nav", "footer", "header"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKED:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCKED and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data.strip())
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def _resolve_public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public http/https URLs without credentials are accepted")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Non-standard URL ports are not accepted")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".test")):
        raise ValueError("Local and internal hostnames are not accepted")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)]
        except OSError as exc:
            raise ValueError("URL host could not be resolved") from exc
    if not addresses or any(not addr.is_global for addr in addresses):
        raise ValueError("URL resolves to a non-public address")
    return parsed, str(addresses[0])


def _public_http_url(url):
    return _resolve_public_url(url)[0]


def _fetch_url(url):
    current = url
    for redirect in range(MAX_REDIRECTS + 1):
        parsed, pinned_ip = _resolve_public_url(current)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # Connect directly to the address validated above. HTTPS uses the URL
        # hostname for both SNI and certificate checks, preventing DNS rebinding
        # between validation and the actual connection.
        if parsed.scheme == "https":
            class PinnedHTTPSConnection(http.client.HTTPSConnection):
                def connect(self):
                    raw = socket.create_connection((pinned_ip, port), timeout=5)
                    self.sock = self._context.wrap_socket(raw, server_hostname=parsed.hostname)
            connection = PinnedHTTPSConnection(parsed.hostname, port, timeout=15)
        else:
            class PinnedHTTPConnection(http.client.HTTPConnection):
                def connect(self):
                    self.sock = socket.create_connection((pinned_ip, port), timeout=5)
            connection = PinnedHTTPConnection(parsed.hostname, port, timeout=15)
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        try:
            host_header = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
            connection.request("GET", target, headers={"Host": host_header, "User-Agent": "SecondBrain-Capture/1.0", "Accept": "text/html,text/plain", "Connection": "close"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                if redirect == MAX_REDIRECTS:
                    raise ValueError("Too many redirects")
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirect missing Location")
                current = urljoin(current, location)
                continue
            if response.status < 200 or response.status >= 300:
                raise ValueError(f"Web request returned HTTP {response.status}")
            content_type = (response.getheader("Content-Type") or "").lower()
            if not ("text/html" in content_type or "text/plain" in content_type or not content_type):
                raise ValueError("URL response is not readable HTML or text")
            body = response.read(MAX_WEB_BYTES + 1)
            if len(body) > MAX_WEB_BYTES:
                raise ValueError("Web page exceeds the 5 MiB limit")
            charset = response.headers.get_content_charset() or "utf-8"
            return current, body.decode(charset, errors="replace"), content_type
        finally:
            connection.close()
    raise ValueError("Unable to fetch URL")


class CaptureService:
    def __init__(self, raw_root, review_root, state_root, processors=None):
        self.raw_root = Path(raw_root)
        self.review_root = Path(review_root)
        self.state_root = Path(state_root) / "captures"
        self._active = set()
        self._active_lock = threading.Lock()
        if processors is None:
            from .multimodal_capture import MultimodalCaptureProcessors
            processors = MultimodalCaptureProcessors()
        self.processors = processors
        self._validate_root(self.raw_root)
        self._validate_root(self.review_root)
        self._validate_root(self.state_root, allow_missing=True)
        if not os.access(self.raw_root, os.W_OK) or not os.access(self.review_root, os.W_OK):
            raise RuntimeError("Capture Raw and Review roots must be writable by the Core UID")
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_info = self.state_root.lstat()
        if (not stat.S_ISDIR(state_info.st_mode) or stat.S_ISLNK(state_info.st_mode)
                or state_info.st_uid != os.geteuid() or state_info.st_mode & 0o077
                or not os.access(self.state_root, os.W_OK)):
            raise RuntimeError("Capture state directory must be private and writable by the Core UID")
        self._state_root_identity = (state_info.st_dev, state_info.st_ino)

    @staticmethod
    def _validate_root(path, allow_missing=False):
        if not path.is_absolute():
            raise RuntimeError("Capture roots must be absolute paths")
        if not path.exists() and not allow_missing:
            raise RuntimeError("Capture data roots must exist as explicitly mounted directories")
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            raise RuntimeError("Capture roots must be real directories, not symlinks")

    def _state_path(self, capture_id):
        if not re.fullmatch(r"[0-9a-f]{32}", capture_id):
            raise HTTPException(404, "Capture not found")
        return self.state_root / (capture_id + ".json")

    @staticmethod
    def _fsync_directory(path):
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write_state(self, value):
        target = self._state_path(value["capture_id"])
        temp = self.state_root / ("." + value["capture_id"] + "." + uuid.uuid4().hex + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(value, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, target)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def _read_state(self, path):
        if (not isinstance(path, Path) or path.parent != self.state_root
                or not re.fullmatch(r"[0-9a-f]{32}\.json", path.name)):
            return None
        root_fd = None
        state_fd = None
        try:
            root_fd = os.open(self.state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                              | getattr(os, "O_NOFOLLOW", 0))
            root_info = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                    or root_info.st_mode & 0o077
                    or (root_info.st_dev, root_info.st_ino) != self._state_root_identity):
                raise ValueError
            state_fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                               | getattr(os, "O_NONBLOCK", 0), dir_fd=root_fd)
            info = os.fstat(state_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size > MAX_CAPTURE_STATE_BYTES):
                raise ValueError
            chunks, total = [], 0
            while True:
                chunk = os.read(state_fd, min(65536, MAX_CAPTURE_STATE_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_CAPTURE_STATE_BYTES:
                    raise ValueError
            value = json.loads(b"".join(chunks).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError, RecursionError):
            return None
        finally:
            if state_fd is not None:
                os.close(state_fd)
            if root_fd is not None:
                os.close(root_fd)

    def list(self, limit=100):
        result = []
        for path in self.state_root.glob("*.json"):
            item = self._read_state(path)
            if item:
                self._recover_interrupted(item)
            if item:
                result.append(item)
        return sorted((item for item in result if item), key=lambda item: item.get("captured_at", ""), reverse=True)[:limit]

    def list_summary(self, limit=100):
        """Read a bounded metadata projection without recovery or state writes."""
        result = []
        for path in self.state_root.glob("*.json"):
            item = self._read_state(path)
            if not item:
                continue
            source_type = item.get("source_type")
            input_type = item.get("input_type")
            status = item.get("status")
            error = item.get("error")
            error_code = error.get("code") if isinstance(error, dict) else None
            display_filename = item.get("display_filename")
            captured_at = item.get("captured_at")
            capture_id = item.get("capture_id")
            result.append({
                "capture_id": capture_id if isinstance(capture_id, str) and re.fullmatch(r"[0-9a-f]{32}", capture_id) else None,
                "source_type": source_type if isinstance(source_type, str) and source_type in SUMMARY_SOURCE_TYPES else None,
                "input_type": input_type if isinstance(input_type, str) and input_type in SUMMARY_INPUT_TYPES else None,
                "captured_at": captured_at if isinstance(captured_at, str) and len(captured_at) <= 64 else None,
                "display_filename": display_filename if isinstance(display_filename, str) and len(display_filename) <= MAX_DISPLAY_FILENAME_CHARS else None,
                "status": status if isinstance(status, str) and status in SUMMARY_STATUSES else "unknown",
                "error_code": error_code if isinstance(error_code, str) and error_code in SUMMARY_ERROR_CODES else None,
                "has_review": isinstance(item.get("review_path"), str) and bool(item.get("review_path")),
            })
        result.sort(key=lambda item: (item["captured_at"] or "", item["capture_id"] or ""), reverse=True)
        return result[:limit]

    def read_activity_events(self):
        """Read a stable, bounded projection of authoritative Capture state.

        This is deliberately separate from ``list``: Activity reads must not
        repair interrupted Capture work or touch Raw/Review artifacts. A
        directory beyond the fixed file budget is reported incomplete without
        selecting an arbitrary subset as if it were a stable history.
        """
        root_fd = None
        try:
            root_fd = os.open(self.state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                              | getattr(os, "O_NOFOLLOW", 0))
            root_before = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_before.st_mode) or root_before.st_uid != os.geteuid()
                    or root_before.st_mode & 0o077
                    or (root_before.st_dev, root_before.st_ino) != self._state_root_identity):
                return [], False

            names = []
            with os.scandir(os.dup(root_fd)) as entries:
                for entry in entries:
                    if re.fullmatch(r"[0-9a-f]{32}\.json", entry.name):
                        if len(names) >= MAX_ACTIVITY_CAPTURE_STATE_FILES:
                            return [], False
                        names.append(entry.name)
            names.sort()

            total_bytes = 0
            events = []
            complete = True
            for name in names:
                fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0), dir_fd=root_fd)
                try:
                    before = os.fstat(fd)
                    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                            or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                            or before.st_size < 0 or before.st_size > MAX_CAPTURE_STATE_BYTES
                            or total_bytes + before.st_size > MAX_ACTIVITY_CAPTURE_BYTES):
                        return [], False
                    chunks, size = [], 0
                    while size <= before.st_size:
                        chunk = os.read(fd, min(65536, before.st_size + 1 - size))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                    after = os.fstat(fd)
                    if (size != before.st_size
                            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                                before.st_ctime_ns)
                            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                                after.st_ctime_ns)):
                        return [], False
                    total_bytes += size
                finally:
                    os.close(fd)

                try:
                    value = json.loads(b"".join(chunks).decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError, RecursionError):
                    complete = False
                    continue
                capture_id = value.get("capture_id") if isinstance(value, dict) else None
                source_type = value.get("source_type") if isinstance(value, dict) else None
                status = value.get("status") if isinstance(value, dict) else None
                captured_at = value.get("captured_at") if isinstance(value, dict) else None
                if (capture_id != name[:-5] or not isinstance(source_type, str)
                        or source_type not in SUMMARY_SOURCE_TYPES or not isinstance(status, str)
                        or status not in SUMMARY_STATUSES or not isinstance(captured_at, str)
                        or len(captured_at) > 64):
                    complete = False
                    continue
                events.append({"capture_id": capture_id, "captured_at": captured_at,
                               "status": status})

            root_after = os.fstat(root_fd)
            if ((root_before.st_dev, root_before.st_ino, root_before.st_mtime_ns, root_before.st_ctime_ns)
                    != (root_after.st_dev, root_after.st_ino, root_after.st_mtime_ns, root_after.st_ctime_ns)):
                return [], False
            return events, complete
        except OSError:
            return [], False
        finally:
            if root_fd is not None:
                os.close(root_fd)

    def get(self, capture_id):
        path = self._state_path(capture_id)
        state = self._read_state(path)
        if not state:
            raise HTTPException(404, "Capture not found")
        self._recover_interrupted(state)
        return state

    def _recover_interrupted(self, state):
        with self._active_lock:
            active = state.get("capture_id") in self._active
        if state.get("status") == "processing" and not active:
            state.update(status="partial_success", error={"code": "processing_interrupted", "message": "Processing stopped before completion; the preserved Raw asset can be retried."}, updated_at=_now())
            self._write_state(state)

    def mark_scheduled(self, state):
        with self._active_lock:
            if state["capture_id"] in self._active:
                return False
            self._active.add(state["capture_id"])
            return True

    def retry(self, capture_id):
        state = self.get(capture_id)
        if state.get("status") not in {"partial_success", "failed"} or not state.get("raw_path"):
            raise HTTPException(409, "Capture is not retryable")
        raw_name = state.get("raw_path")
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in {".", ".."}:
            raise HTTPException(409, "Raw asset path is invalid")
        raw_file = self.raw_root / raw_name
        try:
            info = raw_file.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise OSError
            raw = raw_file.read_bytes()
        except OSError as exc:
            raise HTTPException(409, "Raw asset is missing or unsafe") from exc
        state.update(status="processing", error=None, updated_at=_now())
        self._write_state(state)
        self.process(state, raw)
        return state

    def _create_raw(self, filename, data, exact_name=False):
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Unsupported file type")
        safe = _safe_name(filename, suffix)
        if exact_name:
            path = self.raw_root / safe
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError as exc:
                # A matching Raw without its durable state is an interrupted write,
                # not proof that this request may recreate the missing state.
                raise FileExistsError("Inbox Raw/state recovery requires manual review") from exc
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            self._fsync_directory(self.raw_root)
            return safe
        for attempt in range(1000):
            candidate = safe if attempt == 0 else f"{Path(safe).stem}-{attempt}{suffix}"
            path = self.raw_root / candidate
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                continue
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return candidate
        raise ValueError("Unable to allocate a collision-safe Raw filename")

    def accept_file(self, filename, data, source_type=None, context="", *,
                    capture_id=None, extra_state=None, exact_raw_name=False):
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("Files must be 20 MiB or smaller")
        suffix = Path((filename or "")).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Supported files: TXT, Markdown, PDF, image, and audio")
        if suffix not in {".txt", ".md", ".markdown"} and not _valid_signature(suffix, data):
            raise ValueError("Uploaded file content does not match its declared file type")
        captured_at = _now()
        source_type = source_type or ({".md": "markdown", ".markdown": "markdown", ".txt": "text",
                                       ".pdf": "pdf", ".png": "image", ".jpg": "image",
                                       ".jpeg": "image", ".webp": "image", ".gif": "image"}.get(
                                           suffix, "audio" if suffix in AUDIO_SUFFIXES else "file"))
        capture_id = capture_id or uuid.uuid4().hex
        if not re.fullmatch(r"[0-9a-f]{32}", capture_id):
            raise ValueError("Invalid Capture ID")
        raw_data = data
        source_url = None
        if source_type == "url":
            source_url = data.decode("utf-8").strip()
            raw_data = f"Original URL: {source_url}\nCaptured at: {captured_at}\n".encode("utf-8")
        try:
            raw_path = self._create_raw(filename, raw_data, exact_name=exact_raw_name)
        except FileExistsError as exc:
            raise HTTPException(503, "Inbox Raw/state recovery requires manual review") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(500, "Could not preserve Raw evidence") from exc
        state = {"capture_id": capture_id, "source_type": source_type,
                 "input_type": "url" if source_type == "url" else "text" if suffix in {".txt", ".md", ".markdown"} else suffix[1:],
                 "captured_at": captured_at, "updated_at": captured_at,
                 "original_asset": "/knowledge-assets/00-Inbox/" + raw_path, "raw_path": raw_path,
                 "display_filename": _display_filename(filename, suffix),
                 "raw_sha256": hashlib.sha256(raw_data).hexdigest(),
                 "review_path": None, "status": "processing", "error": None,
                 "title": Path(raw_path).stem, "content_preview": raw_data[:4096].decode("utf-8", errors="replace") if suffix in {".txt", ".md", ".markdown"} else "",
                 "capture_context": context[:2000], **(extra_state or {})}
        if source_url is not None:
            state["source_url"] = source_url
        self._write_state(state)
        return state

    def _verified_attachment_refs(self, attachment_refs):
        if not isinstance(attachment_refs, list) or len(attachment_refs) > 5:
            raise HTTPException(400, "At most five verified Capture attachment references are accepted")
        verified = []
        seen = set()
        for item in attachment_refs:
            if (not isinstance(item, dict) or set(item) != {"capture_id", "sha256"}
                    or not isinstance(item.get("capture_id"), str)
                    or not re.fullmatch(r"[0-9a-f]{32}", item["capture_id"])
                    or not isinstance(item.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
                raise HTTPException(400, "Attachment references must use a Capture ID and SHA-256")
            capture_id = item["capture_id"]
            if capture_id in seen:
                raise HTTPException(400, "Duplicate attachment reference")
            seen.add(capture_id)
            state = self.get(capture_id)
            if state.get("source_channel") not in {None, "web"}:
                raise HTTPException(409, "Attachment source has no trusted Core channel identity")
            raw_name = state.get("raw_path")
            if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in {".", ".."}:
                raise HTTPException(404, "Attachment source is unavailable")
            try:
                root_fd = os.open(self.raw_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                  getattr(os, "O_NOFOLLOW", 0))
                try:
                    fd = os.open(raw_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                finally:
                    os.close(root_fd)
                try:
                    info = os.fstat(fd)
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                            or info.st_size > MAX_UPLOAD_BYTES
                            or state.get("raw_sha256") != item["sha256"]):
                        raise HTTPException(409, "Attachment source version does not match its Capture record")
                    digest = hashlib.sha256()
                    while True:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        digest.update(chunk)
                finally:
                    os.close(fd)
            except HTTPException:
                raise
            except OSError as exc:
                raise HTTPException(404, "Attachment source is unavailable") from exc
            if digest.hexdigest() != item["sha256"]:
                raise HTTPException(409, "Attachment source changed")
            verified.append({"capture_id": capture_id, "sha256": item["sha256"]})
        return verified

    def accept_channel_text(self, *, text, identity, source_event_id, intent,
                            occurred_at, approved_proposal=None, attachment_refs=None,
                            precommit_validator=None):
        """Persist one explicit, channel-scoped Inbox event with durable idempotency.

        Caller-supplied event IDs are idempotency keys, never caller identity or
        consent evidence. Non-Web callers must arrive through a trusted Core adapter.
        """
        identity = validate_trusted_identity(identity)
        source_channel = identity.channel
        if (not isinstance(source_event_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", source_event_id)
                or not isinstance(intent, str)
                or intent not in {"explicit_capture", "journal_intent", "task_intent", "approved_suggestion"}):
            raise HTTPException(400, "Inbox event identity or intent is invalid")
        consent_subject = getattr(identity, "subject", None)
        if not isinstance(consent_subject, str) or not consent_subject:
            raise HTTPException(401, "Authenticated App identity is required")
        if (intent == "approved_suggestion") != isinstance(approved_proposal, dict):
            raise HTTPException(409, "Approved suggestion must be bound to a current Core approval")
        verified_attachments = self._verified_attachment_refs(attachment_refs or [])
        if not isinstance(occurred_at, str) or len(occurred_at) > 64:
            raise HTTPException(400, "Inbox event time is invalid")
        try:
            occurred = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            if occurred.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(400, "Inbox event time must include a timezone") from exc
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise HTTPException(400, "Text must contain 1-200000 characters")
        identity_scope = {"adapter_id": identity.adapter_id, "tenant": identity.tenant,
                          "principal": consent_subject}
        if source_channel != "web":
            identity_scope["consent_evidence_id"] = identity.consent_evidence_id
        namespace = (source_channel + "\0" + source_event_id if source_channel == "web" else
                     source_channel + "\0" + identity.adapter_id + "\0" + identity.tenant + "\0" +
                     consent_subject + "\0" + source_event_id)
        capture_id = hashlib.sha256(("secondbrain-inbox-event\0" + namespace).encode("utf-8")).hexdigest()[:32]
        event_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        digest_payload = {"source_channel": source_channel, "source_event_id": source_event_id,
             "occurred_at": occurred.isoformat(), "intent": intent,
             "original_text_sha256": event_digest,
             "approved_proposal": approved_proposal,
             "attachment_refs": verified_attachments}
        if source_channel != "web":
            digest_payload["identity_scope"] = identity_scope
        request_digest = hashlib.sha256(json.dumps(
            digest_payload,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        lock_path = self.state_root / (".inbox-event-" + capture_id + ".lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(lock_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise HTTPException(503, "Inbox idempotency state is unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            state_path = self._state_path(capture_id)
            state_present = os.path.lexists(state_path)
            existing = self._read_state(state_path) if state_present else None
            if state_present and existing is None:
                raise HTTPException(503, "Inbox event recovery requires manual review")
            if existing:
                if (existing.get("source_channel") != source_channel
                        or existing.get("source_event_id") != source_event_id
                        or existing.get("identity_scope", {"adapter_id": "web", "tenant": "default",
                                                            "principal": existing.get("consent_evidence", {}).get("subject")}) != identity_scope
                        or existing.get("intent") != intent
                        or existing.get("original_text_sha256") != event_digest
                        or existing.get("approved_proposal") != approved_proposal
                        or existing.get("attachment_refs", []) != verified_attachments
                        or existing.get("source_event_request_sha256") != request_digest):
                    raise HTTPException(409, "Inbox event key is already bound to different content")
                raw_path = existing.get("raw_path")
                if not isinstance(raw_path, str) or Path(raw_path).name != raw_path:
                    raise HTTPException(503, "Inbox event recovery requires review")
                try:
                    raw_fd = os.open(self.raw_root / raw_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    with os.fdopen(raw_fd, "rb") as raw:
                        raw_info = os.fstat(raw.fileno())
                        raw_bytes = raw.read()
                    if (not stat.S_ISREG(raw_info.st_mode) or raw_info.st_uid != os.geteuid()
                            or hashlib.sha256(raw_bytes).hexdigest() != existing.get("raw_sha256")
                            or raw_bytes != text.encode("utf-8")):
                        raise HTTPException(409, "Inbox event source no longer matches its stored version")
                except OSError as exc:
                    raise HTTPException(503, "Inbox event recovery requires review") from exc
                return existing, True
            if precommit_validator is not None:
                precommit_validator()
            server_time = _now()
            is_adapter = identity.authentication == "trusted_adapter_v1"
            evidence = {"kind": ("trusted_adapter_approved_proposal" if approved_proposal else
                                 "trusted_adapter_explicit_action") if is_adapter else
                        ("authenticated_app_approved_proposal" if approved_proposal else
                         "authenticated_app_explicit_action"), "subject": consent_subject,
                        "recorded_at": server_time}
            if is_adapter:
                evidence.update({"adapter_id": identity.adapter_id, "channel": source_channel,
                                 "tenant": identity.tenant,
                                 "consent_evidence_id": identity.consent_evidence_id})
            if approved_proposal:
                evidence.update({"proposal_id": approved_proposal["proposal_id"],
                                 "proposal_version": approved_proposal["version"],
                                 "source_version": approved_proposal["source_version"]})
            state = self.accept_file(
                "Inbox-" + capture_id + ".md", text.encode("utf-8"), "markdown",
                context="explicit channel event; consent recorded by Core",
                capture_id=capture_id, exact_raw_name=True,
                extra_state={"source_channel": source_channel, "source_event_id": source_event_id,
                             "identity_scope": identity_scope,
                             "occurred_at": occurred.isoformat(), "intent": intent,
                             "original_text_sha256": event_digest,
                             "source_event_request_sha256": request_digest,
                             "consent_evidence": evidence,
                             "approved_proposal": approved_proposal,
                             "attachment_refs": verified_attachments},
            )
            return state, False
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def accept_text(self, text, source_type="text", context=""):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise HTTPException(400, "Text must contain 1-200000 characters")
        filename = "capture.md" if source_type == "text" else "capture.txt"
        return self.accept_file(filename, text.encode("utf-8"), source_type, context)

    def create_approved_review(self, *, text, title, execution_key, proposal_id,
                               source_ref, source_version_sha256, captured_at):
        """Submit an explicitly confirmed Inbox candidate through Capture→Review.

        The deterministic operation ID, Raw name and Review name let a retry
        after a lost response recover the same immutable target. Existing
        artifacts are reused only when their bytes match; nothing is overwritten.
        """
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise HTTPException(400, "Review text must contain 1-200000 characters")
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            raise HTTPException(400, "Review title must contain 1-160 characters")
        if (not isinstance(execution_key, str) or not re.fullmatch(r"c2c-[0-9a-f]{32}", execution_key)
                or not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{32}", proposal_id)
                or not isinstance(source_version_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_version_sha256)
                or not isinstance(source_ref, str) or len(source_ref) > 512):
            raise HTTPException(400, "Approved Review provenance is invalid")
        try:
            datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise HTTPException(400, "Approved Review timestamp is invalid") from exc

        operation_digest = hashlib.sha256(execution_key.encode("ascii")).hexdigest()
        capture_id = operation_digest[:32]
        raw_name = f"Inbox-Proposal-{capture_id}.md"
        review_name = f"Inbox-Proposal-{capture_id}.md"
        raw_data = text.encode("utf-8")
        raw_digest = hashlib.sha256(raw_data).hexdigest()
        context = f"approved_proposal={proposal_id}; source={source_ref}; source_sha256={source_version_sha256}"
        state_path = self._state_path(capture_id)
        lock_path = self.state_root / ".approved-review-create.lock"
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            lock_info = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid() or lock_info.st_mode & 0o077:
                raise HTTPException(500, "Approved Review creation lock is unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            existing = self._read_state(state_path) if state_path.exists() else None
            replayed = existing is not None
            if existing:
                if (existing.get("approved_proposal_execution_key") != execution_key
                        or existing.get("approved_proposal_id") != proposal_id
                        or existing.get("approved_source_sha256") != source_version_sha256
                        or existing.get("approved_content_sha256") != raw_digest
                        or existing.get("title") != title.strip()
                        or existing.get("raw_path") != raw_name
                        or existing.get("review_path_hint") != review_name):
                    raise HTTPException(409, "Approved Review idempotency key belongs to different content")
                captured_at = existing["captured_at"]
                state = existing
            else:
                state = {"capture_id": capture_id, "source_type": "inbox_proposal_review",
                         "input_type": "markdown", "captured_at": captured_at,
                         "updated_at": captured_at, "original_asset": "/knowledge-assets/00-Inbox/" + raw_name,
                         "raw_path": raw_name, "display_filename": title.strip() + ".md",
                         "raw_sha256": raw_digest, "review_path": None, "review_sha256": None,
                         "review_path_hint": review_name, "status": "prepared", "error": None,
                         "title": title.strip(), "approved_title": title.strip(),
                         "content_preview": raw_data[:4096].decode("utf-8", errors="replace"),
                         "capture_context": context,
                         "approved_proposal_execution_key": execution_key,
                         "approved_proposal_id": proposal_id,
                         "approved_source_sha256": source_version_sha256,
                         "approved_content_sha256": raw_digest}
                # Persist the operation identity before creating either artifact.
                self._write_state(state)

            raw_path = self.raw_root / raw_name
            try:
                raw_fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                try:
                    info = raw_path.lstat()
                    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or hashlib.sha256(raw_path.read_bytes()).hexdigest() != raw_digest:
                        raise HTTPException(409, "Existing approved Raw artifact does not match this operation")
                except OSError as exc:
                    raise HTTPException(409, "Existing approved Raw artifact is unsafe") from exc
            else:
                try:
                    with os.fdopen(raw_fd, "wb") as output:
                        output.write(raw_data)
                        output.flush()
                        os.fsync(output.fileno())
                except OSError as exc:
                    raise HTTPException(500, "Approved Raw artifact could not be saved safely") from exc
            try:
                self._fsync_directory(self.raw_root)
            except OSError as exc:
                raise HTTPException(500, "Approved Raw directory could not be synchronized safely") from exc
            state.update(status="processing", error=None, updated_at=_now())
            self._write_state(state)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

        process_lock_path = self.state_root / f".{capture_id}.approved-review.lock"
        process_fd = os.open(process_lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(process_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(500, "Approved Review process lock is unsafe")
            fcntl.flock(process_fd, fcntl.LOCK_EX)
            state = self._read_state(state_path)
            if not state or state.get("approved_proposal_execution_key") != execution_key:
                raise HTTPException(409, "Approved Review state is unavailable")
            if state.get("status") == "completed" and state.get("review_path"):
                self._verify_artifacts(state)
                state["_idempotent_replay"] = replayed
                return state
            try:
                raw_fd = os.open(raw_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(raw_fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_UPLOAD_BYTES:
                        raise HTTPException(409, "Approved Raw artifact is unsafe")
                    current_raw = stream.read(MAX_UPLOAD_BYTES + 1)
            except OSError as exc:
                raise HTTPException(409, "Approved Raw artifact is unavailable") from exc
            if hashlib.sha256(current_raw).hexdigest() != raw_digest:
                raise HTTPException(409, "Approved Raw artifact changed")
            state.update(status="processing", error=None, updated_at=_now())
            self._write_state(state)
            self.process(state, current_raw)
            state = self._read_state(state_path)
            if state and state.get("review_path") and state.get("review_sha256"):
                self._verify_artifacts(state)
            if not state or not state.get("review_path"):
                raise HTTPException(503, "Capture did not produce a verified Review item")
            state["_idempotent_replay"] = replayed
            return state
        finally:
            fcntl.flock(process_fd, fcntl.LOCK_UN)
            os.close(process_fd)

    def accept_url(self, url, context=""):
        if not isinstance(url, str) or len(url) > 2048:
            raise HTTPException(400, "A valid URL up to 2048 characters is required")
        try:
            _public_http_url(url)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        state = self.accept_file("web-capture.md", url.encode("utf-8"), "url", context)
        return state

    def process(self, state, raw):
        capture_id = state["capture_id"]
        with self._active_lock:
            self._active.add(capture_id)
        try:
            self._process(state, raw)
        finally:
            with self._active_lock:
                self._active.discard(capture_id)

    def _process(self, state, raw):
        source_type = state["source_type"]
        input_type = state["input_type"]
        try:
            if source_type == "url":
                original_url = state.get("source_url") or raw.decode("utf-8").strip()
                final_url, body, content_type = _fetch_url(original_url)
                if "text/html" in content_type:
                    parser = _TextExtractor()
                    parser.feed(body)
                    title = " ".join(" ".join(parser.title).split()) or final_url
                    extracted = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
                else:
                    title, extracted = final_url, body
                if not extracted.strip():
                    raise ValueError("No readable page text was extracted")
                state["title"] = title[:300]
                content = extracted[:500_000]
                state["derived_source_url"] = final_url
            elif input_type == "pdf":
                reader = PdfReader(__import__("io").BytesIO(raw), strict=True)
                if reader.is_encrypted:
                    raise ValueError("Encrypted PDFs are not supported")
                if len(reader.pages) > 500:
                    raise ValueError("PDF exceeds the 500 page limit")
                content = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
                if not content:
                    page_sizes = [(page.mediabox.width, page.mediabox.height) for page in reader.pages]
                    content = self.processors.ocr_pdf(raw, len(reader.pages), page_sizes)
                    state["processor"] = {"name": "tesseract", "kind": "pdf_ocr",
                                          "pages": len(reader.pages), "languages": "chi_sim+eng"}
                if reader.metadata and reader.metadata.title:
                    document_title = str(reader.metadata.title).strip()
                    if document_title:
                        state["document_title"] = document_title[:300]
                if len(content) > 1_000_000:
                    content = content[:1_000_000]
            elif input_type in {"png", "jpg", "jpeg", "webp", "gif"}:
                recognized = self.processors.ocr_image(raw)
                state["processor"] = {"name": "tesseract", "kind": "image_ocr",
                                      "languages": "chi_sim+eng"}
                content = ("## OCR 识别文字\n\n" + recognized +
                           "\n\n## AI 画面描述\n\nAI 图像理解尚未配置；以上仅为原图 OCR 结果。")
                state["partial_error"] = {
                    "code": "processor_unavailable",
                    "message": "OCR succeeded; AI scene description is not configured.",
                }
            elif input_type in {"wav", "mp3", "m4a", "aac", "ogg", "flac"}:
                transcript, provider = self.processors.transcribe_audio(raw, input_type)
                state["processor"] = {"name": "hermes_stt", "provider": provider}
                content = "## 转写文本\n\n" + transcript
            else:
                decoded = raw.decode("utf-8-sig", errors="strict")
                if not decoded.strip():
                    raise ValueError("Text file is empty")
                if source_type == "inbox_proposal_review":
                    state["title"] = state.get("approved_title", state["title"])
                    content = decoded
                else:
                    content = decoded.strip()
                if source_type != "inbox_proposal_review" and input_type in {"txt", "text"}:
                    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
                    if first_line:
                        state["title"] = first_line[:120]
            self._write_review(state, content)
            self._verify_artifacts(state)
            if state.get("partial_error"):
                state.update(status="partial_success", error=state.pop("partial_error"), updated_at=_now())
            else:
                state.update(status="completed", error=None, updated_at=_now())
        except ProcessorUnavailable as exc:
            state.pop("partial_error", None)
            state.update(status="partial_success", error={"code": "processor_unavailable", "message": str(exc)}, updated_at=_now())
        except Exception as exc:
            state.pop("partial_error", None)
            state.update(status="partial_success", error={"code": "processing_failed", "message": str(exc)[:500]}, updated_at=_now())
        self._write_state(state)

    def _verify_artifacts(self, state):
        raw_path = self.raw_root / state["raw_path"]
        raw_info = raw_path.lstat()
        if not stat.S_ISREG(raw_info.st_mode) or stat.S_ISLNK(raw_info.st_mode):
            raise ValueError("Raw artifact verification failed")
        raw_digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if raw_digest != state.get("raw_sha256"):
            raise ValueError("Raw artifact hash verification failed")
        review_path = self.review_root / state["review_path"]
        review_info = review_path.lstat()
        if not stat.S_ISREG(review_info.st_mode) or stat.S_ISLNK(review_info.st_mode):
            raise ValueError("Review artifact verification failed")
        review_digest = hashlib.sha256(review_path.read_bytes()).hexdigest()
        if review_digest != state.get("review_sha256"):
            raise ValueError("Review artifact hash verification failed")

    def _write_review(self, state, content):
        review_name = _safe_name(state["title"], ".md")
        body = _frontmatter(state["source_type"], state["captured_at"], state["original_asset"], state.get("capture_context", ""))
        if state["source_type"] == "url":
            original_url = state.get("source_url", "")
            final_url = state.get("derived_source_url", original_url)
            body += f"\n# {state['title']}\n\nSource URL: {original_url}\nFetched URL: {final_url}\n\n"
        else:
            body += f"\n# {state['title']}\n\n"
        processor = state.get("processor")
        if isinstance(processor, dict):
            if processor.get("kind") == "pdf_ocr":
                body += (f"OCR: {processor.get('name', 'OCR')}; "
                         f"languages: {processor.get('languages', 'unknown')}; "
                         f"pages: {processor.get('pages', 'unknown')}\n\n")
            elif processor.get("kind") == "image_ocr":
                body += f"OCR: {processor.get('name', 'OCR')}; languages: {processor.get('languages', 'unknown')}\n\n"
            elif processor.get("name") == "hermes_stt":
                body += f"Transcription provider: {processor.get('provider', 'Hermes STT')}\n\n"
        if state.get("source_type") == "inbox_proposal_review":
            # C2c stores precisely the text shown in the execution preview.
            body += content
        else:
            body += content.strip() + "\n"
        hinted_name = state.get("review_path_hint")
        if isinstance(hinted_name, str):
            if Path(hinted_name).name != hinted_name or hinted_name in {".", ".."}:
                raise ValueError("Review target path is invalid")
            path = self.review_root / hinted_name
            encoded = body.encode("utf-8")
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                try:
                    existing_fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    with os.fdopen(existing_fd, "rb") as existing:
                        info = os.fstat(existing.fileno())
                        if not stat.S_ISREG(info.st_mode) or existing.read() != encoded:
                            raise ValueError("Existing idempotent Review item does not match")
                except OSError as exc:
                    raise ValueError("Existing idempotent Review item is unsafe") from exc
            else:
                with os.fdopen(fd, "wb") as output:
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
            self._fsync_directory(self.review_root)
            state["review_path"] = hinted_name
            state["review_sha256"] = hashlib.sha256(encoded).hexdigest()
            return
        # A retry may reproduce the same partial image Review (OCR succeeded
        # while vision remains unavailable). Reuse only the exact already
        # verified, service-linked artifact; never overwrite it. Changed output
        # still receives a new collision-safe filename and preserves history.
        existing_name = state.get("review_path")
        existing_digest = state.get("review_sha256")
        if (isinstance(existing_name, str) and Path(existing_name).name == existing_name
                and existing_name not in {".", ".."} and isinstance(existing_digest, str)):
            existing = self.review_root / existing_name
            try:
                info = existing.lstat()
                if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    old_body = existing.read_bytes()
                    if (hashlib.sha256(old_body).hexdigest() == existing_digest
                            and old_body == body.encode("utf-8")):
                        return
            except OSError:
                pass
        for attempt in range(1000):
            name = review_name if attempt == 0 else f"{Path(review_name).stem}-{attempt}.md"
            path = self.review_root / name
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            state["review_path"] = name
            state["review_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
            state["title"] = state["title"][:300]
            return
        raise ValueError("Unable to allocate a collision-safe Review filename")


class ProcessorUnavailable(Exception):
    pass


def create_capture_router(auth, service):
    router = APIRouter(prefix="/api")

    @router.post("/capture/text", status_code=202)
    async def capture_text(request: Request, background_tasks: BackgroundTasks, body: dict):
        auth.require_action(request, "capture.write")
        source = body.get("source_type", "text")
        if source not in {"text", "markdown", "capture_context"}:
            raise HTTPException(400, "Unsupported text source type")
        item = service.accept_text(body.get("text"), source, body.get("capture_context", ""))
        service.mark_scheduled(item)
        background_tasks.add_task(service.process, item, service.raw_root.joinpath(item["raw_path"]).read_bytes())
        return item

    @router.post("/capture/url", status_code=202)
    async def capture_url(request: Request, background_tasks: BackgroundTasks, body: dict):
        auth.require_action(request, "capture.write")
        item = service.accept_url(body.get("url"), body.get("capture_context", ""))
        service.mark_scheduled(item)
        background_tasks.add_task(service.process, item, service.raw_root.joinpath(item["raw_path"]).read_bytes())
        return item

    @router.post("/capture/files", status_code=202)
    async def capture_file(request: Request, background_tasks: BackgroundTasks, file: UploadFile, capture_context: str = ""):
        auth.require_action(request, "capture.write")
        if file.size is not None and file.size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Files must be 20 MiB or smaller")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Files must be 20 MiB or smaller")
        try:
            item = service.accept_file(file.filename or "upload", data, None, capture_context)
            service.mark_scheduled(item)
            background_tasks.add_task(service.process, item, data)
            return item
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/inbox")
    def inbox(request: Request, limit: int = 100):
        auth.require_action(request, "inbox.read")
        if limit < 1 or limit > 200:
            raise HTTPException(400, "Limit must be 1-200")
        return {"items": service.list(limit), "status": "real"}

    @router.get("/inbox/summary")
    def inbox_summary(request: Request, limit: int = 100):
        auth.require_action(request, "inbox.read")
        if limit < 1 or limit > 200:
            raise HTTPException(400, "Limit must be 1-200")
        return {"items": service.list_summary(limit), "status": "real"}

    @router.get("/capture/{capture_id}")
    def capture_status(request: Request, capture_id: str):
        auth.require_action(request, "capture.read")
        return service.get(capture_id)

    @router.post("/capture/{capture_id}/retry")
    def retry_capture(request: Request, capture_id: str):
        auth.require_action(request, "capture.write")
        result = service.retry(capture_id)
        return result

    @router.get("/inbox/{capture_id}/raw")
    def raw_file(request: Request, capture_id: str):
        from fastapi.responses import FileResponse
        auth.require_action(request, "inbox.read")
        item = service.get(capture_id)
        raw_name = item.get("raw_path")
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in {".", ".."}:
            raise HTTPException(404, "Raw asset not found")
        path = service.raw_root / raw_name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise HTTPException(404, "Raw asset not found")
        return FileResponse(path, filename=Path(item["raw_path"]).name, media_type="application/octet-stream")

    @router.get("/inbox/{capture_id}/preview")
    def preview_file(request: Request, capture_id: str):
        from fastapi.responses import FileResponse
        auth.require_action(request, "inbox.read")
        item = service.get(capture_id)
        raw_name = item.get("raw_path")
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in {".", ".."}:
            raise HTTPException(404, "Raw asset not found")
        suffix = Path(raw_name).suffix.lower()
        media_type = PREVIEW_MEDIA_TYPES.get(suffix)
        if not media_type:
            raise HTTPException(415, "This Raw asset type is not supported for in-app preview")
        path = service.raw_root / raw_name
        try:
            info = path.lstat()
        except OSError as exc:
            raise HTTPException(404, "Raw asset not found") from exc
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise HTTPException(404, "Raw asset not found")
        return FileResponse(path, media_type=media_type, content_disposition_type="inline",
                            headers={"Content-Disposition": "inline",
                                     "X-Content-Type-Options": "nosniff"})

    return router


def create_inbox_entry_router(auth, service, proposals=None, proposal_sources=None, vocabulary_store=None):
    """Channel-neutral Core intake; only server-authenticated adapters may create events."""
    router = APIRouter(prefix="/api/inbox/entries")

    @router.post("", status_code=202)
    async def create_entry(request: Request, response: Response,
                           background_tasks: BackgroundTasks, body: dict):
        subject = auth.require_action(request, "capture.write")
        allowed = {"original_text", "source_channel", "source_event_id", "occurred_at",
                   "intent", "attachment_refs", "approved_proposal_id", "approved_proposal_version"}
        if not isinstance(body, dict) or set(body) - allowed:
            raise HTTPException(400, "Client-supplied identity or consent evidence is not accepted")
        attachments = body.get("attachment_refs", [])
        identity = authenticated_web_identity(subject, body.get("source_channel"))
        approved_proposal = None
        precommit_validator = None
        text = body.get("original_text")
        if body.get("intent") == "approved_suggestion":
            proposal_id = body.get("approved_proposal_id")
            proposal_version = body.get("approved_proposal_version")
            if (proposals is None or proposal_sources is None or
                    not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{32}", proposal_id) or
                    not isinstance(proposal_version, int) or isinstance(proposal_version, bool)):
                raise HTTPException(409, "Approved suggestion must identify an existing Core approval")

            def current_approval_binding():
                proposal = proposals.get(proposal_id)
                if (proposal.get("status") != "approved_recorded" or
                        proposal.get("version") != proposal_version or
                        proposal.get("kind") not in {"journal", "review", "project"}):
                    raise HTTPException(409, "Approved suggestion is missing, stale, or not approved")
                if (vocabulary_store is not None and
                        proposal.get("vocabulary_version") != vocabulary_store.read().get("revision")):
                    raise HTTPException(409, "Approved suggestion vocabulary changed after approval")
                try:
                    _, source_version, approved_text, _, _ = proposal_sources.execution_content(proposal)
                except HTTPException as exc:
                    raise HTTPException(409, "Approved suggestion source is unavailable or changed") from exc
                if source_version != proposal.get("source_version"):
                    raise HTTPException(409, "Approved suggestion source changed after approval")
                if not isinstance(text, str) or text != approved_text:
                    raise HTTPException(409, "Approved suggestion content must match its approved source")
                return {"proposal_id": proposal_id, "version": proposal_version,
                        "kind": proposal["kind"], "source_version": source_version}

            approved_proposal = current_approval_binding()

            def revalidate_before_persist():
                if current_approval_binding() != approved_proposal:
                    raise HTTPException(409, "Approved suggestion changed before Inbox persistence")

            precommit_validator = revalidate_before_persist
        elif "approved_proposal_id" in body or "approved_proposal_version" in body:
            raise HTTPException(400, "Proposal approval binding is only valid for approved_suggestion")
        state, replayed = service.accept_channel_text(
            text=text, identity=identity,
            source_event_id=body.get("source_event_id"), intent=body.get("intent"),
            occurred_at=body.get("occurred_at"), approved_proposal=approved_proposal,
            attachment_refs=attachments, precommit_validator=precommit_validator,
        )
        if state.get("status") == "processing" and service.mark_scheduled(state):
            raw_path = service.raw_root / state["raw_path"]
            try:
                raw = raw_path.read_bytes()
            except OSError as exc:
                raise HTTPException(503, "Inbox capture recovery requires review") from exc
            background_tasks.add_task(service.process, state, raw)
        response.headers["Cache-Control"] = "private, no-store"
        result = {"inbox_id": state["capture_id"], "status": state["status"],
                  "captured_at": state["captured_at"],
                  "source": {"channel": state["source_channel"], "event_id": state["source_event_id"]},
                  "intent": state["intent"], "consent_evidence": state["consent_evidence"],
                  "attachment_refs": state.get("attachment_refs", []),
                  "approved_proposal": state.get("approved_proposal"),
                  "replayed": replayed}
        error = state.get("error")
        if isinstance(error, dict) and error.get("code") in SUMMARY_ERROR_CODES:
            result["error_code"] = error["code"]
        return result

    @router.get("/{inbox_id}")
    def get_entry(request: Request, inbox_id: str, response: Response):
        auth.require_action(request, "inbox.read")
        if not re.fullmatch(r"[0-9a-f]{32}", inbox_id):
            raise HTTPException(404, "Inbox entry not found")
        state = service.get(inbox_id)
        if state.get("source_channel") is None:
            raise HTTPException(404, "Inbox entry not found")
        response.headers["Cache-Control"] = "private, no-store"
        result = {"inbox_id": inbox_id, "status": state.get("status", "unknown"),
                  "captured_at": state.get("captured_at"), "occurred_at": state.get("occurred_at"),
                  "source": {"channel": state.get("source_channel"), "event_id": state.get("source_event_id")},
                  "intent": state.get("intent"), "consent_evidence": state.get("consent_evidence"),
                  "attachment_refs": state.get("attachment_refs", []),
                  "approved_proposal": state.get("approved_proposal"),
                  "source_ref": {"capture_id": inbox_id,
                                 "review_path": state.get("review_path"),
                                 "review_sha256": state.get("review_sha256")}}
        error = state.get("error")
        if isinstance(error, dict) and error.get("code") in SUMMARY_ERROR_CODES:
            result["error_code"] = error["code"]
        return result

    return router
