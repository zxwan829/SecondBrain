import concurrent.futures
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from secondbrain_core.modules.tasks import TaskStore
from secondbrain_core.modules import tasks as tasks_module


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

    def test_projection_read_enforces_actual_byte_budget_after_fstat(self):
        self.store.create("Synthetic bounded task", None, "bounded-task-create")
        original_read = os.read
        changed = {"done": False}

        def grow_store_before_read(fd, size):
            if not changed["done"]:
                changed["done"] = True
                with self.store.path.open("ab") as output:
                    output.write(b" " * (2 * 1024 * 1024 + 1))
                    output.flush()
                    os.fsync(output.fileno())
            return original_read(fd, size)

        with patch.object(tasks_module.os, "read", side_effect=grow_store_before_read):
            with self.assertRaises(HTTPException) as over_budget:
                self.store.list_for_projection()
        self.assertEqual(over_budget.exception.status_code, 503)
        self.assertEqual(over_budget.exception.detail, "Task projection exceeds read budget")

    def test_projection_accepts_exact_budget_and_rejects_one_byte_over(self):
        budget = 2 * 1024 * 1024
        prefix = b'{"tasks":[],"idempotency":{},"padding":"'
        suffix = b'"}'
        exact = prefix + b"x" * (budget - len(prefix) - len(suffix)) + suffix
        self.store.path.write_bytes(exact)
        self.store.path.chmod(0o600)
        self.assertEqual(self.store.list_for_projection(), {"tasks": []})
        self.store.path.write_bytes(exact + b" ")
        self.store.path.chmod(0o600)
        with self.assertRaises(HTTPException) as over_budget:
            self.store.list_for_projection()
        self.assertEqual(over_budget.exception.status_code, 503)

    def test_task_store_rejects_replaced_root_after_initialization(self):
        self.store.create("Synthetic root pin", None, "root-pin-create")
        displaced = Path(self.temp.name) / "tasks-original"
        self.root.rename(displaced)
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        with self.assertRaises(HTTPException) as replaced:
            self.store.list("all")
        self.assertEqual(replaced.exception.status_code, 503)

    def test_task_write_does_not_follow_root_replaced_after_lock_and_read(self):
        displaced = Path(self.temp.name) / "tasks-original"
        original_read = self.store._read_unlocked

        def read_then_replace_root(*args, **kwargs):
            data = original_read(*args, **kwargs)
            self.root.rename(displaced)
            self.root.mkdir(mode=0o700)
            self.root.chmod(0o700)
            return data

        with patch.object(self.store, "_read_unlocked", side_effect=read_then_replace_root):
            with self.assertRaises(HTTPException) as replaced:
                self.store.create("Synthetic root swap", None, "root-swap-create")

        self.assertEqual(replaced.exception.status_code, 503)
        self.assertFalse((self.root / "tasks.json").exists())

    def test_task_write_fd_stays_pinned_if_root_moves_after_open(self):
        displaced = Path(self.temp.name) / "tasks-original"
        original_open_root = self.store._open_root
        calls = {"count": 0}

        def open_then_replace_root():
            calls["count"] += 1
            fd = original_open_root()
            if calls["count"] == 3:  # lock, read, then write directory FD
                self.root.rename(displaced)
                self.root.mkdir(mode=0o700)
                self.root.chmod(0o700)
            return fd

        with patch.object(self.store, "_open_root", side_effect=open_then_replace_root):
            with self.assertRaises(HTTPException) as replaced:
                self.store.create("Synthetic pinned fd", None, "pinned-fd-create")

        self.assertEqual(replaced.exception.status_code, 503)
        self.assertFalse((self.root / "tasks.json").exists())
        self.assertFalse(list(self.root.glob(".tasks-*.tmp")))
        # A fail-closed error may leave the atomic write in the displaced private
        # directory, but it must never cross into the replacement path.
        self.assertTrue((displaced / "tasks.json").exists())

    def test_task_data_reader_preserves_owner_only_read_only_file_compatibility(self):
        task = self.store.create("Synthetic read-only legacy mode", None, "legacy-mode-create")["task"]
        self.store.path.chmod(0o400)
        self.assertEqual(self.store.list("all")["tasks"], [task])


if __name__ == "__main__":
    unittest.main()
