import hashlib
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from dashboard_approval import (
    ApprovalFileStore,
    ApprovalRequestError,
    DashboardAuthorizationError,
    FileApprovalSource,
)
from promote_worker import PromoteWorker


class RequestStub:
    def __init__(self, user_id="joe", provider="basic", origin="http://dashboard.local:9119",
                 auth_required=True):
        self.app = SimpleNamespace(state=SimpleNamespace(auth_required=auth_required))
        session = None if user_id is None else SimpleNamespace(
            user_id=user_id, provider=provider, expires_at=time.time() + 600
        )
        self.state = SimpleNamespace(session=session)
        self.headers = {"origin": origin} if origin else {}
        self.base_url = "http://dashboard.local:9119/"


class DashboardApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.temp.name)
        self.review = os.path.join(self.root, "review")
        self.queue = os.path.join(self.root, "approval-queue")
        self.knowledge = os.path.join(self.root, "knowledge")
        self.audit = os.path.join(self.root, "audit")
        for path in (self.review, self.queue, self.knowledge, self.audit):
            os.mkdir(path)
        self.body = (b"---\ntype: review\nstatus: pending\nsource_type: external-text\n"
                     b"captured_at: 2026-10-12T00:00:00Z\nreview_status: pending\n"
                     b"tags: [demo]\n---\n# Approved note\n\nContent reviewed by the operator.\n")
        with open(os.path.join(self.review, "item.md"), "wb") as handle:
            handle.write(self.body)
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.request = RequestStub()
        self.body_args = {
            "request_id": "approve-001",
            "review_path": "item.md",
            "review_sha256": self.digest,
            "target_filename": "approved-note.md",
            # Neither of these untrusted values grants approval or identity.
            "approved": False,
            "approver_subject": "agent:forged",
        }
        self.store = ApprovalFileStore(self.queue)

    def tearDown(self):
        self.temp.cleanup()

    def test_authenticated_same_origin_approval_is_consumed_by_worker(self):
        result = self.store.approve(self.request, self.body_args, self.review)
        self.assertEqual(result["status"], "approved")
        approval = self.store.read("approve-001")
        self.assertEqual(approval["approver_subject"], "joe")
        self.assertEqual(approval["status"], "approved")
        worker = PromoteWorker(self.review, self.knowledge,
                               os.path.join(self.audit, "promote.jsonl"),
                               FileApprovalSource(self.queue))
        promoted = worker.promote("approve-001", "item.md", self.digest)
        self.assertEqual(promoted["status"], "promoted")

    def test_missing_dashboard_session_is_denied(self):
        with self.assertRaises(DashboardAuthorizationError):
            self.store.approve(RequestStub(user_id=None), self.body_args, self.review)

    def test_non_basic_or_expired_session_is_denied(self):
        with self.assertRaises(DashboardAuthorizationError):
            self.store.approve(RequestStub(provider="other"), self.body_args, self.review)
        expired = RequestStub()
        expired.state.session.expires_at = time.time() - 1
        with self.assertRaises(DashboardAuthorizationError):
            self.store.approve(expired, self.body_args, self.review)

    def test_non_gated_dashboard_session_is_denied(self):
        with self.assertRaises(DashboardAuthorizationError):
            self.store.approve(RequestStub(auth_required=False), self.body_args, self.review)

    def test_cross_origin_request_is_denied(self):
        request = RequestStub(origin="https://attacker.example")
        with self.assertRaisesRegex(DashboardAuthorizationError, "Same-origin"):
            self.store.approve(request, self.body_args, self.review)

    def test_client_approval_flag_and_identity_are_ignored(self):
        args = dict(self.body_args, approved=False, approver_subject="agent:claimed")
        self.store.approve(self.request, args, self.review)
        approval = self.store.read("approve-001")
        self.assertEqual(approval["approver_subject"], "joe")
        self.assertEqual(approval["status"], "approved")

    def test_stale_digest_and_traversal_are_rejected(self):
        stale = dict(self.body_args, review_sha256="0" * 64)
        with self.assertRaisesRegex(ApprovalRequestError, "changed"):
            self.store.approve(self.request, stale, self.review)
        traversal = dict(self.body_args, request_id="approve-002", review_path="../private.md")
        with self.assertRaises(ApprovalRequestError):
            self.store.approve(self.request, traversal, self.review)

    def test_symlink_escape_is_rejected(self):
        outside = os.path.join(self.root, "outside.md")
        with open(outside, "wb") as handle:
            handle.write(self.body)
        os.symlink(outside, os.path.join(self.review, "link.md"))
        args = dict(self.body_args, request_id="approve-003", review_path="link.md")
        with self.assertRaises(ApprovalRequestError):
            self.store.approve(self.request, args, self.review)

    def test_duplicate_approval_is_idempotent_and_conflict_is_denied(self):
        first = self.store.approve(self.request, self.body_args, self.review)
        second = self.store.approve(self.request, self.body_args, self.review)
        self.assertEqual(first["status"], "approved")
        self.assertEqual(second["status"], "already_approved")
        conflict = dict(self.body_args, target_filename="different.md")
        with self.assertRaisesRegex(ApprovalRequestError, "different approval"):
            self.store.approve(self.request, conflict, self.review)


if __name__ == "__main__":
    unittest.main()
