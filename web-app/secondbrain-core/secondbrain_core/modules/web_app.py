"""Browser-facing App auth, Home aggregation, and Hermes BFF routes."""
import hashlib
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .app_auth import AppSessionAuth
from .hermes_api import HermesAPI
from .review_promote.approval import _read_review


def _review_items(review_root, service):
    root = Path(review_root)
    items = []
    if not root.is_dir() or root.is_symlink():
        return items
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not Path(current, name).is_symlink())
        for name in sorted(files):
            absolute = Path(current, name)
            if absolute.suffix.lower() != ".md" or absolute.is_symlink():
                continue
            relative = absolute.relative_to(root).as_posix()
            try:
                content = _read_review(str(root), relative)
            except Exception:
                continue
            decoded = content.decode("utf-8", errors="replace")
            title = next((line[2:].strip() for line in decoded.splitlines() if line.startswith("# ")), absolute.stem)
            digest = hashlib.sha256(content).hexdigest()
            decision = service.get_decision(relative, digest)
            items.append({"review_path": relative, "review_sha256": digest,
                          "target_filename": name, "title": title,
                          "status": (decision or {}).get("status") or "pending",
                          "decision": decision,
                          "updated": absolute.lstat().st_mtime})
    return items


def _knowledge_items(knowledge_root, limit=8):
    root = Path(knowledge_root)
    items = []
    if not root.is_dir() or root.is_symlink():
        return items
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not Path(current, name).is_symlink()]
        for name in files:
            path = Path(current, name)
            if path.suffix.lower() != ".md" or path.is_symlink():
                continue
            try:
                stat = path.stat(follow_symlinks=False)
                with path.open("r", encoding="utf-8", errors="replace") as stream:
                    title = next((line[2:].strip() for line in stream if line.startswith("# ")), path.stem)
                items.append({"title": title, "status": "active", "updated": stat.st_mtime})
            except OSError:
                continue
    return sorted(items, key=lambda row: row["updated"], reverse=True)[:limit]


def create_web_app_router(auth: AppSessionAuth, hermes: HermesAPI, service, review_root, knowledge_root,
                          organizer=None, personal_learning=None):
    router = APIRouter(prefix="/api")

    @router.post("/auth/login")
    def login(request: Request, response: Response, body: dict):
        token = auth.login(request, body.get("password"))
        auth.set_cookie(response, request, token, auth.session_ttl)
        return {"status": "authenticated", "expires_in": auth.session_ttl, "subject": "owner"}

    @router.get("/auth/session")
    def session(request: Request):
        auth.require_action(request, "auth.session")
        return {"status": "authenticated", "subject": "owner"}

    @router.post("/auth/logout")
    def logout(request: Request, response: Response):
        auth.require_action(request, "auth.logout")
        auth.logout(request)
        auth.clear_cookie(response, request)
        return {"status": "logged_out"}

    @router.get("/home")
    async def home(request: Request):
        auth.require_action(request, "home.read")
        all_reviews = _review_items(review_root, service)
        pending = [item for item in all_reviews if item["status"] in {"pending", "failed"}]
        knowledge = _knowledge_items(knowledge_root)
        try:
            await hermes.capabilities()
            agent = {"status": "online", "source": "hermes-runtime"}
        except HTTPException:
            agent = {"status": "unavailable", "source": "unavailable"}
        home_items = pending[:50]
        return {
            "status": "ok",
            "review": {"status": "real" if home_items else "empty", "items": home_items, "pending_count": len(home_items)},
            "knowledge": {"status": "real" if knowledge else "empty", "items": knowledge},
            "projects": {"status": "unavailable", "items": []},
            "today": None,
            "agent": agent,
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
        auth.require_action(request, "chat.run")
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
        watermark = None
        if personal_learning:
            try:
                # Learning is optional: if the pre-Run history read fails, allow
                # Chat to proceed but do not learn without a source watermark.
                watermark = await personal_learning.capture_message_watermark(safe_session_id, hermes)
            except Exception:
                watermark = None
            instructions = personal_learning.instructions_for(text)
            if instructions:
                # Hermes v0.21.5 /v1/runs accepts `instructions` as an
                # ephemeral system prompt; user input remains byte-for-byte intact.
                run_body["instructions"] = instructions
        result = await hermes.start_run(run_body, key)
        if personal_learning:
            personal_learning.register_run(result["run_id"], safe_session_id, text, watermark)
        return result

    @router.get("/chat/runs/{run_id}/events")
    async def run_events(request: Request, run_id: str):
        auth.require_action(request, "chat.read")
        chunks = await hermes.stream_run(run_id)

        async def events():
            async for chunk in chunks:
                if personal_learning and personal_learning.is_success_event(chunk):
                    try:
                        await personal_learning.complete_run(hermes._safe_id(run_id), hermes)
                    except Exception:
                        # Learning is best-effort and must not break a completed Chat run.
                        pass
                elif personal_learning and personal_learning.is_discard_event(chunk):
                    personal_learning.discard_run(hermes._safe_id(run_id))
                yield chunk

        return StreamingResponse(events(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
        })

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
        elif personal_learning and result.get("status") in {
            "failed", "cancelled", "canceled", "stopped", "interrupted",
        }:
            personal_learning.discard_run(safe_run_id)
        return result

    @router.post("/chat/runs/{run_id}/stop")
    async def stop_run(request: Request, run_id: str):
        auth.require_action(request, "chat.stop")
        safe_run_id = hermes._safe_id(run_id)
        result = await hermes.stop_run(safe_run_id)
        if personal_learning:
            personal_learning.discard_run(safe_run_id)
        return result

    return router
