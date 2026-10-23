"""Browser-facing App auth, Home aggregation, and Hermes BFF routes."""
import hashlib
import asyncio
import json
import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .app_auth import AppSessionAuth
from .hermes_api import HermesAPI
from .run_approvals import RunApprovalRegistry
from .chat_knowledge import RECALL_TIMEOUT_SECONDS, recall_query


_HOME_SCAN_ENTRY_LIMIT = 500
_HOME_SCAN_DEPTH_LIMIT = 4
_HOME_FILE_LIMIT = 50
_HOME_FILE_BYTES_LIMIT = 256 * 1024


def _read_bounded_review(root, relative):
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise OSError("invalid Review path")
    directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                           | getattr(os, "O_NOFOLLOW", 0))
    try:
        current_fd = directory_fd
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                              | getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd)
            if current_fd != directory_fd:
                os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise OSError("Review item is not a regular file")
            chunks = []
            remaining = _HOME_FILE_BYTES_LIMIT + 1
            while remaining:
                chunk = os.read(file_fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) > _HOME_FILE_BYTES_LIMIT:
                raise OSError("Review item exceeds Home read limit")
            return payload
        finally:
            os.close(file_fd)
    finally:
        if current_fd != directory_fd:
            os.close(current_fd)
        os.close(directory_fd)


def _bounded_markdown_paths(root, *, max_entries=_HOME_SCAN_ENTRY_LIMIT,
                            max_depth=_HOME_SCAN_DEPTH_LIMIT, max_files=_HOME_FILE_LIMIT):
    """Return a bounded, no-symlink traversal of Markdown paths and truncation state."""
    root = Path(root)
    try:
        if not root.is_dir() or root.is_symlink():
            return [], False
    except OSError:
        return [], False
    pending = [(root, 0)]
    paths = []
    visited = 0
    truncated = False
    while pending:
        current, depth = pending.pop(0)
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if visited >= max_entries:
                        truncated = True
                        break
                    visited += 1
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if depth < max_depth:
                                pending.append((Path(entry.path), depth + 1))
                            else:
                                truncated = True
                            continue
                        if (entry.is_file(follow_symlinks=False)
                                and Path(entry.name).suffix.lower() == ".md"):
                            if len(paths) >= max_files:
                                truncated = True
                                break
                            paths.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            truncated = True
        if truncated:
            break
    return paths, truncated


def _trusted_directory_available(root):
    try:
        return Path(root).is_dir() and not Path(root).is_symlink()
    except OSError:
        return False


def _review_items(review_root, service):
    root = Path(review_root)
    items = []
    paths, truncated = _bounded_markdown_paths(root)
    for absolute in paths:
        try:
            info = absolute.lstat()
            if info.st_size > _HOME_FILE_BYTES_LIMIT:
                truncated = True
                continue
            relative = absolute.relative_to(root).as_posix()
            content = _read_bounded_review(str(root), relative)
            decoded = content.decode("utf-8", errors="replace")
            title = next((line[2:].strip() for line in decoded.splitlines() if line.startswith("# ")), absolute.stem)
            digest = hashlib.sha256(content).hexdigest()
            decision = service.get_decision(relative, digest)
            items.append({"review_path": relative, "review_sha256": digest,
                          "target_filename": absolute.name, "title": title,
                          "status": (decision or {}).get("status") or "pending",
                          "decision": decision,
                          "updated": info.st_mtime})
        except (OSError, ValueError):
            truncated = True
            continue
    return items, truncated


def _knowledge_items(knowledge_root, limit=8):
    root = Path(knowledge_root)
    items = []
    paths, truncated = _bounded_markdown_paths(root)
    for path in paths:
        fd = None
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _HOME_FILE_BYTES_LIMIT:
                truncated = True
                continue
            with os.fdopen(fd, "r", encoding="utf-8", errors="replace", closefd=False) as stream:
                title = next((line[2:].strip() for line in stream
                              if line.startswith("# ") and len(line) <= 4096), path.stem)
            items.append({"title": title, "status": "active", "updated": info.st_mtime})
        except OSError:
            truncated = True
            continue
        finally:
            if fd is not None:
                os.close(fd)
    return sorted(items, key=lambda row: row["updated"], reverse=True)[:limit], truncated


