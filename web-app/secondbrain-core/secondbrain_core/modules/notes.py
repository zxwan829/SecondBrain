"""Narrow Core-owned Notes API for explicitly configured Markdown roots."""
from __future__ import annotations
import csv
import base64
import binascii
import hashlib
import fcntl
import json
import os
import re
import stat
import unicodedata
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from PIL import Image, UnidentifiedImageError

_SAFE_NAME = re.compile(r"^[^\W_][\w. -]{0,119}\.md$", re.I | re.UNICODE)
_IMAGE_TYPES = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".gif": b"GIF8", ".webp": b"RIFF"}
MAX_MARKDOWN_BYTES = 1_000_000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VISUAL_BYTES = 10 * 1024 * 1024
_VISUAL_FILENAME = re.compile(r"^[0-9a-f]{32}\.(?:mindmap|excalidraw)\.json$")
_VISUAL_KINDS = {"mindmap", "excalidraw"}
_BLOCKSUITE_RESOURCE_ID = re.compile(r"^[0-9a-f]{32}$")
_BLOCKSUITE_DOC_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_BLOCKSUITE_RESOURCE_FILENAME = re.compile(r"^[0-9a-f]{32}\.blocksuite\.json$")
_BLOCKSUITE_RESOURCE_KINDS = {"database", "edgeless-canvas", "rich-page"}
MAX_BLOCKSUITE_RESOURCE_BYTES = 10 * 1024 * 1024
MAX_BLOCKSUITE_RESOURCES_PER_NOTE = 64
MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE = 64 * 1024 * 1024
MAX_BLOCKSUITE_UPDATE_BYTES = 7 * 1024 * 1024
MAX_BLOCKSUITE_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_BLOCKSUITE_SNAPSHOT_NODES = 50_000
MAX_BLOCKSUITE_SNAPSHOT_DEPTH = 64
MAX_BLOCKSUITE_REQUEST_BYTES = MAX_BLOCKSUITE_RESOURCE_BYTES + 64 * 1024
MAX_BLOCKSUITE_BLOB_BYTES = MAX_IMAGE_BYTES
_BLOCKSUITE_BLOB_FILENAME = re.compile(r"^[A-Za-z0-9_-]{43}=$")
_BLOCKSUITE_BLOB_DISK_FILENAME = re.compile(r"^[0-9a-f]{64}\.blocksuite-blob$")
_BLOCKSUITE_BLOB_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}
_BLOCKSUITE_RESOURCE_REFERENCE = re.compile(r"\]\(attachments/([0-9a-f]{32}\.blocksuite\.json)\)")


