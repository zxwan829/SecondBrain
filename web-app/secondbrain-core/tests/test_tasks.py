import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from secondbrain_core.modules.tasks import TaskStore


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "tasks"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.store = TaskStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_persists_and_idempotency_prevents_duplicates_and_conflicts(self):
        created = self.store.create("合成待办", "2026-10-20", "create-1", "添加待办：合成待办")
        duplicate = self.store.create("合成待办", "2026-10-20", "create-1", "添加待办：合成待办")
        self.assertEqual(created["status"], "created")
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(duplicate["task"]["id"], created["task"]["id"])
        self.assertEqual(created["task"]["history"][0]["event"], "created")
        self.assertEqual(TaskStore(self.root).list("all")["tasks"], [created["task"]])
        with self.assertRaises(HTTPException) as conflict:
            self.store.create("不同内容", None, "create-1", "建个待办：不同内容")
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_updates_are_optimistic_traceable_and_filterable_by_status_and_due_date(self):
        task = self.store.create("待修改", "2026-10-21", "create-2")["task"]
        updated = self.store.update(task["id"], {"title": "已修改", "due_date": "2026-10-22",
                                                 "expected_updated_at": task["updated_at"]})["task"]
        self.assertEqual(updated["title"], "已修改")
        self.assertEqual(updated["history"][-1]["changes"]["title"], {"from": "待修改", "to": "已修改"})
        self.assertEqual(self.store.list("open", "2026-10-22")["tasks"], [updated])
        completed = self.store.update(task["id"], {"status": "completed", "expected_updated_at": updated["updated_at"]})["task"]
        self.assertEqual(self.store.list("open")["tasks"], [])
        self.assertEqual(self.store.list("completed")["tasks"], [completed])
        reopened = self.store.update(task["id"], {"status": "open", "expected_updated_at": completed["updated_at"]})["task"]
        self.assertEqual(reopened["status"], "open")
        self.assertEqual(len(reopened["history"]), 4)
        with self.assertRaises(HTTPException) as stale:
            self.store.update(task["id"], {"title": "覆盖", "expected_updated_at": task["updated_at"]})
        self.assertEqual(stale.exception.status_code, 409)

    def test_concurrent_creates_do_not_lose_updates(self):
        def create(index):
            return self.store.create(f"合成任务 {index}", None, f"concurrent-{index}")["task"]["id"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(create, range(20)))
        tasks = self.store.list("all")["tasks"]
        self.assertEqual(len(tasks), 20)
        self.assertEqual(len(set(ids)), 20)

    def test_invalid_date_and_missing_task_are_rejected(self):
        with self.assertRaises(HTTPException) as invalid_date:
            self.store.create("待办", "下周五", "invalid-date")
        self.assertEqual(invalid_date.exception.status_code, 400)
        with self.assertRaises(HTTPException) as missing:
            self.store.update("0" * 32, {"status": "completed", "expected_updated_at": "x"})
        self.assertEqual(missing.exception.status_code, 404)

    def test_refuses_symlink_task_store(self):
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text('{"tasks":[],"idempotency":{}}', encoding="utf-8")
        outside.chmod(0o600)
        self.store.path.symlink_to(outside)
        with self.assertRaises(HTTPException):
            self.store.list("all")


if __name__ == "__main__":
    unittest.main()
