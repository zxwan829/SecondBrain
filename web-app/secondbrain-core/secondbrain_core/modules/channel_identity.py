"""Server-created identities for channel-neutral Inbox intake.

Request JSON is never an identity source. Production currently registers only
the authenticated App/Web adapter; future channel adapters must independently
authenticate their caller before constructing this value.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
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
    permissions: frozenset[str] = frozenset()


class TrustedChannelIdentityProvider(Protocol):
    """Verifier must authenticate the exact bytes and ignore body identity claims."""

    def authenticate(self, request, raw_body: bytes) -> TrustedChannelIdentity: ...


class WeixinHmacIdentityProvider:
    """Default-off Hermes v0.22.2 Weixin adapter authenticator.

    Sender-to-Core-subject mapping is configuration owned by Core. The exact
    event bytes are signed by the separately configured Hermes plugin key.
    """

    def __init__(self, secret: bytes, allowed_senders: dict[str, str]):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("Weixin adapter key must contain at least 32 bytes")
        if not isinstance(allowed_senders, dict) or not allowed_senders or any(
                not isinstance(sender, str) or not sender or
                not isinstance(subject, str) or not subject
                for sender, subject in allowed_senders.items()):
            raise ValueError("Weixin sender allowlist is invalid")
        self._secret = secret
        self._allowed_senders = dict(allowed_senders)

    def authenticate(self, request, raw_body: bytes) -> TrustedChannelIdentity:
        supplied = request.headers.get("X-SecondBrain-Signature", "")
        expected = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(401, "Trusted adapter authentication failed")
        try:
            body = json.loads(raw_body)
            source = body["source"]
            sender = source["user_id"]
            event_id = body["source_event_id"]
            if (source["platform"] != "weixin" or source["chat_type"] != "dm" or
                    not isinstance(sender, str) or not isinstance(event_id, str) or
                    not event_id or body["intent"] != "explicit_capture"):
                raise ValueError
            subject = self._allowed_senders[sender]
        except (KeyError, TypeError, ValueError):
            raise HTTPException(403, "Weixin sender or explicit DM capture is not authorized")
        return TrustedChannelIdentity(
            channel="wechat", subject=subject, authentication="trusted_adapter_v1",
            adapter_id="hermes-v0.22.2-weixin", tenant="default",
            consent_evidence_id=event_id, permissions=frozenset({"capture.write"}),
        )

    def sign_receipt(self, event_id: str, inbox_id: str, status: str, raw_request: bytes) -> str:
        request_digest = hashlib.sha256(raw_request).hexdigest()
        receipt = "secondbrain-weixin-receipt-v1\0{}\0{}\0{}\0{}".format(
            event_id, inbox_id, status, request_digest)
        return hmac.new(self._secret, receipt.encode("utf-8"), hashlib.sha256).hexdigest()


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
    if not isinstance(identity.permissions, frozenset) or any(
            not isinstance(permission, str) or not permission for permission in identity.permissions):
        raise HTTPException(401, "Trusted adapter permissions are invalid")
    return identity


def authenticated_web_identity(subject, requested_channel):
    if requested_channel != "web":
        raise HTTPException(501, "This Inbox channel has no trusted Core adapter")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(401, "Authenticated App identity is required")
    return TrustedChannelIdentity("web", subject, "app_session_action")
