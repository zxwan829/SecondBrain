"""SecondBrain Core HTTP application factory."""
import os
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from .modules.app_auth import AppSessionAuth
from .modules.auto_organize import create_auto_organize_router
from .modules.capture import CaptureService, create_capture_router
from .modules.hermes_api import HermesAPI
from .modules.multimodal_capture import MultimodalCaptureProcessors
from .modules.review_promote.http import create_core_router
from .modules.review_promote.service import PromoteService
from .modules.web_app import create_web_app_router


def create_app():
    review_root = os.environ["SB_REVIEW_ROOT"]
    knowledge_root = os.environ["SB_KNOWLEDGE_ROOT"]
    approval_root = os.environ["SB_PROMOTE_STATE_ROOT"]
    audit_path = os.path.join(approval_root, "audit.jsonl")
    origins = [value.strip().rstrip("/") for value in os.environ["SB_DASHBOARD_ORIGINS"].split(",") if value.strip()]
    allowed_hosts = [value.strip().lower() for value in os.environ["SB_CORE_ALLOWED_HOSTS"].split(",") if value.strip()]
    if not allowed_hosts or any("*" in host for host in allowed_hosts):
        raise RuntimeError("Core requires a nonempty exact Host allowlist")
    ttl = int(os.environ.get("SB_APP_SESSION_TTL", "28800"))
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
    app_password_file = os.environ["SB_APP_PASSWORD_FILE"]
    auth = AppSessionAuth(app_password_file, origins, ttl)
    hermes = HermesAPI()
    capture = CaptureService(os.environ["SB_CAPTURE_RAW_ROOT"], review_root, approval_root,
                             processors=MultimodalCaptureProcessors(hermes))
    app = FastAPI(title="SecondBrain Core", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.include_router(create_web_app_router(auth, hermes, service, review_root, knowledge_root))
    app.include_router(create_auto_organize_router(auth, approval_root))
    app.include_router(create_capture_router(auth, capture))
    app.include_router(create_core_router(service, review_root, auth,
                                          promote_enabled=promote_enabled,
                                          include_auth_routes=False), prefix="/api/promote")

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy",
                                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "promote_enabled": promote_enabled,
                "hermes_configured": hermes.configured}

    static_root_value = os.environ.get("SB_STATIC_ROOT", "")
    if static_root_value:
        static_root = Path(static_root_value).resolve(strict=True)
        if not static_root.is_dir() or not (static_root / "index.html").is_file():
            raise RuntimeError("SB_STATIC_ROOT must contain the built frontend index.html")
        if (static_root / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static_root / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend_fallback(path: str):
            candidate = (static_root / path).resolve()
            if candidate.is_relative_to(static_root) and candidate.is_file():
                return FileResponse(candidate)
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse(static_root / "index.html")

    return app
