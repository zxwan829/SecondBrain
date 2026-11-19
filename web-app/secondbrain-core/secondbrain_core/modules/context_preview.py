"""Metadata-only, session-bound P2-1 context preview.

This endpoint is intentionally not a model-input adapter. Source text is used
only by existing trusted Core readers to verify relevance and provenance; only
bounded metadata is returned to the authenticated Web client.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Request, Response

from .knowledge_read import MAX_FILE_BYTES, MAX_TOTAL_BYTES

MAX_QUERY_CHARS = 200
MAX_CANDIDATE_INPUT_CHARS = 2_000
MAX_ITEMS_PER_SOURCE = 3
MAX_RESPONSE_BYTES = 8 * 1024
MAX_REQUEST_BYTES = 4 * 1024
MAX_CANDIDATE_REQUEST_BYTES = 16 * 1024
MAX_TOTAL_SECONDS = 0.75
MAX_GROUNDING_RESPONSE_BYTES = 8 * 1024
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_REQUIRED_ACTIONS = ("chat.run", "personal_memory.read", "knowledge.read")
_RECALL_STOP_WORDS = {"about", "after", "also", "and", "are", "can", "could", "for", "from",
                      "have", "help", "how", "into", "just", "please", "that", "the", "this",
                      "with", "would", "you", "your", "我", "的", "了", "是", "在", "这个", "一下"}


def _natural_query_terms(value: str) -> list[str]:
    terms = set()
    for part in re.findall(r"[A-Za-z0-9]+|[\u3400-\u9fff]+", value.casefold()):
        if "\u3400" <= part[0] <= "\u9fff":
            terms.update(part[index:index + 2] for index in range(max(1, len(part) - 1)))
        elif len(part) >= 3:
            terms.add(part[:MAX_QUERY_CHARS])
    return sorted(terms - _RECALL_STOP_WORDS, key=lambda term: (-len(term), term))[:3]


def _memory_items(store, query, *, natural=False):
    if store is None:
        return "unavailable", []
    try:
        if natural:
            rows = store.context_candidates_for_input(user_input=query, limit=MAX_ITEMS_PER_SOURCE)
        else:
            rows = store.context_candidates(query=query, limit=MAX_ITEMS_PER_SOURCE)
    except Exception:
        return "unavailable", []
    return ("available" if rows else "none"), [
        {"source_kind": "personal_memory", **row,
         "verification_status": "source_version_verified"}
        for row in rows
    ]


def _knowledge_items(store, query, *, natural=False):
    if store is None:
        return "unavailable", []
    try:
        terms = _natural_query_terms(query) if natural else [query]
        if not terms:
            return "none", []
        result_items = []
        result_status = "none"
        per_scan_budget = max(1, (MAX_TOTAL_BYTES - MAX_ITEMS_PER_SOURCE * 3 * MAX_FILE_BYTES) // len(terms))
        for term in terms:
            result = store.chat_recall(
                term, max_items=MAX_ITEMS_PER_SOURCE,
                max_item_bytes=8 * 1024, max_total_bytes=16 * 1024,
                max_scan_bytes=per_scan_budget,
            )
            if not isinstance(result, dict) or not isinstance(result.get("items"), list):
                return "unavailable", []
            if result.get("status") not in {"available", "partial", "none"}:
                return "unavailable", []
            if result["status"] == "partial":
                result_status = "partial"
            result_items.extend(result["items"])
            if len(result_items) >= MAX_ITEMS_PER_SOURCE:
                break
    except Exception:
        return "unavailable", []
    rows = []
    rejected = False
    for item in result_items[:MAX_ITEMS_PER_SOURCE]:
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
    if result_status == "partial" or rejected:
        return "partial", rows
    return ("available" if rows else "none"), rows


def create_context_preview_router(auth, hermes, memory_store, knowledge_store):
    router = APIRouter(prefix="/api/chat/sessions", tags=["chat-context"])

    async def read_query(request: Request, *, field: str, max_bytes: int, max_chars: int, label: str):
        raw = bytearray()
        try:
            async for chunk in request.stream():
                if len(raw) + len(chunk) > max_bytes:
                    raise HTTPException(status_code=400, detail=f"Invalid {label} request")
                raw.extend(chunk)
            body = json.loads(raw.decode("utf-8"))
        except HTTPException:
            raise
        except (UnicodeDecodeError, JSONDecodeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid {label} request") from exc
        if not isinstance(body, dict) or set(body) != {field}:
            raise HTTPException(status_code=400, detail=f"Invalid {label} request")
        query_value = body.get(field)
        query = query_value.strip() if isinstance(query_value, str) else ""
        if not query or len(query) > max_chars:
            raise HTTPException(status_code=400, detail=f"Invalid {label} input")
        return query

    async def build_candidates(session_id: str, request: Request, query: str, *, natural=False):
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
        jobs = [asyncio.to_thread(_memory_items, memory_store, query, natural=natural),
                asyncio.to_thread(_knowledge_items, knowledge_store, query, natural=natural)]
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

    @router.post("/{session_id}/context-preview")
    async def context_preview(session_id: str, request: Request):
        query = await read_query(request, field="query", max_bytes=MAX_REQUEST_BYTES,
                                 max_chars=MAX_QUERY_CHARS, label="context")
        return await build_candidates(session_id, request, query)

    @router.post("/{session_id}/context-candidates")
    async def context_candidates(session_id: str, request: Request):
        user_input = await read_query(request, field="input", max_bytes=MAX_CANDIDATE_REQUEST_BYTES,
                                      max_chars=MAX_CANDIDATE_INPUT_CHARS, label="candidate")
        # This is a read-only metadata selector for ordinary turns. It deliberately
        # does not modify the Hermes Run request or persist/cache source material.
        return await build_candidates(session_id, request, user_input, natural=True)

    @router.post("/{session_id}/grounding-candidates")
    async def grounding_candidates(session_id: str, request: Request, response: Response):
        """Return verified source metadata without asserting model grounding.

        Knowledge excerpts are processed only inside the trusted Core reader;
        this route never changes or starts a Hermes Run and never returns text.
        """
        if not _SESSION_ID.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="Invalid session identifier")
        # Permissions precede session and Knowledge IO.
        auth.require_action(request, "chat.run")
        auth.require_action(request, "knowledge.read")
        query = await read_query(request, field="query", max_bytes=MAX_CANDIDATE_REQUEST_BYTES,
                                 max_chars=MAX_CANDIDATE_INPUT_CHARS, label="grounding")
        response.headers["Cache-Control"] = "private, no-store"
        deadline = time.monotonic() + MAX_TOTAL_SECONDS
        try:
            session = await asyncio.wait_for(
                hermes.get_session(session_id), timeout=max(0.001, deadline - time.monotonic()))
        except Exception as exc:
            if isinstance(exc, HTTPException) and exc.status_code == 404:
                raise HTTPException(status_code=404, detail="Chat session not found") from exc
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable") from exc
        if not isinstance(session, dict) or session.get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="Chat session not found")
        # A revocation during the upstream lookup must stop before source IO.
        auth.require_action(request, "chat.run")
        auth.require_action(request, "knowledge.read")
        if knowledge_store is None:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable")

        def read_candidates():
            result = knowledge_store.chat_recall(
                query, max_items=MAX_ITEMS_PER_SOURCE, max_item_bytes=8 * 1024,
                max_total_bytes=16 * 1024, max_scan_bytes=MAX_TOTAL_BYTES,
            )
            if (not isinstance(result, dict) or not isinstance(result.get("items"), list)
                    or result.get("status") not in {"available", "partial", "none"}):
                raise ValueError("invalid bounded Knowledge result")
            rows = []
            partial = result.get("status") == "partial"
            seen = set()
            for item in result["items"][:MAX_ITEMS_PER_SOURCE]:
                if (not isinstance(item, dict) or item.get("provenance_status") != "verified"
                        or not isinstance(item.get("relative_path"), str)
                        or not isinstance(item.get("title"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
                        or not isinstance(item.get("content"), str)):
                    partial = True
                    continue
                path = item["relative_path"]
                digest = item["sha256"]
                if path in seen:
                    continue
                seen.add(path)
                if knowledge_store.verify_chat_reference(path, digest) != "version_verified":
                    partial = True
                    continue
                rows.append(({
                    "citation_id": secrets.token_urlsafe(18),
                    "title": "".join(char for char in item["title"][:200]
                                     if char >= " " and char not in {"\u007f", "\u2028", "\u2029"}),
                    "sha256": digest,
                    "knowledge_status": "version_verified",
                    "provenance_status": "verified",
                }, path, digest))
            return rows, partial

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable")
        try:
            rows, partial = await asyncio.wait_for(asyncio.to_thread(read_candidates), timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable") from exc
        # Recheck authorization and source versions at the response boundary;
        # the first version check alone leaves a drift window during candidate assembly.
        auth.require_action(request, "chat.run")
        auth.require_action(request, "knowledge.read")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable")
        def recheck_versions():
            current = []
            stale = False
            for row, path, digest in rows:
                if knowledge_store.verify_chat_reference(path, digest) == "version_verified":
                    current.append((row, path, digest))
                else:
                    stale = True
            return current, stale
        try:
            current_rows, stale = await asyncio.wait_for(asyncio.to_thread(recheck_versions), timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Grounding candidates unavailable") from exc
        partial = partial or stale
        auth.require_action(request, "chat.run")
        auth.require_action(request, "knowledge.read")
        items = [row for row, _path, _digest in current_rows]
        status = ("partial" if partial else "needs_review" if len(items) > 1
                  else "available" if items else "none")
        payload = {"event": "knowledge.grounding-candidates", "version": 1,
                   "session_id": session_id, "status": status,
                   "answer_attribution": "not_established", "items": items}
        if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_GROUNDING_RESPONSE_BYTES:
            payload.update(status="partial", items=[])
        return payload

    return router
