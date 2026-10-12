"""Dashboard plugin router factory for the Core Review/Promote module."""
import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .approval import ApprovalRequestError, DashboardAuthorizationError, _read_review


def create_router(service, review_root):
    router = APIRouter()
    review_root = Path(review_root)

    @router.get("/review/items")
    def list_review_items():
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
                              "target_filename": name, "title": title})
        return {"status": "ok", "items": items}

    @router.post("/review/approve")
    def approve_review(request: Request, body: dict):
        try:
            return service.approve_and_promote(request, body, str(review_root))
        except DashboardAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ApprovalRequestError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            # Service errors fail closed; keep the original Review available.
            raise HTTPException(status_code=409, detail=str(exc))

    return router
