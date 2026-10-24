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

    def test_keyed_update_replays_same_receipt_without_second_mutation(self):
        task = self.store.create("待重试更新", None, "update-create")["task"]
        body = {"title": "更新一次", "expected_updated_at": task["updated_at"]}
        first = self.store.update(task["id"], body, idempotency_key="task-update-once")
        replay = self.store.update(task["id"], body, idempotency_key="task-update-once")
        self.assertEqual(replay, first)
        self.assertEqual(len(self.store.list("all")["tasks"][0]["history"]), 2)

        with self.assertRaises(HTTPException) as changed_body:
            self.store.update(task["id"], {**body, "title": "不同内容"}, idempotency_key="task-update-once")
        self.assertEqual(changed_body.exception.status_code, 409)
        with self.assertRaises(HTTPException) as changed_target:
            self.store.update("0" * 32, body, idempotency_key="task-update-once")
        self.assertEqual(changed_target.exception.status_code, 409)
        with self.assertRaises(HTTPException) as cross_operation:
            self.store.create("不同操作", None, "task-update-once")
        self.assertEqual(cross_operation.exception.status_code, 409)

    def test_keyed_update_conflicts_after_task_advances_and_cas_stops_competing_keys(self):
        task = self.store.create("并发待办", None, "update-concurrent-create")["task"]
        body = {"status": "completed", "expected_updated_at": task["updated_at"]}

        def update(key):
            try:
                return self.store.update(task["id"], body, idempotency_key=key)["task"]["updated_at"]
            except HTTPException as exc:
                return exc.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(update, ["same-key"] * 8))
        self.assertEqual(len({item for item in outcomes if isinstance(item, str)}), 1)
        self.assertEqual(outcomes.count(409), 0)
        completed = self.store.list("all")["tasks"][0]
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(len(completed["history"]), 2)
        advanced_task = self.store.update(
            task["id"],
            {"status": "open", "expected_updated_at": completed["updated_at"]},
        )["task"]

        with self.assertRaises(HTTPException) as advanced:
            self.store.update(task["id"], body, idempotency_key="same-key")
        self.assertEqual(advanced.exception.status_code, 409)
        with self.assertRaises(HTTPException) as stale:
            self.store.update(task["id"], {
                "status": "completed", "expected_updated_at": completed["updated_at"],
            }, idempotency_key="different-key")
        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(self.store.list("all")["tasks"][0], advanced_task)

    def test_keyed_update_recovers_after_commit_then_store_reports_failure(self):
        task = self.store.create("恢复待办", None, "update-recovery-create")["task"]
        body = {"status": "completed", "expected_updated_at": task["updated_at"]}
        write = self.store._write_unlocked

        def commit_then_fail(data, rollback):
            write(data, rollback)
            raise HTTPException(status_code=503, detail="synthetic response interruption after durable commit")

        with patch.object(self.store, "_write_unlocked", side_effect=commit_then_fail):
            with self.assertRaises(HTTPException) as interrupted:
                self.store.update(task["id"], body, idempotency_key="task-update-recovery")
        self.assertEqual(interrupted.exception.status_code, 503)

        retry = self.store.update(task["id"], body, idempotency_key="task-update-recovery")
        self.assertEqual(retry["task"]["status"], "completed")
        self.assertEqual(len(retry["task"]["history"]), 2)

    def test_keyed_update_limit_fails_before_mutating_task(self):
        task = self.store.create("容量待办", None, "update-capacity-create")["task"]
        body = {"status": "completed", "expected_updated_at": task["updated_at"]}
        with patch("secondbrain_core.modules.tasks._MAX_TASK_UPDATE_IDEMPOTENCY_KEYS", 0):
            with self.assertRaises(HTTPException) as full:
                self.store.update(task["id"], body, idempotency_key="task-update-full")
        self.assertEqual(full.exception.status_code, 503)
        unchanged = self.store.list("all")["tasks"][0]
        self.assertEqual(unchanged["status"], "open")
        self.assertEqual(unchanged["updated_at"], task["updated_at"])

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

    def test_task_write_aborts_if_root_moves_before_atomic_commit(self):
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
        self.assertFalse((displaced / "tasks.json").exists())

    def test_task_write_rolls_back_if_root_moves_after_commit_before_path_check(self):
        task = self.store.create("Synthetic pre-swap task", None, "pre-swap-create")["task"]
        displaced = Path(self.temp.name) / "tasks-original"
        replacement = Path(self.temp.name) / "tasks-replacement"
        original_fsync = os.fsync
        moved = {"done": False}

        def fsync_then_replace_directory(fd):
            original_fsync(fd)
            if not moved["done"] and os.fstat(fd).st_mode & 0o170000 == 0o040000:
                moved["done"] = True
                self.root.rename(displaced)
                self.root.mkdir(mode=0o700)
                self.root.chmod(0o700)

        with patch.object(tasks_module.os, "fsync", side_effect=fsync_then_replace_directory):
            with self.assertRaises(HTTPException) as interrupted:
                self.store.update(task["id"], {
                    "status": "completed", "expected_updated_at": task["updated_at"],
                }, idempotency_key="root-swap-update")

        self.assertTrue(moved["done"])
        self.assertEqual(interrupted.exception.status_code, 503)
        self.assertEqual(interrupted.exception.detail, "Task write was rolled back because storage changed")
        self.assertFalse((self.root / "tasks.json").exists())
        self.assertEqual(tasks_module.json.loads((displaced / "tasks.json").read_text())["tasks"], [task])

        # Restore the original store root; retry proceeds as a new commit because
        # the prior attempt was durably rolled back.
        self.root.rename(replacement)
        displaced.rename(self.root)
        replay = self.store.update(task["id"], {
            "status": "completed", "expected_updated_at": task["updated_at"],
        }, idempotency_key="root-swap-update")
        self.assertEqual(replay["task"]["status"], "completed")
        self.assertEqual(len(replay["task"]["history"]), 2)
        self.assertEqual(len(self.store.list("all")["tasks"]), 1)

    def test_task_write_rolls_back_if_directory_fsync_fails_then_keyed_retry_commits(self):
        original_fsync = os.fsync
        failed = {"once": False}

        def fail_first_directory_sync(fd):
            if (not failed["once"]
                    and tasks_module.stat.S_ISDIR(os.fstat(fd).st_mode)):
                failed["once"] = True
                raise OSError("synthetic directory fsync failure")
            return original_fsync(fd)

        with patch.object(tasks_module.os, "fsync", side_effect=fail_first_directory_sync):
            with self.assertRaises(HTTPException) as interrupted:
                self.store.create("Synthetic fsync recovery", None, "fsync-retry-key")

        self.assertTrue(failed["once"])
        self.assertEqual(interrupted.exception.status_code, 503)
        self.assertEqual(interrupted.exception.detail,
                         "Task write was rolled back after storage sync failure")
        self.assertEqual(tasks_module.json.loads(self.store.path.read_text()),
                         {"tasks": [], "idempotency": {}})

        retry = self.store.create("Synthetic fsync recovery", None, "fsync-retry-key")
        self.assertEqual(retry["status"], "created")
        self.assertEqual(len(self.store.list("all")["tasks"]), 1)

    def test_task_write_reports_recovery_if_rollback_directory_fsync_also_fails(self):
        original_fsync = os.fsync
        directory_syncs = {"count": 0}

        def fail_commit_and_rollback_directory_sync(fd):
            if tasks_module.stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_syncs["count"] += 1
                if directory_syncs["count"] <= 2:
                    raise OSError("synthetic directory fsync failure")
            return original_fsync(fd)

        with patch.object(tasks_module.os, "fsync", side_effect=fail_commit_and_rollback_directory_sync):
            with self.assertRaises(HTTPException) as interrupted:
                self.store.create("Synthetic rollback uncertainty", None, "rollback-retry-key")

        self.assertEqual(directory_syncs["count"], 2)
        self.assertEqual(interrupted.exception.status_code, 503)
        self.assertEqual(interrupted.exception.detail,
                         "Task write outcome requires recovery; reload Task state before retrying")

        # The visible state is read under the same store lock; keyed retry either
        # replays the committed receipt or performs the rolled-back operation.
        retry = self.store.create("Synthetic rollback uncertainty", None, "rollback-retry-key")
        self.assertIn(retry["status"], {"created", "duplicate"})
        self.assertEqual(len(self.store.list("all")["tasks"]), 1)

    def test_task_write_rolls_back_root_swap_between_validation_and_replace(self):
        displaced = Path(self.temp.name) / "tasks-original"
        original_replace = os.replace
        swapped = {"done": False}

        def swap_root_then_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
            if not swapped["done"]:
                swapped["done"] = True
                self.root.rename(displaced)
                self.root.mkdir(mode=0o700)
                self.root.chmod(0o700)
            return original_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

        with patch.object(tasks_module.os, "replace", side_effect=swap_root_then_replace):
            with self.assertRaises(HTTPException) as interrupted:
                self.store.create("Synthetic mid-commit root swap", None, "mid-swap-key")

        self.assertTrue(swapped["done"])
        self.assertEqual(interrupted.exception.status_code, 503)
        self.assertEqual(interrupted.exception.detail, "Task write was rolled back because storage changed")
        self.assertFalse((self.root / "tasks.json").exists())
        self.assertEqual(tasks_module.json.loads((displaced / "tasks.json").read_text()),
                         {"tasks": [], "idempotency": {}})

    def test_task_data_reader_preserves_owner_only_read_only_file_compatibility(self):
        task = self.store.create("Synthetic read-only legacy mode", None, "legacy-mode-create")["task"]
        self.store.path.chmod(0o400)
        self.assertEqual(self.store.list("all")["tasks"], [task])


if __name__ == "__main__":
    unittest.main()
