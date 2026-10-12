import hashlib
import os
import tempfile
import unittest
import base64
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.review_promote.core_auth import CorePromoteAuth
from secondbrain_core.app import create_app
from secondbrain_core.modules.review_promote.http import create_core_router
from secondbrain_core.modules.review_promote.service import PromoteService


class CoreOwnedApprovalAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review, self.knowledge, self.state = [self.root / n for n in ("review", "knowledge", "state")]
        for path in (self.review, self.knowledge, self.state):
            path.mkdir(mode=0o700)
        (self.state / "approvals").mkdir(mode=0o700)
        self.unlock_secret = base64.urlsafe_b64encode(os.urandom(48))
        self.secret_file = self.root / "unlock.secret"
        self.secret_file.write_bytes(self.unlock_secret)
        self.secret_file.chmod(0o600)
        self.content = (b"---\ntype: review\nstatus: pending\nsource_type: external-text\n"
                        b"captured_at: 2026-10-12T00:00:00Z\nreview_status: pending\n---\n"
                        b"# Authorized note\nCore-only approval test.\n")
        (self.review / "candidate.md").write_bytes(self.content)
        self.body = {"request_id": "core-owner-1", "review_path": "candidate.md",
                     "review_sha256": hashlib.sha256(self.content).hexdigest(),
                     "target_filename": "approved.md"}
        self.service = PromoteService(str(self.review), str(self.knowledge),
                                      str(self.state / "approvals"), str(self.state / "audit.jsonl"))
        self.auth = CorePromoteAuth(str(self.secret_file), ["https://testserver"])
        app = FastAPI()
        app.include_router(create_core_router(self.service, self.review, self.auth), prefix="/api/promote")
        self.client = TestClient(app, base_url="https://testserver")
        self.headers = {"Origin": "https://testserver"}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def unlock(self):
        return self.client.post("/api/promote/auth/unlock",
                                json={"passphrase": self.unlock_secret.decode("ascii")},
                                headers=self.headers)

    def test_no_credentials_or_forged_identity_fields_cannot_approve(self):
        body = dict(self.body, user_id="owner", session={"provider": "basic", "verified": True}, approved=True)
        response = self.client.post("/api/promote/review/approve", json=body, headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertFalse((self.knowledge / "approved.md").exists())
        self.assertEqual(list((self.state / "approvals").iterdir()), [])

    def test_wrong_unlock_and_wrong_origin_are_rejected(self):
        bad = self.client.post("/api/promote/auth/unlock", json={"passphrase": "x" * 48}, headers=self.headers)
        self.assertEqual(bad.status_code, 401)
        wrong_origin = self.client.post("/api/promote/auth/unlock",
                                        json={"passphrase": self.unlock_secret.decode("ascii")},
                                        headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(wrong_origin.status_code, 403)
        self.assertNotIn(CorePromoteAuth.COOKIE_NAME, self.client.cookies)

    def test_http_transport_is_rejected(self):
        http_client = TestClient(self.client.app, base_url="http://testserver")
        response = http_client.post("/api/promote/auth/unlock",
                                    json={"passphrase": self.unlock_secret.decode("ascii")},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 403)
        http_client.close()

    def test_app_cors_allows_only_dashboard_origin_with_credentials(self):
        env = {
            "SB_REVIEW_ROOT": str(self.review),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge),
            "SB_PROMOTE_STATE_ROOT": str(self.root / "app-state"),
            "SB_DASHBOARD_ORIGINS": "https://testserver",
            "SB_PROMOTE_UNLOCK_SECRET_FILE": str(self.secret_file),
        }
        app_state = self.root / "app-state"
        app_state.mkdir(mode=0o700)
        with patch.dict(os.environ, env):
            app = create_app()
        client = TestClient(app, base_url="https://testserver")
        allowed = client.options("/api/promote/auth/unlock", headers={
            "Origin": "https://testserver",
            "Access-Control-Request-Method": "POST",
        })
        denied = client.options("/api/promote/auth/unlock", headers={
            "Origin": "https://evil.invalid",
            "Access-Control-Request-Method": "POST",
        })
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "https://testserver")
        self.assertEqual(allowed.headers.get("access-control-allow-credentials"), "true")
        self.assertNotIn("access-control-allow-origin", denied.headers)
        client.close()

    def test_unlocked_browser_can_approve_directly_and_retry_idempotently(self):
        login = self.unlock()
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("httponly", login.headers["set-cookie"].lower())
        self.assertIn("secure", login.headers["set-cookie"].lower())
        first = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        second = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "promoted")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "already_promoted")
        self.assertTrue((self.knowledge / "approved.md").is_file())
        audit = (self.state / "audit.jsonl").read_text()
        self.assertIn('"approver_subject":"owner"', audit)

    def test_review_change_invalidates_approved_digest(self):
        self.assertEqual(self.unlock().status_code, 200)
        changed = dict(self.body, review_sha256="0" * 64)
        response = self.client.post("/api/promote/review/approve", json=changed, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_lock_revokes_core_session(self):
        self.assertEqual(self.unlock().status_code, 200)
        locked = self.client.post("/api/promote/auth/lock", headers=self.headers)
        self.assertEqual(locked.status_code, 200)
        response = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
