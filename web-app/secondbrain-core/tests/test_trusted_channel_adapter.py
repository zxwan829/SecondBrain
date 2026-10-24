import json
import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.channel_identity import TrustedChannelIdentity
from secondbrain_core.modules.trusted_channel_adapter import create_trusted_channel_router


class SyntheticIdentityProvider:
    """Test-only provider; no production route or credential is involved."""
    def __init__(self, identity=None):
        self.identity = identity or TrustedChannelIdentity(
            "feishu", "synthetic-principal-1", "trusted_adapter_v1", "test-adapter",
            "synthetic-tenant", "synthetic-explicit-save-1",
        )
        self.last_raw_body = None

    def authenticate(self, request, raw_body):
        self.last_raw_body = raw_body
        if request.headers.get("X-Synthetic-Adapter") != "test-adapter-v1":
            from fastapi import HTTPException
            raise HTTPException(401, "Synthetic adapter authentication failed")
        return self.identity


class SyntheticWeixinIdentityProvider:
    """Test-only contract model for a verified native Hermes caller.

    The key and platform subject below are synthetic fixtures. A production
    provider must verify Hermes' authenticated caller envelope and map its
    verified platform subject through a server-owned allowlist/consent store.
    """
    _TEST_KEY = b"synthetic-only-weixin-test-key"

    def __init__(self):
        self.consent_active = True
        self.calls = 0

    def signature(self, raw_body):
        return hmac.new(self._TEST_KEY, raw_body, hashlib.sha256).hexdigest()

    def authenticate(self, request, raw_body):
        from fastapi import HTTPException

        self.calls += 1
        supplied = request.headers.get("X-Synthetic-Signature", "")
        expected = self.signature(raw_body)
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(401, "Synthetic Hermes caller authentication failed")
        # Platform subject is mapped server-side; no body field selects the
        # Core principal, tenant, consent record, adapter, or channel.
        if request.headers.get("X-Synthetic-Platform-User") != "platform-user-ref-1":
            raise HTTPException(401, "Synthetic platform identity is not mapped")
        if not self.consent_active:
            raise HTTPException(403, "Synthetic user consent is revoked")
        return TrustedChannelIdentity(
            "wechat", "synthetic-core-principal-1", "trusted_adapter_v1",
            "hermes-v0.22.2-native-weixin", "synthetic-tenant-1",
            "synthetic-consent-grant-1",
        )


class TrustedChannelAdapterHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.raw, self.review, self.state = (root / name for name in ("raw", "review", "state"))
        for path in (self.raw, self.review, self.state):
            path.mkdir(mode=0o700)
        self.service = CaptureService(str(self.raw), str(self.review), str(self.state))
        self.app = FastAPI()
        self.provider = SyntheticIdentityProvider()
        self.app.include_router(create_trusted_channel_router(self.service, self.provider))
        self.client = TestClient(self.app)
        self.payload = {"original_text": "synthetic explicit save", "source_event_id": "evt-001",
                        "occurred_at": "2026-10-20T03:00:00Z", "intent": "explicit_capture",
                        "attachment_refs": []}
        self.headers = {"X-Synthetic-Adapter": "test-adapter-v1"}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def post(self, payload=None, headers=None):
        # Do not let synthetic tests start the capture processor subprocess or
        # perform downstream classification; this suite checks intake only.
        with patch.object(self.service, "mark_scheduled", return_value=False):
            return self.client.post("/api/internal/v1/channel-events", json=payload or self.payload,
                                    headers=self.headers if headers is None else headers)

    def test_explicit_event_persists_server_identity_and_replays_idempotently(self):
        first = self.post()
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(first.json()["source"], {"channel": "feishu", "event_id": "evt-001"})
        evidence = first.json()["consent_evidence"]
        self.assertEqual(evidence["kind"], "trusted_adapter_explicit_action")
        self.assertEqual(evidence["consent_evidence_id"], "synthetic-explicit-save-1")
        self.assertIn(b"synthetic explicit save", self.provider.last_raw_body)
        self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)
        replay = self.post()
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertEqual(replay.headers["idempotent-replay"], "true")
        self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)
        stored = json.loads((self.state / "captures" / (first.json()["inbox_id"] + ".json")).read_text())
        self.assertEqual(stored["identity_scope"], {"adapter_id": "test-adapter", "tenant": "synthetic-tenant",
                                                     "principal": "synthetic-principal-1",
                                                     "consent_evidence_id": "synthetic-explicit-save-1"})

    def test_missing_auth_and_body_identity_or_consent_spoof_are_rejected(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        spoofed = {**self.payload, "source_channel": "web", "principal": "owner", "consent": True}
        self.assertEqual(self.post(payload=spoofed).status_code, 400)
        self.assertEqual(list(self.raw.glob("Inbox-*.md")), [])

    def test_ordinary_chat_approved_suggestion_and_external_attachment_fail_closed(self):
        self.assertEqual(self.post(payload={**self.payload, "intent": "ordinary_chat"}).status_code, 400)
        approved = {**self.payload, "intent": "approved_suggestion", "approved_proposal_id": "a" * 32,
                    "approved_proposal_version": 1}
        self.assertEqual(self.post(payload=approved).status_code, 501)
        attached = {**self.payload, "source_event_id": "evt-attachment", "attachment_refs": [
            {"capture_id": "a" * 32, "sha256": "b" * 64}]}
        self.assertEqual(self.post(payload=attached).status_code, 501)
        self.assertEqual(list(self.raw.glob("Inbox-*.md")), [])

    def test_proposal_fields_are_rejected_for_explicit_intents_before_any_write(self):
        for intent in ("explicit_capture", "journal_intent", "task_intent"):
            for field, value in (("approved_proposal_id", "a" * 32),
                                 ("approved_proposal_version", 1)):
                with self.subTest(intent=intent, field=field):
                    response = self.post(payload={**self.payload, "intent": intent, field: value})
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertIn("Core approval binding", response.text)
                    self.assertEqual(list(self.raw.iterdir()), [])
                    self.assertEqual(list(self.review.iterdir()), [])
                    self.assertEqual(list((self.state / "captures").glob("*.json")), [])

    def test_event_key_conflict_is_rejected_and_scope_is_separated(self):
        self.assertEqual(self.post().status_code, 202)
        first_id = self.post().json()["inbox_id"]
        changed = {**self.payload, "original_text": "changed content"}
        self.assertEqual(self.post(payload=changed).status_code, 409)
        other_scope_id = self.post_same_native_event(
            TrustedChannelIdentity("feishu", "synthetic-principal-2", "trusted_adapter_v1",
                                   "test-adapter", "synthetic-tenant", "consent-2"))
        self.assertNotEqual(other_scope_id, first_id)

    def post_same_native_event(self, identity):
        app = FastAPI()
        app.include_router(create_trusted_channel_router(self.service, SyntheticIdentityProvider(identity)))
        client = TestClient(app)
        try:
            with patch.object(self.service, "mark_scheduled", return_value=False):
                response = client.post("/api/internal/v1/channel-events", json=self.payload,
                                       headers=self.headers)
            self.assertEqual(response.status_code, 202, response.text)
            return response.json()["inbox_id"]
        finally:
            client.close()

    def test_authenticated_channel_tenant_and_adapter_are_all_in_idempotency_scope(self):
        first = self.post().json()["inbox_id"]
        for identity in (
            TrustedChannelIdentity("feishu", "synthetic-principal-1", "trusted_adapter_v1",
                                   "other-adapter", "synthetic-tenant", "consent-1"),
            TrustedChannelIdentity("feishu", "synthetic-principal-1", "trusted_adapter_v1",
                                   "test-adapter", "other-tenant", "consent-1"),
            TrustedChannelIdentity("wechat", "synthetic-principal-1", "trusted_adapter_v1",
                                   "test-adapter", "synthetic-tenant", "consent-1"),
        ):
            self.assertNotEqual(self.post_same_native_event(identity), first)

    def test_same_channel_event_with_changed_consent_evidence_conflicts(self):
        first = self.post()
        self.assertEqual(first.status_code, 202)
        changed_consent = TrustedChannelIdentity("feishu", "synthetic-principal-1", "trusted_adapter_v1",
                                                 "test-adapter", "synthetic-tenant", "different-consent")
        app = FastAPI()
        app.include_router(create_trusted_channel_router(self.service, SyntheticIdentityProvider(changed_consent)))
        client = TestClient(app)
        try:
            with patch.object(self.service, "mark_scheduled", return_value=False):
                response = client.post("/api/internal/v1/channel-events", json=self.payload,
                                       headers=self.headers)
            self.assertEqual(response.status_code, 409)
        finally:
            client.close()

    def test_synthetic_weixin_auth_maps_verified_subject_and_binds_exact_body(self):
        provider = SyntheticWeixinIdentityProvider()
        app = FastAPI()
        app.include_router(create_trusted_channel_router(self.service, provider))
        client = TestClient(app)
        raw_body = json.dumps(self.payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Synthetic-Platform-User": "platform-user-ref-1",
            "X-Synthetic-Signature": provider.signature(raw_body),
        }
        try:
            with patch.object(self.service, "mark_scheduled", return_value=False):
                response = client.post("/api/internal/v1/channel-events", content=raw_body,
                                       headers=headers)
                self.assertEqual(response.status_code, 202, response.text)
                state = json.loads((self.state / "captures" /
                                    (response.json()["inbox_id"] + ".json")).read_text())
                self.assertEqual(state["identity_scope"], {
                    "adapter_id": "hermes-v0.22.2-native-weixin",
                    "tenant": "synthetic-tenant-1",
                    "principal": "synthetic-core-principal-1",
                    "consent_evidence_id": "synthetic-consent-grant-1",
                })
                self.assertNotIn("platform-user-ref-1", json.dumps(state["identity_scope"]))

                # A valid signature for different bytes cannot be reused.
                changed_body = raw_body.replace(b"synthetic explicit save", b"altered")
                tampered = client.post("/api/internal/v1/channel-events", content=changed_body,
                                       headers=headers)
                self.assertEqual(tampered.status_code, 401)
                self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)
        finally:
            client.close()

    def test_synthetic_weixin_replay_is_idempotent_and_revocation_blocks_replay(self):
        provider = SyntheticWeixinIdentityProvider()
        app = FastAPI()
        app.include_router(create_trusted_channel_router(self.service, provider))
        client = TestClient(app)
        raw_body = json.dumps(self.payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Synthetic-Platform-User": "platform-user-ref-1",
            "X-Synthetic-Signature": provider.signature(raw_body),
        }
        try:
            with patch.object(self.service, "mark_scheduled", return_value=False):
                first = client.post("/api/internal/v1/channel-events", content=raw_body,
                                    headers=headers)
                self.assertEqual(first.status_code, 202, first.text)
                # Recreate Core's service/router over the same synthetic roots
                # to verify the idempotency record survives a process restart.
                restarted_service = CaptureService(str(self.raw), str(self.review), str(self.state))
                restarted_app = FastAPI()
                restarted_app.include_router(create_trusted_channel_router(restarted_service, provider))
                restarted_client = TestClient(restarted_app)
                replay = restarted_client.post("/api/internal/v1/channel-events", content=raw_body,
                                               headers=headers)
                self.assertEqual(replay.status_code, 202, replay.text)
                self.assertEqual(replay.headers["idempotent-replay"], "true")
                self.assertEqual(first.json()["inbox_id"], replay.json()["inbox_id"])
                self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)

                # The authoritative consent check runs before Inbox idempotency;
                # revocation blocks both retries and newly observed events.
                provider.consent_active = False
                revoked_replay = restarted_client.post("/api/internal/v1/channel-events", content=raw_body,
                                                       headers=headers)
                self.assertEqual(revoked_replay.status_code, 403)
                new_payload = {**self.payload, "source_event_id": "evt-after-revoke"}
                new_body = json.dumps(new_payload, separators=(",", ":")).encode("utf-8")
                new_headers = {**headers, "X-Synthetic-Signature": provider.signature(new_body)}
                after_revoke = restarted_client.post("/api/internal/v1/channel-events", content=new_body,
                                                     headers=new_headers)
                self.assertEqual(after_revoke.status_code, 403)
                self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)
                restarted_client.close()
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
