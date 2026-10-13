"""HTTP integration coverage for the registered approval router.

Hermes' host auth middleware is represented by the test middleware below: only
the test operator cookie creates the verified request.state.session expected by
the plugin contract. This tests route wiring and handler behavior, not Hermes'
production session implementation or filesystem mount isolation.
"""
import hashlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import plugin_api
from dashboard_approval import FileApprovalSource
from promote_worker import PromoteWorker


class ApprovalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.temp.name))
        self.review = self.root / "review"
        self.queue = self.root / "approval-queue"
        self.knowledge = self.root / "knowledge"
        self.audit = self.root / "audit"
        for directory in (self.review, self.queue, self.knowledge, self.audit):
            directory.mkdir()
        self.review_bytes = (b"---\ntype: review\nstatus: pending\nsource_type: external-text\n"
                             b"captured_at: 2026-10-12T00:00:00Z\nreview_status: pending\n"
                             b"tags: [test]\n---\n# HTTP-approved note\n\nIsolated integration test.\n")
        (self.review / "candidate.md").write_bytes(self.review_bytes)
        self.digest = hashlib.sha256(self.review_bytes).hexdigest()
        self.old_review_root = plugin_api.REVIEW_ROOT
        plugin_api.REVIEW_ROOT = self.review
        os.environ["SECONDBRAIN_APPROVAL_QUEUE"] = str(self.queue)

        app = FastAPI()
        app.state.auth_required = True

        @app.middleware("http")
        async def hermes_auth_contract(request, call_next):
            # Simulates Hermes' already-verified dashboard session context.
            if request.cookies.get("test_dashboard_session") == "valid":
                request.state.session = SimpleNamespace(
                    user_id="joe",
                    provider="basic",
                    expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(),
                )
            response = await call_next(request)
            return response

        app.include_router(plugin_api.router, prefix="/api/plugins/secondbrain")
        self.client = TestClient(app)
        self.base_headers = {"Origin": "http://testserver"}
        self.body = {
            "request_id": "http-approve-001",
            "review_path": "candidate.md",
            "review_sha256": self.digest,
            "target_filename": "http-approved.md",
        }

    def tearDown(self):
        self.client.close()
        plugin_api.REVIEW_ROOT = self.old_review_root
        os.environ.pop("SECONDBRAIN_APPROVAL_QUEUE", None)
        self.temp.cleanup()

    def approve(self, body=None, headers=None, logged_in=True):
        if logged_in:
            self.client.cookies.set("test_dashboard_session", "valid")
        else:
            self.client.cookies.delete("test_dashboard_session")
        return self.client.post(
            "/api/plugins/secondbrain/review/approve",
            json=body or self.body,
            headers=headers or self.base_headers,
        )

    def test_registered_post_route_allows_verified_login_and_worker_promotes(self):
        response = self.approve(dict(self.body, approved=False, approver_subject="agent:fake"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "approved")
        record = next(self.queue.glob("*.json"))
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)
        worker = PromoteWorker(
            str(self.review), str(self.knowledge), str(self.audit / "events.jsonl"),
            FileApprovalSource(str(self.queue)),
        )
        result = worker.promote(self.body["request_id"], self.body["review_path"], self.digest)
        self.assertEqual(result["status"], "promoted")
        self.assertTrue((self.knowledge / "http-approved.md").is_file())
        promoted_text = (self.knowledge / "http-approved.md").read_text()
        self.assertIn("type: knowledge", promoted_text)
        self.assertIn("status: active", promoted_text)
        self.assertNotIn("review_status:", promoted_text)
        audit = (self.audit / "events.jsonl").read_text()
        self.assertIn('"approver_subject":"joe"', audit)

    def test_missing_login_is_rejected_even_when_agent_claims_approved(self):
        response = self.approve(dict(self.body, approved=True), logged_in=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(self.queue.iterdir()), [])

    def test_illegal_origin_is_rejected(self):
        response = self.approve(headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(response.status_code, 403)

    def test_review_digest_mismatch_is_rejected(self):
        response = self.approve(dict(self.body, review_sha256="0" * 64))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(list(self.queue.iterdir()), [])

    def test_duplicate_request_id_is_idempotent(self):
        first = self.approve()
        second = self.approve()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["status"], "approved")
        self.assertEqual(second.json()["status"], "already_approved")
        self.assertEqual(len(list(self.queue.glob("*.json"))), 1)

    def test_review_list_exposes_safe_path_digest_and_existing_unicode_filename(self):
        name = "20261012-用户想法.md"
        (self.review / name).write_bytes(self.review_bytes)
        response = self.client.get("/api/plugins/secondbrain/review/items")
        self.assertEqual(response.status_code, 200, response.text)
        item = next(item for item in response.json()["items"] if item["review_path"] == name)
        self.assertEqual(item["review_sha256"], self.digest)
        self.assertEqual(item["target_filename"], name)
        self.assertEqual(item["title"], "HTTP-approved note")

    def test_approval_accepts_existing_unicode_knowledge_filename(self):
        response = self.approve(dict(self.body, target_filename="用户运营复购.md"))
        self.assertEqual(response.status_code, 200, response.text)

    def test_worker_rejects_agent_claim_without_server_approval_record(self):
        worker = PromoteWorker(
            str(self.review), str(self.knowledge), str(self.audit / "events.jsonl"),
            FileApprovalSource(str(self.queue)),
        )
        with self.assertRaisesRegex(Exception, "No trusted approval"):
            worker.promote(self.body["request_id"], self.body["review_path"], self.digest)
        self.assertFalse((self.knowledge / "http-approved.md").exists())


if __name__ == "__main__":
    unittest.main()
