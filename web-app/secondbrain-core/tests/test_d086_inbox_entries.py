import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from secondbrain_core.app import create_app


ORIGIN = "https://testserver"


class D086InboxEntryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.raw, self.review, self.knowledge, self.state = [self.root / name
                                                               for name in ("raw", "review", "knowledge", "state")]
        for path in (self.raw, self.review, self.knowledge, self.state):
            path.mkdir(mode=0o700)
        self.password = self.root / "app.password"
        self.password.write_text("synthetic-d086-app-password")
        self.password.chmod(0o600)
        self.secret = self.root / "promote.secret"
        self.secret.write_text("synthetic-unused-promote-secret-" + "x" * 40)
        self.secret.chmod(0o600)
        self.env = {
            "SB_REVIEW_ROOT": str(self.review), "SB_CAPTURE_RAW_ROOT": str(self.raw),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge), "SB_PROMOTE_STATE_ROOT": str(self.state),
            "SB_DASHBOARD_ORIGINS": ORIGIN, "SB_CORE_ALLOWED_HOSTS": "testserver",
            "SB_APP_PASSWORD_FILE": str(self.password), "SB_PROMOTE_UNLOCK_SECRET_FILE": str(self.secret),
            "SB_PROMOTE_ENABLED": "false", "SB_HERMES_API_URL": "", "SB_HERMES_API_KEY": "",
        }
        with patch.dict(os.environ, self.env, clear=True):
            self.app = create_app()
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.headers = {"Origin": ORIGIN}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def login(self):
        result = self.client.post("/api/auth/login", headers=self.headers,
                                  json={"password": "synthetic-d086-app-password"})
        self.assertEqual(result.status_code, 200, result.text)

    def payload(self, **changes):
        result = {"original_text": "# Explicit synthetic capture\nKeep this exact text.",
                  "source_channel": "web", "source_event_id": "web-event-0001",
                  "occurred_at": "2026-10-20T03:00:00Z", "intent": "explicit_capture",
                  "attachment_refs": []}
        result.update(changes)
        return result

    def test_explicit_capture_is_authenticated_persisted_and_restorable(self):
        self.assertEqual(self.client.post("/api/inbox/entries", headers=self.headers,
                                          json=self.payload()).status_code, 401)
        self.login()
        response = self.client.post("/api/inbox/entries", headers=self.headers, json=self.payload())
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        first = response.json()
        self.assertEqual(first["source"], {"channel": "web", "event_id": "web-event-0001"})
        self.assertEqual(first["intent"], "explicit_capture")
        self.assertEqual(first["consent_evidence"]["kind"], "authenticated_app_explicit_action")
        self.assertEqual(first["consent_evidence"]["subject"], "owner")
        raw_files = list(self.raw.glob("*.md"))
        self.assertEqual(len(raw_files), 1)
        self.assertEqual(raw_files[0].read_text(), self.payload()["original_text"])
        state = json.loads((self.state / "captures" / (first["inbox_id"] + ".json")).read_text())
        self.assertEqual(state["original_text_sha256"], hashlib.sha256(self.payload()["original_text"].encode()).hexdigest())
        self.assertEqual(state["consent_evidence"], first["consent_evidence"])

        replay = self.client.post("/api/inbox/entries", headers=self.headers, json=self.payload())
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertEqual(replay.json()["inbox_id"], first["inbox_id"])
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(len(list(self.raw.glob("*.md"))), 1)
        restored = self.client.get(f"/api/inbox/entries/{first['inbox_id']}", headers=self.headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["source"], first["source"])
        self.assertEqual(restored.json()["intent"], "explicit_capture")
        self.assertEqual(restored.json()["source_ref"]["capture_id"], first["inbox_id"])
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_idempotency_conflict_and_untrusted_or_unsupported_channel_evidence_fail_closed(self):
        self.login()
        first = self.client.post("/api/inbox/entries", headers=self.headers, json=self.payload())
        self.assertEqual(first.status_code, 202, first.text)
        conflict = self.client.post("/api/inbox/entries", headers=self.headers,
                                    json=self.payload(original_text="different text"))
        self.assertEqual(conflict.status_code, 409, conflict.text)
        timestamp_conflict = self.client.post(
            "/api/inbox/entries", headers=self.headers,
            json=self.payload(occurred_at="2026-10-20T04:00:00Z"),
        )
        self.assertEqual(timestamp_conflict.status_code, 409, timestamp_conflict.text)
        forged_consent = self.client.post("/api/inbox/entries", headers=self.headers,
                                          json=self.payload(consent_evidence={"subject": "owner", "consent": True}))
        self.assertEqual(forged_consent.status_code, 400, forged_consent.text)
        unsupported = self.client.post("/api/inbox/entries", headers=self.headers,
                                       json=self.payload(source_channel="hermes"))
        self.assertEqual(unsupported.status_code, 501, unsupported.text)
        approved = self.client.post("/api/inbox/entries", headers=self.headers,
                                    json=self.payload(intent="approved_suggestion"))
        self.assertEqual(approved.status_code, 409, approved.text)
        malformed_intent = self.client.post("/api/inbox/entries", headers=self.headers,
                                            json=self.payload(intent=["task_intent"]))
        self.assertEqual(malformed_intent.status_code, 400, malformed_intent.text)
        attachments = self.client.post("/api/inbox/entries", headers=self.headers,
                                       json=self.payload(attachment_refs=["/some/path"]))
        self.assertEqual(attachments.status_code, 501, attachments.text)
        self.assertEqual(len(list(self.raw.glob("*.md"))), 1)
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_journal_and_task_intents_are_stored_in_inbox_without_execution(self):
        self.login()
        for intent, event_id in (("journal_intent", "journal-1"), ("task_intent", "task-1")):
            response = self.client.post("/api/inbox/entries", headers=self.headers,
                                        json=self.payload(source_event_id=event_id, intent=intent))
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["intent"], intent)
        self.assertEqual(len(list(self.raw.glob("*.md"))), 2)
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertFalse((self.state / "journal").exists())
        self.assertFalse((self.state / "tasks").exists())
