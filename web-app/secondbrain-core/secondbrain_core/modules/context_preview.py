"""Metadata-only, session-bound P2-1 context preview.

This endpoint is intentionally not a model-input adapter. Source text is used
only by existing trusted Core readers to verify relevance and provenance; only
bounded metadata is returned to the authenticated Web client.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Request

from .knowledge_read import MAX_FILE_BYTES, MAX_TOTAL_BYTES

MAX_QUERY_CHARS = 200
MAX_ITEMS_PER_SOURCE = 3
MAX_RESPONSE_BYTES = 8 * 1024
MAX_REQUEST_BYTES = 4 * 1024
MAX_TOTAL_SECONDS = 0.75
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_REQUIRED_ACTIONS = ("chat.run", "personal_memory.read", "knowledge.read")


def _memory_items(store, query):
    if store is None:
        return "unavailable", []
    try:
        rows = store.context_candidates(query=query, limit=MAX_ITEMS_PER_SOURCE)
    except Exception:
        return "unavailable", []
    return ("available" if rows else "none"), [
        {"source_kind": "personal_memory", **row,
         "verification_status": "source_version_verified"}
        for row in rows
    ]


def _knowledge_items(store, query):
    if store is None:
        return "unavailable", []
    try:
        result = store.chat_recall(
            query, max_items=MAX_ITEMS_PER_SOURCE,
            max_item_bytes=8 * 1024, max_total_bytes=16 * 1024,
            max_scan_bytes=MAX_TOTAL_BYTES - MAX_ITEMS_PER_SOURCE * 3 * MAX_FILE_BYTES,
        )
    except Exception:
        return "unavailable", []
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        return "unavailable", []
    rows = []
    rejected = False
    for item in result["items"][:MAX_ITEMS_PER_SOURCE]:
        if (not isinstance(item, dict) or item.get("provenance_status") != "verified"
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
                or not isinstance(item.get("relative_path"), str)
                or not isinstance(item.get("updated"), str)):
            rejected = True
            continue
        try:
            updated = datetime.fromisoformat(item["updated"].replace("Z", "+00:00"))
            if updated.tzinfo is None:
                raise ValueError
            source_timestamp = updated.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (ValueError, AttributeError):
            rejected = True
            continue
        relative = item["relative_path"]
        parts = relative.split("/")
        if (relative.startswith("/") or "\\" in relative or "\x00" in relative
                or any(part in {"", ".", ".."} or part.casefold() == "private" for part in parts)):
            rejected = True
            continue
        digest = item["sha256"]
        try:
            if store.verify_chat_reference(relative, digest) != "version_verified":
                rejected = True
                continue
        except Exception:
            rejected = True
            continue
        try:
            source_id = store.context_source_id(relative, digest)
        except Exception:
            rejected = True
            continue
        rows.append({
            "source_kind": "knowledge",
            "source_id": source_id,
            "source_version": digest,
            "sha256": digest,
            "source_timestamp": source_timestamp,
            "fact_kind": None,
            "verification_status": "verified",
            "state": "available",
            "expires_at": None,
        })
    status = result.get("status")
    if status not in {"available", "partial", "none"}:
        return "unavailable", []
    if status == "partial" or rejected:
        return "partial", rows
    return ("available" if rows else "none"), rows


def create_context_preview_router(auth, hermes, memory_store, knowledge_store):
    router = APIRouter(prefix="/api/chat/sessions", tags=["chat-context"])

    @router.post("/{session_id}/context-preview")
    async def context_preview(session_id: str, request: Request):
        raw = bytearray()
        try:
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
                    raise HTTPException(status_code=400, detail="Invalid context request")
                raw.extend(chunk)
            body = json.loads(raw.decode("utf-8"))
        except HTTPException:
            raise
        except (UnicodeDecodeError, JSONDecodeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid context request") from exc
        if not isinstance(body, dict) or set(body) != {"query"}:
            raise HTTPException(status_code=400, detail="Invalid context request")
        query_value = body.get("query")
        query = query_value.strip() if isinstance(query_value, str) else ""
        if not query or len(query) > MAX_QUERY_CHARS:
            raise HTTPException(status_code=400, detail="Invalid context query")
        if not _SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session identifier")

        # Authorization must precede both Hermes session lookup and all source IO.
        for action in _REQUIRED_ACTIONS:
            auth.require_action(request, action)

        deadline = time.monotonic() + MAX_TOTAL_SECONDS
        try:
            session = await asyncio.wait_for(hermes.get_session(session_id),
                                             timeout=max(0.001, deadline - time.monotonic()))
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=503, detail="Context preview unavailable") from exc
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(status_code=404, detail="Chat session not found") from exc
            raise HTTPException(status_code=503, detail="Context preview unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Context preview unavailable") from exc
        if not isinstance(session, dict) or session.get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="Chat session not found")

        # Recheck after the upstream lookup so a logout/revocation during that
        # wait cannot start source reads under stale authorization.
        for action in _REQUIRED_ACTIONS:
            auth.require_action(request, action)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(status_code=503, detail="Context preview unavailable")
        jobs = [asyncio.to_thread(_memory_items, memory_store, query),
                asyncio.to_thread(_knowledge_items, knowledge_store, query)]
        try:
            memory_result, knowledge_result = await asyncio.wait_for(
                asyncio.gather(*jobs), timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=503, detail="Context preview unavailable") from exc

        # Never return candidates if the owner session was revoked while the
        # bounded source checks were running.
        for action in _REQUIRED_ACTIONS:
            auth.require_action(request, action)

        source_status = {
            "personal_memory": memory_result[0],
            "knowledge": knowledge_result[0],
        }
        items = memory_result[1] + knowledge_result[1]
        seen = set()
        unique = []
        for item in items:
            identity = (item["source_kind"], item["source_id"], item["source_version"])
            if identity not in seen:
                seen.add(identity)
                unique.append(item)
        unique.sort(key=lambda item: item["source_id"])
        unique.sort(key=lambda item: item["source_timestamp"], reverse=True)
        items = unique[:MAX_ITEMS_PER_SOURCE * 2]
        unavailable = sum(value == "unavailable" for value in source_status.values())
        partial = any(value in {"partial", "unavailable"} for value in source_status.values())
        status = ("unavailable" if unavailable == 2 else
                  "partial" if partial else "available" if items else "none")
        response = {
            "schema_version": "context.v1",
            "request_id": str(uuid.uuid4()),
            "session_id": session_id,
            "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": status,
            "source_status": source_status,
            "items": items,
        }
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_RESPONSE_BYTES:
            response["status"] = "partial"
            response["source_status"] = {key: "partial" for key in source_status}
            response["items"] = []
        if response["status"] == "unavailable":
            raise HTTPException(status_code=503, detail="Context preview unavailable")
        return response

    return router
