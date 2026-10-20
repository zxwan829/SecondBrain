"""Server-created identities for channel-neutral Inbox intake.

Request JSON is never an identity source. Production currently registers only
the authenticated App/Web adapter; future channel adapters must independently
authenticate their caller before constructing this value.
"""
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException


@dataclass(frozen=True)
class TrustedChannelIdentity:
    channel: str
    subject: str
    authentication: str
    adapter_id: str = "web"
    tenant: str = "default"
    consent_evidence_id: str = ""


class TrustedChannelIdentityProvider(Protocol):
    """Verifier must authenticate the exact bytes and ignore body identity claims."""

    def authenticate(self, request, raw_body: bytes) -> TrustedChannelIdentity: ...


def validate_trusted_identity(identity):
    if (not isinstance(identity, TrustedChannelIdentity) or
            not all(isinstance(value, str) and value and len(value) <= 200 for value in
                    (identity.channel, identity.subject, identity.authentication,
                     identity.adapter_id, identity.tenant))):
        raise HTTPException(401, "Trusted channel identity is invalid")
    if identity.channel == "web":
        if identity.authentication != "app_session_action":
            raise HTTPException(401, "Web identity requires an authenticated App action")
    elif (identity.authentication != "trusted_adapter_v1" or
          not isinstance(identity.consent_evidence_id, str) or not identity.consent_evidence_id or
          len(identity.consent_evidence_id) > 200):
        raise HTTPException(401, "Trusted adapter authentication and consent evidence are required")
    return identity


def authenticated_web_identity(subject, requested_channel):
    if requested_channel != "web":
        raise HTTPException(501, "This Inbox channel has no trusted Core adapter")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(401, "Authenticated App identity is required")
    return TrustedChannelIdentity("web", subject, "app_session_action")
