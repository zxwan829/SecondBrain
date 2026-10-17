"""Narrow Core-owned Notes API for explicitly configured Markdown roots."""
import hashlib
import fcntl
import json
import os
import re
import stat
import tempfile
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from PIL import Image, UnidentifiedImageError

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.md$", re.I)
_IMAGE_TYPES = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".gif": b"GIF8", ".webp": b"RIFF"}
MAX_MARKDOWN_BYTES = 1_000_000
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def markdown_safety(content: str) -> list[str]:
    """Return constructs that the basic editor cannot safely round-trip."""
    reasons = []
    if content.lstrip("\ufeff").startswith("---\n") or content.lstrip("\ufeff").startswith("---\r\n"):
        reasons.append("frontmatter")
    checks = {
        "wiki links": r"!?\[\[[^\]]+\]\]", "callouts": r"^\s*>\s*\[![-\w]+\]",
        "block IDs": r"\^[-\w]+\s*$", "reference links": r"^\s*\[[^\]]+\]:",
        "footnotes": r"\[\^[^\]]+\]", "HTML blocks": r"<\s*/?\s*[A-Za-z][^>]*>",
        "Obsidian comments": r"%%.*?%%",
    }
    for label, pattern in checks.items():
        if re.search(pattern, content, re.M | re.S if label == "Obsidian comments" else re.M):
            reasons.append(label)
    return reasons


