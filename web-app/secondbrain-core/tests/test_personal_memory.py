import concurrent.futures
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.personal_memory import (
    MemoryStoreError,
    PersonalMemoryStore,
    create_personal_memory_router,
)


class PersonalMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name) / "40-Memory"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.store = PersonalMemoryStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, *, source_ref="session-a:message-1", text="Prefers concise answers",
               fact_kind="user_stated", exact=False, key="create-1"):
        return self.store.create(content={"text": text}, category="preference", fact_kind=fact_kind,
                                 source_type="user_message", source_ref=source_ref,
                                 exact=exact, idempotency_key=key)

    def test_create_correct_history_revoke_and_restart_recovery(self):
        first = self.create()
        replay = self.create()
        self.assertEqual(first, replay)
        corrected = self.store.correct(first["memory_id"], content={"text": "Prefers short paragraphs"},
                                       source_type="user_message", source_ref="session-b:message-2")
        self.assertEqual(corrected["revision"], 2)
        reopened = PersonalMemoryStore(self.root)
        self.assertEqual(reopened.active_view()[0]["content"]["text"], "Prefers short paragraphs")
        self.assertEqual([row["content"]["text"] for row in reopened.history(first["memory_id"])],
                         ["Prefers concise answers", "Prefers short paragraphs"])
        self.assertEqual([row["revision_status"] for row in reopened.history(first["memory_id"])],
                         ["superseded", "active"])
        revoked = reopened.revoke(first["memory_id"], source_type="user_message",
                                  source_ref="session-c:message-3")
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(PersonalMemoryStore(self.root).active_view(), [])
        self.assertEqual(len(PersonalMemoryStore(self.root).history(first["memory_id"])), 3)

    def test_inference_is_not_recalled_and_unverified_facts_are_redacted_from_recall(self):
        inferred = self.create(source_ref="session-a:message-4", text="May like tea",
                               fact_kind="inference", key="create-4")
        self.assertEqual(inferred["status"], "pending_verification")
        self.assertEqual(self.store.active_view(), [])
        with self.assertRaises(ValueError):
            self.store.create(content={"text": "Release v4.2"}, category="fact", fact_kind="user_stated",
                              source_type="user_message", source_ref="", exact=True)
        with self.assertRaisesRegex(ValueError, "traversal"):
            self.store.create(content={"text": "Synthetic"}, category="fact", fact_kind="user_stated",
                              source_type="original_file", source_ref="../Private/secret.md")
        exact = self.store.create(content={"text": "Release v4.2"}, category="fact", fact_kind="user_stated",
                                  source_type="original_file", source_ref="missing/synthetic-spec.md#version")
        self.assertEqual(exact["verification_status"], "source_required")
        recalled = self.store.active_view()[0]
        self.assertEqual(recalled["source"]["ref"], "missing/synthetic-spec.md#version")
        self.assertEqual(recalled["recall_status"], "source_required")
        self.assertNotIn("v4.2", json.dumps(recalled))
        self.assertEqual(self.store.history(exact["memory_id"])[0]["content"]["text"], "Release v4.2")

    def test_distinct_facts_from_one_source_are_idempotent_and_concurrent_appends_remain_valid(self):
        first = self.store.create(content={"text": "Uses metric units"}, category="preference",
                                  fact_kind="user_stated", source_type="user_message",
                                  source_ref="session-a:message-1")
        second = self.store.create(content={"text": "Prefers paragraph summaries"}, category="preference",
                                   fact_kind="user_stated", source_type="user_message",
                                   source_ref="session-a:message-1")
        replay_first = self.store.create(content={"text": "Uses metric units"}, category="preference",
                                         fact_kind="user_stated", source_type="user_message",
                                         source_ref="session-a:message-1")
        self.assertEqual(first, replay_first)
        self.assertNotEqual(first["memory_id"], second["memory_id"])
        self.assertEqual({row["content"]["text"] for row in self.store.active_view(limit=10)},
                         {"Uses metric units", "Prefers paragraph summaries"})

        def write(index):
            return self.create(source_ref=f"session-parallel:message-{index}",
                               text=f"Synthetic item {index}", key=f"parallel-{index}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(24)))
        rows = [json.loads(line) for line in (self.root / "personal-memory.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 26)
        self.assertEqual(len(self.store.active_view(limit=20)), 20)
        self.assertTrue(all(row["schema"] == 1 for row in rows))

    def test_expiry_and_write_permission_fail_closed(self):
        root2 = Path(self.temp.name) / "40-Memory-expiry"
        root2.mkdir(mode=0o700)
        root2.chmod(0o700)
        store = PersonalMemoryStore(root2)
        item = store.create(content={"text": "Old project alias"}, category="project_context",
                            fact_kind="user_stated", source_type="user_message",
                            source_ref="session-expiry:message-2", expires_at="2000-01-01T00:00:00Z")
        self.assertEqual(store.active_view(), [])
        store.expire(item["memory_id"], source_type="user_message", source_ref="session-expiry:message-3")
        self.assertEqual(store.history(item["memory_id"])[-1]["revision_status"], "expired")
        self.root.chmod(0o755)
        try:
            with self.assertRaises(MemoryStoreError):
                PersonalMemoryStore(self.root)
        finally:
            self.root.chmod(0o700)

    def test_incomplete_final_record_fails_closed_without_modification(self):
        path = self.root / "personal-memory.jsonl"
        path.write_bytes(b'{"schema":1')
        path.chmod(0o600)
        before = path.read_bytes()
        with self.assertRaisesRegex(MemoryStoreError, "incomplete final record"):
            self.store.active_view()
        with self.assertRaises(MemoryStoreError):
            self.create(source_ref="session-a:message-9", key="no-write")
        self.assertEqual(path.read_bytes(), before)

    def test_symlink_root_and_data_file_are_rejected(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir(mode=0o700)
        outside.chmod(0o700)
        linked_root = Path(self.temp.name) / "linked"
        linked_root.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(MemoryStoreError):
            PersonalMemoryStore(linked_root)
        (self.root / "personal-memory.jsonl").symlink_to(outside / "target")
        with self.assertRaises(MemoryStoreError):
            self.store.active_view()


class PersonalMemoryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        password = self.root / "password"
        password.write_text("synthetic-test-password")
        password.chmod(0o600)
        self.auth = AppSessionAuth(str(password), ["https://testserver"])
        self.store = PersonalMemoryStore(self.root)
        app = FastAPI()
        app.include_router(create_personal_memory_router(self.auth, self.store))
        self.client = TestClient(app, base_url="https://testserver")
        token = "synthetic-auth-session"
        self.auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 60
        self.client.cookies.set(self.auth.COOKIE_NAME, token)
        self.headers = {"Origin": "https://testserver"}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_api_create_correct_history_recall_revoke_and_security(self):
        unauthenticated = TestClient(self.client.app, base_url="https://testserver")
        self.assertEqual(unauthenticated.get("/api/personal-memory").status_code, 401)
        unauthenticated.close()
        denied_origin = self.client.post("/api/personal-memory", headers={"Origin": "https://evil.invalid"}, json={
            "content": {"text": "No"}, "category": "preference", "fact_kind": "user_stated",
            "source_type": "user_message", "source_ref": "invalid-origin:message-1",
        })
        self.assertEqual(denied_origin.status_code, 403)
        created = self.client.post("/api/personal-memory", headers=self.headers, json={
            "content": {"text": "Prefers a short answer"}, "category": "preference",
            "fact_kind": "user_stated", "source_type": "user_message",
            "source_ref": "synthetic-session:message-1", "idempotency_key": "synthetic-create-1",
        })
        self.assertEqual(created.status_code, 201, created.text)
        memory_id = created.json()["memory_id"]
        corrected = self.client.post(f"/api/personal-memory/{memory_id}/correct", headers=self.headers,
                                     json={"content": {"text": "Prefers short paragraphs"},
                                           "source_type": "user_message",
                                           "source_ref": "synthetic-session-2:message-2"})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        recall = self.client.get("/api/personal-memory", headers=self.headers).json()["items"]
        self.assertEqual([row["content"]["text"] for row in recall], ["Prefers short paragraphs"])
        history = self.client.get(f"/api/personal-memory/{memory_id}/history", headers=self.headers).json()
        self.assertEqual([row["revision"] for row in history["revisions"]], [1, 2])
        revoked = self.client.post(f"/api/personal-memory/{memory_id}/revoke", headers=self.headers,
                                   json={"source_type": "user_message", "source_ref": "synthetic-session-3:message-3"})
        self.assertEqual(revoked.json()["status"], "revoked")
        self.assertEqual(self.client.get("/api/personal-memory", headers=self.headers).json()["items"], [])
        malformed = self.client.post("/api/personal-memory", headers=self.headers, json={
            "content": {"text": "version v1.0"}, "category": "fact", "fact_kind": "user_stated",
            "source_type": "user_message", "source_ref": "", "exact": True,
        })
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(self.client.get("/api/personal-memory/../../password/history", headers=self.headers).status_code, 404)

    def test_api_recall_redacts_fact_when_exact_flag_is_omitted(self):
        created = self.client.post("/api/personal-memory", headers=self.headers, json={
            "content": {"text": "Synthetic contract value is 987654321 units"}, "category": "fact",
            "fact_kind": "user_stated", "source_type": "original_file",
            "source_ref": "missing/synthetic-contract.md#amount",
        })
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["verification_status"], "source_required")
        memory_id = created.json()["memory_id"]
        recall = self.client.get("/api/personal-memory", headers=self.headers).json()["items"]
        self.assertEqual(len(recall), 1)
        self.assertEqual(recall[0]["recall_status"], "source_required")
        self.assertEqual(recall[0]["source"]["ref"], "missing/synthetic-contract.md#amount")
        self.assertNotIn("987654321", json.dumps(recall))
        history = self.client.get(f"/api/personal-memory/{memory_id}/history", headers=self.headers).json()
        self.assertIn("987654321", history["revisions"][0]["content"]["text"])


if __name__ == "__main__":
    unittest.main()
