"""SecondBrain Core HTTP application factory."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .modules.review_promote.core_auth import CorePromoteAuth
from .modules.review_promote.http import create_core_router
from .modules.review_promote.service import PromoteService


def create_app():
    review_root = os.environ["SB_REVIEW_ROOT"]
    knowledge_root = os.environ["SB_KNOWLEDGE_ROOT"]
    approval_root = os.environ["SB_PROMOTE_STATE_ROOT"]
    audit_path = os.path.join(approval_root, "audit.jsonl")
    origins = [value.strip().rstrip("/") for value in os.environ["SB_DASHBOARD_ORIGINS"].split(",") if value.strip()]
    allowed_hosts = [value.strip().lower() for value in os.environ["SB_CORE_ALLOWED_HOSTS"].split(",") if value.strip()]
    if not allowed_hosts or any("*" in host for host in allowed_hosts):
        raise RuntimeError("Core requires a nonempty exact Host allowlist")
    secret_file = os.environ["SB_PROMOTE_UNLOCK_SECRET_FILE"]
    ttl = int(os.environ.get("SB_PROMOTE_SESSION_TTL", "3600"))
    # Fail closed: a deployment must explicitly enable final Knowledge writes.
    promote_enabled_value = os.environ.get("SB_PROMOTE_ENABLED", "false").strip().lower()
    if promote_enabled_value not in {"true", "false"}:
        raise RuntimeError("SB_PROMOTE_ENABLED must be true or false")
    promote_enabled = promote_enabled_value == "true"

    state_info = os.stat(approval_root, follow_symlinks=False)
    if (not os.path.isdir(approval_root) or os.path.islink(approval_root)
            or state_info.st_uid != os.geteuid() or state_info.st_mode & 0o077
            or not os.access(approval_root, os.W_OK)):
        raise RuntimeError("Core state directory must be a private writable directory owned by the Core UID")
    approvals_path = os.path.join(approval_root, "approvals")
    os.makedirs(approvals_path, mode=0o700, exist_ok=True)
    approvals_info = os.stat(approvals_path, follow_symlinks=False)
    if (not os.path.isdir(approvals_path) or os.path.islink(approvals_path)
            or approvals_info.st_uid != os.geteuid() or approvals_info.st_mode & 0o077
            or not os.access(approvals_path, os.W_OK)):
        raise RuntimeError("Core approval directory must be private and owned by the Core UID")
    service = PromoteService(review_root, knowledge_root,
                             approvals_path, audit_path)
    auth = CorePromoteAuth(secret_file, origins, ttl)
    app = FastAPI(title="SecondBrain Core", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.include_router(create_core_router(service, review_root, auth,
                                          promote_enabled=promote_enabled), prefix="/api/promote")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
