import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from secondbrain_core.modules.vocabulary import (
    FRONTMATTER_TAGS_KEY,
    FRONTMATTER_TYPE_KEY,
    INITIAL_TYPES,
    NoteVocabularyOverrides,
    VocabularyStore,
    apply_automatic_metadata,
    create_vocabulary_router,
    preview_inventory_candidates,
)


class VocabularyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = VocabularyStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_are_spec_types_and_tag_catalog_starts_empty(self):
        state = self.store.read()
        self.assertEqual([item["name"] for item in state["types"]], list(INITIAL_TYPES))
        self.assertEqual(state["tags"], [])
        self.assertEqual(state["revision"], 0)
        self.assertEqual(state["audit"], [])

    def test_add_tag_disable_and_synonym_are_confirmed_versioned_and_audited(self):
        with self.assertRaises(HTTPException) as unconfirmed:
            self.store.add_tag("CRM", 0, False)
        self.assertEqual(unconfirmed.exception.status_code, 400)
        state = self.store.add_tag("CRM", 0, True)
        tag = state["tags"][0]
        self.assertEqual(state["revision"], 1)
        state = self.store.add_synonym("客户关系", tag["id"], 1, True)
        self.assertEqual(state["revision"], 2)
        state = self.store.set_tag_enabled(tag["id"], False, 2, True)
        self.assertEqual(state["revision"], 3)
        self.assertEqual(state["tags"][0]["enabled"], False)
        self.assertEqual(state["synonyms"][0]["alias"], "客户关系")
        self.assertEqual([entry["revision"] for entry in state["audit"]], [1, 2, 3])
        self.assertEqual([entry["operation"] for entry in state["audit"]], ["tag.add", "synonym.add", "tag.set_enabled"])
        self.assertFalse(any("note" in str(entry).lower() for entry in state["audit"]))
        self.assertEqual((self.root / "vocabulary" / "catalog.json").stat().st_mode & 0o777, 0o600)

    def test_revision_mismatch_fails_closed_and_type_limit_is_ten_total(self):
        with self.assertRaises(HTTPException) as stale:
            self.store.add_tag("CRM", 1, True)
        self.assertEqual(stale.exception.status_code, 412)
        state = self.store.read()
        for index in range(5):
            state = self.store.add_type(f"自定义类型{index}", state["revision"], True)
        state = self.store.set_type_enabled(state["types"][-1]["id"], False, state["revision"], True)
        with self.assertRaises(HTTPException) as full:
            self.store.add_type("第十一种", state["revision"], True)
        self.assertEqual(full.exception.status_code, 409)
        self.assertEqual(len(state["types"]), 10)

    def test_two_writers_using_same_revision_only_commit_once(self):
        second_store = VocabularyStore(self.root)

        def add(store, name):
            try:
                store.add_tag(name, 0, True)
                return "saved"
            except HTTPException as error:
                return error.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda args: add(*args), [(self.store, "CRM"), (second_store, "Project")]))
        self.assertCountEqual(outcomes, ["saved", 412])
        state = self.store.read()
        self.assertEqual(state["revision"], 1)
        self.assertEqual(len(state["audit"]), 1)

    def test_manual_type_lock_and_removed_tag_suppression_contract(self):
        metadata = apply_automatic_metadata(NoteVocabularyOverrides("笔记", True, ("CRM",)), "摘要",
                                            ["CRM", "SecondBrain", "CRM", "roadmap"],
                                            ["日记", "笔记", "摘要"], ["CRM", "SecondBrain"])
        self.assertEqual(metadata, {FRONTMATTER_TYPE_KEY: "笔记", FRONTMATTER_TAGS_KEY: ["SecondBrain"]})
        self.assertEqual(FRONTMATTER_TYPE_KEY, "类型")
        self.assertEqual(FRONTMATTER_TAGS_KEY, "tags")
        self.assertNotIn("状态", metadata)
        self.assertEqual(apply_automatic_metadata(NoteVocabularyOverrides("笔记", False, ()), "摘要",
                                                  ["CRM", "新词"], ["笔记", "摘要"], ["CRM"]),
                         {"类型": "摘要", "tags": ["CRM"]})
        self.assertEqual(apply_automatic_metadata(NoteVocabularyOverrides("笔记", False, ()), "新类型",
                                                  [], ["笔记", "摘要"], []),
                         {"类型": "笔记", "tags": []})

    def test_inventory_preview_is_read_only_and_does_not_persist_candidates(self):
        state = self.store.add_tag("CRM", 0, True)
        before = self.store.read()
        result = preview_inventory_candidates(["CRM", "roadmap", "roadmap"], state)
        self.assertEqual(result["known"], ["CRM"])
        self.assertEqual(result["new_pending_review"], ["roadmap"])
        self.assertFalse(result["source_read"])
        self.assertFalse(result["persisted"])
        self.assertEqual(self.store.read(), before)

    def test_vocabulary_api_requires_owner_uses_revision_and_separates_read_write_actions(self):
        class SessionAuth:
            def __init__(self):
                self.actions = []

            def require_action(self, request: Request, action: str):
                self.actions.append(action)
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        auth = SessionAuth()
        app = FastAPI()
        app.include_router(create_vocabulary_router(auth, self.store))
        client = TestClient(app)
        self.assertEqual(client.get("/api/vocabulary").status_code, 401)
        client.cookies.set("session", "owner")
        initial = client.get("/api/vocabulary")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.headers["etag"], '"0"')
        missing_revision = client.post("/api/vocabulary/tags", json={"name": "CRM", "confirmed": True})
        self.assertEqual(missing_revision.status_code, 428)
        added = client.post("/api/vocabulary/tags", json={"name": "CRM", "confirmed": True}, headers={"If-Match": '"0"'})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.headers["etag"], '"1"')
        self.assertIn("vocabulary.read", auth.actions)
        self.assertIn("vocabulary.write", auth.actions)


if __name__ == "__main__":
    unittest.main()
