import hashlib
import os
import tempfile
import unittest

from dashboard_approval import ApprovalFileStore
from promote_worker_runner import ApprovalQueueConsumer


class PromoteRunnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.temp.name)
        self.review = os.path.join(self.root, "review")
        self.queue = os.path.join(self.root, "approvals")
        self.knowledge = os.path.join(self.root, "knowledge")
        self.audit = os.path.join(self.root, "audit")
        for path in (self.review, self.queue, self.knowledge, self.audit):
            os.mkdir(path)
        self.content = (
            b"---\ntype: review\nstatus: pending\nsource_type: external-text\n"
            b"captured_at: 2026-10-12T00:00:00Z\nreview_status: pending\n"
            b"tags: [test]\n---\n# Runner integration\nPreserve this body.\n"
        )
        with open(os.path.join(self.review, "candidate.md"), "wb") as handle:
            handle.write(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.request_id = "runner-001"
        ApprovalFileStore(self.queue).create({
            "request_id": self.request_id,
            "status": "approved",
            "approver_subject": "joe",
            "approved_at": "2026-10-12T00:00:00+00:00",
            "review_path": "candidate.md",
            "review_sha256": self.digest,
            "target_filename": "runner-note.md",
        })
        self.consumer = ApprovalQueueConsumer(
            self.review, self.knowledge, self.queue, os.path.join(self.audit, "events.jsonl")
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_runner_consumes_server_record_and_is_idempotent(self):
        first = self.consumer.run_once()
        second = self.consumer.run_once()
        self.assertEqual(first[0]["status"], "promoted")
        self.assertEqual(second[0]["status"], "already_promoted")
        with open(os.path.join(self.knowledge, "runner-note.md"), "rb") as handle:
            output = handle.read()
        self.assertIn(b"type: knowledge", output)
        self.assertIn(b"status: active", output)
        self.assertNotIn(b"review_status:", output)
        self.assertIn(b"# Runner integration\nPreserve this body.", output)

    def test_runner_does_not_infer_approval_from_unrelated_files(self):
        with open(os.path.join(self.queue, "agent-claim.txt"), "w") as handle:
            handle.write('{"approved": true}')
        os.unlink(os.path.join(self.queue, self.request_id + ".json"))
        self.assertEqual(self.consumer.run_once(), [])
        self.assertFalse(os.path.exists(os.path.join(self.knowledge, "runner-note.md")))


if __name__ == "__main__":
    unittest.main()
