import hashlib
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from secondbrain_core.app import create_app
from secondbrain_core.modules.review_promote.approval import ApprovalRequestError


class B1bPromoteAppFactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.review = self.root / "review"
        self.knowledge = self.root / "knowledge"
        self.raw = self.root / "raw"
        self.state = self.root / "state"
        for path in (self.review, self.knowledge, self.raw, self.state):
            path.mkdir(mode=0o700)
        self.source = (b"---\ntype: review\nstatus: pending\ntags:\n  - synthetic\n"
                       b"custom_field: preserve-me\nreview_status: pending\n---\n"
                       b"# Synthetic approved note\nBody remains exact.\n")
        (self.review / "candidate.md").write_bytes(self.source)
        self.app_password = self.root / "app.password"
        self.app_password.write_text("synthetic-app-password", encoding="utf-8")
        self.app_password.chmod(0o600)
        self.unlock_secret = self.root / "promote.secret"
        self.unlock_secret.write_text("synthetic-independent-promote-secret-96-bytes-" + "x" * 48,
                                      encoding="utf-8")
        self.unlock_secret.chmod(0o600)
        self.env = {
            "SB_REVIEW_ROOT": str(self.review),
            "SB_CAPTURE_RAW_ROOT": str(self.raw),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge),
            "SB_PROMOTE_STATE_ROOT": str(self.state),
            "SB_DASHBOARD_ORIGINS": "https://testserver",
            "SB_CORE_ALLOWED_HOSTS": "testserver",
            "SB_APP_PASSWORD_FILE": str(self.app_password),
            "SB_PROMOTE_UNLOCK_SECRET_FILE": str(self.unlock_secret),
            "SB_PROMOTE_UNLOCK_TTL": "900",
            "SB_HERMES_API_URL": "",
            "SB_HERMES_API_KEY": "",
            "SB_PROMOTE_ENABLED": "true",
        }
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.headers = {"Origin": "https://testserver"}
        self.login()

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def _create_app(self):
        with patch.dict(os.environ, self.env, clear=True):
            return create_app()

    def login(self):
        response = self.client.post("/api/auth/login", json={"password": "synthetic-app-password"},
                                   headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def unlock(self, client=None):
        active = client or self.client
        response = active.post("/api/promote/auth/unlock",
                               json={"passphrase": self.unlock_secret.read_text()},
                               headers=self.headers)
        return response

    def preview(self, client=None):
        active = client or self.client
        return active.post("/api/promote/review/preview", headers=self.headers, json={
            "review_path": "candidate.md",
            "review_sha256": hashlib.sha256(self.source).hexdigest(),
            "target_filename": "synthetic-approved.md",
        })

    def confirm(self, preview_id, client=None):
        return (client or self.client).post("/api/promote/review/confirm", headers=self.headers,
                                            json={"preview_id": preview_id,
                                                  "confirm_intent": "promote_review_to_knowledge"})

    def test_preview_is_exact_read_only_and_old_approve_fails_closed(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        body = response.json()
        output = body["projected_markdown"].encode()
        self.assertEqual(hashlib.sha256(output).hexdigest(), body["output_sha256"])
        self.assertIn("custom_field: preserve-me", body["projected_markdown"])
        self.assertIn("  - synthetic", body["projected_markdown"])
        self.assertEqual((self.review / "candidate.md").read_bytes(), self.source)
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(list(self.knowledge.iterdir()), [])

        legacy = self.client.post("/api/promote/review/approve", headers=self.headers,
                                  json={"request_id": "forged", "review_path": "candidate.md",
                                        "review_sha256": hashlib.sha256(self.source).hexdigest(),
                                        "target_filename": "legacy.md"})
        self.assertEqual(legacy.status_code, 423)
        self.assertEqual(legacy.json()["detail"]["code"], "legacy_approve_disabled")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])

    def test_disabled_confirm_returns_423_with_zero_durable_side_effects(self):
        self.client.close()
        self.env["SB_PROMOTE_ENABLED"] = "false"
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        response = self.confirm(preview["preview_id"])
        self.assertEqual(response.status_code, 423, response.text)
        self.assertEqual(response.json()["detail"]["code"], "promote_disabled")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_create_app_unlock_confirm_exact_hash_audit_status_and_same_ticket_retry(self):
        self.env["SB_PROMOTE_ENABLED"] = "true"
        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        unlock = self.unlock()
        self.assertEqual(unlock.status_code, 200, unlock.text)
        cookie = unlock.headers.get("set-cookie", "").lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("max-age=900", cookie)

        preview_response = self.preview()
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        expected_output = preview["projected_markdown"].encode("utf-8")
        first = self.confirm(preview["preview_id"])
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "promoted")
        target = self.knowledge / "synthetic-approved.md"
        self.assertEqual(target.read_bytes(), expected_output)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), preview["output_sha256"])
        self.assertEqual((self.review / "candidate.md").read_bytes(), self.source)

        claim_files = list((self.state / "approvals").glob("*.claim"))
        self.assertEqual(len(claim_files), 1)
        claim = json.loads(claim_files[0].read_text())
        self.assertEqual(claim["version"], 1)
        self.assertEqual(set(claim), {"version", "version_key", "review_path", "review_sha256",
                                      "request_id", "target_filename", "approver_subject", "approved_at"})
        audit = [json.loads(line) for line in (self.state / "audit.jsonl").read_text().splitlines()]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["output_sha256"], preview["output_sha256"])

        operation = self.client.get("/api/promote/operations/" + preview["request_id"],
                                    headers=self.headers)
        self.assertEqual(operation.status_code, 200, operation.text)
        self.assertEqual(operation.json()["status"], "promoted")
        second = self.confirm(preview["preview_id"])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "already_promoted")
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)
        self.assertEqual(len(list(self.knowledge.iterdir())), 1)

        # A process restart drops the in-memory unlock session, but durable completed
        # operations remain verifiable after fresh App and Promote authorization.
        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        restored = self.client.get("/api/promote/operations/" + preview["request_id"], headers=self.headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["status"], "promoted")

    def test_source_drift_target_collision_session_rotation_and_expiry_fail_closed(self):
        self.assertEqual(self.unlock().status_code, 200)
        first = self.preview().json()
        (self.review / "candidate.md").write_bytes(self.source + b"drift\n")
        changed = self.confirm(first["preview_id"])
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json()["detail"]["code"], "source_stale")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        (self.review / "candidate.md").write_bytes(self.source)

        second = self.preview().json()
        (self.knowledge / "synthetic-approved.md").write_text("occupied", encoding="utf-8")
        occupied = self.confirm(second["preview_id"])
        self.assertEqual(occupied.status_code, 409)
        self.assertEqual(occupied.json()["detail"]["code"], "target_occupied")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        (self.knowledge / "synthetic-approved.md").unlink()

        third = self.preview().json()
        self.client.post("/api/auth/logout", headers=self.headers, json={})
        self.login()
        rotated = self.confirm(third["preview_id"])
        self.assertEqual(rotated.status_code, 401)

        self.assertEqual(self.unlock().status_code, 200)
        fourth = self.preview().json()
        future = time.time() + 601
        with patch("secondbrain_core.modules.review_promote.b1b.time.time", return_value=future):
            expired = self.confirm(fourth["preview_id"])
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(expired.json()["detail"]["code"], "preview_expired")

    def test_cross_session_ticket_is_rejected_and_unlock_attempts_are_rate_limited(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        second_client = TestClient(self.app, base_url="https://testserver")
        second_client.post("/api/auth/login", json={"password": "synthetic-app-password"},
                           headers=self.headers)
        self.assertEqual(self.unlock(second_client).status_code, 200)
        crossed = self.confirm(preview["preview_id"], second_client)
        self.assertEqual(crossed.status_code, 401)
        self.assertEqual(crossed.json()["detail"]["code"], "preview_session_mismatch")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        second_client.close()

        for _ in range(5):
            bad = self.client.post("/api/promote/auth/unlock", headers=self.headers,
                                   json={"passphrase": "incorrect-synthetic-passphrase"})
            self.assertEqual(bad.status_code, 401)
        limited = self.client.post("/api/promote/auth/unlock", headers=self.headers,
                                   json={"passphrase": self.unlock_secret.read_text()})
        self.assertEqual(limited.status_code, 429)

    def test_concurrent_confirm_of_one_ticket_produces_one_claim_output_and_audit(self):
        self.env["SB_PROMOTE_ENABLED"] = "true"
        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.confirm(preview["preview_id"]), range(2)))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 200])
        self.assertEqual({response.json()["status"] for response in responses}, {"promoted", "already_promoted"})
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 1)
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)
        self.assertEqual(len(list(self.knowledge.iterdir())), 1)

    def test_missing_secret_http_and_wrong_origin_fail_closed(self):
        http_client = TestClient(self.app, base_url="http://testserver")
        http_response = http_client.post("/api/promote/auth/unlock", headers=self.headers,
                                         json={"passphrase": "synthetic"})
        self.assertEqual(http_response.status_code, 403)
        http_client.close()
        wrong_origin = self.client.post("/api/promote/review/preview", headers={"Origin": "https://evil.invalid"},
                                        json={"review_path": "candidate.md",
                                              "review_sha256": hashlib.sha256(self.source).hexdigest(),
                                              "target_filename": "safe.md"})
        self.assertEqual(wrong_origin.status_code, 403)
        self.assertEqual(wrong_origin.headers.get("cache-control"), "private, no-store")

        self.env.pop("SB_PROMOTE_UNLOCK_SECRET_FILE")
        missing = self._create_app()
        missing_client = TestClient(missing, base_url="https://testserver")
        self.assertEqual(missing_client.post("/api/auth/login", json={"password": "synthetic-app-password"},
                                             headers=self.headers).status_code, 200)
        denied = missing_client.post("/api/promote/auth/unlock", json={"passphrase": "anything"},
                                     headers=self.headers)
        self.assertEqual(denied.status_code, 503)
        missing_client.close()

    def test_audit_failure_is_redacted_and_same_operation_recovers(self):
        self.env["SB_PROMOTE_ENABLED"] = "true"
        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        from secondbrain_core.modules.review_promote import worker
        original = worker._append_audit
        calls = {"count": 0}

        def fail_once(fd, record):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("/private/synthetic/path must not leak")
            return original(fd, record)

        with patch("secondbrain_core.modules.review_promote.worker._append_audit", side_effect=fail_once):
            failed = self.confirm(preview["preview_id"])
        self.assertIn(failed.status_code, (409, 503))
        self.assertNotIn("/private/synthetic/path", failed.text)
        self.assertTrue((self.knowledge / "synthetic-approved.md").exists())
        retry = self.confirm(preview["preview_id"])
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["status"], "already_promoted")
        operation = self.client.get("/api/promote/operations/" + preview["request_id"], headers=self.headers)
        self.assertEqual(operation.status_code, 200)
        self.assertEqual(operation.json()["status"], "promoted")
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)

    def test_restart_after_durable_confirm_is_recovery_required_and_blocks_new_request_id(self):
        self.env["SB_PROMOTE_ENABLED"] = "true"
        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        with patch("secondbrain_core.modules.review_promote.service.PromoteService.approve_and_promote_as",
                   side_effect=ApprovalRequestError("synthetic interruption; recovery required")):
            interrupted = self.confirm(preview["preview_id"])
        self.assertEqual(interrupted.status_code, 503)
        self.assertEqual(len(list((self.state / "b1b-operations").glob("*.json"))), 1)
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])

        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        operation = self.client.get("/api/promote/operations/" + preview["request_id"],
                                    headers=self.headers)
        self.assertEqual(operation.status_code, 200, operation.text)
        self.assertEqual(operation.json()["status"], "recovery_required")
        another_preview = self.preview()
        self.assertEqual(another_preview.status_code, 409)
        self.assertEqual(another_preview.json()["detail"]["code"], "operation_recovery_required")
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())

    def test_status_reconciles_output_and_audit_after_final_decision_write_failure(self):
        self.env["SB_PROMOTE_ENABLED"] = "true"
        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        from secondbrain_core.modules.review_promote.approval import ReviewDecisionStore
        original = ReviewDecisionStore.set
        calls = {"count": 0}

        def fail_final_decision_once(store, review_path, digest, status, **fields):
            if status == "promoted" and calls["count"] == 0:
                calls["count"] += 1
                raise OSError("synthetic decision write interruption")
            return original(store, review_path, digest, status, **fields)

        with patch.object(ReviewDecisionStore, "set", fail_final_decision_once):
            interrupted = self.confirm(preview["preview_id"])
        self.assertEqual(interrupted.status_code, 503)
        self.assertTrue((self.knowledge / "synthetic-approved.md").exists())

        self.client.close()
        self.app = self._create_app()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        operation = self.client.get("/api/promote/operations/" + preview["request_id"],
                                    headers=self.headers)
        self.assertEqual(operation.status_code, 200, operation.text)
        self.assertEqual(operation.json()["status"], "promoted")


if __name__ == "__main__":
    unittest.main()
