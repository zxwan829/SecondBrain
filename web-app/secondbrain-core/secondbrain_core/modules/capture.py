"""File-backed Universal Capture intake and deterministic processors.

Raw evidence is immutable. The capture status journal lives in Core's private
state directory; Review files reuse the canonical Markdown frontmatter fields.
"""
import hashlib
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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from pypdf import PdfReader


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_DISPLAY_FILENAME_CHARS = 255
MAX_WEB_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 4
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf", ".png", ".jpg", ".jpeg",
                    ".webp", ".gif", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
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
    def __init__(self, raw_root, review_root, state_root):
        self.raw_root = Path(raw_root)
        self.review_root = Path(review_root)
        self.state_root = Path(state_root) / "captures"
        self._active = set()
        self._active_lock = threading.Lock()
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
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ValueError
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def list(self, limit=100):
        result = []
        for path in self.state_root.glob("*.json"):
            item = self._read_state(path)
            if item:
                self._recover_interrupted(item)
            if item:
                result.append(item)
        return sorted((item for item in result if item), key=lambda item: item.get("captured_at", ""), reverse=True)[:limit]

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
            self._active.add(state["capture_id"])

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

    def _create_raw(self, filename, data):
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Unsupported file type")
        safe = _safe_name(filename, suffix)
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

    def accept_file(self, filename, data, source_type=None, context=""):
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
        capture_id = uuid.uuid4().hex
        raw_data = data
        source_url = None
        if source_type == "url":
            source_url = data.decode("utf-8").strip()
            raw_data = f"Original URL: {source_url}\nCaptured at: {captured_at}\n".encode("utf-8")
        try:
            raw_path = self._create_raw(filename, raw_data)
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
                 "capture_context": context[:2000]}
        if source_url is not None:
            state["source_url"] = source_url
        self._write_state(state)
        return state

    def accept_text(self, text, source_type="text", context=""):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise HTTPException(400, "Text must contain 1-200000 characters")
        filename = "capture.md" if source_type == "text" else "capture.txt"
        return self.accept_file(filename, text.encode("utf-8"), source_type, context)

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
                    raise ValueError("No extractable PDF text; OCR is not configured")
                if reader.metadata and reader.metadata.title:
                    document_title = str(reader.metadata.title).strip()
                    if document_title:
                        state["document_title"] = document_title[:300]
                if len(content) > 1_000_000:
                    content = content[:1_000_000]
            elif input_type in {"png", "jpg", "jpeg", "webp", "gif"}:
                raise ProcessorUnavailable("Image understanding is not configured in this App/Core deployment")
            elif input_type in {"wav", "mp3", "m4a", "aac", "ogg", "flac"}:
                raise ProcessorUnavailable("Audio transcription is not configured in this App/Core deployment")
            else:
                content = raw.decode("utf-8-sig", errors="strict").strip()
                if not content:
                    raise ValueError("Text file is empty")
                heading = next((line.lstrip("# ").strip() for line in content.splitlines() if line.startswith("# ") and line.lstrip("# ").strip()), "")
                if heading:
                    state["title"] = heading[:300]
                elif input_type in {"txt", "text"}:
                    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
                    if first_line:
                        state["title"] = first_line[:120]
            self._write_review(state, content)
            self._verify_artifacts(state)
            state.update(status="completed", error=None, updated_at=_now())
        except ProcessorUnavailable as exc:
            state.update(status="partial_success", error={"code": "processor_unavailable", "message": str(exc)}, updated_at=_now())
        except Exception as exc:
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
        body += content.strip() + "\n"
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
