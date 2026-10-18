import hashlib
import errno
import json
import multiprocessing
import os
import tempfile
import unittest
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from secondbrain_core.modules.review_promote.core_auth import CorePromoteAuth
from secondbrain_core.app import create_app
from secondbrain_core.modules.review_promote.approval import ApprovalRequestError, ReviewDecisionStore
from secondbrain_core.modules.review_promote.http import create_core_router
from secondbrain_core.modules.review_promote.service import PromoteService
from secondbrain_core.modules.app_auth import AppSessionAuth


def _promote_in_process(review_root, knowledge_root, approval_dir, audit_path, digest,
                        request_id, target_filename, barrier, result_queue):
    service = PromoteService(review_root, knowledge_root, approval_dir, audit_path)
    barrier.wait(timeout=15)
    try:
        result = service.approve_and_promote_as("owner", {
            "request_id": request_id,
            "review_path": "candidate.md",
            "review_sha256": digest,
            "target_filename": target_filename,
        })
        result_queue.put(("ok", request_id, result["status"]))
    except Exception as exc:
        result_queue.put(("error", request_id, type(exc).__name__, str(exc)))


def _promote_distinct_version_in_process(review_root, knowledge_root, approval_dir, audit_path,
                                         review_path, digest, request_id, target_filename,
                                         barrier, result_queue):
    service = PromoteService(review_root, knowledge_root, approval_dir, audit_path)
    acquire_request_lock = service.decisions.lock_request_id

    @contextmanager
    def synchronized_request_lock(candidate_request_id):
        # Both distinct version locks are already held. Synchronize immediately
        # before the global request-ID lock so the race reaches the pre-claim gate.
        barrier.wait(timeout=15)
        with acquire_request_lock(candidate_request_id) as key:
            yield key

    service.decisions.lock_request_id = synchronized_request_lock
    body = {"request_id": request_id, "review_path": review_path,
            "review_sha256": digest, "target_filename": target_filename}
    try:
        result = service.approve_and_promote_as("owner", body)
        result_queue.put(("ok", request_id, review_path, target_filename, result["status"]))
    except Exception as exc:
        result_queue.put(("error", request_id, review_path, target_filename,
                          type(exc).__name__, str(exc)))


class CoreOwnedApprovalAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.review, self.knowledge, self.state, self.raw = [self.root / n for n in ("review", "knowledge", "state", "raw")]
        for path in (self.review, self.knowledge, self.state, self.raw):
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
        app_password_file = self.root / "app.password"
        app_password_file.write_text("synthetic-app-password", encoding="utf-8")
        app_password_file.chmod(0o600)
        self.app_auth = AppSessionAuth(str(app_password_file), ["https://testserver"])
        self.auth = CorePromoteAuth(str(self.secret_file), ["https://testserver"], self.app_auth,
                                    allowed_hosts=["testserver"])
        app = FastAPI()
        self._add_app_login(app)
        app.include_router(create_core_router(
            self.service, self.review, self.app_auth, promote_enabled=True, include_auth_routes=False,
            promote_auth=self.auth, operations_root=str(self.state / "operations"),
            knowledge_root=str(self.knowledge)), prefix="/api/promote")
        self.client = TestClient(app, base_url="https://testserver")
        self.headers = {"Origin": "https://testserver"}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def unlock(self):
        login = self.client.post("/api/auth/login", json={"password": "synthetic-app-password"},
                                 headers=self.headers)
        if login.status_code != 200:
            return login
        return self.client.post("/api/promote/auth/unlock",
                                json={"passphrase": self.unlock_secret.decode("ascii")},
                                headers=self.headers)

    def _add_app_login(self, app):
        @app.post("/api/auth/login")
        def app_login(request: Request, response: Response, body: dict):
            token = self.app_auth.login(request, body.get("password"))
            self.app_auth.set_cookie(response, request, token, self.app_auth.session_ttl)
            return {"status": "ok"}

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
            "SB_CAPTURE_RAW_ROOT": str(self.raw),
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

    def test_legacy_approve_is_closed_even_after_both_sessions_are_unlocked(self):
        login = self.unlock()
        self.assertEqual(login.status_code, 200, login.text)
        cookie = login.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("path=/api/promote", cookie)
        self.assertEqual(self.client.get("/api/promote/review/items", headers=self.headers).status_code, 200)
        first = self.client.post("/api/promote/review/approve", json=self.body, headers=self.headers)
        self.assertEqual(first.status_code, 423)
        self.assertEqual(first.json()["detail"]["code"], "legacy_approve_disabled")
        self.assertFalse((self.knowledge / "approved.md").exists())
        self.assertFalse((self.state / "audit.jsonl").exists())

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
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
            self.assertTrue((self.knowledge / "approved.md").is_file())
            state = self.client.get("/api/promote/review/items", headers=self.headers).json()["items"][0]["decision"]
            self.assertEqual(state["status"], "failed")
            retry = self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(retry["status"], "already_promoted")
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

    def test_legacy_64_hex_orphan_approval_blocks_approve_and_defer_without_rewriting(self):
        version_key = ReviewDecisionStore.version_key(self.body["review_path"], self.body["review_sha256"])
        legacy_request_id = "a" * 64
        if legacy_request_id == version_key:
            legacy_request_id = "b" * 64
        legacy_record = {
            "request_id": legacy_request_id,
            "status": "approved",
            "approver_subject": "legacy-owner",
            "approved_at": "2026-10-18T12:00:00+00:00",
            "review_path": self.body["review_path"],
            "review_sha256": self.body["review_sha256"],
            "target_filename": "legacy-approved.md",
        }
        legacy_bytes = (json.dumps(legacy_record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        legacy_path = self.state / "approvals" / (legacy_request_id + ".json")
        legacy_path.write_bytes(legacy_bytes)
        legacy_path.chmod(0o600)

        self.assertEqual(self.unlock().status_code, 200)
        competing = {**self.body, "request_id": "history-replay", "target_filename": "replay.md"}
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", competing)
        defer = self.client.post("/api/promote/review/defer", json={
            "review_path": self.body["review_path"], "review_sha256": self.body["review_sha256"],
        }, headers=self.headers)

        self.assertEqual(defer.status_code, 409, defer.text)
        self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertEqual(self.service.get_decision(self.body["review_path"], self.body["review_sha256"])["status"],
                         "pending")

    def test_torn_audit_tail_fails_closed_without_losing_original_bytes(self):
        self.assertEqual(self.unlock().status_code, 200)
        damaged = b'{"event":"interrupted"'
        (self.state / "audit.jsonl").write_bytes(damaged)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual((self.state / "audit.jsonl").read_bytes(), damaged)
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_partial_audit_write_preserves_output_and_blocks_retry_for_manual_recovery(self):
        self.assertEqual(self.unlock().status_code, 200)

        def partial_write(fd, record):
            os.write(fd, b'{"event":"partial-promotion"')
            raise OSError("synthetic interrupted audit append")

        with patch("secondbrain_core.modules.review_promote.worker._append_audit", side_effect=partial_write):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
        self.assertTrue((self.knowledge / "approved.md").is_file())
        damaged = b'{"event":"partial-promotion"'
        self.assertEqual((self.state / "audit.jsonl").read_bytes(), damaged)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual((self.state / "audit.jsonl").read_bytes(), damaged)

    def test_malformed_complete_audit_line_fails_closed_without_mutation(self):
        self.assertEqual(self.unlock().status_code, 200)
        damaged = b'{"event":broken}\n'
        (self.state / "audit.jsonl").write_bytes(damaged)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual((self.state / "audit.jsonl").read_bytes(), damaged)
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_existing_knowledge_target_is_never_overwritten(self):
        self.assertEqual(self.unlock().status_code, 200)
        target = self.knowledge / "approved.md"
        original = b"keep existing synthetic target\n"
        target.write_bytes(original)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(target.read_bytes(), original)

    def test_knowledge_target_symlink_is_rejected_without_touching_target(self):
        self.assertEqual(self.unlock().status_code, 200)
        external = self.root / "outside-synthetic-target.md"
        external.write_bytes(b"outside target remains unchanged\n")
        (self.knowledge / "approved.md").symlink_to(external)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertTrue((self.knowledge / "approved.md").is_symlink())
        self.assertEqual(external.read_bytes(), b"outside target remains unchanged\n")

    def test_review_path_traversal_is_rejected_before_claim_creation(self):
        self.assertEqual(self.unlock().status_code, 200)
        outside = self.root / "outside-review.md"
        outside.write_bytes(b"synthetic path traversal sentinel\n")
        traversal = dict(self.body, review_path="../outside-review.md")
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", traversal)
        self.assertEqual(outside.read_bytes(), b"synthetic path traversal sentinel\n")
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_different_request_and_target_cannot_claim_same_review_version(self):
        self.assertEqual(self.unlock().status_code, 200)
        first = self.service.approve_and_promote_as("owner", self.body)
        competing = dict(self.body, request_id="core-owner-2", target_filename="other.md")
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", competing)
        claims = list((self.state / "approvals").glob("*.claim"))
        self.assertEqual(len(claims), 1)
        claim = json.loads(claims[0].read_text())
        self.assertEqual(claim["request_id"], self.body["request_id"])
        self.assertEqual(claim["target_filename"], self.body["target_filename"])
        self.assertFalse((self.knowledge / "other.md").exists())

    def test_retry_recovers_after_claim_is_durable_but_approval_write_fails(self):
        self.assertEqual(self.unlock().status_code, 200)
        original = self.service.approvals.approve_as
        calls = {"count": 0}

        def fail_once(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("synthetic interruption after claim")
            return original(*args, **kwargs)

        with patch.object(self.service.approvals, "approve_as", side_effect=fail_once):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 1)
        version_record = hashlib.sha256(("candidate.md\0" + self.body["review_sha256"])
                                        .encode()).hexdigest() + ".json"
        self.assertEqual([path.name for path in (self.state / "approvals").glob("*.json")
                          if path.name != version_record], [])
        competing = dict(self.body, request_id="claim-takeover", target_filename="takeover.md")
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", competing)
        recovered = self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(recovered["status"], "promoted")
        self.assertTrue((self.knowledge / "approved.md").is_file())

    def test_claim_file_fsync_failure_leaves_no_claim_and_same_key_can_retry(self):
        self.assertEqual(self.unlock().status_code, 200)
        with patch("secondbrain_core.modules.review_promote.approval.os.fsync",
                   side_effect=OSError(errno.EIO, "synthetic claim file fsync failure")):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])
        self.assertEqual(list((self.state / "approvals").glob(".claim-*")), [])
        recovered = self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(recovered["status"], "promoted")

    def test_claim_directory_fsync_failure_keeps_claim_and_recovers_only_same_key(self):
        self.assertEqual(self.unlock().status_code, 200)
        original = os.fsync
        calls = {"count": 0}

        def fail_directory_fsync_once(fd):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError(errno.EIO, "synthetic claim directory fsync failure")
            return original(fd)

        with patch("secondbrain_core.modules.review_promote.approval.os.fsync",
                   side_effect=fail_directory_fsync_once):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 1)
        competing = dict(self.body, request_id="directory-fsync-takeover", target_filename="takeover.md")
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", competing)
        recovered = self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(recovered["status"], "promoted")

    def test_enospc_during_claim_write_leaves_no_claim_and_allows_retry(self):
        self.assertEqual(self.unlock().status_code, 200)
        with patch("secondbrain_core.modules.review_promote.approval.os.write",
                   side_effect=OSError(errno.ENOSPC, "synthetic no-space claim write")):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(list((self.state / "approvals").glob("*.claim")), [])
        self.assertEqual(list((self.state / "approvals").glob(".claim-*")), [])
        recovered = self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(recovered["status"], "promoted")

    def test_retry_recovers_when_output_and_audit_exist_but_decision_write_failed(self):
        self.assertEqual(self.unlock().status_code, 200)
        original = self.service.decisions.set
        calls = {"count": 0}

        def fail_promoted_once(review_path, digest, status, **fields):
            if status == "promoted" and calls["count"] == 0:
                calls["count"] += 1
                raise OSError("synthetic decision persistence interruption")
            return original(review_path, digest, status, **fields)

        with patch.object(self.service.decisions, "set", side_effect=fail_promoted_once):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", self.body)
        self.assertTrue((self.knowledge / "approved.md").is_file())
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)
        recovered = self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(recovered["status"], "already_promoted")
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)

    def test_same_version_process_race_allows_only_one_request_target_claim(self):
        ctx = multiprocessing.get_context("fork")
        barrier = ctx.Barrier(2)
        result_queue = ctx.Queue()
        args = (str(self.review), str(self.knowledge), str(self.state / "approvals"),
                str(self.state / "audit.jsonl"), self.body["review_sha256"])
        processes = [
            ctx.Process(target=_promote_in_process,
                        args=(*args, request_id, target, barrier, result_queue))
            for request_id, target in (("race-a", "race-a.md"), ("race-b", "race-b.md"))
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
        self.assertTrue(all(not process.is_alive() for process in processes))
        self.assertEqual([process.exitcode for process in processes], [0, 0])
        lock_key = ReviewDecisionStore.version_key(self.body["review_path"], self.body["review_sha256"])
        self.assertTrue((self.state / "approvals" / (lock_key + ".lock")).exists())
        outcomes = [result_queue.get(timeout=3) for _ in processes]
        self.assertEqual(sum(outcome[0] == "ok" for outcome in outcomes), 1, outcomes)
        self.assertEqual(sum(outcome[0] == "error" for outcome in outcomes), 1, outcomes)
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 1)
        approval_records = [path for path in (self.state / "approvals").glob("*.json")
                            if path.name != (hashlib.sha256(("candidate.md\0" + self.body["review_sha256"])
                                                           .encode()).hexdigest() + ".json")]
        self.assertEqual(len(approval_records), 1)
        self.assertEqual(len(list(self.knowledge.glob("*.md"))), 1)

    def test_same_version_thread_race_allows_only_one_request_target_claim(self):
        barrier = __import__("threading").Barrier(2)

        def promote(request_id, target_filename):
            barrier.wait(timeout=5)
            body = {**self.body, "request_id": request_id, "target_filename": target_filename}
            try:
                result = self.service.approve_and_promote_as("owner", body)
                return ("ok", request_id, result["status"])
            except Exception as exc:
                return ("error", request_id, type(exc).__name__)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(promote, request_id, target)
                       for request_id, target in (("thread-race-a", "thread-race-a.md"),
                                                  ("thread-race-b", "thread-race-b.md"))]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(result[0] == "ok" for result in results), 1, results)
        self.assertEqual(sum(result[0] == "error" for result in results), 1, results)
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 1)
        self.assertEqual(len(list(self.knowledge.glob("*.md"))), 1)

    def test_same_key_concurrent_process_retries_are_idempotent(self):
        ctx = multiprocessing.get_context("fork")
        barrier = ctx.Barrier(2)
        result_queue = ctx.Queue()
        args = (str(self.review), str(self.knowledge), str(self.state / "approvals"),
                str(self.state / "audit.jsonl"), self.body["review_sha256"])
        processes = [ctx.Process(target=_promote_in_process,
                                  args=(*args, "same-process-key", "same-process.md", barrier, result_queue))
                     for _ in range(2)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
        self.assertTrue(all(not process.is_alive() for process in processes))
        self.assertEqual([process.exitcode for process in processes], [0, 0])
        outcomes = [result_queue.get(timeout=3) for _ in processes]
        self.assertTrue(all(outcome[0] == "ok" for outcome in outcomes), outcomes)
        self.assertCountEqual([outcome[2] for outcome in outcomes], ["promoted", "already_promoted"])
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 1)
        self.assertEqual(len(list(self.knowledge.glob("*.md"))), 1)

    def test_distinct_review_versions_receive_independent_claims(self):
        first = self.service.approve_and_promote_as("owner", self.body)
        updated_content = self.content + b"A second synthetic Review version.\n"
        (self.review / "candidate.md").write_bytes(updated_content)
        second_body = {
            "request_id": "core-owner-version-2",
            "review_path": "candidate.md",
            "review_sha256": hashlib.sha256(updated_content).hexdigest(),
            "target_filename": "approved-v2.md",
        }
        second = self.service.approve_and_promote_as("owner", second_body)
        self.assertEqual(first["status"], "promoted")
        self.assertEqual(second["status"], "promoted")
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 2)
        self.assertTrue((self.knowledge / "approved.md").is_file())
        self.assertTrue((self.knowledge / "approved-v2.md").is_file())
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 2)

    def test_cross_version_process_race_reserves_request_id_before_claim_and_loser_retries(self):
        second_content = self.content + b"A second concurrent synthetic Review item.\n"
        second_path = "candidate-b.md"
        (self.review / second_path).write_bytes(second_content)
        second_digest = hashlib.sha256(second_content).hexdigest()
        shared_request_id = "shared-cross-version-id"
        cases = ((self.body["review_path"], self.body["review_sha256"], "cross-a.md"),
                 (second_path, second_digest, "cross-b.md"))

        ctx = multiprocessing.get_context("fork")
        barrier = ctx.Barrier(2)
        result_queue = ctx.Queue()
        args = (str(self.review), str(self.knowledge), str(self.state / "approvals"),
                str(self.state / "audit.jsonl"))
        processes = [ctx.Process(target=_promote_distinct_version_in_process,
                                  args=(*args, review_path, digest, shared_request_id, target,
                                        barrier, result_queue))
                     for review_path, digest, target in cases]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)

        self.assertTrue(all(not process.is_alive() for process in processes))
        self.assertEqual([process.exitcode for process in processes], [0, 0])
        outcomes = [result_queue.get(timeout=3) for _ in processes]
        successes = [outcome for outcome in outcomes if outcome[0] == "ok"]
        failures = [outcome for outcome in outcomes if outcome[0] == "error"]
        self.assertEqual(len(successes), 1, outcomes)
        self.assertEqual(len(failures), 1, outcomes)
        winner = successes[0]
        loser = failures[0]
        loser_digest = self.body["review_sha256"] if loser[2] == self.body["review_path"] else second_digest
        loser_key = ReviewDecisionStore.version_key(loser[2], loser_digest)
        self.assertFalse((self.state / "approvals" / (loser_key + ".claim")).exists())
        self.assertEqual(self.service.decisions.claims_for_request_id(shared_request_id)[0]["review_path"], winner[2])
        self.assertEqual(self.service.get_decision(loser[2], loser_digest)["status"], "pending")
        self.assertEqual([path.name for path in self.knowledge.glob("*.md")], [winner[3]])

        retry = self.service.approve_and_promote_as("owner", {
            "request_id": "cross-version-retry",
            "review_path": loser[2],
            "review_sha256": loser_digest,
            "target_filename": "cross-version-retry.md",
        })
        self.assertEqual(retry["status"], "promoted")
        self.assertTrue((self.knowledge / "cross-version-retry.md").is_file())
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 2)
        self.assertEqual(len((self.state / "audit.jsonl").read_text().splitlines()), 2)

    def test_request_id_lock_failure_before_claim_leaves_no_half_binding_and_same_id_retries(self):
        failed_body = {**self.body, "request_id": "request-lock-fault", "target_filename": "fault.md"}
        with patch.object(self.service.decisions, "create_claim",
                          side_effect=OSError("synthetic interruption after request-ID reservation")):
            with self.assertRaises(ApprovalRequestError):
                self.service.approve_and_promote_as("owner", failed_body)

        key = ReviewDecisionStore.version_key(failed_body["review_path"], failed_body["review_sha256"])
        self.assertFalse((self.state / "approvals" / (key + ".claim")).exists())
        self.assertEqual(self.service.get_decision(failed_body["review_path"], failed_body["review_sha256"])["status"],
                         "pending")
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertEqual(list((self.state / "approvals").glob("*.json")), [])
        request_lock_key = ReviewDecisionStore.request_id_lock_key(failed_body["request_id"])
        self.assertTrue((self.state / "approvals" / ("request-id-" + request_lock_key + ".lock")).is_file())

        retry = self.service.approve_and_promote_as("owner", failed_body)
        self.assertEqual(retry["status"], "promoted")
        self.assertTrue((self.knowledge / "fault.md").is_file())
        self.assertEqual(len(list((self.state / "approvals").glob("*.claim"))), 1)

    def test_malformed_claim_fails_closed_and_preserves_claim_bytes(self):
        self.assertEqual(self.unlock().status_code, 200)
        key = ReviewDecisionStore.version_key(self.body["review_path"], self.body["review_sha256"])
        claim_path = self.state / "approvals" / (key + ".claim")
        damaged = b'{"request_id":"partial"'
        claim_path.write_bytes(damaged)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(claim_path.read_bytes(), damaged)
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_lock_symlink_fails_closed_without_touching_symlink_target(self):
        key = ReviewDecisionStore.version_key(self.body["review_path"], self.body["review_sha256"])
        external = self.root / "external-lock-target"
        external.write_bytes(b"do-not-change")
        (self.state / "approvals" / (key + ".lock")).symlink_to(external)
        self.assertEqual(self.unlock().status_code, 200)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(external.read_bytes(), b"do-not-change")
        self.assertFalse((self.state / "approvals" / (key + ".claim")).exists())
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_lock_with_group_permissions_fails_closed_without_chmod(self):
        key = ReviewDecisionStore.version_key(self.body["review_path"], self.body["review_sha256"])
        lock_path = self.state / "approvals" / (key + ".lock")
        lock_path.write_bytes(b"")
        lock_path.chmod(0o640)
        self.assertEqual(self.unlock().status_code, 200)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", self.body)
        self.assertEqual(lock_path.stat().st_mode & 0o777, 0o640)
        self.assertFalse((self.state / "approvals" / (key + ".claim")).exists())
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_defer_and_approval_threads_serialize_on_the_same_review_version(self):
        barrier = __import__("threading").Barrier(2)

        def approve():
            barrier.wait(timeout=5)
            try:
                return ("approve", self.service.approve_and_promote_as("owner", self.body)["status"])
            except Exception as exc:
                return ("approve-error", type(exc).__name__)

        def defer():
            barrier.wait(timeout=5)
            try:
                result = self.service.defer(self.body["review_path"], self.body["review_sha256"], "owner")
                return ("defer", result["status"])
            except Exception as exc:
                return ("defer-error", type(exc).__name__)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [pool.submit(approve), pool.submit(defer)]
            results = [future.result(timeout=10) for future in outcomes]
        self.assertTrue(any(result[0] == "approve" for result in results), results)
        self.assertTrue(any(result[0] in {"defer-error", "defer"} for result in results), results)
        decision = self.service.get_decision(self.body["review_path"], self.body["review_sha256"])
        self.assertIn(decision["status"], {"promoted", "deferred"})
        if decision["status"] == "promoted":
            self.assertTrue((self.knowledge / "approved.md").is_file())
        else:
            self.assertFalse((self.knowledge / "approved.md").exists())

    def test_review_list_and_detail_are_owner_only_and_return_real_content_and_state(self):
        self.assertEqual(self.unlock().status_code, 200)
        listing = self.client.get("/api/promote/review/items", headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["status"], "pending")
        self.assertEqual(listing.json()["items"][0]["captured_at"], "2026-10-12T00:00:00Z")
        detail = self.client.get("/api/promote/review/items/candidate.md", headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["content"], self.content.decode())
        self.assertEqual(detail.json()["review_sha256"], self.body["review_sha256"])
        self.assertEqual(detail.json()["status"], "pending")
        self.assertEqual(detail.json()["captured_at"], "2026-10-12T00:00:00Z")
        self.assertEqual(self.client.get("/api/promote/review/items/missing.md", headers=self.headers).status_code, 404)

    def test_review_list_marks_missing_or_unverifiable_capture_time_as_unknown(self):
        (self.review / "undated.md").write_text(
            "---\ntype: review\ncaptured_at: someday\nreview_status: pending\n---\n# Undated\n",
            encoding="utf-8")
        (self.review / "date-only.md").write_text(
            "---\ntype: review\ncaptured_at: 2026-10-10\nreview_status: pending\n---\n# Date only\n",
            encoding="utf-8")
        self.assertEqual(self.unlock().status_code, 200)
        listing = self.client.get("/api/promote/review/items", headers=self.headers)
        undated = next(item for item in listing.json()["items"] if item["review_path"] == "undated.md")
        self.assertIsNone(undated["captured_at"])
        date_only = next(item for item in listing.json()["items"] if item["review_path"] == "date-only.md")
        self.assertEqual(date_only["captured_at"], "2026-10-10")

    def test_review_change_invalidates_approved_digest(self):
        self.assertEqual(self.unlock().status_code, 200)
        changed = dict(self.body, review_sha256="0" * 64)
        with self.assertRaises(ApprovalRequestError):
            self.service.approve_and_promote_as("owner", changed)
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_lock_revokes_core_session(self):
        self.assertEqual(self.unlock().status_code, 200)
        preview = self.client.post("/api/promote/review/preview", json={
            "review_path": self.body["review_path"],
            "review_sha256": self.body["review_sha256"],
            "target_filename": self.body["target_filename"],
        }, headers=self.headers)
        self.assertEqual(preview.status_code, 200, preview.text)
        locked = self.client.post("/api/promote/auth/lock", headers=self.headers)
        self.assertEqual(locked.status_code, 200)
        response = self.client.post("/api/promote/review/confirm", json={
            "preview_id": preview.json()["preview_id"],
            "confirm_intent": "promote_exact_preview",
        }, headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertFalse((self.knowledge / "approved.md").exists())

    def test_promote_disabled_blocks_approval_without_creating_records(self):
        app = FastAPI()
        self._add_app_login(app)
        app.include_router(create_core_router(
            self.service, self.review, self.app_auth, promote_enabled=False, include_auth_routes=False,
            promote_auth=self.auth, operations_root=str(self.state / "disabled-operations"),
            knowledge_root=str(self.knowledge)), prefix="/api/promote")
        client = TestClient(app, base_url="https://testserver")
        self.assertEqual(client.post("/api/auth/login", json={"password": "synthetic-app-password"},
                                     headers=self.headers).status_code, 200)
        self.assertEqual(client.post("/api/promote/auth/unlock",
                                     json={"passphrase": self.unlock_secret.decode("ascii")},
                                     headers=self.headers).status_code, 200)
        self.assertEqual(client.get("/api/promote/status", headers=self.headers).json(),
                         {"status": "ok", "promote_enabled": False})
        preview = client.post("/api/promote/review/preview", json={
            "review_path": self.body["review_path"], "review_sha256": self.body["review_sha256"],
            "target_filename": self.body["target_filename"],
        }, headers=self.headers)
        self.assertEqual(preview.status_code, 200, preview.text)
        response = client.post("/api/promote/review/confirm", json={
            "preview_id": preview.json()["preview_id"],
            "confirm_intent": "promote_exact_preview",
        }, headers=self.headers)
        self.assertEqual(response.status_code, 423)
        self.assertFalse((self.knowledge / "approved.md").exists())
        self.assertEqual(list((self.state / "approvals").iterdir()), [])
        self.assertEqual(list((self.state / "disabled-operations").iterdir()), [])
        self.assertFalse((self.state / "audit.jsonl").exists())
        client.close()


if __name__ == "__main__":
    unittest.main()
