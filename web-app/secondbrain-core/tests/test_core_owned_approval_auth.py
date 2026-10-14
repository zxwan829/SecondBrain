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
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
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
        self.assertEqual(self.client.get("/api/promote/review/items", headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get("/api/promote/review/items/candidate.md", headers=self.headers).status_code, 401)
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

    def test_app_session_is_single_login_and_promote_stays_disabled(self):
        app_password_file = self.root / "app.password"
        app_password_file.write_text("correct horse battery staple", encoding="utf-8")
        app_password_file.chmod(0o600)
        env = {
            "SB_REVIEW_ROOT": str(self.review),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge),
            "SB_PROMOTE_STATE_ROOT": str(self.root / "app-state"),
            "SB_DASHBOARD_ORIGINS": "https://testserver",
            "SB_CORE_ALLOWED_HOSTS": "testserver",
            "SB_APP_PASSWORD_FILE": str(app_password_file),
            "SB_HERMES_API_URL": "http://hermes.invalid",
            "SB_HERMES_API_KEY": "test-server-only-key",
        }
        app_state = self.root / "app-state"
        app_state.mkdir(mode=0o700)
        with patch.dict(os.environ, env):
            app = create_app()
        client = TestClient(app, base_url="https://testserver")
        self.assertEqual(client.get("/api/promote/status").status_code, 401)
        login = client.post("/api/auth/login", json={"password": "correct horse battery staple"},
                            headers={"Origin": "https://testserver"})
        self.assertEqual(login.status_code, 200, login.text)
        cookie = login.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("path=/", cookie)
        self.assertEqual(client.get("/api/promote/status").json(),
                         {"status": "ok", "promote_enabled": False})
        denied = client.post("/api/promote/review/defer", json={}, headers={"Origin": "https://evil.invalid"})
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn("access-control-allow-origin", denied.headers)
        bad_host = client.get("/health", headers={"Host": "attacker.invalid"})
        self.assertEqual(bad_host.status_code, 400)
        client.close()

    def test_unlocked_browser_can_approve_directly_and_retry_idempotently(self):
        login = self.unlock()
        self.assertEqual(login.status_code, 200, login.text)
        cookie = login.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("path=/api/promote", cookie)
        self.assertEqual(self.client.get("/api/promote/review/items", headers=self.headers).status_code, 200)
        first = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        second = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "promoted")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "already_promoted")
        self.assertTrue((self.knowledge / "approved.md").is_file())
        audit = (self.state / "audit.jsonl").read_text()
        self.assertIn('"approver_subject":"owner"', audit)
        self.assertEqual(self.client.get("/api/promote/review/items", headers=self.headers)
                         .json()["items"][0]["decision"]["status"], "promoted")
        history = self.client.get("/api/promote/review/items/candidate.md", headers=self.headers)
        self.assertEqual([event["status"] for event in history.json()["decision"]["history"]],
                         ["approved", "promoting", "promoted"])
        cannot_defer = self.client.post("/api/promote/review/defer", json={
            "review_path": self.body["review_path"], "review_sha256": self.body["review_sha256"]
        }, headers=self.headers)
        self.assertEqual(cannot_defer.status_code, 409)

    def test_audit_failure_after_file_creation_is_visible_and_retry_reconciles(self):
        self.assertEqual(self.unlock().status_code, 200)
        from secondbrain_core.modules.review_promote import worker
        original = worker._append_audit
        calls = {"count": 0}

        def fail_once(fd, record):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("simulated audit storage failure")
            return original(fd, record)

        with patch("secondbrain_core.modules.review_promote.worker._append_audit", side_effect=fail_once):
            failed = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
            self.assertEqual(failed.status_code, 409)
            self.assertTrue((self.knowledge / "approved.md").is_file())
            state = self.client.get("/api/promote/review/items", headers=self.headers).json()["items"][0]["decision"]
            self.assertEqual(state["status"], "failed")
            retry = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["status"], "already_promoted")
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)
        self.assertEqual(self.client.get("/api/promote/review/items", headers=self.headers)
                         .json()["items"][0]["decision"]["status"], "promoted")

    def test_defer_is_persisted_per_review_version_and_does_not_write_knowledge(self):
        self.assertEqual(self.unlock().status_code, 200)
        deferred = self.client.post("/api/promote/review/defer", json={
            "review_path": self.body["review_path"],
            "review_sha256": self.body["review_sha256"],
        }, headers=self.headers)
        self.assertEqual(deferred.status_code, 200, deferred.text)
        self.assertEqual(deferred.json()["status"], "deferred")
        detail = self.client.get("/api/promote/review/items/candidate.md", headers=self.headers)
        self.assertEqual(detail.json()["decision"]["status"], "deferred")
        self.assertFalse((self.knowledge / "approved.md").exists())
        changed = self.content + b"changed\n"
        (self.review / "candidate.md").write_bytes(changed)
        changed_detail = self.client.get("/api/promote/review/items/candidate.md", headers=self.headers)
        self.assertEqual(changed_detail.json()["decision"]["status"], "pending")

    def test_torn_audit_tail_is_repaired_on_retry(self):
        self.assertEqual(self.unlock().status_code, 200)
        (self.state / "audit.jsonl").write_bytes(b'{"event":"interrupted"')
        response = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        audit_lines = (self.state / "audit.jsonl").read_text().splitlines()
        self.assertEqual(len(audit_lines), 1)
        self.assertIn('"event":"promoted"', audit_lines[0])

    def test_review_list_and_detail_are_owner_only_and_return_real_content_and_state(self):
        self.assertEqual(self.unlock().status_code, 200)
        listing = self.client.get("/api/promote/review/items", headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["status"], "pending")
        detail = self.client.get("/api/promote/review/items/candidate.md", headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["content"], self.content.decode())
        self.assertEqual(detail.json()["review_sha256"], self.body["review_sha256"])
        self.assertEqual(detail.json()["status"], "pending")
        self.assertEqual(self.client.get("/api/promote/review/items/missing.md", headers=self.headers).status_code, 404)

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

    def test_promote_disabled_blocks_approval_without_creating_records(self):
        app = FastAPI()
        app.include_router(create_core_router(self.service, self.review, self.auth,
                                              promote_enabled=False), prefix="/api/promote")
        client = TestClient(app, base_url="https://testserver")
        self.assertEqual(client.post("/api/promote/auth/unlock",
                                     json={"passphrase": self.unlock_secret.decode("ascii")},
                                     headers=self.headers).status_code, 200)
        self.assertEqual(client.get("/api/promote/status", headers=self.headers).json(),
                         {"status": "ok", "promote_enabled": False})
        response = client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 423)
        self.assertFalse((self.knowledge / "approved.md").exists())
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        client.close()


if __name__ == "__main__":
    unittest.main()
