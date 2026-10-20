import hashlib
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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
                                                  "confirm_intent": "promote_exact_preview"})

    def test_preview_is_exact_read_only_and_old_approve_fails_closed(self):
        wrong_unlock_field = self.client.post("/api/promote/auth/unlock", headers=self.headers,
                                              json={"password": self.unlock_secret.read_text()})
        self.assertEqual(wrong_unlock_field.status_code, 401)
        self.assertEqual(wrong_unlock_field.json()["detail"]["code"], "promote_unlock_rejected")
        self.assertEqual(self.unlock().status_code, 200)
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        body = response.json()
        self.assertEqual(body["source_sha256"], hashlib.sha256(self.source).hexdigest())
        self.assertEqual(body["target_precondition"], {"exists": False})
        self.assertIsInstance(body["expires_at"], str)
        expiry = datetime.fromisoformat(body["expires_at"]).timestamp()
        self.assertGreater(expiry, time.time())
        self.assertLessEqual(expiry - time.time(), 600)
        self.assertIsInstance(body["change_summary"], list)
        self.assertTrue(all(isinstance(item, str) for item in body["change_summary"]))
        self.assertNotIn("review_sha256", body)
        self.assertNotIn("expires_in", body)
        self.assertNotIn("target_available", body)
        output = body["projected_markdown"].encode()
        self.assertEqual(hashlib.sha256(output).hexdigest(), body["output_sha256"])
        self.assertIn("custom_field: preserve-me", body["projected_markdown"])
        self.assertIn("  - synthetic", body["projected_markdown"])
        self.assertEqual((self.review / "candidate.md").read_bytes(), self.source)
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(list(self.knowledge.iterdir()), [])

        wrong_intent = self.client.post("/api/promote/review/confirm", headers=self.headers,
                                        json={"preview_id": body["preview_id"],
                                              "confirm_intent": "promote_review_to_knowledge"})
        self.assertEqual(wrong_intent.status_code, 409)
        self.assertEqual(wrong_intent.json()["detail"]["code"], "confirmation_invalid")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertEqual(list(self.knowledge.iterdir()), [])

        legacy = self.client.post("/api/promote/review/approve", headers=self.headers,
                                  json={"request_id": "forged", "review_path": "candidate.md",
                                        "review_sha256": hashlib.sha256(self.source).hexdigest(),
                                        "target_filename": "legacy.md"})
        self.assertEqual(legacy.status_code, 423)
        self.assertEqual(legacy.json()["detail"]["code"], "legacy_approve_disabled")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])

    def test_unset_promote_gate_defaults_off_with_zero_durable_side_effects(self):
        self.client.close()
        self.env.pop("SB_PROMOTE_ENABLED", None)
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
        self.assertEqual(operation.json()["request_id"], preview["request_id"])
        self.assertEqual(operation.json()["output_sha256"], preview["output_sha256"])
        with patch("secondbrain_core.modules.review_promote.provenance.PromoteProvenanceVerifier.verify",
                   autospec=True) as verify_source:
            search = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers)
            verify_source.assert_not_called()
        self.assertEqual(search.status_code, 200, search.text)
        row = next(item for item in search.json()["items"] if item["title"] == "Synthetic approved note")
        self.assertEqual(row["provenance_status"], "unverified")
        source = self.client.get(f"/api/knowledge/items/{row['id']}/source", headers=self.headers)
        self.assertEqual(source.status_code, 200, source.text)
        self.assertEqual(source.json(), {
            "status": "available", "provenance_status": "verified",
            "source": {"kind": "review", "ref": "candidate.md",
                       "sha256": hashlib.sha256(self.source).hexdigest(),
                       "request_id": preview["request_id"]},
        })
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

    def test_promote_enabled_refuses_same_uid_subprocess_candidate_before_startup(self):
        self.env["SB_PROMOTE_ENABLED"] = "true"
        self.env["SB_PROMOTE_WORKER_MODE"] = "subprocess"
        self.client.close()
        with self.assertRaisesRegex(RuntimeError, "same-UID subprocess candidate"):
            self._create_app()
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_default_promote_off_allows_subprocess_start_but_confirm_is_read_only(self):
        from secondbrain_core.modules.review_promote.subprocess_worker_client import SubprocessPromoteWorker

        self.env.pop("SB_PROMOTE_ENABLED", None)
        self.env["SB_PROMOTE_WORKER_MODE"] = "subprocess"
        self.client.close()
        with patch("secondbrain_core.app.SubprocessPromoteWorker",
                   wraps=SubprocessPromoteWorker) as worker_factory:
            self.app = self._create_app()
        worker_factory.assert_called_once_with(
            str(self.review), str(self.knowledge), str(self.state / "audit.jsonl"),
            str(self.state / "approvals"),
        )
        self.client = TestClient(self.app, base_url="https://testserver")
        self.login()
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview()
        self.assertEqual(preview.status_code, 200, preview.text)
        result = self.confirm(preview.json()["preview_id"])
        self.assertEqual(result.status_code, 423, result.text)
        self.assertEqual(result.json()["detail"]["code"], "promote_disabled")
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_subprocess_protocol_rejection_fails_closed_without_writes(self):
        from types import SimpleNamespace
        from secondbrain_core.modules.review_promote.subprocess_worker_client import SubprocessPromoteWorker
        from secondbrain_core.modules.review_promote.worker import PromotionError

        worker = SubprocessPromoteWorker(
            str(self.review), str(self.knowledge), str(self.state / "audit.jsonl"),
            str(self.state / "approvals"),
        )
        invalid_responses = (
            SimpleNamespace(returncode=1, stdout=b'{"error":"worker_operation_failed"}'),
            SimpleNamespace(returncode=0, stdout=b"not-json"),
            SimpleNamespace(returncode=0, stdout=b'{"status":"promoted","request_id":"other"}'),
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                with patch("secondbrain_core.modules.review_promote.subprocess_worker_client.subprocess.run",
                           return_value=response) as run_worker:
                    with self.assertRaises(PromotionError):
                        worker.promote("synthetic-protocol-request", "candidate.md", "a" * 64)
                    run_worker.assert_called_once()
                self.assertEqual(list((self.state / "approvals").iterdir()), [])
                self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
                self.assertFalse((self.state / "audit.jsonl").exists())
                self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_worker_rejects_malformed_ipc_before_opening_paths(self):
        from secondbrain_core.modules.review_promote.subprocess_worker import _run

        with self.assertRaises(ValueError):
            _run({"request_id": "synthetic-malformed"})
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "b1b-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_legacy_b1a_approval_is_verified_only_for_reconstructed_canonical_bytes(self):
        from secondbrain_core.modules.review_promote.service import PromoteService

        request_id = "legacy-b1a-synthetic-1"
        digest = hashlib.sha256(self.source).hexdigest()
        approved_at = "2026-10-20T00:00:00+00:00"
        service = PromoteService(str(self.review), str(self.knowledge),
                                 str(self.state / "approvals"), str(self.state / "audit.jsonl"))
        result = service.approve_and_promote_as(
            "owner", {"request_id": request_id, "review_path": "candidate.md",
                      "review_sha256": digest, "target_filename": "synthetic-approved.md"},
            str(self.review), approved_at=approved_at,
        )
        self.assertEqual(result["status"], "promoted")
        self.assertFalse((self.state / "b1b-operations" / (request_id + ".json")).exists())
        self.login()
        row = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers).json()["items"][0]
        source = self.client.get(f"/api/knowledge/items/{row['id']}/source", headers=self.headers)
        self.assertEqual(source.status_code, 200, source.text)
        self.assertEqual(source.json(), {
            "status": "available", "provenance_status": "verified",
            "source": {"kind": "review", "ref": "candidate.md", "sha256": digest,
                       "request_id": request_id},
        })

    def test_promoted_source_fails_closed_when_any_pinned_review_evidence_drifts(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        self.assertEqual(self.confirm(preview["preview_id"]).status_code, 200)
        row = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers).json()["items"][0]
        self.assertEqual(row["provenance_status"], "unverified")
        (self.review / "candidate.md").write_bytes(self.source + b"drift\n")
        response = self.client.get(f"/api/knowledge/items/{row['id']}/source", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "status": "unavailable", "provenance_status": "unverified", "source": None,
        })

    def test_promoted_source_requires_exact_audit_digest_and_unique_request_record(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        self.assertEqual(self.confirm(preview["preview_id"]).status_code, 200)
        row = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers).json()["items"][0]
        self.assertEqual(row["provenance_status"], "unverified")
        audit_path = self.state / "audit.jsonl"
        record = json.loads(audit_path.read_text())
        record["output_sha256"] = "0" * 64
        audit_path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        response = self.client.get(f"/api/knowledge/items/{row['id']}/source", headers=self.headers)
        self.assertEqual(response.json(), {
            "status": "unavailable", "provenance_status": "unverified", "source": None,
        })

    def test_promoted_source_rejects_knowledge_and_audit_hashes_that_drift_together(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        self.assertEqual(self.confirm(preview["preview_id"]).status_code, 200)
        target = self.knowledge / "synthetic-approved.md"
        original = target.read_bytes()
        original_digest = hashlib.sha256(original).hexdigest()
        operation_path = self.state / "b1b-operations" / (preview["request_id"] + ".json")
        original_operation = json.loads(operation_path.read_text())
        self.assertEqual(original_operation["confirm_intent"], "promote_exact_preview")
        self.assertEqual(original_operation["output_sha256"], original_digest)

        # Keep marker, Review, Approval, Claim and Decision intact. A coordinated
        # Knowledge + Audit digest rewrite must still fail against rendered bytes
        # and the durable preview output digest.
        drifted = original + b"Unapproved body drift.\n"
        target.write_bytes(drifted)
        audit_path = self.state / "audit.jsonl"
        audit = json.loads(audit_path.read_text())
        audit["output_sha256"] = hashlib.sha256(drifted).hexdigest()
        audit_path.write_text(json.dumps(audit, sort_keys=True, separators=(",", ":")) + "\n")

        search = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers)
        self.assertEqual(search.status_code, 200, search.text)
        item = next(value for value in search.json()["items"]
                    if value["title"] == "Synthetic approved note")
        source = self.client.get(f"/api/knowledge/items/{item['id']}/source", headers=self.headers)
        self.assertEqual(source.status_code, 200, source.text)
        self.assertEqual(source.json(), {
            "status": "unavailable", "provenance_status": "unverified", "source": None,
        })
        self.assertEqual(json.loads(operation_path.read_text()), original_operation)

    def test_promoted_source_requires_the_original_durable_confirmation_intent(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        self.assertEqual(self.confirm(preview["preview_id"]).status_code, 200)
        row = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers).json()["items"][0]
        operation_path = self.state / "b1b-operations" / (preview["request_id"] + ".json")
        operation = json.loads(operation_path.read_text())
        self.assertEqual(operation["confirm_intent"], "promote_exact_preview")
        operation["confirm_intent"] = "promote_other_content"
        operation_path.write_text(json.dumps(operation, sort_keys=True, separators=(",", ":")) + "\n")
        operation_path.chmod(0o600)
        source = self.client.get(f"/api/knowledge/items/{row['id']}/source", headers=self.headers)
        self.assertEqual(source.status_code, 200, source.text)
        self.assertEqual(source.json(), {
            "status": "unavailable", "provenance_status": "unverified", "source": None,
        })

    def test_provenance_audit_reader_fails_closed_on_nonregular_audit_without_blocking(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        self.assertEqual(self.confirm(preview["preview_id"]).status_code, 200)
        row = self.client.get("/api/knowledge/search?q=Synthetic approved", headers=self.headers).json()["items"][0]
        audit_path = self.state / "audit.jsonl"
        audit_path.unlink()
        os.mkfifo(audit_path, 0o600)
        response = self.client.get(f"/api/knowledge/items/{row['id']}/source", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "status": "unavailable", "provenance_status": "unverified", "source": None,
        })

    def test_operation_status_originless_same_origin_get_and_security_denials(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        confirmed = self.confirm(preview["preview_id"])
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        request_id = preview["request_id"]
        path = "/api/promote/operations/" + request_id

        same_origin = self.client.get(path, headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(same_origin.status_code, 200, same_origin.text)
        self.assertEqual(same_origin.json()["request_id"], request_id)
        self.assertEqual(self.client.get(path, headers=self.headers).status_code, 200)

        denied = (
            ({"Origin": "https://attacker.example"}, 403),
            ({"Sec-Fetch-Site": "cross-site"}, 403),
            ({"Origin": "https://testserver", "Sec-Fetch-Site": "cross-site"}, 403),
            ({}, 403),
            ({"Sec-Fetch-Site": "same-site"}, 403),
            ({"Host": "attacker.example", "Sec-Fetch-Site": "same-origin"}, 400),
        )
        for headers, expected in denied:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get(path, headers=headers).status_code, expected)

        no_app = TestClient(self.app, base_url="https://testserver")
        try:
            response = no_app.get(path, headers={"Sec-Fetch-Site": "same-origin"})
            self.assertEqual(response.status_code, 401)
        finally:
            no_app.close()

        app_only = TestClient(self.app, base_url="https://testserver")
        try:
            self.assertEqual(app_only.post("/api/auth/login", json={"password": "synthetic-app-password"},
                                           headers=self.headers).status_code, 200)
            response = app_only.get(path, headers={"Sec-Fetch-Site": "same-origin"})
            self.assertEqual(response.status_code, 401)
        finally:
            app_only.close()

        http_client = TestClient(self.app, base_url="http://testserver")
        try:
            response = http_client.get(path, headers={"Sec-Fetch-Site": "same-origin"})
            self.assertEqual(response.status_code, 403)
        finally:
            http_client.close()

    def test_all_promote_post_routes_still_require_exact_origin(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.preview().json()
        originless = {"Sec-Fetch-Site": "same-origin"}
        requests = (
            ("/api/promote/auth/unlock", {"passphrase": self.unlock_secret.read_text()}),
            ("/api/promote/auth/lock", {}),
            ("/api/promote/review/preview", {
                "review_path": "candidate.md",
                "review_sha256": hashlib.sha256(self.source).hexdigest(),
                "target_filename": "second.md",
            }),
            ("/api/promote/review/confirm", {
                "preview_id": preview["preview_id"], "confirm_intent": "promote_exact_preview",
            }),
            ("/api/promote/review/approve", {"request_id": "forged"}),
            ("/api/promote/review/defer", {
                "review_path": "candidate.md", "review_sha256": hashlib.sha256(self.source).hexdigest(),
            }),
        )
        for path, body in requests:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, headers=originless, json=body).status_code, 403)
                self.assertEqual(self.client.post(path, headers={"Origin": "https://attacker.example"},
                                                  json=body).status_code, 403)
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])
        self.assertEqual(list((self.state / "b1b-operations").glob("*.json")), [])
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())

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
        stale_confirm = self.confirm(preview["preview_id"])
        self.assertEqual(stale_confirm.status_code, 410)
        operation = self.client.get("/api/promote/operations/" + preview["request_id"],
                                    headers=self.headers)
        self.assertEqual(operation.status_code, 200, operation.text)
        self.assertEqual(operation.json()["status"], "recovery_required")
        self.assertEqual(operation.json()["request_id"], preview["request_id"])
        self.assertEqual(operation.json()["error_code"], "operation_recovery_required")
        another_preview = self.preview()
        self.assertEqual(another_preview.status_code, 409)
        self.assertEqual(another_preview.json()["detail"]["code"], "operation_recovery_required")
        self.assertEqual((self.review / "candidate.md").read_bytes(), self.source)
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
