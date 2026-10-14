"""Dashboard plugin router factory for the Core Review/Promote module."""
import hashlib
import os
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request, Response

from .approval import ApprovalRequestError, _read_review
from .core_auth import CorePromoteAuth


def _review_status(content):
    """Expose the declared Review state without interpreting arbitrary YAML."""
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return "unknown"
    if not lines or lines[0].strip() != "---":
        return "unknown"
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^(review_status|status):\s*['\"]?([^'\"]+)['\"]?\s*$", line)
        if match:
            return match.group(2).strip()
    return "unknown"


def create_core_router(service, review_root, auth, *, promote_enabled=True, include_auth_routes=True):
    """Router for direct browser→Core approval; never trusts Hermes state/headers."""
    router = APIRouter()
    review_root = Path(review_root)

    @router.get("/review/items")
    def list_review_items(request: Request):
        auth.require_action(request, "review.read")
        items = []
        for current, dirs, files in os.walk(review_root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(current, d)))
            for name in sorted(files):
                absolute = os.path.join(current, name)
                if not name.lower().endswith(".md") or os.path.islink(absolute):
                    continue
                relative = os.path.relpath(absolute, review_root).replace(os.sep, "/")
                try:
                    content = _read_review(str(review_root), relative)
                except ApprovalRequestError:
                    continue
                title = next((line[2:].strip() for line in content.decode("utf-8", errors="replace").splitlines()
                              if line.startswith("# ")), Path(name).stem)
                items.append({"review_path": relative,
                              "review_sha256": hashlib.sha256(content).hexdigest(),
                              "target_filename": name, "title": title,
                              "status": _review_status(content),
                              "decision": service.get_decision(relative, hashlib.sha256(content).hexdigest())})
        return {"status": "ok", "items": items}

    @router.get("/review/items/{review_path:path}")
    def get_review_item(request: Request, review_path: str):
        auth.require_action(request, "review.read")
        try:
            content = _read_review(str(review_root), review_path)
        except ApprovalRequestError as exc:
            raise HTTPException(status_code=404, detail="Review item not found") from exc
        decoded = content.decode("utf-8", errors="replace")
        title = next((line[2:].strip() for line in decoded.splitlines() if line.startswith("# ")),
                     Path(review_path).name)
        digest = hashlib.sha256(content).hexdigest()
        return {"status": _review_status(content), "review_path": review_path,
                "review_sha256": digest,
                "target_filename": Path(review_path).name, "title": title,
                "content": decoded, "decision": service.get_decision(review_path, digest)}

    if include_auth_routes:
        @router.post("/auth/unlock")
        def unlock(request: Request, response: Response, body: dict):
            token = auth.unlock(request, body.get("passphrase"))
            auth.set_session_cookie(response, request, token, auth.session_ttl)
            return {"status": "unlocked", "expires_in": auth.session_ttl}

        @router.post("/auth/lock")
        def lock(request: Request, response: Response):
            auth.lock(request)
            auth.clear_session_cookie(response)
            return {"status": "locked"}

    @router.get("/status")
    def promote_status(request: Request):
        auth.require_action(request, "promote.read")
        return {"status": "ok", "promote_enabled": promote_enabled}

    @router.post("/review/approve")
    def approve_review(request: Request, body: dict):
        approver = auth.require_action(request, "knowledge.promote")
        if not promote_enabled:
            raise HTTPException(status_code=423, detail="Promote is disabled pending production write approval")
        try:
            return service.approve_and_promote_as(approver, body, str(review_root))
        except ApprovalRequestError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @router.post("/review/defer")
    def defer_review(request: Request, body: dict):
        approver = auth.require_action(request, "review.defer")
        try:
            return service.defer(body.get("review_path"), body.get("review_sha256"), approver)
        except ApprovalRequestError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
