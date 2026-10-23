import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

        def commit_then_fail(data):
            write(data)
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


if __name__ == "__main__":
    unittest.main()