async def _read_bounded_json_request(request: Request, max_bytes: int):
    """Read a JSON request incrementally so schema limits also bound input memory."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=413, detail="BlockSuite resource request is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail="BlockSuite resource request is too large")
        raw.extend(chunk)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="BlockSuite resource request must be valid JSON") from exc


async def _read_bounded_body(request: Request, max_bytes: int):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=413, detail="BlockSuite blob is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail="BlockSuite blob is too large")
        raw.extend(chunk)
    return bytes(raw)


def _frontmatter_prefix(content: str):
    """Return an exact leading YAML frontmatter prefix, if present."""
    offset = 1 if content.startswith("\ufeff") else 0
    normalized = content[offset:]
    if not normalized.startswith(("---\n", "---\r\n")):
        return ""
    match = re.match(r"^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)", normalized)
    return content[:offset + match.end()] if match else None


def markdown_safety(content: str) -> list[str]:
    """Return body constructs that the rich-text editor cannot safely round-trip.

    Frontmatter is an opaque prefix owned by Notes. Editors may edit the Markdown
    body only when they return that prefix byte-for-byte unchanged.
    """
    reasons = []
    body = content
    prefix = _frontmatter_prefix(content)
    if prefix is not None and prefix:
        body = content[len(prefix):]
    elif prefix is None:
        reasons.append("incomplete frontmatter")
    checks = {
        "wiki links": r"!?\[\[[^\]]+\]\]", "callouts": r"^(?:[ \t]*>[ \t]*)+\[![-\w]+\]",
        "block IDs": r"\^[-\w]+\s*$", "reference links": r"^\s*\[[^\]]+\]:",
        "footnotes": r"\[\^[^\]]+\]", "HTML blocks": r"<\s*/?\s*[A-Za-z][^>]*>",
        "Obsidian comments": r"%%.*?%%",
    }
    for label, pattern in checks.items():
        if re.search(pattern, body, re.M | re.S if label == "Obsidian comments" else re.M):
            reasons.append(label)
    return reasons


def _note_properties(content: str) -> tuple[str | None, list[str]]:
    """Read the two managed properties from a deliberately small YAML subset."""
    lines = content.removeprefix("\ufeff").splitlines()
    if not lines or lines[0] != "---":
        return None, []
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Note frontmatter is incomplete") from exc
    type_lines = [index for index, line in enumerate(lines[1:end], 1) if line.startswith("类型:")]
    tag_lines = [index for index, line in enumerate(lines[1:end], 1) if line.startswith("tags:")]
    if len(type_lines) > 1 or len(tag_lines) > 1:
        raise HTTPException(status_code=422, detail="Managed note properties contain duplicate keys")

    def scalar(raw):
        value = raw.strip()
        if not value:
            return ""
        if value.startswith('"'):
            try:
                parsed = json.loads(value)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Managed note property is not supported") from exc
            if not isinstance(parsed, str):
                raise HTTPException(status_code=422, detail="Managed note property is not a string")
            return parsed
        if value.startswith("'") and value.endswith("'") and len(value) >= 2:
            return value[1:-1].replace("''", "'")
        if (value in {"|", ">", "|-", "|+", ">-", ">+"}
                or value.startswith(("&", "*", "!", "{", "["))
                or any(mark in value for mark in ("\n", "\r", " #", ": "))):
            raise HTTPException(status_code=422, detail="Managed note property is not supported")
        return value

    selected_type = scalar(lines[type_lines[0]].split(":", 1)[1]) if type_lines else ""
    if type_lines and type_lines[0] + 1 < end and lines[type_lines[0] + 1].startswith((" ", "\t")):
        raise HTTPException(status_code=422, detail="Multiline type values are not supported")
    tags: list[str] = []
    if tag_lines:
        index = tag_lines[0]
        raw = lines[index].split(":", 1)[1].strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except ValueError:
                if not (raw.startswith("[") and raw.endswith("]")):
                    raise HTTPException(status_code=422, detail="Managed tags must be a YAML string list")
                try:
                    parsed = next(csv.reader([raw[1:-1]], skipinitialspace=True))
                    parsed = [scalar(item) for item in parsed if item.strip()]
                except (csv.Error, StopIteration) as exc:
                    raise HTTPException(status_code=422, detail="Managed tags must be a YAML string list") from exc
            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise HTTPException(status_code=422, detail="Managed tags must be a string list")
            tags = parsed
        else:
            cursor = index + 1
            while cursor < end and lines[cursor].startswith("  - "):
                tags.append(scalar(lines[cursor][4:]))
                cursor += 1
            if cursor < end and lines[cursor].startswith(" "):
                raise HTTPException(status_code=422, detail="Managed tags use unsupported YAML syntax")
    return selected_type or None, tags


def _replace_note_properties(content: str, note_type: str, tags: list[str]) -> str:
    """Replace only top-level 类型/tags lines, preserving all other bytes and body."""
    newline = "\r\n" if "\r\n" in content else "\n"
    bom = "\ufeff" if content.startswith("\ufeff") else ""
    source = content[len(bom):]
    lines = source.splitlines(keepends=True)
    bare = lambda line: line.removesuffix("\r\n").removesuffix("\n").removesuffix("\r")
    has_frontmatter = bool(lines and bare(lines[0]) == "---")
    if has_frontmatter:
        end = next((index for index, line in enumerate(lines[1:], 1) if bare(line) == "---"), None)
        if end is None:
            raise HTTPException(status_code=422, detail="Note frontmatter is incomplete")
        _note_properties(content)
        body = "".join(lines[end + 1:])
        header = lines[1:end]
        closing_line = lines[end]
    else:
        body, header = source, []
        closing_line = "---" + newline

    kept: list[str] = []
    skip_tag_items = False
    found_type = found_tags = False
    for line in header:
        value = bare(line)
        if value.startswith("类型:"):
            if not found_type:
                kept.append("类型: " + json.dumps(note_type, ensure_ascii=False) + newline)
                found_type = True
            skip_tag_items = False
            continue
        if value.startswith("tags:"):
            if not found_tags:
                kept.append("tags: " + json.dumps(tags, ensure_ascii=False) + newline)
                found_tags = True
            skip_tag_items = not value.split(":", 1)[1].strip()
            continue
        if skip_tag_items and (value.startswith("  - ") or not value.strip()):
            continue
        skip_tag_items = False
        kept.append(line)
    if not found_type:
        kept.append("类型: " + json.dumps(note_type, ensure_ascii=False) + newline)
    if not found_tags:
        kept.append("tags: " + json.dumps(tags, ensure_ascii=False) + newline)

    if has_frontmatter:
        return bom + "---" + newline + "".join(kept) + closing_line + body
    return bom + "---" + newline + "".join(kept) + closing_line + body


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
        self._blocksuite_history = None

    def _history_store(self):
        if self._blocksuite_history is None:
            from .blocksuite_history import BlockSuiteHistoryStore
            self._blocksuite_history = BlockSuiteHistoryStore(self)
        return self._blocksuite_history

    def _blocksuite_artifacts_at(self, directory_fd):
        try:
            attachments_fd = self._open_attachments_directory(directory_fd)
        except HTTPException as exc:
            if exc.status_code == 404:
                return []
            raise
        try:
            artifacts = []
            for filename in os.listdir(attachments_fd):
                if _BLOCKSUITE_RESOURCE_FILENAME.fullmatch(filename):
                    resource_id = filename.split(".", 1)[0]
                    _body, raw, etag = self._read_blocksuite_resource_at(attachments_fd, resource_id)
                    artifacts.append({"kind": "resource", "id": resource_id, "sha256": etag,
                                      "data": raw, "filename": filename, "content_type": "application/json"})
                elif _BLOCKSUITE_BLOB_DISK_FILENAME.fullmatch(filename):
                    digest = filename.split(".", 1)[0]
                    blob_id = base64.urlsafe_b64encode(bytes.fromhex(digest)).decode("ascii")
                    raw, content_type, etag = self._read_blocksuite_blob_at(attachments_fd, blob_id)
                    artifacts.append({"kind": "blob", "id": blob_id, "sha256": etag,
                                      "data": raw, "filename": filename, "content_type": content_type})
            if (len(artifacts) > MAX_BLOCKSUITE_RESOURCES_PER_NOTE
                    or sum(len(item["data"]) for item in artifacts) > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE):
                raise HTTPException(status_code=409, detail="BlockSuite artifact closure exceeds note limits")
            return sorted(artifacts, key=lambda item: (item["kind"], item["id"]))
        except OSError as exc:
            raise HTTPException(status_code=503, detail="BlockSuite artifact inventory is unavailable") from exc
        finally:
            os.close(attachments_fd)

    @staticmethod
    def _artifact_set_etag(artifacts):
        inventory = [{"kind": item["kind"], "id": item["id"], "sha256": item["sha256"],
                      "bytes": len(item["data"]), "content_type": item.get("content_type", "application/json")}
                     for item in artifacts]
        inventory.sort(key=lambda item: (item["kind"], item["id"]))
        raw = json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _check_artifact_set_etag(self, artifacts, expected, *, required_when_nonempty=True):
        actual = self._artifact_set_etag(artifacts)
        if not expected:
            if required_when_nonempty and artifacts:
                raise HTTPException(status_code=428, detail="If-Artifact-Set-Match is required for this note")
            return actual
        if expected.strip('"') != actual:
            raise HTTPException(status_code=412, detail="BlockSuite artifact set changed; reload before saving")
        return actual

    def _snapshot_current_locked(self, collection, relative, directory_fd, note_content, artifacts=None):
        artifacts = artifacts if artifacts is not None else self._blocksuite_artifacts_at(directory_fd)
        expected = {item["id"] + ".blocksuite.json" for item in artifacts if item["kind"] == "resource"}
        referenced = set(_BLOCKSUITE_RESOURCE_REFERENCE.findall(note_content))
        if not referenced.issubset(expected):
            raise HTTPException(status_code=409, detail="Note references a missing BlockSuite resource")
        summary = self._history_store().snapshot_locked(collection, relative, directory_fd, note_content, artifacts)
        return summary, artifacts

    def list_blocksuite_snapshots(self, collection, relative):
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        lock_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            content = self._read_at(directory_fd, path.name)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
            snapshots = self._history_store().list_snapshots_locked(collection, relative, directory_fd)
            return {"note_etag": self._digest(content), "artifact_set_etag": self._artifact_set_etag(artifacts),
                    "snapshots": snapshots}
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def read_blocksuite_snapshot(self, collection, relative, snapshot_id):
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        lock_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            self._read_at(directory_fd, path.name)
            manifest, note_bytes, raw_artifacts = self._history_store().read_snapshot_locked(
                collection, relative, directory_fd, snapshot_id)
            try:
                note_content = note_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=503, detail="BlockSuite snapshot Markdown is invalid UTF-8") from exc
            self._validate(note_content)
            artifact_rows = []
            for item in manifest["artifacts"]:
                raw = raw_artifacts[item["id"]]
                if item["kind"] == "resource":
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, ValueError) as exc:
                        raise HTTPException(status_code=503, detail="BlockSuite snapshot resource is invalid") from exc
                    if self._validate_blocksuite_resource(item["id"], body) != raw:
                        raise HTTPException(status_code=503, detail="BlockSuite snapshot resource is not canonical")
                    artifact_rows.append({"kind": "resource", "id": item["id"], "etag": item["sha256"],
                                          "resource": body})
                else:
                    if self._validate_blocksuite_blob(raw, item["content_type"]) != item["content_type"]:
                        raise HTTPException(status_code=503, detail="BlockSuite snapshot blob is invalid")
                    artifact_rows.append({"kind": "blob", "id": item["id"], "etag": item["sha256"],
                                          "content_type": item["content_type"], "size_bytes": len(raw),
                                          "data_base64": base64.b64encode(raw).decode("ascii")})
            expected = {item["id"] + ".blocksuite.json" for item in artifact_rows
                        if item["kind"] == "resource"}
            if not set(_BLOCKSUITE_RESOURCE_REFERENCE.findall(note_content)).issubset(expected):
                raise HTTPException(status_code=503, detail="BlockSuite snapshot Markdown has a broken resource reference")
            return {"snapshot_id": snapshot_id, "note": {"content": note_content,
                    "etag": manifest["note_sha256"]}, "artifact_set_etag": manifest["artifact_set_etag"],
                    "artifacts": artifact_rows}
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def restore_blocksuite_snapshot(self, collection, relative, snapshot_id, expected_note, expected_artifacts):
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        lock_fd = attachments_fd = snapshots_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            history = self._history_store()
            snapshots_fd = history._open_snapshot_directory(directory_fd, collection, relative, create=True)
            journal = history._read_restore_journal(snapshots_fd)
            current = self._read_at(directory_fd, path.name)
            current_note_etag = self._digest(current)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
            current_artifact_etag = self._artifact_set_etag(artifacts)
            if journal is not None and journal["snapshot_id"] != snapshot_id:
                if journal["state"] != "complete":
                    raise HTTPException(status_code=409, detail="A different BlockSuite restore is already in progress")
                if (not expected_note or expected_note.strip('"') != current_note_etag
                        or not expected_artifacts or expected_artifacts.strip('"') != current_artifact_etag):
                    raise HTTPException(status_code=412, detail="Note or artifacts changed after the previous restore")
                journal = None
            was_resuming = journal is not None
            if journal is not None:
                if (journal["snapshot_id"] != snapshot_id
                        or not expected_note or expected_note.strip('"') != journal["source_note_etag"]
                        or not expected_artifacts or expected_artifacts.strip('"') != journal["source_artifact_set_etag"]):
                    raise HTTPException(status_code=412, detail="Restore request does not match its journal")
            elif (not expected_note or expected_note.strip('"') != current_note_etag
                  or not expected_artifacts or expected_artifacts.strip('"') != current_artifact_etag):
                raise HTTPException(status_code=412, detail="Note or BlockSuite artifacts changed; reload before restoring")

            manifest, note_bytes, raw_artifacts = history.read_snapshot_locked(
                collection, relative, directory_fd, snapshot_id)
            try:
                target_note = note_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=409, detail="BlockSuite snapshot Markdown is invalid UTF-8") from exc
            self._validate(target_note)
            target_artifacts = {}
            for row in manifest["artifacts"]:
                raw = raw_artifacts[row["id"]]
                if row["kind"] == "resource":
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, ValueError) as exc:
                        raise HTTPException(status_code=409, detail="BlockSuite snapshot resource is invalid") from exc
                    if self._validate_blocksuite_resource(row["id"], body) != raw:
                        raise HTTPException(status_code=409, detail="BlockSuite snapshot resource is not canonical")
                else:
                    if self._blocksuite_blob_digest(row["id"]) != row["sha256"]:
                        raise HTTPException(status_code=409, detail="BlockSuite snapshot blob ID does not match its digest")
                    if self._validate_blocksuite_blob(raw, row["content_type"]) != row["content_type"]:
                        raise HTTPException(status_code=409, detail="BlockSuite snapshot blob is invalid")
                target_artifacts[(row["kind"], row["id"])] = (raw, row["sha256"], row["content_type"])
            target_resource_ids = {resource_id for kind, resource_id in target_artifacts if kind == "resource"}
            if not set(_BLOCKSUITE_RESOURCE_REFERENCE.findall(target_note)).issubset(
                    {resource_id + ".blocksuite.json" for resource_id in target_resource_ids}):
                raise HTTPException(status_code=409, detail="BlockSuite snapshot Markdown has a broken resource reference")

            source_rows = [{"kind": item["kind"], "id": item["id"], "sha256": item["sha256"],
                            "bytes": len(item["data"]), "content_type": item["content_type"]}
                           for item in artifacts]
            source_rows.sort(key=lambda item: (item["kind"], item["id"]))
            if journal is None:
                history.snapshot_locked(collection, relative, directory_fd, current, artifacts,
                                        preserve_ids={snapshot_id})
                journal = {"schema": 1, "snapshot_id": snapshot_id,
                           "source_note_etag": current_note_etag,
                           "source_artifact_set_etag": current_artifact_etag,
                           "target_note_sha256": manifest["note_sha256"],
                           "target_artifact_set_etag": manifest["artifact_set_etag"],
                           "source_artifacts": source_rows, "state": "writing"}
                history.write_restore_journal(snapshots_fd, journal)
            else:
                immutable_match = (journal["target_note_sha256"] == manifest["note_sha256"]
                                   and journal["target_artifact_set_etag"] == manifest["artifact_set_etag"])
                if not immutable_match:
                    raise HTTPException(status_code=409, detail="BlockSuite restore journal does not match current state")

            source_by_key = {(item["kind"], item["id"]): item for item in journal["source_artifacts"]}
            target_by_key = {key: (digest, len(raw), content_type)
                             for key, (raw, digest, content_type) in target_artifacts.items()}
            current_by_key = {(item["kind"], item["id"]): item for item in artifacts}
            allowed_keys = set(source_by_key) | set(target_by_key)
            if set(current_by_key) - allowed_keys:
                raise HTTPException(status_code=409, detail="An untracked BlockSuite resource occupies the restore scope")
            missing_source = set(source_by_key) - set(current_by_key)
            if missing_source and (journal["state"] not in {"writing", "complete"}
                                   or missing_source & set(target_by_key)):
                raise HTTPException(status_code=409, detail="A BlockSuite resource disappeared during restore")
            for key, item in current_by_key.items():
                if (item["sha256"] != source_by_key.get(key, {}).get("sha256")
                        and item["sha256"] != target_by_key.get(key, (None,))[0]):
                    raise HTTPException(status_code=409, detail="A BlockSuite resource changed during restore")
            source_note_hash = journal["source_note_etag"]
            if current_note_etag not in {source_note_hash, manifest["note_sha256"]}:
                raise HTTPException(status_code=409, detail="Markdown changed during BlockSuite restore")

            if journal["state"] == "complete":
                if (current_note_etag != manifest["note_sha256"] or set(current_by_key) != set(target_by_key)
                        or any(current_by_key[key]["sha256"] != value[0] for key, value in target_by_key.items())):
                    raise HTTPException(status_code=409, detail="Completed BlockSuite restore no longer matches its result")
                return {"snapshot_id": snapshot_id, "note_etag": current_note_etag,
                        "artifact_set_etag": current_artifact_etag, "restored": True, "duplicate": True}

            if target_artifacts or artifacts:
                attachments_fd = self._open_attachments_directory(directory_fd, create=bool(target_artifacts))
            existing_count, existing_bytes = (self._blocksuite_resource_usage(attachments_fd)
                                              if attachments_fd is not None else (0, 0))
            removals = [(key, item) for key, item in source_by_key.items()
                        if key not in target_by_key and key in current_by_key]
            next_count = existing_count - len(removals)
            next_bytes = existing_bytes - sum(item["bytes"] for _key, item in removals)
            for key, (raw, digest, _content_type) in target_artifacts.items():
                old = current_by_key.get(key)
                if old is not None and old["sha256"] == digest:
                    continue
                next_bytes += len(raw) - (len(old["data"]) if old is not None else 0)
                if old is None:
                    next_count += 1
            if next_count > MAX_BLOCKSUITE_RESOURCES_PER_NOTE or next_bytes > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE:
                raise HTTPException(status_code=413, detail="Restored BlockSuite artifacts exceed note limits")

            # Resources first, then blobs, all before the Markdown references are changed.
            for kind in ("resource", "blob"):
                for (artifact_kind, artifact_id), (raw, digest, _content_type) in target_artifacts.items():
                    if artifact_kind != kind:
                        continue
                    current_item = current_by_key.get((kind, artifact_id))
                    if current_item is not None and current_item["sha256"] == digest:
                        continue
                    if current_item is not None:
                        try:
                            if kind == "resource":
                                _current_body, _current_raw, observed_digest = self._read_blocksuite_resource_at(
                                    attachments_fd, artifact_id)
                            else:
                                _current_raw, _current_type, observed_digest = self._read_blocksuite_blob_at(
                                    attachments_fd, artifact_id)
                        except HTTPException as exc:
                            raise HTTPException(status_code=409, detail="BlockSuite restore target changed") from exc
                        if observed_digest not in {source_by_key.get((kind, artifact_id), {}).get("sha256"), digest}:
                            raise HTTPException(status_code=409, detail="BlockSuite restore target changed")
                    filename = (f"{artifact_id}.blocksuite.json" if kind == "resource"
                                else f"{digest}.blocksuite-blob")
                    self._atomic_write(directory / "attachments" / filename, raw,
                                       exclusive=current_item is None, directory_fd=attachments_fd)
            for key, item in removals:
                kind, artifact_id = key
                if kind == "resource":
                    _body, raw, digest = self._read_blocksuite_resource_at(attachments_fd, artifact_id)
                else:
                    raw, _mime, digest = self._read_blocksuite_blob_at(attachments_fd, artifact_id)
                if digest != item["sha256"] or len(raw) != item["bytes"]:
                    raise HTTPException(status_code=409, detail="A source BlockSuite artifact changed during restore")
                filename = (f"{artifact_id}.blocksuite.json" if kind == "resource"
                            else f"{digest}.blocksuite-blob")
                os.unlink(filename, dir_fd=attachments_fd)
                os.fsync(attachments_fd)
            # Write the Markdown only after all target resources are present and verified.
            for (kind, artifact_id), (_raw, digest, content_type) in target_artifacts.items():
                if kind == "resource":
                    _body, _raw, actual_digest = self._read_blocksuite_resource_at(attachments_fd, artifact_id)
                    actual_type = "application/json"
                else:
                    _raw, actual_type, actual_digest = self._read_blocksuite_blob_at(attachments_fd, artifact_id)
                if actual_digest != digest or actual_type != content_type:
                    raise HTTPException(status_code=503, detail="Restored BlockSuite artifact failed verification")
            restored_artifacts = self._blocksuite_artifacts_at(directory_fd)
            restored_by_key = {(item["kind"], item["id"]): item["sha256"] for item in restored_artifacts}
            if restored_by_key != {key: value[0] for key, value in target_by_key.items()}:
                raise HTTPException(status_code=409, detail="Restored BlockSuite artifact set does not match the snapshot")
            if self._digest(current) != manifest["note_sha256"]:
                self._atomic_write(path, note_bytes, directory_fd=directory_fd)
            journal["state"] = "complete"
            history.write_restore_journal(snapshots_fd, journal)
            restored_etag = self._artifact_set_etag(restored_artifacts)
            return {"snapshot_id": snapshot_id, "note_etag": manifest["note_sha256"],
                    "artifact_set_etag": restored_etag, "restored": True,
                    "duplicate": bool(was_resuming and current_note_etag == manifest["note_sha256"])}
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if snapshots_fd is not None:
                os.close(snapshots_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

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
        if any(unicodedata.category(char).startswith("C") for char in parsed.name):
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
    def _read_at(directory_fd, filename, max_bytes=MAX_MARKDOWN_BYTES):
        try:
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Note not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > max_bytes):
                raise HTTPException(status_code=403, detail="Note file permissions or size are unsafe")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(max_bytes + 1)
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

    @staticmethod
    def _history_namespace(collection, relative):
        if collection == "drafts":
            return None
        canonical_path = PurePosixPath(relative).as_posix()
        return hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()

    @staticmethod
    def _check_history_directory(fd):
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise HTTPException(status_code=403, detail="History directory permissions are unsafe")

    @classmethod
    def _open_history_directory_for_update(cls, directory_fd, namespace):
        try:
            os.mkdir(".history", mode=0o700, dir_fd=directory_fd)
        except FileExistsError:
            pass
        os.fsync(directory_fd)
        root_fd = os.open(".history", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                          | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        if namespace is None:
            try:
                cls._check_history_directory(root_fd)
            except Exception:
                os.close(root_fd)
                raise
            return root_fd
        try:
            cls._check_history_directory(root_fd)
            try:
                os.mkdir(namespace, mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            os.fsync(root_fd)
            history_fd = os.open(namespace, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                 | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                cls._check_history_directory(history_fd)
                return history_fd
            except Exception:
                os.close(history_fd)
                raise
        finally:
            os.close(root_fd)

    @classmethod
    def _open_history_directory_for_read(cls, directory_fd, namespace):
        try:
            root_fd = os.open(".history", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                              | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HTTPException(status_code=403, detail="History directory could not be opened safely") from exc
        try:
            cls._check_history_directory(root_fd)
            if namespace is None:
                return root_fd
            # The former ordinary-note format stored every note's revisions as
            # flat files here. Their source cannot be inferred from content hashes,
            # so never expose them under any note's history endpoint.
            for name in os.listdir(root_fd):
                try:
                    info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                except OSError as exc:
                    raise HTTPException(status_code=403, detail="History entry could not be inspected safely") from exc
                if stat.S_ISLNK(info.st_mode):
                    raise HTTPException(status_code=403, detail="History entry cannot be a symlink")
                if not stat.S_ISDIR(info.st_mode):
                    raise HTTPException(status_code=409, detail="Legacy shared history has no verifiable note owner")
            try:
                history_fd = os.open(namespace, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                     | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise HTTPException(status_code=403, detail="History directory could not be opened safely") from exc
            try:
                cls._check_history_directory(history_fd)
            except Exception:
                os.close(history_fd)
                raise
            return history_fd
        finally:
            if namespace is not None:
                os.close(root_fd)

    def read(self, collection, relative):
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        lock_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            content = self._read_at(directory_fd, path.name)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)
        return {"collection": collection, "path": relative, "content": content,
                "etag": self._digest(content), "read_only": bool(markdown_safety(content)),
                "safety_reasons": markdown_safety(content),
                "artifact_set_etag": self._artifact_set_etag(artifacts)}

    def read_source_draft(self, draft_id, *, max_bytes=MAX_MARKDOWN_BYTES):
        """Resolve a NotesStore-issued Draft UUID without scanning collections."""
        path, directory = self._path("drafts", draft_id)
        directory_fd = self._open_directory(directory, missing_status=404)
        lock_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            content = self._read_at(directory_fd, path.name, max_bytes=max_bytes)
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)
        encoded = content.encode("utf-8")
        return {"etag": self._digest(content), "size_bytes": len(encoded)}

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
                "read_only": False, "safety_reasons": [],
                "artifact_set_etag": self._artifact_set_etag([])}

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

    def update(self, collection, relative, content, expected, *, metadata_only=False, expected_artifacts=None):
        if collection not in self.roots:
            raise HTTPException(status_code=404, detail="Notes collection not found")
        self._validate(content)
        if markdown_safety(content) and not metadata_only:
            raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and cannot be saved through the rich-text editor")
        path, directory = self._path(collection, relative, create=collection == "drafts")
        directory_fd = self._open_directory(directory)
        try:
            lock_fd = self._open_note_lock(directory_fd)
        except HTTPException:
            os.close(directory_fd)
            raise
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
            if not metadata_only and _frontmatter_prefix(content) != _frontmatter_prefix(current):
                raise HTTPException(status_code=422, detail="Markdown editors must preserve the existing frontmatter exactly")
            if markdown_safety(current) and not metadata_only:
                raise HTTPException(status_code=422, detail="This Markdown contains unsupported syntax and is read-only")
            artifacts = self._blocksuite_artifacts_at(directory_fd)
            if not metadata_only:
                self._check_artifact_set_etag(artifacts, expected_artifacts)
            new_note_etag = self._digest(content)
            rebound_resources = []
            if metadata_only:
                for artifact in artifacts:
                    if artifact["kind"] != "resource":
                        continue
                    try:
                        resource = json.loads(artifact["data"])
                    except (TypeError, ValueError, UnicodeDecodeError) as exc:
                        raise HTTPException(status_code=409, detail="BlockSuite resource cannot be rebound safely") from exc
                    if resource.get("resourceKind") != "rich-page":
                        continue
                    snapshot = resource.get("snapshot")
                    receipt = snapshot.get("secondbrainRichPage") if isinstance(snapshot, dict) else None
                    if (not isinstance(receipt, dict) or receipt.get("schemaVersion") != 1
                            or receipt.get("markdownSha256") != current_etag):
                        raise HTTPException(status_code=412, detail="Rich Page binding is stale; reload and reconcile before editing properties")
                    rebound = {**resource, "snapshot": {**snapshot,
                        "secondbrainRichPage": {**receipt, "markdownSha256": new_note_etag}}}
                    raw = self._validate_blocksuite_resource(artifact["id"], rebound)
                    rebound_resources.append((artifact["filename"], artifact["data"], raw))
            self._snapshot_current_locked(collection, relative, directory_fd, current, artifacts)
            namespace = self._history_namespace(collection, relative)
            history_fd = self._open_history_directory_for_update(directory_fd, namespace)
            previous_name = f"{current_etag}.md"
            try:
                previous = self._read_at(history_fd, previous_name)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                history_path = directory / ".history" / (namespace or "") / previous_name
                self._atomic_write(history_path, current.encode("utf-8"),
                                   exclusive=True, directory_fd=history_fd)
            else:
                if previous != current:
                    raise HTTPException(status_code=409, detail="History entry is not safe to replace")
            if rebound_resources:
                attachments_fd = self._open_attachments_directory(directory_fd)
                try:
                    try:
                        for filename, _old_raw, rebound_raw in rebound_resources:
                            self._atomic_write(directory / "attachments" / filename, rebound_raw,
                                               directory_fd=attachments_fd)
                        self._atomic_write(path, content.encode("utf-8"), directory_fd=directory_fd)
                    except Exception:
                        try:
                            for filename, old_raw, _rebound_raw in rebound_resources:
                                self._atomic_write(directory / "attachments" / filename, old_raw,
                                                   directory_fd=attachments_fd)
                            self._atomic_write(path, current.encode("utf-8"), directory_fd=directory_fd)
                        except Exception as rollback_error:
                            raise HTTPException(status_code=503,
                                detail="Property update failed; a verified BlockSuite snapshot is retained for recovery") from rollback_error
                        raise
                finally:
                    os.close(attachments_fd)
            else:
                self._atomic_write(path, content.encode("utf-8"), directory_fd=directory_fd)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
        finally:
            if history_fd is not None:
                os.close(history_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
                os.close(directory_fd)
        return {"collection": collection, "path": relative, "content": content, "etag": self._digest(content),
                "read_only": bool(markdown_safety(content)), "safety_reasons": markdown_safety(content),
                "artifact_set_etag": self._artifact_set_etag(artifacts)}

    def update_properties(self, collection, relative, note_type, tags, expected):
        """Update only managed frontmatter keys using Notes' existing CAS/history path."""
        current = self.read(collection, relative)
        if not expected or expected.strip('"') != current["etag"]:
            raise HTTPException(status_code=412, detail="Note changed; reload before saving properties")
        replacement = _replace_note_properties(current["content"], note_type, tags)
        return self.update(collection, relative, replacement, expected, metadata_only=True)

    def history(self, collection, relative):
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        try:
            # A missing history directory means a valid note has no revisions;
            # a missing note itself is a 404 and must not look like an empty list.
            self._read_at(directory_fd, path.name)
            namespace = self._history_namespace(collection, relative)
            history_fd = self._open_history_directory_for_read(directory_fd, namespace)
            if history_fd is None:
                return {"versions": []}
            try:
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
    def _validate_blocksuite_resource(resource_id, body):
        """Validate one bounded, versioned BlockSuite Yjs resource envelope."""
        if not isinstance(resource_id, str) or not _BLOCKSUITE_RESOURCE_ID.fullmatch(resource_id):
            raise HTTPException(status_code=400, detail="Invalid BlockSuite resource id")
        if not isinstance(body, dict) or set(body) != {
                "schemaVersion", "resourceId", "resourceKind", "docId", "updateB64", "snapshot"}:
            raise HTTPException(status_code=422, detail="BlockSuite resource schema is invalid")
        if (body.get("schemaVersion") != 1 or body.get("resourceId") != resource_id
                or body.get("resourceKind") not in _BLOCKSUITE_RESOURCE_KINDS):
            raise HTTPException(status_code=422, detail="BlockSuite resource version or identity is invalid")
        doc_id = body.get("docId")
        encoded = body.get("updateB64")
        if not isinstance(doc_id, str) or not _BLOCKSUITE_DOC_ID.fullmatch(doc_id):
            raise HTTPException(status_code=422, detail="BlockSuite document id is invalid")
        if not isinstance(encoded, str) or not encoded or len(encoded) > ((MAX_BLOCKSUITE_UPDATE_BYTES + 2) // 3) * 4:
            raise HTTPException(status_code=413, detail="BlockSuite document update is too large")
        try:
            update = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=422, detail="BlockSuite document update is not valid Base64") from exc
        if not update or len(update) > MAX_BLOCKSUITE_UPDATE_BYTES:
            raise HTTPException(status_code=413, detail="BlockSuite document update is too large")
        snapshot = body.get("snapshot")
        if not isinstance(snapshot, dict):
            raise HTTPException(status_code=422, detail="BlockSuite snapshot must be an object")
        pending = [(snapshot, 0)]
        nodes = 0
        while pending:
            value, depth = pending.pop()
            nodes += 1
            if nodes > MAX_BLOCKSUITE_SNAPSHOT_NODES or depth > MAX_BLOCKSUITE_SNAPSHOT_DEPTH:
                raise HTTPException(status_code=422, detail="BlockSuite snapshot exceeds structural limits")
            if isinstance(value, dict):
                pending.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                pending.extend((child, depth + 1) for child in value)
            elif isinstance(value, str):
                try:
                    string_size = len(value.encode("utf-8"))
                except UnicodeEncodeError as exc:
                    raise HTTPException(status_code=422, detail="BlockSuite snapshot string is invalid Unicode") from exc
                if string_size > 100_000:
                    raise HTTPException(status_code=422, detail="BlockSuite snapshot string is too long")
            elif value is not None and not isinstance(value, (str, int, float, bool)):
                raise HTTPException(status_code=422, detail="BlockSuite snapshot contains unsupported values")
        try:
            snapshot_bytes = json.dumps(snapshot, ensure_ascii=False, allow_nan=False,
                                        separators=(",", ":")).encode("utf-8")
            resource_bytes = json.dumps(body, ensure_ascii=False, allow_nan=False,
                                        separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise HTTPException(status_code=422, detail="BlockSuite resource JSON is invalid") from exc
        if len(snapshot_bytes) > MAX_BLOCKSUITE_SNAPSHOT_BYTES:
            raise HTTPException(status_code=413, detail="BlockSuite snapshot is too large")
        if len(resource_bytes) > MAX_BLOCKSUITE_RESOURCE_BYTES:
            raise HTTPException(status_code=413, detail="BlockSuite resource is too large")
        return resource_bytes

    @staticmethod
    def _open_note_lock(directory_fd):
        try:
            os.stat(".notes.lock", dir_fd=directory_fd, follow_symlinks=False)
            lock_existed = True
        except FileNotFoundError:
            lock_existed = False
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note lock could not be inspected safely") from exc
        try:
            lock_fd = os.open(".notes.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                              0o600, dir_fd=directory_fd)
        except FileNotFoundError as first_error:
            # On macOS/APFS, a concurrent O_CREAT on the same dirfd can
            # transiently report ENOENT even though the first creator has
            # already installed the regular lock. Re-open that existing file
            # without O_CREAT only after a no-follow dirfd stat proves it exists.
            try:
                info = os.stat(".notes.lock", dir_fd=directory_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise HTTPException(status_code=403, detail="Note lock permissions are unsafe")
                lock_fd = os.open(".notes.lock", os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                                  dir_fd=directory_fd)
            except OSError as exc:
                raise HTTPException(status_code=403, detail="Note lock could not be opened safely") from first_error
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note lock could not be opened safely") from exc
        info = os.fstat(lock_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            os.close(lock_fd)
            raise HTTPException(status_code=403, detail="Note lock permissions are unsafe")
        if not lock_existed:
            os.fsync(directory_fd)
        return lock_fd

    @staticmethod
    def _open_attachments_directory(directory_fd, *, create=False):
        if create:
            try:
                os.mkdir("attachments", mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            os.fsync(directory_fd)
        try:
            attachments_fd = os.open("attachments", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                                     | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Note resource directory not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note resource directory is unsafe") from exc
        info = os.fstat(attachments_fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(attachments_fd)
            raise HTTPException(status_code=403, detail="Note resource directory permissions are unsafe")
        return attachments_fd

    def _read_blocksuite_resource_at(self, attachments_fd, resource_id):
        filename = f"{resource_id}.blocksuite.json"
        if not _BLOCKSUITE_RESOURCE_FILENAME.fullmatch(filename):
            raise HTTPException(status_code=400, detail="Invalid BlockSuite resource filename")
        try:
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=attachments_fd)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="BlockSuite resource not found")
        except OSError as exc:
            raise HTTPException(status_code=403, detail="BlockSuite resource could not be opened safely") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise HTTPException(status_code=403, detail="BlockSuite resource file permissions are unsafe")
            if info.st_size > MAX_BLOCKSUITE_RESOURCE_BYTES:
                raise HTTPException(status_code=413, detail="BlockSuite resource file is too large")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BLOCKSUITE_RESOURCE_BYTES + 1)
        finally:
            os.close(fd)
        if len(raw) > MAX_BLOCKSUITE_RESOURCE_BYTES:
            raise HTTPException(status_code=413, detail="BlockSuite resource file is too large")
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="BlockSuite resource file is invalid JSON") from exc
        canonical = self._validate_blocksuite_resource(resource_id, body)
        if canonical != raw:
            raise HTTPException(status_code=409, detail="BlockSuite resource file is not canonical")
        return body, raw, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _blocksuite_blob_digest(blob_id):
        if not _BLOCKSUITE_BLOB_FILENAME.fullmatch(blob_id or ""):
            raise HTTPException(status_code=400, detail="Invalid BlockSuite blob id")
        try:
            decoded = base64.b64decode(blob_id.encode("ascii"), altchars=b"-_", validate=True)
        except (UnicodeError, binascii.Error) as exc:
            raise HTTPException(status_code=400, detail="Invalid BlockSuite blob id") from exc
        if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode("ascii") != blob_id:
            raise HTTPException(status_code=400, detail="Noncanonical BlockSuite blob id")
        return decoded.hex()

    @staticmethod
    def _validate_blocksuite_blob(data, expected_content_type=None):
        if not isinstance(data, bytes) or not data or len(data) > MAX_BLOCKSUITE_BLOB_BYTES:
            raise HTTPException(status_code=413, detail="BlockSuite blob size is not supported")
        try:
            with Image.open(BytesIO(data)) as image:
                content_type = _BLOCKSUITE_BLOB_TYPES.get(image.format)
                if (content_type is None or image.width <= 0 or image.height <= 0
                        or image.width * image.height > 40_000_000
                        or (expected_content_type and expected_content_type.split(";", 1)[0].strip().lower()
                            != content_type)):
                    raise HTTPException(status_code=415, detail="BlockSuite image format or dimensions are unsupported")
                image.verify()
                return content_type
        except HTTPException:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise HTTPException(status_code=415, detail="BlockSuite image data is invalid") from exc

    def _read_blocksuite_blob_at(self, attachments_fd, blob_id):
        digest = self._blocksuite_blob_digest(blob_id)
        filename = f"{digest}.blocksuite-blob"
        try:
            fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0), dir_fd=attachments_fd)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="BlockSuite blob not found")
        except OSError as exc:
            raise HTTPException(status_code=409, detail="BlockSuite blob path is unsafe") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or info.st_nlink != 1 or info.st_size <= 0 or info.st_size > MAX_BLOCKSUITE_BLOB_BYTES):
                raise HTTPException(status_code=409, detail="BlockSuite blob file is unsafe")
            raw_buffer = bytearray()
            while len(raw_buffer) <= MAX_BLOCKSUITE_BLOB_BYTES:
                chunk = os.read(fd, min(65536, MAX_BLOCKSUITE_BLOB_BYTES + 1 - len(raw_buffer)))
                if not chunk:
                    break
                raw_buffer.extend(chunk)
            raw = bytes(raw_buffer)
            after = os.fstat(fd)
            if ((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    or len(raw) != info.st_size or hashlib.sha256(raw).hexdigest() != digest):
                raise HTTPException(status_code=409, detail="BlockSuite blob digest verification failed")
            content_type = self._validate_blocksuite_blob(raw)
            return raw, content_type, digest
        finally:
            os.close(fd)

    def _blocksuite_resource_usage(self, attachments_fd):
        count = total_bytes = 0
        try:
            names = os.listdir(attachments_fd)
        except OSError as exc:
            raise HTTPException(status_code=403, detail="Note resource directory could not be listed safely") from exc
        for name in names:
            if _BLOCKSUITE_RESOURCE_FILENAME.fullmatch(name):
                try:
                    info = os.stat(name, dir_fd=attachments_fd, follow_symlinks=False)
                except OSError as exc:
                    raise HTTPException(status_code=403, detail="BlockSuite resource could not be inspected safely") from exc
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                        or info.st_nlink != 1 or info.st_size > MAX_BLOCKSUITE_RESOURCE_BYTES):
                    raise HTTPException(status_code=403, detail="BlockSuite resource file permissions or size are unsafe")
                count += 1
                total_bytes += info.st_size
            elif _BLOCKSUITE_BLOB_DISK_FILENAME.fullmatch(name):
                digest = name.split(".", 1)[0]
                blob_id = base64.urlsafe_b64encode(bytes.fromhex(digest)).decode("ascii")
                raw, _content_type, _etag = self._read_blocksuite_blob_at(attachments_fd, blob_id)
                count += 1
                total_bytes += len(raw)
        if count > MAX_BLOCKSUITE_RESOURCES_PER_NOTE or total_bytes > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE:
            raise HTTPException(status_code=409, detail="Existing BlockSuite resources exceed configured note limits")
        return count, total_bytes

    def create_blocksuite_resource(self, collection, relative, body, expected_note, expected_artifacts=None):
        path, directory = self._path(collection, relative)
        resource_id = uuid.uuid4().hex
        create_fields = {"schemaVersion", "resourceKind", "docId", "updateB64", "snapshot"}
        if not isinstance(body, dict) or set(body) != create_fields:
            raise HTTPException(status_code=422, detail="BlockSuite resource creation schema is invalid")
        body = {**body, "resourceId": resource_id}
        raw = self._validate_blocksuite_resource(resource_id, body)
        directory_fd = self._open_directory(directory)
        lock_fd = attachments_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read_at(directory_fd, path.name)
            note_etag = self._digest(current)
            if not expected_note or expected_note.strip('"') != note_etag:
                raise HTTPException(status_code=412, detail="Note changed; reload before creating a resource")
            attachments_fd = self._open_attachments_directory(directory_fd, create=True)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
            self._check_artifact_set_etag(artifacts, expected_artifacts)
            resource_count, resource_bytes = self._blocksuite_resource_usage(attachments_fd)
            if (resource_count + 1 > MAX_BLOCKSUITE_RESOURCES_PER_NOTE
                    or resource_bytes + len(raw) > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE):
                raise HTTPException(status_code=413, detail="BlockSuite resources exceed per-note storage limits")
            self._snapshot_current_locked(collection, relative, directory_fd, current, artifacts)
            filename = f"{resource_id}.blocksuite.json"
            self._atomic_write(directory / "attachments" / filename, raw, exclusive=True,
                               directory_fd=attachments_fd)
            etag = hashlib.sha256(raw).hexdigest()
            artifact_set_etag = self._artifact_set_etag(self._blocksuite_artifacts_at(directory_fd))
            return {"resource_id": resource_id, "resource_kind": body["resourceKind"], "doc_id": body["docId"],
                    "filename": filename, "reference": f"[BlockSuite resource](attachments/{filename})",
                    "etag": etag, "note_etag": note_etag, "artifact_set_etag": artifact_set_etag}
        except OSError as exc:
            raise HTTPException(status_code=403, detail="BlockSuite resource path could not be opened safely") from exc
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def read_blocksuite_resource(self, collection, relative, resource_id):
        if not _BLOCKSUITE_RESOURCE_ID.fullmatch(resource_id or ""):
            raise HTTPException(status_code=400, detail="Invalid BlockSuite resource id")
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        attachments_fd = lock_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            note = self._read_at(directory_fd, path.name)
            attachments_fd = self._open_attachments_directory(directory_fd)
            body, _raw, etag = self._read_blocksuite_resource_at(attachments_fd, resource_id)
            artifact_set_etag = self._artifact_set_etag(self._blocksuite_artifacts_at(directory_fd))
            return {**body, "etag": etag, "note_etag": self._digest(note),
                    "artifact_set_etag": artifact_set_etag,
                    "filename": f"{resource_id}.blocksuite.json"}
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def update_blocksuite_resource(self, collection, relative, resource_id, body, expected_note,
                                   expected_resource, expected_artifacts=None):
        if not _BLOCKSUITE_RESOURCE_ID.fullmatch(resource_id or ""):
            raise HTTPException(status_code=400, detail="Invalid BlockSuite resource id")
        raw = self._validate_blocksuite_resource(resource_id, body)
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory)
        lock_fd = attachments_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read_at(directory_fd, path.name)
            note_etag = self._digest(current)
            if not expected_note or expected_note.strip('"') != note_etag:
                raise HTTPException(status_code=412, detail="Note changed; reload before saving a resource")
            attachments_fd = self._open_attachments_directory(directory_fd)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
            self._check_artifact_set_etag(artifacts, expected_artifacts)
            old_body, _old_raw, current_resource_etag = self._read_blocksuite_resource_at(attachments_fd, resource_id)
            if not expected_resource or expected_resource.strip('"') != current_resource_etag:
                raise HTTPException(status_code=412, detail="BlockSuite resource changed; reload before saving")
            if (body["resourceKind"] != old_body["resourceKind"]
                    or body["docId"] != old_body["docId"]):
                raise HTTPException(status_code=409, detail="BlockSuite resource identity is immutable")
            resource_count, resource_bytes = self._blocksuite_resource_usage(attachments_fd)
            if (resource_count > MAX_BLOCKSUITE_RESOURCES_PER_NOTE
                    or resource_bytes - len(_old_raw) + len(raw) > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE):
                raise HTTPException(status_code=413, detail="BlockSuite resources exceed per-note storage limits")
            self._snapshot_current_locked(collection, relative, directory_fd, current, artifacts)
            filename = f"{resource_id}.blocksuite.json"
            self._atomic_write(directory / "attachments" / filename, raw, directory_fd=attachments_fd)
            etag = hashlib.sha256(raw).hexdigest()
            artifact_set_etag = self._artifact_set_etag(self._blocksuite_artifacts_at(directory_fd))
            return {"resource_id": resource_id, "resource_kind": body["resourceKind"], "doc_id": body["docId"],
                    "filename": filename, "etag": etag, "note_etag": note_etag,
                    "artifact_set_etag": artifact_set_etag}
        except OSError as exc:
            raise HTTPException(status_code=403, detail="BlockSuite resource path could not be opened safely") from exc
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def read_blocksuite_blob(self, collection, relative, blob_id):
        digest = self._blocksuite_blob_digest(blob_id)
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory, missing_status=404)
        lock_fd = attachments_fd = None
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            note = self._read_at(directory_fd, path.name)
            attachments_fd = self._open_attachments_directory(directory_fd)
            raw, content_type, etag = self._read_blocksuite_blob_at(attachments_fd, blob_id)
            artifact_set_etag = self._artifact_set_etag(self._blocksuite_artifacts_at(directory_fd))
            if etag != digest:
                raise HTTPException(status_code=409, detail="BlockSuite blob digest changed")
            return {"blob_id": blob_id, "data": raw, "content_type": content_type,
                    "etag": etag, "note_etag": self._digest(note),
                    "artifact_set_etag": artifact_set_etag, "size_bytes": len(raw)}
        finally:
            if attachments_fd is not None:
                os.close(attachments_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def put_blocksuite_blob(self, collection, relative, blob_id, data, content_type,
                            expected_note, expected_artifacts):
        digest = self._blocksuite_blob_digest(blob_id)
        validated_type = self._validate_blocksuite_blob(data, content_type)
        actual_digest = hashlib.sha256(data).hexdigest()
        if digest != actual_digest:
            raise HTTPException(status_code=422, detail="BlockSuite blob id does not match content SHA-256")
        path, directory = self._path(collection, relative)
        directory_fd = self._open_directory(directory)
        lock_fd = attachments_fd = None
        created = False
        try:
            lock_fd = self._open_note_lock(directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self._read_at(directory_fd, path.name)
            note_etag = self._digest(current)
            if not expected_note or expected_note.strip('"') != note_etag:
                raise HTTPException(status_code=412, detail="Note changed; reload before uploading a blob")
            attachments_fd = self._open_attachments_directory(directory_fd, create=True)
            artifacts = self._blocksuite_artifacts_at(directory_fd)
            self._check_artifact_set_etag(artifacts, expected_artifacts)
            previous = next((item for item in artifacts if item["kind"] == "blob" and item["id"] == blob_id), None)
            if previous is not None:
                if previous["data"] != data or previous["content_type"] != validated_type:
                    raise HTTPException(status_code=409, detail="BlockSuite blob key is already bound to different content")
                artifact_set_etag = self._artifact_set_etag(artifacts)
                return {"blob_id": blob_id, "etag": digest, "note_etag": note_etag,
                        "artifact_set_etag": artifact_set_etag, "content_type": validated_type,
                        "size_bytes": len(data), "created": False}
            count, total_bytes = self._blocksuite_resource_usage(attachments_fd)
            if (count + 1 > MAX_BLOCKSUITE_RESOURCES_PER_NOTE
                    or total_bytes + len(data) > MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE):
                raise HTTPException(status_code=413, detail="BlockSuite artifact closure exceeds per-note limits")
            self._snapshot_current_locked(collection, relative, directory_fd, current, artifacts)
            filename = f"{digest}.blocksuite-blob"
            try:
                self._atomic_write(directory / "attachments" / filename, data, exclusive=True,
                                   directory_fd=attachments_fd)
                created = True
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                _existing, existing_type, existing_digest = self._read_blocksuite_blob_at(attachments_fd, blob_id)
                if _existing != data or existing_type != validated_type or existing_digest != digest:
                    raise HTTPException(status_code=409, detail="BlockSuite blob path is occupied") from exc
            artifact_set_etag = self._artifact_set_etag(self._blocksuite_artifacts_at(directory_fd))
            return {"blob_id": blob_id, "etag": digest, "note_etag": note_etag,
                    "artifact_set_etag": artifact_set_etag, "content_type": validated_type,
                    "size_bytes": len(data), "created": created}
        except OSError as exc:
            raise HTTPException(status_code=403, detail="BlockSuite blob path could not be opened safely") from exc
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


def create_notes_router(auth, store, vocabulary_store=None):
    router = APIRouter(prefix="/api/notes")

    def require(request, action):
        auth.require_action(request, f"notes.{action}")
        if store is None:
            raise HTTPException(status_code=503, detail="Notes is not configured")

    @router.post("/{collection}/{relative:path}/blocksuite/resources")
    async def create_blocksuite_resource(request: Request, response: Response, collection: str,
                                         relative: str):
        require(request, "write")
        body = await _read_bounded_json_request(request, MAX_BLOCKSUITE_REQUEST_BYTES)
        result = store.create_blocksuite_resource(collection, relative, body,
                                                  request.headers.get("if-match", ""),
                                                  request.headers.get("if-artifact-set-match"))
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Note-ETag"] = f'"{result["note_etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    @router.get("/{collection}/{relative:path}/blocksuite/resources/{resource_id}")
    def read_blocksuite_resource(request: Request, response: Response, collection: str,
                                 relative: str, resource_id: str):
        require(request, "read")
        result = store.read_blocksuite_resource(collection, relative, resource_id)
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Note-ETag"] = f'"{result["note_etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return result

    @router.get("/{collection}/{relative:path}/blocksuite/snapshots")
    def list_blocksuite_snapshots(request: Request, response: Response, collection: str, relative: str):
        require(request, "read")
        result = store.list_blocksuite_snapshots(collection, relative)
        response.headers["X-Note-ETag"] = f'"{result["note_etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    @router.get("/{collection}/{relative:path}/blocksuite/snapshots/{snapshot_id}")
    def read_blocksuite_snapshot(request: Request, response: Response, collection: str, relative: str,
                                 snapshot_id: str):
        require(request, "read")
        result = store.read_blocksuite_snapshot(collection, relative, snapshot_id)
        response.headers["ETag"] = f'"{result["snapshot_id"]}"'
        response.headers["X-Note-ETag"] = f'"{result["note"]["etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        response.headers["Cache-Control"] = "private, no-store"
        return result

    @router.post("/{collection}/{relative:path}/blocksuite/snapshots/{snapshot_id}/restore")
    def restore_blocksuite_snapshot(request: Request, response: Response, collection: str, relative: str,
                                    snapshot_id: str):
        require(request, "write")
        result = store.restore_blocksuite_snapshot(collection, relative, snapshot_id,
                                                   request.headers.get("if-match", ""),
                                                   request.headers.get("if-artifact-set-match", ""))
        response.headers["ETag"] = f'"{result["snapshot_id"]}"'
        response.headers["X-Note-ETag"] = f'"{result["note_etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    @router.put("/{collection}/{relative:path}/blocksuite/resources/{resource_id}")
    async def update_blocksuite_resource(request: Request, response: Response, collection: str,
                                         relative: str, resource_id: str):
        require(request, "write")
        body = await _read_bounded_json_request(request, MAX_BLOCKSUITE_REQUEST_BYTES)
        result = store.update_blocksuite_resource(collection, relative, resource_id, body,
                                                  request.headers.get("if-match", ""),
                                                  request.headers.get("if-resource-match", ""),
                                                  request.headers.get("if-artifact-set-match"))
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Note-ETag"] = f'"{result["note_etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    @router.put("/{collection}/{relative:path}/blocksuite/blobs/{blob_id}")
    async def put_blocksuite_blob(request: Request, response: Response, collection: str, relative: str,
                                  blob_id: str):
        require(request, "write")
        content_type = request.headers.get("content-type", "")
        if not content_type:
            raise HTTPException(status_code=415, detail="BlockSuite blob Content-Type is required")
        data = await _read_bounded_body(request, MAX_BLOCKSUITE_BLOB_BYTES)
        result = store.put_blocksuite_blob(collection, relative, blob_id, data, content_type,
                                           request.headers.get("if-match", ""),
                                           request.headers.get("if-artifact-set-match", ""))
        response.status_code = 201 if result.pop("created") else 200
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Note-ETag"] = f'"{result["note_etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return result

    @router.get("/{collection}/{relative:path}/blocksuite/blobs/{blob_id}", response_class=Response)
    def get_blocksuite_blob(request: Request, collection: str, relative: str, blob_id: str):
        require(request, "read")
        result = store.read_blocksuite_blob(collection, relative, blob_id)
        return Response(content=result["data"], media_type=result["content_type"], headers={
            "ETag": f'"{result["etag"]}"', "X-Note-ETag": f'"{result["note_etag"]}"',
            "X-Artifact-Set-ETag": f'"{result["artifact_set_etag"]}"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @router.post("")
    def create(request: Request, response: Response, body: dict):
        require(request, "create")
        result = store.create(body.get("content"))
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
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

    @router.get("/{collection}/{relative:path}/properties")
    def read_properties(request: Request, response: Response, collection: str, relative: str):
        require(request, "read")
        result = store.read(collection, relative)
        note_type, tags = _note_properties(result["content"])
        response.headers["ETag"] = f'"{result["etag"]}"'
        return {"type": note_type or "", "tags": tags, "etag": result["etag"]}

    @router.get("/{collection}/{relative:path}")
    def read(request: Request, response: Response, collection: str, relative: str):
        require(request, "read")
        result = store.read(collection, relative)
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    @router.put("/{collection}/{relative:path}/properties")
    def update_properties(request: Request, response: Response, collection: str, relative: str, body: dict):
        require(request, "write")
        if vocabulary_store is None:
            raise HTTPException(status_code=503, detail="Vocabulary is not configured")
        if body.get("confirmed") is not True:
            raise HTTPException(status_code=400, detail="Explicit property confirmation is required")
        note_type = body.get("type")
        tags = body.get("tags")
        if not isinstance(note_type, str) or not isinstance(tags, list) or len(tags) > 30:
            raise HTTPException(status_code=422, detail="Type and tags are invalid")
        if any(not isinstance(tag, str) for tag in tags) or len(set(tags)) != len(tags):
            raise HTTPException(status_code=422, detail="Tags must be unique strings")
        catalog = vocabulary_store.read()
        active_types = {item["name"] for item in catalog["types"] if item["enabled"]}
        active_tags = {item["name"] for item in catalog["tags"] if item["enabled"]}
        current_type, current_tags = _note_properties(store.read(collection, relative)["content"])
        if ((note_type not in active_types and note_type != current_type)
                or any(tag not in active_tags and tag not in current_tags for tag in tags)):
            raise HTTPException(status_code=409, detail="Properties must use active Core vocabulary values")
        result = store.update_properties(collection, relative, note_type, tags,
                                         request.headers.get("if-match", ""))
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    @router.put("/{collection}/{relative:path}")
    def update(request: Request, response: Response, collection: str, relative: str, body: dict):
        require(request, "write")
        result = store.update(collection, relative, body.get("content"), request.headers.get("if-match", ""),
                              expected_artifacts=request.headers.get("if-artifact-set-match"))
        response.headers["ETag"] = f'"{result["etag"]}"'
        response.headers["X-Artifact-Set-ETag"] = f'"{result["artifact_set_etag"]}"'
        return result

    return router