def create_web_app_router(auth: AppSessionAuth, hermes: HermesAPI, service, review_root, knowledge_root,
                          organizer=None, personal_learning=None, knowledge_store=None,
                          citation_store=None, chat_cost_gate=None):
    router = APIRouter(prefix="/api")
    run_approvals = RunApprovalRegistry()
    citation_fallback = {}

    @router.post("/auth/login")
    def login(request: Request, response: Response, body: dict):
        token = auth.login(request, body.get("password"))
        auth.set_cookie(response, request, token, auth.session_ttl)
        return {"status": "authenticated", "expires_in": auth.session_ttl, "subject": "owner"}

    @router.get("/auth/session")
    def session(request: Request):
        auth.require_action(request, "auth.session")
        return {"status": "authenticated", "subject": "owner"}

    @router.patch("/auth/session/actions")
    def set_session_action(request: Request, body: dict):
        auth.require_action(request, "auth.session")
        if not isinstance(body, dict) or set(body) != {"action", "granted"}:
            raise HTTPException(status_code=400, detail="Invalid session action request")
        granted = auth.set_session_action(request, body["action"], body["granted"])
        return {"status": "updated", "action": body["action"], "granted": granted,
                "scope": "current_session"}

    @router.post("/auth/logout")
    def logout(request: Request, response: Response):
        auth.require_action(request, "auth.logout")
        auth.logout(request)
        auth.clear_cookie(response, request)
        return {"status": "logged_out"}

    @router.get("/home")
    async def home(request: Request):
        auth.require_action(request, "home.read")
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        all_reviews, reviews_truncated = _review_items(review_root, service)
        pending = [item for item in all_reviews if item["status"] in {"pending", "failed"}]
        knowledge, knowledge_truncated = _knowledge_items(knowledge_root)
        review_available = _trusted_directory_available(review_root)
        knowledge_available = _trusted_directory_available(knowledge_root)
        try:
            if not getattr(hermes, "configured", False):
                raise HTTPException(status_code=503, detail="Hermes is not configured")
            await hermes.capabilities()
            agent_status = "online"
        except HTTPException:
            agent_status = "unavailable" if getattr(hermes, "configured", False) else "not_configured"
        home_items = pending[:50]
        review_status = ("unavailable" if not review_available else
                         "partial" if reviews_truncated else ("real" if home_items else "empty"))
        knowledge_status = ("unavailable" if not knowledge_available else
                            "partial" if knowledge_truncated else ("real" if knowledge else "empty"))
        return {
            "status": "ok",
            "review": {"status": review_status, "items": home_items,
                       "pending_count": len(home_items),
                       "source": "configured-review-root" if review_available else None,
                       "freshness": {"checked_at": checked_at}},
            "knowledge": {"status": knowledge_status, "items": knowledge,
                          "source": "configured-knowledge-root" if knowledge_available else None,
                          "freshness": {"checked_at": checked_at}},
            "projects": {"status": "not_configured", "items": [], "source": None,
                         "freshness": {"checked_at": checked_at}},
            "today": {"status": "not_configured", "items": [], "source": None,
                      "freshness": {"checked_at": checked_at}},
            "agent": {"status": agent_status, "items": [], "source": "hermes-runtime",
                      "freshness": {"checked_at": checked_at}},
        }

    @router.get("/chat/capabilities")
    async def chat_capabilities(request: Request):
        auth.require_action(request, "chat.read")
        return await hermes.capabilities()

    @router.get("/chat/sessions")
    async def sessions(request: Request, limit: int = 50, offset: int = 0):
        auth.require_action(request, "chat.read")
        if limit < 1 or limit > 100 or offset < 0:
            raise HTTPException(status_code=400, detail="Invalid pagination")
        result = await hermes.list_sessions(limit, offset)
        if organizer:
            # The App-visible, paginated session set defines the Organizer source scope.
            # Existing history is baselined, never replayed as newly captured content.
            for row in result["sessions"]:
                session_id = row.get("session_id", "")
                if not session_id:
                    continue
                try:
                    await organizer.baseline_session(hermes._safe_id(session_id), row)
                except HTTPException:
                    # Keep Chat usable during a concurrently deleted/unavailable session;
                    # opening it later will retry baseline admission.
                    continue
        return result

    @router.post("/chat/sessions")
    async def create_session(request: Request, body: Optional[dict] = None):
        auth.require_action(request, "chat.write")
        created = await hermes.create_session(body or {})
        if organizer:
            organizer.state.register_session(created["session_id"], baseline_count=0)
        return created

    @router.get("/chat/sessions/{session_id}")
    async def get_session(request: Request, session_id: str):
        auth.require_action(request, "chat.read")
        return await hermes.get_session(session_id)

    @router.get("/chat/sessions/{session_id}/messages")
    async def messages(request: Request, session_id: str):
        auth.require_action(request, "chat.read")
        if organizer:
            await organizer.baseline_session(hermes._safe_id(session_id))
        return await hermes.get_messages(session_id)

    @router.post("/chat/sessions/{session_id}/fork")
    async def fork_session(request: Request, session_id: str, body: Optional[dict] = None):
        auth.require_action(request, "chat.write")
        forked = await hermes.fork_session(session_id, body or {})
        if organizer:
            await organizer.baseline_session(forked["session_id"])
        return forked

    @router.patch("/chat/sessions/{session_id}")
    async def patch_session(request: Request, session_id: str, body: dict):
        auth.require_action(request, "chat.manage")
        return await hermes.patch_session(session_id, body)

    @router.delete("/chat/sessions/{session_id}")
    async def delete_session(request: Request, session_id: str):
        auth.require_action(request, "chat.manage")
        result = await hermes.delete_session(session_id)
        if organizer:
            organizer.state.mark_session_deleted(hermes._safe_id(session_id))
        return result

    @router.post("/chat/sessions/{session_id}/runs")
    async def start_run(request: Request, session_id: str, body: dict):
        owner = auth.require_action(request, "chat.run")
        text = body.get("input")
        if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
            raise HTTPException(status_code=400, detail="Message must contain 1-100000 characters")
        key = request.headers.get("idempotency-key", "")
        if not key or len(key) > 255 or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        if organizer:
            await organizer.baseline_session(hermes._safe_id(session_id))
        safe_session_id = hermes._safe_id(session_id)
        run_body = {"input": text, "session_id": safe_session_id}
        recall = {"items": [], "status": "unavailable"}
        recall_auth = True
        try:
            # Check read permission before any Knowledge filesystem operation.
            auth.require_action(request, "knowledge.read")
        except HTTPException:
            recall_auth = False
        if recall_auth and knowledge_store is not None and citation_store is not None:
            query = recall_query(text)
            if query:
                try:
                    recall = await asyncio.wait_for(
                        asyncio.to_thread(knowledge_store.chat_recall, query),
                        timeout=RECALL_TIMEOUT_SECONDS)
                except (asyncio.TimeoutError, HTTPException, OSError, ValueError):
                    recall = {"items": [], "status": "unavailable"}
        watermark = None
        if personal_learning:
            try:
                # Learning is optional: if the pre-Run history read fails, allow
                # Chat to proceed but do not learn without a source watermark.
                watermark = await personal_learning.capture_message_watermark(safe_session_id, hermes)
            except Exception:
                watermark = None
            instructions = personal_learning.instructions_for(text)
        else:
            instructions = ""
        if instructions:
            # Personal Learning's existing gated behavior is unchanged. Knowledge
            # excerpts are never sent through Hermes' system-level instructions.
            run_body["instructions"] = instructions
        cost_reservation = None
        if chat_cost_gate is not None:
            # The live Hermes contract must attest enforcement before any
            # reservation or paid Run is admitted. Missing/unknown capability
            # fails closed; legacy behavior remains unchanged while disabled.
            capabilities = await hermes.capabilities()
            chat_cost_gate.require_hermes_envelope(capabilities)
            run_body = chat_cost_gate.bind_envelope(run_body)
            cost_reservation = chat_cost_gate.reserve(
                owner=owner, session_id=safe_session_id, idempotency_key=key,
                run_body=run_body, request_class="passive",
            )
            chat_cost_gate.require_replay_window(cost_reservation)
        try:
            result = await hermes.start_run(run_body, key)
        except asyncio.CancelledError:
            if chat_cost_gate is not None and cost_reservation is not None:
                chat_cost_gate.mark_reservation_unknown(cost_reservation["reservation_id"])
            raise
        except Exception:
            if chat_cost_gate is not None and cost_reservation is not None:
                chat_cost_gate.mark_reservation_unknown(cost_reservation["reservation_id"])
            # A failed transport may have reached Hermes; keep the reservation
            # and never auto-retry. An explicit identical idempotency replay is
            # the only path that can reconcile a run at Hermes.
            raise
        if chat_cost_gate is not None and cost_reservation is not None:
            chat_cost_gate.attach_run(cost_reservation["reservation_id"], result["run_id"])
        run_approvals.register_run(hermes._safe_id(result["run_id"]), safe_session_id, owner)
        if citation_store is not None:
            try:
                bound = citation_store.bind(hermes._safe_id(result["run_id"]), safe_session_id, text, recall)
                if bound is None:
                    citation_fallback[result["run_id"]] = safe_session_id
                else:
                    citation_fallback.pop(result["run_id"], None)
            except Exception:
                # Citations are a best-effort read-only enhancement. A failed
                # ledger write never turns a successful Hermes Run into a false
                # HTTP failure; no client-supplied citation is ever substituted.
                citation_fallback[result["run_id"]] = safe_session_id
            while len(citation_fallback) > 1000:
                citation_fallback.pop(next(iter(citation_fallback)))
        if personal_learning:
            personal_learning.register_run(result["run_id"], safe_session_id, text, watermark)
        return result

    @router.get("/chat/runs/{run_id}/events")
    async def run_events(request: Request, run_id: str):
        owner = auth.require_action(request, "chat.read")
        # Chat history remains readable after Knowledge access is revoked, but
        # the citation ledger and source verifier must not be consulted then.
        try:
            auth.require_action(request, "knowledge.read")
            knowledge_read_allowed = True
        except HTTPException:
            knowledge_read_allowed = False
        safe_run_id = hermes._safe_id(run_id)
        try:
            chunks = await hermes.stream_run(run_id)
        except Exception:
            if chat_cost_gate is not None:
                chat_cost_gate.mark_unknown(safe_run_id)
            raise

        async def events():
            cost_terminal_seen = False
            if citation_store is not None:
                registered_session = run_approvals.session_for_run(safe_run_id, owner)
                current_knowledge_access = knowledge_read_allowed
                if current_knowledge_access:
                    # Recheck at the point of citation access as stream setup
                    # may yield while a grant is being revoked.
                    try:
                        auth.require_action(request, "knowledge.read")
                    except HTTPException:
                        current_knowledge_access = False
                if not current_knowledge_access and registered_session:
                    # Preserve the ordinary Chat stream while returning no
                    # previously authorized Knowledge metadata after revocation.
                    citation_event = {"event": "knowledge.citations", "version": 1,
                                      "run_id": safe_run_id, "session_id": registered_session,
                                      "status": "unavailable", "citations": []}
                elif citation_fallback.get(safe_run_id) == registered_session and registered_session:
                    citation_event = {"event": "knowledge.citations", "version": 1,
                                      "run_id": safe_run_id, "session_id": registered_session,
                                      "status": "unavailable", "citations": []}
                else:
                    try:
                        citation_event = await asyncio.to_thread(citation_store.read_for_run, safe_run_id)
                    except Exception:
                        citation_event = None
                if (citation_event is not None and registered_session
                        and citation_event.get("session_id") == registered_session):
                    yield _sse_event_frame("knowledge.citations", citation_event)
            try:
                async for chunk in chunks:
                    outgoing = chunk
                    payload = _sse_payload(chunk)
                    if chat_cost_gate is not None and payload:
                        event_name = payload.get("event")
                        if event_name in {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}:
                            cost_terminal_seen = True
                            if event_name == "run.completed":
                                if not chat_cost_gate.settle_completed(safe_run_id, payload):
                                    chat_cost_gate.mark_unknown(safe_run_id)
                            else:
                                # Non-success terminals are never trusted usage
                                # receipts, even when they include token numbers.
                                chat_cost_gate.mark_unknown(safe_run_id)
                    if payload and payload.get("event") == "approval.request":
                        card = run_approvals.bind_event(safe_run_id, owner, payload)
                        if card:
                            outgoing = _sse_frame(card)
                        else:
                            request_id = payload.get("request_id")
                            if isinstance(request_id, str) and request_id:
                                try:
                                    await hermes.resolve_run_approval(safe_run_id, request_id, "deny")
                                except HTTPException:
                                    pass  # Native approval timeout is also fail-closed.
                            outgoing = _sse_frame({"event": "approval.blocked", "failure_code": "approval_event_invalid"})
                    if personal_learning and personal_learning.is_success_event(chunk):
                        try:
                            await personal_learning.complete_run(hermes._safe_id(run_id), hermes)
                        except Exception:
                            # Learning is best-effort and must not break a completed Chat run.
                            pass
                    elif personal_learning and personal_learning.is_discard_event(chunk):
                        personal_learning.discard_run(hermes._safe_id(run_id))
                    yield outgoing
            finally:
                if chat_cost_gate is not None:
                    chat_cost_gate.finish_stream(safe_run_id, cost_terminal_seen)

        return StreamingResponse(events(), media_type="text/event-stream", headers={
            "Cache-Control": "private, no-store, no-transform", "X-Accel-Buffering": "no",
        })

    @router.get("/chat/sessions/{session_id}/runs/{run_id}/knowledge-citations")
    async def knowledge_citations(request: Request, session_id: str, run_id: str, response: Response):
        auth.require_action(request, "chat.read")
        # Check current Knowledge permission before any session, ledger, or
        # source-version read. The app middleware adds no-store to errors too.
        auth.require_action(request, "knowledge.read")
        safe_session_id = hermes._safe_id(session_id)
        safe_run_id = hermes._safe_id(run_id)
        await hermes.get_session(safe_session_id)
        if citation_store is None:
            raise HTTPException(status_code=404, detail="Chat citations not found")
        if citation_fallback.get(safe_run_id) == safe_session_id:
            result = {"event": "knowledge.citations", "version": 1,
                      "run_id": safe_run_id, "session_id": safe_session_id,
                      "status": "unavailable", "citations": []}
        else:
            result = await asyncio.to_thread(citation_store.read_for_session, safe_session_id, safe_run_id)
        response.headers["Cache-Control"] = "private, no-store"
        return result

    @router.post("/chat/sessions/{session_id}/runs/{run_id}/approval")
    async def resolve_run_approval(request: Request, session_id: str, run_id: str, body: dict):
        owner = auth.require_action(request, "chat.approve_tool")
        safe_run_id = hermes._safe_id(run_id)
        safe_session_id = hermes._safe_id(session_id)
        approval_id = body.get("approval_id")
        digest = body.get("command_sha256")
        choice = body.get("choice")
        if not isinstance(approval_id, str) or not isinstance(digest, str):
            raise HTTPException(status_code=400, detail="Approval identifier and command digest are required")
        run_approvals.begin_resolution(run_id=safe_run_id, session_id=safe_session_id,
                                       request_id=hermes._safe_id(approval_id), owner=owner,
                                       digest=digest, choice=choice)
        try:
            result = await hermes.resolve_run_approval(safe_run_id, approval_id, choice)
        except Exception:
            run_approvals.finish_resolution(safe_run_id, approval_id, False)
            raise
        run_approvals.finish_resolution(safe_run_id, approval_id, True)
        return {"status": "resolved", "choice": choice,
                "resolved": result.get("resolved", 0) if isinstance(result, dict) else 0}

    @router.get("/chat/runs/{run_id}")
    async def get_run(request: Request, run_id: str):
        auth.require_action(request, "chat.read")
        safe_run_id = hermes._safe_id(run_id)
        result = await hermes.get_run(safe_run_id)
        if personal_learning and result.get("status") == "completed":
            try:
                await personal_learning.complete_run(safe_run_id, hermes)
            except Exception:
                # Learning failure never changes the upstream run status response.
                pass
        elif personal_learning and result.get("status") in {"failed", "cancelled", "canceled", "stopped"}:
            personal_learning.discard_run(safe_run_id)
        return result

    @router.post("/chat/runs/{run_id}/stop")
    async def stop_run(request: Request, run_id: str):
        auth.require_action(request, "chat.stop")
        safe_run_id = hermes._safe_id(run_id)
        for approval_id in run_approvals.cancel_pending(safe_run_id):
            try:
                await hermes.resolve_run_approval(safe_run_id, approval_id, "deny")
                run_approvals.finish_resolution(safe_run_id, approval_id, True)
            except HTTPException:
                run_approvals.finish_resolution(safe_run_id, approval_id, False)
        result = await hermes.stop_run(safe_run_id)
        if personal_learning:
            personal_learning.discard_run(safe_run_id)
        return result

    return router


def _sse_payload(chunk):
    try:
        raw = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        data = "\n".join(line[5:].lstrip() for line in raw.splitlines() if line.startswith("data:"))
        payload = json.loads(data)
        return payload if isinstance(payload, dict) else None
    except (UnicodeDecodeError, ValueError, TypeError):
        return None


def _sse_frame(payload):
    return ("data: " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n\n").encode("utf-8")


def _sse_event_frame(event_name, payload):
    return ("event: " + event_name + "\ndata: " +
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n\n").encode("utf-8")
