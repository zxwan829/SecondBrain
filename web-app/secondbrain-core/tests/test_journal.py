import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from secondbrain_core.modules.journal import JournalStore, create_journal_router


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

    def test_idempotency_is_global_across_dates_and_concurrent_retries(self):
        text = "记一下：零点前已写入但响应丢失"
        days = ("2026-10-17", "2026-10-18")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda day: self.store.append(day, text, "midnight-retry", "session-a"), days))
        self.assertCountEqual([result["status"] for result in results], ["created", "duplicate"])
        created = next(result for result in results if result["status"] == "created")
        duplicate = next(result for result in results if result["status"] == "duplicate")
        self.assertEqual(duplicate["date"], created["date"])
        rows = [row for path in self.root.glob("????-??-??.jsonl") for row in self.store.read(path.stem)["entries"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["operation_id"], "midnight-retry")

    def test_authenticated_journal_route_append_retry_and_readback_preserve_existing_entry(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if (request.cookies.get("session") != "owner"
                        or action not in {"journal.read", "journal.append"}):
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_journal_router(SessionAuth(), self.store))
        client = TestClient(app)
        day = "2026-10-17"
        original = self.store.append(day, "记一下：已有合成日记", "seed-original")
        url = "/api/journal/entries"
        headers = {"Idempotency-Key": "browser-operation-1"}
        payload = {"date": day, "text": "写日记：新合成追加"}

        denied = client.post(url, json=payload, headers=headers)
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(len(self.store.read(day)["entries"]), 1)
        ordinary_chat = client.post(url, json={"date": day, "text": "普通聊天内容"},
                                    headers={"Idempotency-Key": "ordinary-chat"},
                                    cookies={"session": "owner"})
        self.assertEqual(ordinary_chat.status_code, 422)
        self.assertEqual(len(self.store.read(day)["entries"]), 1)

        created = client.post(url, json=payload, headers=headers, cookies={"session": "owner"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "created")
        replay = client.post(url, json=payload, headers=headers, cookies={"session": "owner"})
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["status"], "duplicate")
        readback = client.get(f"/api/journal/{day}", cookies={"session": "owner"})
        self.assertEqual(readback.status_code, 200)
        rows = readback.json()["entries"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], original["entry"])
        self.assertEqual(rows[1]["original_text"], payload["text"])
        self.assertEqual(rows[1]["operation_id"], headers["Idempotency-Key"])

        conflicting_replay = client.post(url, json={"date": day, "text": "记一下：不同内容"},
                                         headers=headers, cookies={"session": "owner"})
        self.assertEqual(conflicting_replay.status_code, 409)
        self.assertEqual(len(self.store.read(day)["entries"]), 2)


if __name__ == "__main__":
    unittest.main()
