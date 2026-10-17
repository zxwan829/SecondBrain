import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from secondbrain_core.modules.journal import JournalStore


class JournalStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "journal"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.store = JournalStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_concurrent_appends_preserve_all_entries_and_exact_original_text(self):
        def append(index):
            return self.store.append("2026-10-17", f"记一下：合成记录 {index}", f"key-{index}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(append, range(24)))
        self.assertTrue(all(result["status"] == "created" for result in results))
        saved = self.store.read("2026-10-17")["entries"]
        self.assertEqual(len(saved), 24)
        self.assertEqual({row["original_text"] for row in saved}, {f"记一下：合成记录 {index}" for index in range(24)})
        self.assertEqual((self.root / "2026-10-17.jsonl").stat().st_mode & 0o777, 0o600)

    def test_invalid_intent_and_path_are_rejected_without_write(self):
        with self.assertRaises(HTTPException) as intent:
            self.store.append("2026-10-17", "普通聊天", "key-1")
        self.assertEqual(intent.exception.status_code, 422)
        with self.assertRaises(HTTPException) as path:
            self.store.append("../outside", "记一下：越界", "key-2")
        self.assertEqual(path.exception.status_code, 400)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rejects_symlink_journal_file(self):
        outside = Path(self.temp.name) / "outside.jsonl"
        outside.write_text("sensitive sentinel\n", encoding="utf-8")
        outside.chmod(0o600)
        (self.root / "2026-10-17.jsonl").symlink_to(outside)
        with self.assertRaises(HTTPException):
            self.store.read("2026-10-17")
        self.assertEqual(outside.read_text(encoding="utf-8"), "sensitive sentinel\n")

    def test_idempotency_replay_is_safe_and_conflicting_text_is_rejected(self):
        original = "记一下：保持完整原句"
        created = self.store.append("2026-10-17", original, "same-key")
        replay = self.store.append("2026-10-17", original, "same-key")
        self.assertEqual(replay["status"], "duplicate")
        self.assertEqual(replay["date"], "2026-10-17")
        self.assertEqual(replay["entry"], created["entry"])
        self.assertEqual(len(self.store.read("2026-10-17")["entries"]), 1)
        with self.assertRaises(HTTPException) as conflict:
            self.store.append("2026-10-17", "记一下：不同内容", "same-key")
        self.assertEqual(conflict.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
