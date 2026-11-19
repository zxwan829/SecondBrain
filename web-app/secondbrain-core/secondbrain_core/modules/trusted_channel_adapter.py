"""Opt-in router factory for authenticated channel adapters.

The production app deliberately does not register this router until a real,
reviewed identity provider and its key lifecycle are supplied. Tests inject a
synthetic provider; request JSON never establishes identity or consent.
"""
import re

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from .channel_identity import TrustedChannelIdentityProvider, validate_trusted_identity


_EVENT_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_FIELDS = {"original_text", "source_event_id", "occurred_at", "intent", "source",
           "attachment_refs", "approved_proposal_id", "approved_proposal_version"}


def create_trusted_channel_router(service, identity_provider: TrustedChannelIdentityProvider):
    """Create a server-to-server adapter router; caller must explicitly register it."""
    router = APIRouter(prefix="/api/internal/v1/channel-events")

    @router.post("", status_code=202)
    async def accept_event(request: Request, response: Response,
                           background_tasks: BackgroundTasks, body: dict):
        if not isinstance(body, dict) or set(body) - _FIELDS:
            raise HTTPException(400, "Channel identity and consent are server-authenticated only")
        raw_body = await request.body()
        identity = validate_trusted_identity(identity_provider.authenticate(request, raw_body))
        if identity.channel == "web":
            raise HTTPException(400, "Trusted adapter route requires a non-Web channel identity")
        if identity.channel not in {"wechat", "feishu"}:
            raise HTTPException(501, "This channel has no approved adapter contract")
        if "capture.write" not in identity.permissions:
            raise HTTPException(403, "Trusted channel identity lacks capture.write permission")
        event_id = body.get("source_event_id")
        if not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id):
            raise HTTPException(400, "Native channel event ID is invalid")
        if body.get("intent") == "approved_suggestion":
            # Until a trusted adapter can bind proposal, source and vocabulary
            # versions through Core's approval service, fail closed.
            raise HTTPException(501, "Approved suggestions require the Core approval binding adapter")
        if "approved_proposal_id" in body or "approved_proposal_version" in body:
            raise HTTPException(400, "Proposal evidence requires the Core approval binding adapter")
        if body.get("intent") != "explicit_capture":
            raise HTTPException(400, "Only explicit Inbox capture is supported by this adapter")
        attachments = body.get("attachment_refs", [])
        if attachments:
            raise HTTPException(501, "External attachment references require a trusted channel binding")
        state, replayed = service.accept_channel_text(
            text=body.get("original_text"), identity=identity, source_event_id=event_id,
            intent=body.get("intent"), occurred_at=body.get("occurred_at"),
            attachment_refs=[],
        )
        if state.get("status") == "processing" and service.mark_scheduled(state):
            try:
                raw = (service.raw_root / state["raw_path"]).read_bytes()
            except OSError as exc:
                raise HTTPException(503, "Inbox capture recovery requires review") from exc
            background_tasks.add_task(service.process, state, raw)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Idempotent-Replay"] = "true" if replayed else "false"
        sign_receipt = getattr(identity_provider, "sign_receipt", None)
        if callable(sign_receipt):
            response.headers["X-SecondBrain-Receipt-Signature"] = sign_receipt(
                event_id, state["capture_id"], state["status"], raw_body)
        return {"inbox_id": state["capture_id"], "status": state["status"],
                "source": {"channel": state["source_channel"], "event_id": state["source_event_id"]},
                "intent": state["intent"], "consent_evidence": state["consent_evidence"]}

    return router
