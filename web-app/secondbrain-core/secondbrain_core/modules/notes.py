"""Narrow Core-owned Notes API for explicitly configured Markdown roots."""
import hashlib
import fcntl
import json
import os
import re
import stat
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from PIL import Image, UnidentifiedImageError

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.md$", re.I)
_IMAGE_TYPES = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".gif": b"GIF8", ".webp": b"RIFF"}
MAX_MARKDOWN_BYTES = 1_000_000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VISUAL_BYTES = 10 * 1024 * 1024
_VISUAL_FILENAME = re.compile(r"^[0-9a-f]{32}\.(?:mindmap|excalidraw)\.json$")
_VISUAL_KINDS = {"mindmap", "excalidraw"}


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
    def _read_at(directory_fd, filename):
        try:
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Note not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_MARKDOWN_BYTES):
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
    def _open_directory(path, missing_status=403):
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError as exc:
            if missing_status == 404:
                raise HTTPException(status_code=404, detail="Note not found") from exc
            raise HTTPException(status_code=403, detail="Directory could not be opened safely") from exc
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Directory could not be opened safely") from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            os.close(fd)
            raise HTTPException(status_code=403, detail="Directory permissions are unsafe")
        return fd

    @classmethod
    def _read(cls, path):
        if path.is_symlink():
            raise HTTPException(status_code=403, detail="Symlink files are not allowed")
        directory_fd = cls._open_directory(path.parent)
        try:
            return cls._read_at(directory_fd, path.name)
        finally:
            os.close(directory_fd)

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
    def _atomic_write(path, data, exclusive=False, directory_fd=None):
        owned_fd = directory_fd is None
        if owned_fd:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.parent.is_symlink():
                raise HTTPException(status_code=403, detail="Symlink paths are not allowed")
            directory_fd = NotesStore._open_directory(path.parent)
        temp_name = f".notes-{uuid.uuid4().hex}.tmp"
        fd = None
        try:
            fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                         0o600, dir_fd=directory_fd)
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive:
                try:
                    os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
                    raise HTTPException(status_code=409, detail="Note already exists")
                except FileNotFoundError:
                    pass
            os.replace(temp_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.chmod(path.name, 0o600, dir_fd=directory_fd, follow_symlinks=False)
            os.fsync(directory_fd)
        except Exception:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            if fd is not None:
                os.close(fd)
            if owned_fd:
                os.close(directory_fd)

    def update(self, collection, relative, content, expected):
        if collection not in self.roots:
            raise HTTPException(status_code=404, detail="Notes collection not found")
        self._validate(content)
        if markdown_safety(content):
            raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and cannot be saved through the rich-text editor")
        path, directory = self._path(collection, relative, create=collection == "drafts")
        directory_fd = self._open_directory(directory)
        try:
            lock_fd = os.open(directory / ".notes.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as exc:
            os.close(directory_fd)
            raise HTTPException(status_code=403, detail="Note lock could not be opened safely") from exc
        history_fd = None
        try:
            lock_info = os.fstat(lock_fd)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                    or lock_info.st_mode & 0o077):
                raise HTTPException(status_code=403, detail="Note lock permissions are unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read_at(directory_fd, path.name)
            current_etag = self._digest(current)
            if not expected or expected.strip('"') != current_etag:
                raise HTTPException(status_code=412, detail="Note changed; reload before saving")
            if markdown_safety(current):
                raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and is read-only")
            try:
                os.mkdir(".history", mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            history_fd = os.open(".history", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                 | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            history_info = os.fstat(history_fd)
            if not stat.S_ISDIR(history_info.st_mode) or history_info.st_uid != os.geteuid() or history_info.st_mode & 0o077:
                raise HTTPException(status_code=403, detail="History directory permissions are unsafe")
            previous_name = f"{current_etag}.md"
            try:
                previous = self._read_at(history_fd, previous_name)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                self._atomic_write(directory / ".history" / previous_name, current.encode("utf-8"),
                                   exclusive=True, directory_fd=history_fd)
            else:
                if previous != current:
                    raise HTTPException(status_code=409, detail="History entry is not safe to replace")
            self._atomic_write(path, content.encode("utf-8"), directory_fd=directory_fd)
        finally:
            if history_fd is not None:
                os.close(history_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
                os.close(directory_fd)
        return {"collection": collection, "path": relative, "content": content, "etag": self._digest(content),
                "read_only": False, "safety_reasons": []}

    def history(self, collection, relative):
        _, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        try:
            # A missing history directory means a valid note has no revisions;
            # a missing note itself is a 404 and must not look like an empty list.
            self._read_at(directory_fd, "note.md")
            try:
                history_fd = os.open(".history", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                     | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                return {"versions": []}
            except OSError as exc:
                raise HTTPException(status_code=403, detail="History directory could not be opened safely") from exc
            try:
                info = os.fstat(history_fd)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise HTTPException(status_code=403, detail="History directory permissions are unsafe")
                names = [name for name in os.listdir(history_fd) if re.fullmatch(r"[0-9a-f]{64}\.md", name)]
                candidates = sorted(names, key=lambda name: os.stat(name, dir_fd=history_fd, follow_symlinks=False).st_mtime_ns)[-20:]
                versions = []
                for name in candidates:
                    content = self._read_at(history_fd, name)
                    if self._digest(content) != name[:-3]:
                        raise HTTPException(status_code=409, detail="History entry hash does not match its content")
                    versions.append({"etag": name[:-3], "content": content})
                return {"versions": versions}
            finally:
                os.close(history_fd)
        finally:
            os.close(directory_fd)

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
        directory_fd = self._open_directory(directory)
        try:
            try:
                os.mkdir("attachments", mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            try:
                attachments_fd = os.open("attachments", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                         | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except OSError as exc:
                raise HTTPException(status_code=403, detail="Attachment path cannot be opened safely") from exc
            try:
                attachment_info = os.fstat(attachments_fd)
                if (not stat.S_ISDIR(attachment_info.st_mode) or attachment_info.st_uid != os.geteuid()
                        or attachment_info.st_mode & 0o077):
                    raise HTTPException(status_code=403, detail="Attachment directory permissions are unsafe")
                name = f"{uuid.uuid4().hex}{suffix}"
                self._atomic_write(directory / "attachments" / name, data, exclusive=True,
                                   directory_fd=attachments_fd)
            finally:
                os.close(attachments_fd)
        finally:
            os.close(directory_fd)
        return {"path": f"attachments/{name}", "url": f"/api/notes/{collection}/{relative}/attachments/{name}"}

    def read_attachment(self, collection, relative, filename):
        _, directory = self._path(collection, relative)
        is_visual = bool(_VISUAL_FILENAME.fullmatch(filename))
        if not is_visual and not re.fullmatch(r"[0-9a-f]{32}\.(?:png|jpg|gif|webp)", filename):
            raise HTTPException(status_code=400, detail="Invalid attachment name")
        max_bytes = MAX_VISUAL_BYTES if is_visual else MAX_IMAGE_BYTES
        directory_fd = self._open_directory(directory)
        try:
            try:
                folder_fd = os.open("attachments", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                    | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Attachment directory not found")
            except OSError as exc:
                raise HTTPException(status_code=403, detail="Symlink attachments are not allowed") from exc
            try:
                folder_info = os.fstat(folder_fd)
                if (not stat.S_ISDIR(folder_info.st_mode) or folder_info.st_uid != os.geteuid()
                        or folder_info.st_mode & 0o077):
                    raise HTTPException(status_code=403, detail="Attachment directory permissions are unsafe")
                try:
                    fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=folder_fd)
                except FileNotFoundError:
                    raise HTTPException(status_code=404, detail="Attachment not found")
                except OSError as exc:
                    raise HTTPException(status_code=403, detail="Attachment could not be opened safely") from exc
                try:
                    info = os.fstat(fd)
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                            or info.st_mode & 0o077 or info.st_size > max_bytes):
                        raise HTTPException(status_code=403, detail="Attachment permissions or size are unsafe")
                    with os.fdopen(fd, "rb", closefd=False) as stream:
                        data = stream.read(max_bytes + 1)
                        if is_visual:
                            self._validate_visual_payload(filename.split(".")[1], data.decode("utf-8"))
                        return data, Path(filename).suffix.lower()
                except UnicodeDecodeError as exc:
                    raise HTTPException(status_code=415, detail="Visual asset is not UTF-8 JSON") from exc
                finally:
                    os.close(fd)
            finally:
                os.close(folder_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _validate_visual_payload(kind, content):
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_VISUAL_BYTES:
            raise HTTPException(status_code=413, detail="Visual asset is too large")
        try:
            payload = json.loads(content)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Visual asset must contain valid JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Visual asset must be a JSON object")
        if kind == "mindmap":
            pending = [payload]
            count = 0
            while pending:
                node = pending.pop()
                count += 1
                if count > 5000 or not isinstance(node, dict) or not isinstance(node.get("data"), dict):
                    raise HTTPException(status_code=422, detail="Mind map structure is invalid or too large")
                data = node["data"]
                if (not isinstance(data.get("text", ""), str) or len(data.get("text", "")) > 20000
                        or data.get("richText") is True or data.get("image") or data.get("hyperlink")):
                    raise HTTPException(status_code=422, detail="Mind map node content is not supported safely")
                children = node.get("children", [])
                if not isinstance(children, list):
                    raise HTTPException(status_code=422, detail="Mind map children must be an array")
                pending.extend(children)

        elif kind == "excalidraw":
            allowed = {"rectangle", "ellipse", "diamond", "line", "arrow", "text", "freedraw"}
            elements = payload.get("elements")
            if payload.get("type") != "excalidraw" or not isinstance(elements, list) or len(elements) > 5000:
                raise HTTPException(status_code=422, detail="Excalidraw scene structure is invalid")
            if any(not isinstance(item, dict) or item.get("type") not in allowed for item in elements):
                raise HTTPException(status_code=422, detail="This Excalidraw element type is not supported")
            if any(isinstance(item.get("text"), str) and len(item["text"]) > 20000 for item in elements):
                raise HTTPException(status_code=422, detail="Excalidraw text is too long")
        else:
            raise HTTPException(status_code=400, detail="Visual asset kind is not supported")
        return payload

    def create_visual_asset(self, collection, relative, kind, content, expected):
        if kind not in _VISUAL_KINDS:
            raise HTTPException(status_code=400, detail="Visual asset kind is not supported")
        self._validate_visual_payload(kind, content)
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory)
        lock_fd = None
        attachments_fd = None
        try:
            lock_fd = os.open(".notes.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                              0o600, dir_fd=directory_fd)
            lock_info = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid() or lock_info.st_mode & 0o077:
                raise HTTPException(status_code=403, detail="Note lock permissions are unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read_at(directory_fd, path.name)
            if not expected or expected.strip('"') != self._digest(current):
                raise HTTPException(status_code=412, detail="Note changed; reload before saving visual assets")
            if markdown_safety(current):
                raise HTTPException(status_code=422, detail="This Markdown note is read-only")
            try:
                os.mkdir("attachments", mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            attachments_fd = os.open("attachments", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                     | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            info = os.fstat(attachments_fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=403, detail="Attachment directory permissions are unsafe")
            filename = f"{uuid.uuid4().hex}.{kind}.json"
            raw = content.encode("utf-8")
            self._atomic_write(directory / "attachments" / filename, raw, exclusive=True,
                               directory_fd=attachments_fd)
            etag = hashlib.sha256(raw).hexdigest()
            return {"path": f"attachments/{filename}", "filename": filename, "etag": etag}
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Visual asset path could not be opened safely") from exc
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def update_visual_asset(self, collection, relative, filename, content, expected_note, expected_asset):
        if not _VISUAL_FILENAME.fullmatch(filename):
            raise HTTPException(status_code=400, detail="Invalid visual asset name")
        kind = filename.split(".")[1]
        self._validate_visual_payload(kind, content)
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory)
        lock_fd = None
        attachments_fd = None
        try:
            lock_fd = os.open(".notes.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                              0o600, dir_fd=directory_fd)
            lock_info = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid() or lock_info.st_mode & 0o077:
                raise HTTPException(status_code=403, detail="Note lock permissions are unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read_at(directory_fd, path.name)
            if not expected_note or expected_note.strip('"') != self._digest(current):
                raise HTTPException(status_code=412, detail="Note changed; reload before saving visual assets")
            if markdown_safety(current):
                raise HTTPException(status_code=422, detail="This Markdown note is read-only")
            attachments_fd = os.open("attachments", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                     | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            info = os.fstat(attachments_fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise HTTPException(status_code=403, detail="Attachment directory permissions are unsafe")
            old = self._read_attachment_at(attachments_fd, filename, MAX_VISUAL_BYTES)
            if not expected_asset or expected_asset.strip('"') != hashlib.sha256(old).hexdigest():
                raise HTTPException(status_code=412, detail="Visual asset changed; reload before saving")
            raw = content.encode("utf-8")
            self._atomic_write(directory / "attachments" / filename, raw, directory_fd=attachments_fd)
            return {"etag": hashlib.sha256(raw).hexdigest()}
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Visual asset path could not be opened safely") from exc
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    @staticmethod
    def _read_attachment_at(directory_fd, filename, max_bytes):
        try:
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Attachment not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Attachment could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > max_bytes:
                raise HTTPException(status_code=403, detail="Attachment permissions or size are unsafe")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return stream.read(max_bytes + 1)
        finally:
            os.close(fd)


def configured_notes_store(drafts_root, authorized_roots_json=""):
    if not drafts_root or not Path(drafts_root).is_absolute():
        return None
    try:
        roots = json.loads(authorized_roots_json or "{}")
        if not isinstance(roots, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in roots.items()):
            raise ValueError
        # Missing Knowledge config is not evidence that an ordinary Notes root
        # is separate from formal Knowledge. Keep Drafts available, fail closed
        # for extra roots until Core can positively check the protected tree.
        if roots and not os.environ.get("SB_KNOWLEDGE_ROOT", "").strip():
            raise ValueError("SB_KNOWLEDGE_ROOT is required for ordinary Notes roots")
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

    @router.post("/{collection}/{relative:path}/visual-assets/{kind}")
    def create_visual_asset(request: Request, response: Response, collection: str, relative: str,
                            kind: str, body: dict):
        require(request, "write")
        result = store.create_visual_asset(collection, relative, kind, body.get("content"),
                                           request.headers.get("if-match", ""))
        response.headers["ETag"] = f'"{result["etag"]}"'
        return result

    @router.put("/{collection}/{relative:path}/attachments/{filename}")
    def update_visual_asset(request: Request, response: Response, collection: str, relative: str,
                            filename: str, body: dict):
        require(request, "write")
        result = store.update_visual_asset(collection, relative, filename, body.get("content"),
                                           request.headers.get("if-match", ""),
                                           request.headers.get("if-asset-match", ""))
        response.headers["ETag"] = f'"{result["etag"]}"'
        return result

    @router.get("/{collection}/{relative:path}/attachments/{filename}")
    def read_attachment(request: Request, collection: str, relative: str, filename: str):
        require(request, "read")
        data, suffix = store.read_attachment(collection, relative, filename)
        media_type = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif",
                      ".webp": "image/webp", ".json": "application/json"}[suffix]
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        if suffix == ".json":
            headers["ETag"] = f'"{hashlib.sha256(data).hexdigest()}"'
        return Response(content=data, media_type=media_type,
                         headers=headers)

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