class NotesStore:
    """Files remain authoritative; configured roots are the entire write allowlist."""
    def __init__(self, drafts_root, authorized_roots=None):
        roots = {"drafts": drafts_root, **(authorized_roots or {})}
        self.roots = {}
        for name, raw in roots.items():
            if (not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name) or name in
                    {"knowledge", "private", "raw", "review", "journal"} or not raw):
                raise ValueError("Invalid Notes root configuration")
            root = Path(raw)
            if not root.is_absolute() or root.is_symlink() or root.resolve(strict=False) != root.absolute():
                raise ValueError("Notes roots must be absolute non-symlink paths")
            self.roots[name] = root
        resolved = list(self.roots.items())
        for index, (left_name, left) in enumerate(resolved):
            for right_name, right in resolved[index + 1:]:
                if left == right or left in right.parents or right in left.parents:
                    raise ValueError("Notes roots must not overlap")

    def _root(self, collection):
        root = self.roots.get(collection)
        if root is None:
            raise HTTPException(status_code=404, detail="Notes collection not found")
        if root.is_symlink():
            raise HTTPException(status_code=403, detail="Notes root cannot be a symlink")
        if not root.exists() and collection != "drafts":
            raise HTTPException(status_code=503, detail="Authorized Notes root is unavailable")
        if root.exists():
            info = root.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or not os.access(root, os.R_OK | os.W_OK)):
                raise HTTPException(status_code=403, detail="Notes root must be a private writable directory owned by Core")
        return root

    @staticmethod
    def _relative(value):
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise HTTPException(status_code=400, detail="Invalid note path")
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or any(part in {".", ".."} for part in parsed.parts) or not _SAFE_NAME.fullmatch(parsed.name):
            raise HTTPException(status_code=400, detail="Invalid note path")
        return parsed

    def _path(self, collection, relative, create=False):
        root = self._root(collection)
        parts = [relative] if collection == "drafts" else list(self._relative(relative).parts)
        if collection == "drafts" and not re.fullmatch(r"[0-9a-f-]{36}", relative):
            raise HTTPException(status_code=400, detail="Invalid draft id")
        current = root
        for part in parts[:-1] if collection != "drafts" else parts:
            current = current / part
            if current.is_symlink():
                raise HTTPException(status_code=403, detail="Symlink paths are not allowed")
        if collection == "drafts":
            if create and not root.exists():
                root.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(root, 0o700, follow_symlinks=False)
            directory = root / parts[0]
            if directory.is_symlink():
                raise HTTPException(status_code=403, detail="Symlink paths are not allowed")
            if create:
                directory.mkdir(mode=0o700, parents=False, exist_ok=True)
            if directory.exists() and (not directory.is_dir() or directory.stat().st_mode & 0o077):
                raise HTTPException(status_code=403, detail="Draft directory permissions are unsafe")
            return directory / "note.md", directory
        path = root.joinpath(*parts)
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=True))
        except (ValueError, FileNotFoundError):
            raise HTTPException(status_code=403, detail="Path is outside the authorized root")
        if path.is_symlink():
            raise HTTPException(status_code=403, detail="Symlink files are not allowed")
        return path, path.parent

    @staticmethod
    def _read(path):
        if path.is_symlink():
            raise HTTPException(status_code=403, detail="Symlink files are not allowed")
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Note not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > MAX_MARKDOWN_BYTES:
                raise HTTPException(status_code=403, detail="Note file permissions or size are unsafe")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_MARKDOWN_BYTES + 1)
        finally:
            os.close(fd)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=415, detail="Note is not UTF-8 Markdown") from exc

    @staticmethod
    def _digest(content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def read(self, collection, relative):
        path, _ = self._path(collection, relative)
        content = self._read(path)
        return {"collection": collection, "path": relative, "content": content,
                "etag": self._digest(content), "read_only": bool(markdown_safety(content)),
                "safety_reasons": markdown_safety(content)}

    def list_notes(self, collection):
        root = self._root(collection)
        if collection == "drafts" and not root.exists():
            return {"collection": collection, "items": []}
        items = []
        candidates = []
        if collection == "drafts":
            if root.is_symlink():
                raise HTTPException(status_code=403, detail="Notes root cannot be a symlink")
            candidates = [(child.name, child / "note.md") for child in root.iterdir()
                          if child.is_dir() and not child.is_symlink() and re.fullmatch(r"[0-9a-f-]{36}", child.name)]
        else:
            if not root.is_dir() or root.is_symlink():
                raise HTTPException(status_code=503, detail="Authorized Notes root is unavailable")
            for current, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = [name for name in dirs if not name.startswith(".") and name != "attachments"
                           and not Path(current, name).is_symlink()]
                for filename in files:
                    candidate = Path(current, filename)
                    if candidate.suffix.lower() == ".md" and not candidate.is_symlink():
                        candidates.append((candidate.relative_to(root).as_posix(), candidate))
        for relative, path in candidates:
            if not path.is_file() or path.is_symlink():
                continue
            title = path.stem
            try:
                content = self._read(path)
                title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem)
            except HTTPException:
                continue
            items.append({"path": relative, "title": title})
        items.sort(key=lambda item: item["path"])
        return {"collection": collection, "items": items[:500]}

    def create(self, content):
        self._validate(content)
        if markdown_safety(content):
            raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and cannot be created through the rich-text editor")
        note_id = str(uuid.uuid4())
        path, directory = self._path("drafts", note_id, create=True)
        self._atomic_write(path, content.encode("utf-8"), exclusive=True)
        return {"collection": "drafts", "path": note_id, "content": content, "etag": self._digest(content),
                "read_only": False, "safety_reasons": []}

    @staticmethod
    def _validate(content):
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=422, detail="Markdown content is required")
        if len(content.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise HTTPException(status_code=413, detail="Markdown note is too large")

    @staticmethod
    def _atomic_write(path, data, exclusive=False):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise HTTPException(status_code=403, detail="Symlink paths are not allowed")
        fd, temp_name = tempfile.mkstemp(prefix=".notes-", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive and path.exists():
                raise HTTPException(status_code=409, detail="Note already exists")
            os.replace(temp_name, path)
            os.chmod(path, 0o600, follow_symlinks=False)
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def update(self, collection, relative, content, expected):
        if collection not in self.roots:
            raise HTTPException(status_code=404, detail="Notes collection not found")
        self._validate(content)
        if markdown_safety(content):
            raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and cannot be saved through the rich-text editor")
        path, directory = self._path(collection, relative, create=collection == "drafts")
        lock_path = directory / ".notes.lock"
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note lock could not be opened safely") from exc
        try:
            lock_info = os.fstat(lock_fd)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                    or lock_info.st_mode & 0o077):
                raise HTTPException(status_code=403, detail="Note lock permissions are unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read(path)
            current_etag = self._digest(current)
            if not expected or expected.strip('"') != current_etag:
                raise HTTPException(status_code=412, detail="Note changed; reload before saving")
            if markdown_safety(current):
                raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and is read-only")
            history = directory / ".history"
            history.mkdir(mode=0o700, exist_ok=True)
            if history.is_symlink():
                raise HTTPException(status_code=403, detail="History path cannot be a symlink")
            previous = history / f"{current_etag}.md"
            if not previous.exists():
                self._atomic_write(previous, current.encode("utf-8"), exclusive=True)
            elif previous.is_symlink() or self._read(previous) != current:
                raise HTTPException(status_code=409, detail="History entry is not safe to replace")
            self._atomic_write(path, content.encode("utf-8"))
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        return {"collection": collection, "path": relative, "content": content, "etag": self._digest(content),
                "read_only": False, "safety_reasons": []}

    def history(self, collection, relative):
        _, directory = self._path(collection, relative)
        history = directory / ".history"
        if history.is_symlink():
            raise HTTPException(status_code=403, detail="History path cannot be a symlink")
        if not history.exists():
            return {"versions": []}
        versions = []
        for item in sorted(history.glob("*.md"), key=lambda entry: entry.lstat().st_mtime_ns)[-20:]:
            if item.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}\.md", item.name):
                continue
            content = self._read(item)
            versions.append({"etag": item.stem, "content": content})
        return {"versions": versions}

    def upload_image(self, collection, relative, filename, data):
        _, directory = self._path(collection, relative)
        suffix = Path(filename or "").suffix.lower()
        signature = _IMAGE_TYPES.get(suffix)
        if not signature or len(data) > MAX_IMAGE_BYTES or not data.startswith(signature):
            raise HTTPException(status_code=415, detail="Image format or size is not supported")
        if suffix == ".webp" and data[8:12] != b"WEBP":
            raise HTTPException(status_code=415, detail="Image format is invalid")
        try:
            with Image.open(BytesIO(data)) as image:
                expected_format = {".jpg": "JPEG", ".png": "PNG", ".gif": "GIF", ".webp": "WEBP"}[suffix]
                if image.format != expected_format or image.width * image.height > 40_000_000:
                    raise HTTPException(status_code=415, detail="Image format or dimensions are not supported")
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(status_code=415, detail="Image data is invalid") from exc
        attachments = directory / "attachments"
        attachments.mkdir(mode=0o700, exist_ok=True)
        if attachments.is_symlink():
            raise HTTPException(status_code=403, detail="Attachment path cannot be a symlink")
        name = f"{uuid.uuid4().hex}{suffix}"
        self._atomic_write(attachments / name, data, exclusive=True)
        return {"path": f"attachments/{name}", "url": f"/api/notes/{collection}/{relative}/attachments/{name}"}

    def read_attachment(self, collection, relative, filename):
        _, directory = self._path(collection, relative)
        if not re.fullmatch(r"[0-9a-f]{32}\.(?:png|jpg|gif|webp)", filename):
            raise HTTPException(status_code=400, detail="Invalid attachment name")
        folder = directory / "attachments"
        path = folder / filename
        if folder.is_symlink() or path.is_symlink():
            raise HTTPException(status_code=403, detail="Symlink attachments are not allowed")
        try:
            path.resolve(strict=True).relative_to(directory.resolve(strict=True))
        except (ValueError, FileNotFoundError):
            raise HTTPException(status_code=403, detail="Attachment is outside the note directory")
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Attachment not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Attachment could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_IMAGE_BYTES):
                raise HTTPException(status_code=403, detail="Attachment permissions or size are unsafe")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return stream.read(MAX_IMAGE_BYTES + 1), Path(filename).suffix.lower()
        finally:
            os.close(fd)


