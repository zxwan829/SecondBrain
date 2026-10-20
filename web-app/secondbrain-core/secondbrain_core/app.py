"""SecondBrain Core HTTP application factory."""
import os
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from .modules.app_auth import AppSessionAuth
from .modules.auto_organize import OrganizerControlStore, create_auto_organize_router
from .modules.capture import CaptureService, create_capture_router, create_inbox_entry_router
from .modules.hermes_api import HermesAPI
from .modules.multimodal_capture import MultimodalCaptureProcessors
from .modules.personal_memory import PersonalMemoryStore, create_personal_memory_router
from .modules.personal_learning import PersonalLearningPipeline
from .modules.chat_activity import ChatActivityStore, create_chat_activity_router
from .modules.journal import JournalStore, create_journal_router
from .modules.tasks import TaskStore, create_task_router
from .modules.projects_activity_read import create_projects_activity_router
from .modules.daily_brief_agent_health import create_daily_brief_agent_health_router
from .modules.projects_source_read import ProjectsSourceReadStore
from .modules.daily_brief_store import DailyBriefRecordReadStore
from .modules.calendar_read import create_calendar_read_router
from .modules.notes import configured_notes_store, create_notes_router
from .modules.knowledge_read import KnowledgeReadStore, create_knowledge_read_router
from .modules.vocabulary import VocabularyStore, create_vocabulary_router
from .modules.inbox_proposals import InboxProposalStore, InboxProposalSources, create_inbox_proposal_router
from .modules.organizer_engine import OrganizerRunner
from .modules.review_promote.http import create_core_router
from .modules.review_promote.service import PromoteService
from .modules.review_promote.core_auth import CorePromoteAuth
from .modules.review_promote.provenance import PromoteProvenanceVerifier
from .modules.review_promote.subprocess_worker_client import SubprocessPromoteWorker
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
    worker_mode = os.environ.get("SB_PROMOTE_WORKER_MODE", "inline").strip().lower()
    if worker_mode not in {"inline", "subprocess"}:
        raise RuntimeError("SB_PROMOTE_WORKER_MODE must be inline or subprocess")
    if promote_enabled:
        raise RuntimeError(
            "Production Promote requires independently verifiable Worker, Writer, and approval authority; "
            "no isolated runtime proof is configured",
        )

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
    promote_operations_path = os.path.join(approval_root, "b1b-operations")
    os.makedirs(promote_operations_path, mode=0o700, exist_ok=True)
    promote_operations_info = os.stat(promote_operations_path, follow_symlinks=False)
    if (not os.path.isdir(promote_operations_path) or os.path.islink(promote_operations_path)
            or promote_operations_info.st_uid != os.geteuid()
            or promote_operations_info.st_mode & 0o077
            or not os.access(promote_operations_path, os.W_OK)):
        raise RuntimeError("B1b operation directory must be private and owned by the Core UID")
    service = PromoteService(review_root, knowledge_root,
                             approvals_path, audit_path)
    if worker_mode == "subprocess":
        service.worker = SubprocessPromoteWorker(
            review_root, knowledge_root, audit_path, approvals_path,
        )
    app_password_file = os.environ["SB_APP_PASSWORD_FILE"]
    auth = AppSessionAuth(app_password_file, origins, ttl)
    promote_unlock_ttl = int(os.environ.get("SB_PROMOTE_UNLOCK_TTL", "900"))
    promote_auth = CorePromoteAuth(
        os.environ.get("SB_PROMOTE_UNLOCK_SECRET_FILE", ""), origins, auth,
        allowed_hosts=allowed_hosts, session_ttl=promote_unlock_ttl,
    )
    hermes = HermesAPI()
    organizer_controls = OrganizerControlStore(Path(approval_root) / "ai-organize")
    organizer_options = organizer_controls.read()
    organizer = OrganizerRunner(approval_root, review_root, hermes,
                                model=organizer_controls.load_model(),
                                scheduler_enabled=organizer_options["scheduler_enabled"])
    capture = CaptureService(os.environ["SB_CAPTURE_RAW_ROOT"], review_root, approval_root,
                             processors=MultimodalCaptureProcessors(hermes))
    notes_store = configured_notes_store(
        os.environ.get("SB_NOTES_DRAFTS_ROOT", "").strip(),
        os.environ.get("SB_NOTES_AUTHORIZED_ROOTS", ""),
    )
    inbox_proposals = InboxProposalStore(Path(approval_root) / "inbox-proposals")
    inbox_proposal_sources = InboxProposalSources(capture, notes_store)
    vocabulary_store = VocabularyStore(approval_root)
    memory_enabled_value = os.environ.get("SB_PERSONAL_MEMORY_ENABLED", "false").strip().lower()
    if memory_enabled_value not in {"true", "false"}:
        raise RuntimeError("SB_PERSONAL_MEMORY_ENABLED must be true or false")
    learning_enabled_value = os.environ.get("SB_PERSONAL_LEARNING_ENABLED", "false").strip().lower()
    if learning_enabled_value not in {"true", "false"}:
        raise RuntimeError("SB_PERSONAL_LEARNING_ENABLED must be true or false")
    if learning_enabled_value == "true" and memory_enabled_value != "true":
        raise RuntimeError("Personal learning requires SB_PERSONAL_MEMORY_ENABLED=true")
    memory_store = None
    learning = None
    if memory_enabled_value == "true":
        memory_root = os.environ.get("SB_PERSONAL_MEMORY_ROOT", "").strip()
        if not memory_root or not os.path.isabs(memory_root):
            raise RuntimeError("An absolute SB_PERSONAL_MEMORY_ROOT is required when personal memory is enabled")
        memory_store = PersonalMemoryStore(memory_root)
        if learning_enabled_value == "true":
            learning = PersonalLearningPipeline(memory_store)

    chat_activity_store = ChatActivityStore(Path(approval_root) / "chat-activity")
    journal_root = os.environ.get("SB_JOURNAL_ROOT", "").strip()
    journal_store = JournalStore(journal_root) if journal_root else None
    task_root = os.environ.get("SB_TASK_ROOT", "").strip()
    task_store = TaskStore(task_root) if task_root else None
    projects_root = os.environ.get("SB_PROJECTS_INDEX_ROOT", "").strip()
    projects_store = ProjectsSourceReadStore(projects_root or None)
    daily_brief_root = os.environ.get("SB_DAILY_BRIEF_STORE_ROOT", "").strip()
    daily_brief_store = DailyBriefRecordReadStore(daily_brief_root or None)

    app = FastAPI(title="SecondBrain Core", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.chat_activity_store = chat_activity_store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.include_router(create_web_app_router(auth, hermes, service, review_root, knowledge_root,
                                             organizer, personal_learning=learning))
    app.include_router(create_auto_organize_router(auth, organizer, organizer_controls))
    app.include_router(create_capture_router(auth, capture))
    app.include_router(create_inbox_entry_router(
        auth, capture, inbox_proposals, inbox_proposal_sources, vocabulary_store,
    ))
    # Journal/Task business records are authoritative and the activity index is
    # repairable under the private Core state root; Hermes has no state mount.
    app.include_router(create_chat_activity_router(auth, hermes, chat_activity_store,
                                                   journal_store, task_store))
    app.include_router(create_journal_router(auth, journal_store, hermes, chat_activity_store))
    app.include_router(create_task_router(auth, task_store, hermes, chat_activity_store))
    app.include_router(create_projects_activity_router(
        auth, journal_store, task_store, projects_store=projects_store, notes_store=notes_store,
    ))
    app.include_router(create_daily_brief_agent_health_router(
        auth, hermes, brief_store=daily_brief_store, projects_store=projects_store,
        task_store=task_store, journal_store=journal_store, notes_store=notes_store,
    ))
    app.include_router(create_calendar_read_router(auth, journal_store, task_store))
    app.include_router(create_notes_router(auth, notes_store))
    provenance = PromoteProvenanceVerifier(review_root, approvals_path, audit_path,
                                           operations_root=promote_operations_path)
    app.include_router(create_knowledge_read_router(
        auth, KnowledgeReadStore(knowledge_root, provenance_verifier=provenance)))
    app.include_router(create_vocabulary_router(auth, vocabulary_store))
    app.include_router(create_inbox_proposal_router(
        auth, inbox_proposals, inbox_proposal_sources, vocabulary_store,
        journal_store=journal_store, capture_service=capture))
    # Default-off, separately injected data root. When disabled, Core neither creates
    # the directory nor scans chat history or starts a background memory task.
    if memory_enabled_value == "true":
        app.include_router(create_personal_memory_router(auth, memory_store))
    app.include_router(create_core_router(service, review_root, auth,
                                          promote_enabled=promote_enabled,
                                          include_auth_routes=False,
                                          promote_auth=promote_auth,
                                          operations_root=promote_operations_path,
                                          knowledge_root=knowledge_root), prefix="/api/promote")
    app.router.add_event_handler("startup", organizer.start_scheduler)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        if (request.url.path in {
                "/api/promote/auth/unlock", "/api/promote/auth/lock",
                "/api/promote/review/preview", "/api/promote/review/confirm",
        } or request.url.path.startswith("/api/promote/operations/")):
            response.headers["Cache-Control"] = "private, no-store"
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
