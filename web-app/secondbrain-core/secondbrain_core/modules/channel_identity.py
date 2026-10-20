"""Server-created identities for channel-neutral Inbox intake.

Request JSON is never an identity source. Production currently registers only
the authenticated App/Web adapter; future channel adapters must independently
authenticate their caller before constructing this value.
"""
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class TrustedChannelIdentity:
    channel: str
    subject: str
    authentication: str


def authenticated_web_identity(subject, requested_channel):
    if requested_channel != "web":
        raise HTTPException(501, "This Inbox channel has no trusted Core adapter")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(401, "Authenticated App identity is required")
    return TrustedChannelIdentity("web", subject, "app_session_action")