def configured_notes_store(drafts_root, authorized_roots_json=""):
    if not drafts_root or not Path(drafts_root).is_absolute():
        return None
    try:
        roots = json.loads(authorized_roots_json or "{}")
        if not isinstance(roots, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in roots.items()):
            raise ValueError
        store = NotesStore(drafts_root, roots)
        protected = [os.environ.get(key, "").strip() for key in
                     ("SB_KNOWLEDGE_ROOT", "SB_REVIEW_ROOT", "SB_CAPTURE_RAW_ROOT", "SB_JOURNAL_ROOT", "SB_PRIVATE_ROOT")]
        for name, root in store.roots.items():
            for raw in protected:
                if not raw:
                    continue
                protected_path = Path(raw).resolve(strict=False)
                candidate = root.resolve(strict=False)
                if candidate == protected_path or candidate in protected_path.parents or protected_path in candidate.parents:
                    raise RuntimeError(f"Notes root '{name}' overlaps a protected storage domain")
        return store
    except (ValueError, TypeError, json.JSONDecodeError):
        raise RuntimeError("SB_NOTES_AUTHORIZED_ROOTS must be a JSON object of named explicit paths")


def create_notes_router(auth, store):
    router = APIRouter(prefix="/api/notes")

    def require(request, action):
        auth.require_action(request, f"notes.{action}")
        if store is None:
            raise HTTPException(status_code=503, detail="Notes is not configured")

    @router.post("")
    def create(request: Request, response: Response, body: dict):
        require(request, "create")
        result = store.create(body.get("content"))
        response.headers["ETag"] = f'"{result["etag"]}"'
        return result

    @router.get("")
    def collections(request: Request):
        require(request, "read")
        return {"collections": [{"id": name, "kind": "drafts" if name == "drafts" else "authorized"}
                                for name in store.roots]}

    @router.get("/{collection}")
    def listing(request: Request, collection: str):
        require(request, "read")
        if collection not in store.roots:
            raise HTTPException(status_code=404, detail="Notes collection not found")
        return store.list_notes(collection)

    @router.get("/{collection}/{relative:path}/history")
    def history(request: Request, collection: str, relative: str):
        require(request, "read")
        return store.history(collection, relative)

    @router.post("/{collection}/{relative:path}/attachments")
    async def attachment(request: Request, collection: str, relative: str, file: UploadFile = File(...)):
        require(request, "write")
        data = await file.read(MAX_IMAGE_BYTES + 1)
        return store.upload_image(collection, relative, file.filename, data)

    @router.get("/{collection}/{relative:path}/attachments/{filename}")
    def read_attachment(request: Request, collection: str, relative: str, filename: str):
        require(request, "read")
        data, suffix = store.read_attachment(collection, relative, filename)
        media_type = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}[suffix]
        return Response(content=data, media_type=media_type,
                         headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @router.get("/{collection}/{relative:path}")
    def read(request: Request, response: Response, collection: str, relative: str):
        require(request, "read")
        result = store.read(collection, relative)
        response.headers["ETag"] = f'"{result["etag"]}"'
        return result

    @router.put("/{collection}/{relative:path}")
    def update(request: Request, response: Response, collection: str, relative: str, body: dict):
        require(request, "write")
        result = store.update(collection, relative, body.get("content"), request.headers.get("if-match", ""))
        response.headers["ETag"] = f'"{result["etag"]}"'
        return result

    return router
