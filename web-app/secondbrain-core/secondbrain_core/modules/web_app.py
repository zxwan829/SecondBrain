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


def create_web_app_router(auth: AppSessionAuth, hermes: HermesAPI, service, review_root, knowledge_root):
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
        return await hermes.list_sessions(limit, offset)

    @router.post("/chat/sessions")
    async def create_session(request: Request, body: Optional[dict] = None):
        auth.require_action(request, "chat.write")
        return await hermes.create_session(body or {})

    @router.get("/chat/sessions/{session_id}")
    async def get_session(request: Request, session_id: str):
        auth.require_action(request, "chat.read")
        return await hermes.get_session(session_id)

    @router.get("/chat/sessions/{session_id}/messages")
    async def messages(request: Request, session_id: str):
        auth.require_action(request, "chat.read")
        return await hermes.get_messages(session_id)

    @router.post("/chat/sessions/{session_id}/fork")
    async def fork_session(request: Request, session_id: str, body: Optional[dict] = None):
        auth.require_action(request, "chat.write")
        return await hermes.fork_session(session_id, body or {})

    @router.patch("/chat/sessions/{session_id}")
    async def patch_session(request: Request, session_id: str, body: dict):
        auth.require_action(request, "chat.manage")
        return await hermes.patch_session(session_id, body)

    @router.delete("/chat/sessions/{session_id}")
    async def delete_session(request: Request, session_id: str):
        auth.require_action(request, "chat.manage")
        return await hermes.delete_session(session_id)

    @router.post("/chat/sessions/{session_id}/runs")
    async def start_run(request: Request, session_id: str, body: dict):
        auth.require_action(request, "chat.run")
        text = body.get("input")
        if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
            raise HTTPException(status_code=400, detail="Message must contain 1-100000 characters")
        key = request.headers.get("idempotency-key", "")
        if not key or len(key) > 255 or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
        return await hermes.start_run({"input": text, "session_id": hermes._safe_id(session_id)}, key)

    @router.get("/chat/runs/{run_id}/events")
    async def run_events(request: Request, run_id: str):
        auth.require_action(request, "chat.read")
        chunks = await hermes.stream_run(run_id)
        return StreamingResponse(chunks, media_type="text/event-stream", headers={
            "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
        })

    @router.get("/chat/runs/{run_id}")
    async def get_run(request: Request, run_id: str):
        auth.require_action(request, "chat.read")
        return await hermes.get_run(run_id)

    @router.post("/chat/runs/{run_id}/stop")
    async def stop_run(request: Request, run_id: str):
        auth.require_action(request, "chat.stop")
        return await hermes.stop_run(run_id)

    return router
