import hashlib
import tempfile
import unittest
from pathlib import Path

from secondbrain_core.modules.chat_knowledge import ChatKnowledgeCitationStore
from secondbrain_core.modules.knowledge_read import KnowledgeReadStore


class VerifiedSyntheticProvenance:
    def verify(self, relative, content, digest):
        return {"review_path": "synthetic/source.md", "review_sha256": hashlib.sha256(b"source").hexdigest()}


class ChatKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.knowledge = self.root / "knowledge"
        self.state = self.root / "citation-state"
        self.knowledge.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def store(self):
        return KnowledgeReadStore(str(self.knowledge), provenance_verifier=VerifiedSyntheticProvenance())

    def test_recall_has_candidate_and_utf8_byte_budgets(self):
        for index in range(4):
            (self.knowledge / f"{index}.md").write_text(
                f"# Item {index}\nneedle " + ("合成内容" * 3000), encoding="utf-8")
        recall = self.store().chat_recall("needle")
        self.assertLessEqual(len(recall["items"]), 3)
        self.assertEqual(recall["status"], "partial")
        total = 0
        for item in recall["items"]:
            size = len(item["content"].encode("utf-8"))
            self.assertLessEqual(size, 8 * 1024)
            self.assertEqual(item["provenance_status"], "verified")
            total += size
        self.assertLessEqual(total, 16 * 1024)

    def test_binding_is_idempotent_private_and_survives_store_recreation(self):
        path = self.knowledge / "ref.md"
        path.write_text("# Reference\nneedle synthetic", encoding="utf-8")
        knowledge_store = self.store()
        recall = knowledge_store.chat_recall("needle")
        first = ChatKnowledgeCitationStore(self.state, knowledge_store)
        initial = first.bind("run-1", "session-1", "needle", recall)
        replay = first.bind("run-1", "session-1", "needle", recall)
        self.assertEqual(replay, initial)

        restarted = ChatKnowledgeCitationStore(self.state, self.store())
        recovered = restarted.read_for_session("session-1", "run-1")
        self.assertEqual(recovered, initial)
        raw_ledger = (self.state / "citations.json").read_text(encoding="utf-8")
        self.assertNotIn("needle synthetic", raw_ledger)
        self.assertNotIn(str(self.root), raw_ledger)
        self.assertNotIn("synthetic/source.md", raw_ledger)

        path.write_text("# Reference\nneedle changed bytes", encoding="utf-8")
        stale = restarted.read_for_session("session-1", "run-1")
        self.assertEqual(stale["status"], "partial")
        self.assertEqual(stale["citations"][0]["knowledge_status"], "stale")

        path.write_text("# Reference\nneedle synthetic", encoding="utf-8")
        restarted.knowledge_store.provenance_verifier.verify = lambda *_args: None
        unavailable = restarted.read_for_session("session-1", "run-1")
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["citations"][0]["knowledge_status"], "unavailable")

        self.assertIsNone(restarted.bind("run-1", "session-2", "needle", recall))
        invalidated = restarted.read_for_session("session-1", "run-1")
        self.assertEqual(invalidated["status"], "unavailable")
        self.assertEqual(invalidated["citations"], [])


if __name__ == "__main__":
    unittest.main()
