import hashlib
import os
import tempfile
import unittest

from promote_worker import ApprovalRecord, PromoteWorker, PromotionError


class FakeApprovalSource:
    """Test-only in-memory authority; never suitable for production."""
    def __init__(self, record=None):
        self.record = record

    def get_approved(self, request_id):
        if self.record and self.record.request_id == request_id:
            return self.record
        return None


class PromoteWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # macOS exposes temp paths through /var -> /private/var; use canonical
        # test roots so component-wise O_NOFOLLOW checks behave like Linux mounts.
        self.root = os.path.realpath(self.temp.name)
        self.review = os.path.join(self.root, "review")
        self.knowledge = os.path.join(self.root, "knowledge")
        self.audit_dir = os.path.join(self.root, "audit")
        os.mkdir(self.review)
        os.mkdir(self.knowledge)
        os.mkdir(self.audit_dir)
        self.body = (b"---\ntype: review\nstatus: pending\nsource_type: external-text\n"
                     b"captured_at: 2026-10-12T00:00:00Z\nreview_status: pending\n"
                     b"tags: [demo]\n---\n# Approved note\n\nSafe content.\n")
        with open(os.path.join(self.review, "item.md"), "wb") as handle:
            handle.write(self.body)
        self.record = ApprovalRecord("req-001", "approved", "human:test-user",
                                     "2026-10-12T00:00:00Z", "item.md",
                                     hashlib.sha256(self.body).hexdigest(), "note.md")
        self.source = FakeApprovalSource(self.record)
        self.worker = PromoteWorker(self.review, self.knowledge,
                                   os.path.join(self.audit_dir, "events.jsonl"), self.source)

    def promote(self, worker=None):
        return (worker or self.worker).promote(
            "req-001", self.record.review_path, self.record.review_sha256
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_unapproved_is_denied(self):
        worker = PromoteWorker(self.review, self.knowledge,
                               os.path.join(self.audit_dir, "events.jsonl"), FakeApprovalSource())
        with self.assertRaises(PromotionError):
            self.promote(worker)
        self.assertFalse(os.path.exists(os.path.join(self.knowledge, "note.md")))

    def test_approved_writes_markdown_and_audit(self):
        result = self.promote()
        self.assertEqual(result["status"], "promoted")
        with open(os.path.join(self.knowledge, "note.md"), "rb") as handle:
            written = handle.read()
        self.assertIn(b"review_sha256=" + self.record.review_sha256.encode(), written)
        self.assertIn(b"type: knowledge", written)
        self.assertIn(b"status: active", written)
        self.assertNotIn(b"review_status:", written)
        self.assertIn(b"created: 2026-10-12", written)
        self.assertIn(b"updated: 2026-10-12", written)
        self.assertTrue(os.path.exists(os.path.join(self.audit_dir, "events.jsonl")))

    def test_repeat_is_idempotent(self):
        first = self.promote()
        second = self.promote()
        self.assertEqual(first["status"], "promoted")
        self.assertEqual(second["status"], "already_promoted")

    def test_changed_review_invalidates_old_approval(self):
        with open(os.path.join(self.review, "item.md"), "wb") as handle:
            handle.write(self.body + b"changed\n")
        with self.assertRaisesRegex(PromotionError, "stale"):
            self.promote()

    def test_traversal_path_is_rejected(self):
        self.record.review_path = "../outside.md"
        with self.assertRaisesRegex(PromotionError, "traversal"):
            self.promote()

    def test_review_symlink_escape_is_rejected(self):
        outside = os.path.join(self.root, "outside.md")
        with open(outside, "wb") as handle:
            handle.write(self.body)
        os.unlink(os.path.join(self.review, "item.md"))
        os.symlink(outside, os.path.join(self.review, "item.md"))
        with self.assertRaises(OSError):
            self.promote()
        self.assertFalse(os.path.exists(os.path.join(self.knowledge, "note.md")))

    def test_knowledge_target_is_never_overwritten(self):
        target = os.path.join(self.knowledge, "note.md")
        with open(target, "wb") as handle:
            handle.write(b"existing content")
        with self.assertRaisesRegex(PromotionError, "exists"):
            self.promote()
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(), b"existing content")


if __name__ == "__main__":
    unittest.main()
