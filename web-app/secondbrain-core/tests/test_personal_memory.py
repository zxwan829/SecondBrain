import concurrent.futures
import hashlib
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.personal_memory import (
    MemoryConflictError,
    MemoryStoreError,
    PersonalMemoryStore,
    create_personal_memory_router,
)
from secondbrain_core.app import create_app


def _correct_in_process(root, memory_id, text, key):
    store = PersonalMemoryStore(root)
    try:
        store.correct(memory_id, content={"text": text}, source_type="user_message",
                      source_ref=f"synthetic-process:{key}", expected_revision=1,
                      idempotency_key=key)
        return "committed"
    except MemoryConflictError:
        return "conflict"


def test_create_app_uvicorn_localhost_lifecycle_http(tmp_path, monkeypatch):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    roots = {}
    for name in ("review", "raw", "knowledge", "state", "memory", "projects", "briefs", "tasks", "journal", "notes"):
        path = tmp_path / name
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
        roots[name] = path
    password = tmp_path / "app-password"
    password.write_bytes(b"synthetic-memory-password\n")
    os.chmod(password, 0o600)
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]), "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password), "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host, "SB_HERMES_API_URL": "",
        "SB_PROMOTE_ENABLED": "false", "SB_PERSONAL_MEMORY_ENABLED": "true",
        "SB_PERSONAL_MEMORY_ROOT": str(roots["memory"]), "SB_PERSONAL_LEARNING_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]), "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]), "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=origin, timeout=3.0) as client:
            unauthenticated = client.get("/api/personal-memory")
            assert unauthenticated.status_code == 401
            assert unauthenticated.headers["cache-control"] == "private, no-store"
            assert not (roots["memory"] / "personal-memory.lock").exists()
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-memory-password"})
            assert login.status_code == 200, login.text
            headers = {"Origin": origin}
            empty = client.get("/api/personal-memory", headers=headers)
            assert empty.status_code == 200 and empty.json() == {"items": []}
            assert empty.headers["cache-control"] == "private, no-store"
            assert not (roots["memory"] / "personal-memory.lock").exists()
            created = client.post("/api/personal-memory", headers=headers, json={
                "content": {"text": "Prefers concise summaries"}, "category": "preference",
                "fact_kind": "user_stated", "source_type": "user_message",
                "source_ref": "synthetic-localhost:message-1", "idempotency_key": "localhost-create",
            })
            assert created.status_code == 201, created.text
            assert "idempotency_digest" not in created.json()
            memory_id = created.json()["memory_id"]
            (roots["memory"] / "personal-memory.lock").unlink()
            legacy_read = client.get("/api/personal-memory", headers=headers)
            assert legacy_read.status_code == 200 and len(legacy_read.json()["items"]) == 1
            assert not (roots["memory"] / "personal-memory.lock").exists()
            correct_body = {"content": {"text": "Prefers short paragraphs"}, "source_type": "user_message",
                            "source_ref": "synthetic-localhost:message-2", "expected_revision": 1,
                            "idempotency_key": "localhost-correct"}
            corrected = client.post(f"/api/personal-memory/{memory_id}/correct", headers=headers, json=correct_body)
            assert corrected.status_code == 200, corrected.text
            replay = client.post(f"/api/personal-memory/{memory_id}/correct", headers=headers, json=correct_body)
            assert replay.status_code == 200 and replay.json() == corrected.json()
            stale = client.post(f"/api/personal-memory/{memory_id}/revoke", headers=headers, json={
                "source_type": "user_message", "source_ref": "synthetic-localhost:message-3",
                "expected_revision": 1, "idempotency_key": "localhost-stale-revoke",
            })
            assert stale.status_code == 409
            revoked = client.post(f"/api/personal-memory/{memory_id}/revoke", headers=headers, json={
                "source_type": "user_message", "source_ref": "synthetic-localhost:message-3",
                "expected_revision": 2, "idempotency_key": "localhost-revoke",
            })
            assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
            assert client.get("/api/personal-memory", headers=headers).json() == {"items": []}
            assert str(tmp_path) not in stale.text
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


class PersonalMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / "40-Memory"
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
        with self.assertRaises(MemoryConflictError):
            self.store.create(content={"text": "Prefers concise answers"}, category="preference",
                              fact_kind="user_stated", source_type="user_message",
                              source_ref="session-a:message-1", exact=True, idempotency_key="create-1")
        corrected = self.store.correct(first["memory_id"], content={"text": "Prefers short paragraphs"},
                                       source_type="user_message", source_ref="session-b:message-2",
                                       expected_revision=1, idempotency_key="correct-1")
        self.assertEqual(corrected["revision"], 2)
        self.assertEqual(self.store.correct(first["memory_id"], content={"text": "Prefers short paragraphs"},
                                            source_type="user_message", source_ref="session-b:message-2",
                                            expected_revision=1, idempotency_key="correct-1"), corrected)
        with self.assertRaises(MemoryConflictError):
            self.store.correct(first["memory_id"], content={"text": "Different correction"},
                               source_type="user_message", source_ref="session-b:message-2",
                               expected_revision=1, idempotency_key="correct-1")
        with self.assertRaises(MemoryConflictError):
            self.store.correct(first["memory_id"], content={"text": "Stale correction"},
                               source_type="user_message", source_ref="session-b:message-3",
                               expected_revision=1, idempotency_key="correct-stale")
        reopened = PersonalMemoryStore(self.root)
        self.assertEqual(reopened.correct(first["memory_id"], content={"text": "Prefers short paragraphs"},
                                          source_type="user_message", source_ref="session-b:message-2",
                                          expected_revision=1, idempotency_key="correct-1"), corrected)
        self.assertEqual(reopened.active_view()[0]["content"]["text"], "Prefers short paragraphs")
        self.assertEqual([row["content"]["text"] for row in reopened.history(first["memory_id"])],
                         ["Prefers concise answers", "Prefers short paragraphs"])
        self.assertEqual([row["revision_status"] for row in reopened.history(first["memory_id"])],
                         ["superseded", "active"])
        revoked = reopened.revoke(first["memory_id"], source_type="user_message",
                                  source_ref="session-c:message-3", expected_revision=2,
                                  idempotency_key="revoke-1")
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(PersonalMemoryStore(self.root).revoke(
            first["memory_id"], source_type="user_message", source_ref="session-c:message-3",
            expected_revision=2, idempotency_key="revoke-1"), revoked)
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

    def test_cross_process_corrections_use_revision_cas(self):
        first = self.create(source_ref="synthetic-cas:message-1", key="cas-create")
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_correct_in_process, str(self.root), first["memory_id"],
                                   text, key) for text, key in (
                                       ("correction A", "process-correct-a"),
                                       ("correction B", "process-correct-b"),
                                   )]
            results = [future.result() for future in futures]
        self.assertCountEqual(results, ["committed", "conflict"])
        self.assertEqual(len(self.store.history(first["memory_id"])), 2)

    def test_expiry_and_write_permission_fail_closed(self):
        root2 = Path(self.temp.name).resolve() / "40-Memory-expiry"
        root2.mkdir(mode=0o700)
        root2.chmod(0o700)
        store = PersonalMemoryStore(root2)
        item = store.create(content={"text": "Old project alias"}, category="project_context",
                            fact_kind="user_stated", source_type="user_message",
                            source_ref="session-expiry:message-2", expires_at="2000-01-01T00:00:00Z")
        self.assertEqual(store.active_view(), [])
        store.expire(item["memory_id"], source_type="user_message", source_ref="session-expiry:message-3",
                     expected_revision=1, idempotency_key="expire-1")
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

    def test_legacy_read_without_lock_file_is_stable_and_read_only(self):
        path = self.root / "personal-memory.jsonl"
        row = self.create()
        self.assertTrue((self.root / "personal-memory.lock").exists())
        (self.root / "personal-memory.lock").unlink()
        result = self.store.active_view()
        self.assertEqual(result[0]["memory_id"], row["memory_id"])
        self.assertFalse((self.root / "personal-memory.lock").exists())

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
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
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
        session_id = hashlib.sha256(token.encode()).hexdigest()
        self.auth._sessions[session_id] = time.time() + 60
        self.auth._session_actions[session_id] = set(self.auth.SUPPORTED_ACTIONS)
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
                                           "source_ref": "synthetic-session-2:message-2",
                                           "expected_revision": 1, "idempotency_key": "api-correct-1"})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        replay = self.client.post(f"/api/personal-memory/{memory_id}/correct", headers=self.headers,
                                  json={"content": {"text": "Prefers short paragraphs"},
                                        "source_type": "user_message",
                                        "source_ref": "synthetic-session-2:message-2",
                                        "expected_revision": 1, "idempotency_key": "api-correct-1"})
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), corrected.json())
        self.assertNotIn("idempotency_digest", corrected.json())
        recall = self.client.get("/api/personal-memory", headers=self.headers).json()["items"]
        self.assertEqual([row["content"]["text"] for row in recall], ["Prefers short paragraphs"])
        history = self.client.get(f"/api/personal-memory/{memory_id}/history", headers=self.headers).json()
        self.assertEqual([row["revision"] for row in history["revisions"]], [1, 2])
        revoked = self.client.post(f"/api/personal-memory/{memory_id}/revoke", headers=self.headers,
                                   json={"source_type": "user_message", "source_ref": "synthetic-session-3:message-3",
                                         "expected_revision": 2, "idempotency_key": "api-revoke-1"})
        self.assertEqual(revoked.json()["status"], "revoked")
        self.assertEqual(self.client.get("/api/personal-memory", headers=self.headers).json()["items"], [])
        malformed = self.client.post("/api/personal-memory", headers=self.headers, json={
            "content": {"text": "version v1.0"}, "category": "fact", "fact_kind": "user_stated",
            "source_type": "user_message", "source_ref": "", "exact": True,
        })
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(self.client.get("/api/personal-memory/../../password/history", headers=self.headers).status_code, 404)

    def test_read_only_get_does_not_create_lock_file(self):
        self.assertFalse((self.root / "personal-memory.lock").exists())
        response = self.client.get("/api/personal-memory", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        history = self.client.get("/api/personal-memory/missing-memory/history", headers=self.headers)
        self.assertEqual(history.status_code, 404)
        self.assertFalse((self.root / "personal-memory.lock").exists())

    def test_api_cas_conflict_and_idempotency_conflict_are_sanitized(self):
        created = self.client.post("/api/personal-memory", headers=self.headers, json={
            "content": {"text": "Prefers concise answers"}, "category": "preference",
            "fact_kind": "user_stated", "source_type": "user_message",
            "source_ref": "synthetic-session:message-10", "idempotency_key": "cas-api-create",
        })
        memory_id = created.json()["memory_id"]
        route = f"/api/personal-memory/{memory_id}/correct"
        body = {"content": {"text": "Prefers short paragraphs"}, "source_type": "user_message",
                "source_ref": "synthetic-session:message-11", "expected_revision": 1,
                "idempotency_key": "cas-api-correct"}
        first = self.client.post(route, headers=self.headers, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        replay = self.client.post(route, headers=self.headers, json=body)
        self.assertEqual(replay.json(), first.json())
        conflict = self.client.post(route, headers=self.headers,
                                    json={**body, "content": {"text": "Other intent"}})
        self.assertEqual(conflict.status_code, 409)
        stale = self.client.post(route, headers=self.headers,
                                 json={**body, "idempotency_key": "cas-api-stale",
                                       "source_ref": "synthetic-session:message-12"})
        self.assertEqual(stale.status_code, 409)
        self.assertNotIn(str(self.root), conflict.text + stale.text)

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
