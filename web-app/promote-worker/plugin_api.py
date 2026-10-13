"""SecondBrain Dashboard plugin API, including the human approval endpoint.

This module belongs to the trusted Hermes Dashboard plugin directory. It writes
only approval records to a separately provisioned queue, never Knowledge.
"""
import hashlib
import os
import sys
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_PLUGIN_DIR = str(Path(__file__).resolve().parent)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from dashboard_approval import (  # noqa: E402
    ApprovalFileStore,
    ApprovalRequestError,
    DashboardAuthorizationError,
    _read_review,
)


router = APIRouter()
ROOT = Path(os.environ.get("SECONDBRAIN_ROOT", "/secondbrain"))
REVIEW_ROOT = ROOT / "10-Review"
ALLOW = {
    "10-Review": REVIEW_ROOT,
    "20-Knowledge": ROOT / "20-Knowledge",
    "30-Projects": ROOT / "30-Projects",
    "40-Memory": ROOT / "40-Memory",
    "50-Journal": ROOT / "50-Journal",
}
DENY = {"00-Inbox", "90-Archive", "90-Private", "Private", "KnowledgeAssets"}


def title_of(path):
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
            if line.lower().startswith("title:"):
                return line.split(":", 1)[1].strip().strip('"')
    except OSError:
        pass
    return path.stem


def list_items(root, limit=5):
    if not root.exists():
        return []
    files = sorted(
        [path for path in root.rglob("*") if path.is_file()
         and not any(part in path.parts for part in ("90-Private", "Private", "90-Archive"))],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [{"title": title_of(path), "updated": int(path.stat().st_mtime)}
            for path in files[:limit]]


@router.get("/proof")
def secondbrain_proof():
    return {"status": "ok", "area": "30-Projects", "title": "SecondBrain V1 — Current State",
            "source_type": "project"}


@router.get("/policy-probe/{area}")
def policy_probe(area: str):
    return {"status": "denied", "reason": "policy"} if area in DENY or area not in ALLOW else {
        "status": "allowed"
    }


@router.get("/home")
def secondbrain_home():
    today_path = ALLOW["50-Journal"] / (date.today().isoformat() + ".md")
    today = {"status": "empty"} if not today_path.exists() else {
        "status": "real", "date": date.today().isoformat(), "title": title_of(today_path)
    }
    review_items = list_items(ALLOW["10-Review"], 5)
    project_items = list_items(ALLOW["30-Projects"], 5)
    knowledge_items = list_items(ALLOW["20-Knowledge"], 5)
    return {
        "status": "ok",
        "agent": {"status": "online"},
        "today": today,
        "review": {"status": "real" if review_items else "empty",
                   "pending_count": len(review_items), "items": review_items},
        "projects": {"status": "real" if project_items else "empty", "items": project_items},
        "knowledge": {"status": "real" if knowledge_items else "empty", "items": knowledge_items},
        "brief": {"status": "not_connected"},
        "activity": {"status": "not_connected", "items": []},
    }


@router.get("/review/items")
def list_review_items():
    """Return stable Review references and digests for an explicit approval UI."""
    items = []
    for current, dirs, files in os.walk(REVIEW_ROOT, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(current, d)))
        for name in sorted(files):
            if not name.lower().endswith(".md"):
                continue
            absolute = os.path.join(current, name)
            if os.path.islink(absolute):
                continue
            relative = os.path.relpath(absolute, REVIEW_ROOT).replace(os.sep, "/")
            try:
                content = _read_review(str(REVIEW_ROOT), relative)
            except ApprovalRequestError:
                continue
            title = next(
                (line[2:].strip() for line in content.decode("utf-8", errors="replace").splitlines()
                 if line.startswith("# ")),
                Path(name).stem,
            )
            items.append({
                "review_path": relative,
                "review_sha256": hashlib.sha256(content).hexdigest(),
                "target_filename": name,
                "title": title,
            })
    return {"status": "ok", "items": items}


@router.post("/review/approve")
def approve_review(request: Request, body: dict):
    """Queue one explicit Review version after Hermes session + Origin validation."""
    queue_dir = os.environ.get("SECONDBRAIN_APPROVAL_QUEUE", "")
    if not queue_dir:
        raise HTTPException(status_code=503, detail="Approval queue is not configured")
    try:
        return ApprovalFileStore(queue_dir).approve(request, body, str(REVIEW_ROOT))
    except DashboardAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ApprovalRequestError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
