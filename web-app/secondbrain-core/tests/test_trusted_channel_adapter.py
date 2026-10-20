import json
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


if __name__ == "__main__":
    unittest.main()
