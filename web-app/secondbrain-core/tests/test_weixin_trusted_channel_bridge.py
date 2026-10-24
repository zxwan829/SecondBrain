"""Synthetic Hermes Weixin -> opt-in Core trusted-channel candidate bridge.

Run with HERMES_SOURCE_ROOT pointing at the pinned v0.22.2 checkout. The test
provider and sender headers below are test fixtures only; they are not a wire,
authentication, identity, consent, or production registration contract.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.channel_identity import TrustedChannelIdentity
from secondbrain_core.modules.trusted_channel_adapter import create_trusted_channel_router


HERMES_SOURCE_ROOT = os.environ.get("HERMES_SOURCE_ROOT")
if HERMES_SOURCE_ROOT:
    import sys
    sys.path.insert(0, HERMES_SOURCE_ROOT)

try:
    from gateway.config import PlatformConfig
    from gateway.platforms.weixin import WeixinAdapter
except ImportError as exc:  # the ordinary Core test environment need not install Hermes
    WeixinAdapter = None
    _HERMES_IMPORT_ERROR = exc
else:
    _HERMES_IMPORT_ERROR = None


pytestmark = pytest.mark.skipif(WeixinAdapter is None,
                               reason="set HERMES_SOURCE_ROOT to the pinned Hermes v0.22.2 source")


class SyntheticHermesIdentityProvider:
    """Test-only sender allowlist and identity mapper; no production secrets."""

    def __init__(self, adapter, allowlisted_sender="synthetic-wxid-allowed"):
        self.adapter = adapter
        self.allowlisted_sender = allowlisted_sender
        self.identity = TrustedChannelIdentity(
            "wechat", "synthetic-principal-1", "trusted_adapter_v1", "synthetic-hermes",
            "synthetic-account", "synthetic-consent-event-1",
        )

    def authenticate(self, request, raw_body):
        if request.headers.get("X-Synthetic-Adapter") != "synthetic-hermes-v0.22.2":
            from fastapi import HTTPException
            raise HTTPException(401, "Synthetic adapter authentication failed")
        sender = request.headers.get("X-Synthetic-Sender", "")
        # Exercise the actual Hermes v0.22.2 OwnAccessPolicyMixin predicate.
        if not self.adapter._is_dm_intake_allowed(sender):
            from fastapi import HTTPException
            raise HTTPException(403, "Synthetic Weixin sender is not allowlisted")
        if sender != self.allowlisted_sender:
            from fastapi import HTTPException
            raise HTTPException(403, "No synthetic Core principal mapping exists")
        # Deliberately ignore all caller-supplied body identity/consent fields.
        json.loads(raw_body)
        return self.identity


class WeixinTrustedChannelBridgeTests(unittest.TestCase):
    def setUp(self):
        if WeixinAdapter is None:
            self.skipTest(f"Hermes source unavailable: {_HERMES_IMPORT_ERROR}")
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.raw, self.review, self.state = (self.root / name for name in ("raw", "review", "state"))
        for path in (self.raw, self.review, self.state):
            path.mkdir(mode=0o700)
        self.hermes_home = self.root / "hermes-synthetic"
        self.hermes_home.mkdir(mode=0o700)
        from hermes_constants import set_hermes_home_override
        self.home_override = set_hermes_home_override(self.hermes_home)
        self.adapter = WeixinAdapter(PlatformConfig(
            enabled=True,
            extra={"account_id": "synthetic-bot", "dm_policy": "allowlist",
                   "allow_from": ["synthetic-wxid-allowed"]},
        ))
        self.provider = SyntheticHermesIdentityProvider(self.adapter)
        self.service = CaptureService(str(self.raw), str(self.review), str(self.state))
        self.app = FastAPI()
        self.app.include_router(create_trusted_channel_router(self.service, self.provider))
        self.client = TestClient(self.app)
        self.payload = {"original_text": "synthetic Weixin explicit capture",
                        "source_event_id": "synthetic-weixin-event-1",
                        "occurred_at": "2026-10-24T00:00:00Z", "intent": "explicit_capture",
                        "attachment_refs": []}
        self.headers = {"X-Synthetic-Adapter": "synthetic-hermes-v0.22.2",
                        "X-Synthetic-Sender": "synthetic-wxid-allowed"}

    def tearDown(self):
        self.client.close()
        from hermes_constants import reset_hermes_home_override
        reset_hermes_home_override(self.home_override)
        self.temp.cleanup()

    def post(self, payload=None, headers=None):
        with patch.object(self.service, "mark_scheduled", return_value=False):
            return self.client.post("/api/internal/v1/channel-events",
                                    json=self.payload if payload is None else payload,
                                    headers=self.headers if headers is None else headers)

    def test_pinned_hermes_allowlist_maps_synthetic_sender_and_replay_survives_restart(self):
        self.assertTrue(self.adapter.enforces_own_access_policy)
        self.assertTrue(self.adapter._is_dm_intake_allowed("synthetic-wxid-allowed"))
        self.assertFalse(self.adapter._is_dm_intake_allowed("synthetic-wxid-denied"))
        self.assertFalse(self.adapter._is_dm_intake_allowed(""))

        first = self.post()
        self.assertEqual(first.status_code, 202, first.text)
        first_json = first.json()
        self.assertEqual(first_json["source"], {"channel": "wechat", "event_id": self.payload["source_event_id"]})
        self.assertEqual(first_json["consent_evidence"]["kind"], "trusted_adapter_explicit_action")
        self.assertEqual(first_json["consent_evidence"]["consent_evidence_id"], "synthetic-consent-event-1")
        self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)

        changed = self.post(payload={**self.payload, "original_text": "changed synthetic payload"})
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)

        # Recreate the Core store over the same synthetic roots to model process restart.
        restarted_service = CaptureService(str(self.raw), str(self.review), str(self.state))
        restarted_app = FastAPI()
        restarted_app.include_router(create_trusted_channel_router(restarted_service, self.provider))
        restarted_client = TestClient(restarted_app)
        try:
            with patch.object(restarted_service, "mark_scheduled", return_value=False):
                replay = restarted_client.post("/api/internal/v1/channel-events", json=self.payload,
                                               headers=self.headers)
            self.assertEqual(replay.status_code, 202, replay.text)
            self.assertEqual(replay.headers["idempotent-replay"], "true")
            self.assertEqual(replay.json()["inbox_id"], first_json["inbox_id"])
            self.assertEqual(len(list(self.raw.glob("Inbox-*.md"))), 1)
        finally:
            restarted_client.close()

    def test_auth_denial_spoofed_identity_and_attachment_refs_fail_closed_without_write(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        denied_headers = {**self.headers, "X-Synthetic-Sender": "synthetic-wxid-denied"}
        self.assertEqual(self.post(headers=denied_headers).status_code, 403)

        # An allowlisted sender still cannot enter Core when the trusted adapter
        # has no authenticated consent evidence in its server-created identity.
        original_identity = self.provider.identity
        self.provider.identity = TrustedChannelIdentity(
            "wechat", "synthetic-principal-1", "trusted_adapter_v1", "synthetic-hermes",
            "synthetic-account", "",
        )
        self.assertEqual(self.post().status_code, 401)
        self.provider.identity = original_identity

        spoofed = {**self.payload, "source_channel": "web", "principal": "owner",
                   "identity": {"subject": "owner"}, "consent": True,
                   "consent_evidence": {"kind": "user_approved"}}
        self.assertEqual(self.post(payload=spoofed).status_code, 400)

        attached = {**self.payload, "source_event_id": "synthetic-attachment-event",
                    "attachment_refs": [{"capture_id": "a" * 32, "sha256": "b" * 64}]}
        self.assertEqual(self.post(payload=attached).status_code, 501)
        self.assertEqual(list(self.raw.glob("Inbox-*.md")), [])
        self.assertEqual(list(self.review.glob("*.md")), [])
        self.assertEqual(list((self.state / "captures").glob("*.json")), [])

    def test_missing_raw_after_restart_is_recovery_required_and_not_recreated(self):
        first = self.post()
        self.assertEqual(first.status_code, 202, first.text)
        state_path = self.state / "captures" / (first.json()["inbox_id"] + ".json")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        raw_path = self.raw / state["raw_path"]
        raw_path.unlink()

        restarted_service = CaptureService(str(self.raw), str(self.review), str(self.state))
        restarted_app = FastAPI()
        restarted_app.include_router(create_trusted_channel_router(restarted_service, self.provider))
        restarted_client = TestClient(restarted_app)
        try:
            with patch.object(restarted_service, "mark_scheduled", return_value=False):
                replay = restarted_client.post("/api/internal/v1/channel-events", json=self.payload,
                                               headers=self.headers)
            self.assertEqual(replay.status_code, 503, replay.text)
            self.assertFalse(raw_path.exists())
            self.assertTrue(state_path.exists())
        finally:
            restarted_client.close()


if __name__ == "__main__":
    unittest.main()
