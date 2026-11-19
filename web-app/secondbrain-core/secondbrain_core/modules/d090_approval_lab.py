"""Standalone approval entry for an isolated synthetic lab."""

import hashlib

from fastapi import FastAPI, HTTPException, Request, Response

from .d090_browser_confirmation import BrowserConfirmation


def create_lab_app(auth, authority_factory, candidate, *, read_source=None):
    confirmation = BrowserConfirmation(auth)
    authority = authority_factory(confirmation)
    fields = {key: candidate[key] for key in (
        "approval_id", "operation_id", "source_revision", "source_sha256", "target_id",
    )}
    content = bytes(candidate["approved_bytes"])
    binding = {**fields, "content_length": len(content),
               "content_sha256": hashlib.sha256(content).hexdigest()}
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def prevent_framing(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    @app.post("/login")
    def login(request: Request, response: Response, body: dict):
        token = auth.login(request, body.get("password"))
        auth.set_cookie(response, request, token, auth.session_ttl)
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": True}

    @app.post("/preview")
    def preview(request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"binding": confirmation.prepare(request, binding),
                "content": content.decode("utf-8")}

    @app.post("/confirm")
    def confirm(request: Request, body: dict):
        auth.check_origin(request)
        auth.require_owner(request)
        if body.get("intent") != "promote_exact_preview":
            raise HTTPException(403, "Exact approval required")
        exact = body.get("binding")
        if not isinstance(exact, dict) or any(exact.get(key) != value for key, value in binding.items()):
            raise HTTPException(403, "Preview binding mismatch")
        if read_source is not None:
            try:
                review, source_revision = read_source()
            except OSError as exc:
                raise HTTPException(409, "Approved source unavailable") from exc
            if (hashlib.sha256(review).hexdigest() != fields["source_sha256"]
                    or source_revision != fields["source_revision"]):
                raise HTTPException(409, "Approved source changed")
        from .d090_authority_writer import D090Rejected, HumanProofUnavailable

        try:
            grant = authority.issue_grant(
                proof=request, **fields, approved_bytes=content,
                nonce=exact.get("nonce"), expires_at=exact.get("expires_at"),
            )
        except (D090Rejected, HumanProofUnavailable) as exc:
            raise HTTPException(403, "Approval rejected") from exc
        if read_source is not None:
            return authority.commit(grant, content)
        return {"operation_id": grant["operation_id"], "status": "issued"}

    return app
