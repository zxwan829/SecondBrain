import tempfile
import unittest
import concurrent.futures
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from secondbrain_core.modules.inbox_proposals import InboxProposalStore, InboxProposalSources, _mock_suggestions


class InboxProposalStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "proposals"
        self.store = InboxProposalStore(self.root)
        self.vocabulary = {"revision": 4,
                          "types": [{"name": name, "enabled": True} for name in ("日记", "笔记", "头脑风暴", "摘要", "会议纪要")],
                          "tags": [{"id": "crm", "name": "CRM", "enabled": True},
                                   {"id": "sb", "name": "SecondBrain", "enabled": True}], "synonyms": []}
        self.source = {"source_kind": "notes", "source_id": "drafts:synthetic/note.md",
                       "collection": "drafts", "path": "synthetic/note.md"}

    def tearDown(self):
        self.temp.cleanup()

    def create(self, version="etag-1", key="create-1"):
        suggestions = _mock_suggestions("记一下：合成内容 #CRM #newterm", "合成", {}, self.vocabulary)
        return self.store.create(self.source, version, suggestions, "owner", key,
                                 vocabulary_version=self.vocabulary["revision"])

    def test_persist_reload_idempotent_decision_and_conflict(self):
        created = self.create()
        journal = next(item for item in created["proposals"] if item["kind"] == "journal")
        self.assertEqual(journal["target_execution_status"], "not_executed")
        approved = self.store.decide(journal["proposal_id"], "approved_recorded", 1, "owner", "decision-1", "etag-1")
        self.assertEqual(approved["target_execution_status"], "not_executed")
        reloaded = InboxProposalStore(self.root).get(journal["proposal_id"])
        self.assertEqual(reloaded["status"], "approved_recorded")
        replay = self.store.idempotent_result(journal["proposal_id"], "decision", "approved_recorded", 1, "owner", "decision-1")
        self.assertEqual(replay["status"], "approved_recorded")
        with self.assertRaises(HTTPException) as stale:
            self.store.decide(journal["proposal_id"], "rejected", 1, "owner", "decision-2", "etag-1")
        self.assertEqual(stale.exception.status_code, 412)

    def test_concurrent_decisions_use_version_conflict_protection(self):
        created = self.create()
        project = next(item for item in created["proposals"] if item["kind"] == "project")

        def decide(value, key):
            try:
                return self.store.decide(project["proposal_id"], value, 1, "owner", key, "etag-1")["status"]
            except HTTPException as error:
                return error.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda args: decide(*args), [("approved_recorded", "race-a"), ("rejected", "race-b")]))
        self.assertCountEqual(outcomes, ["approved_recorded", 412])

    def test_source_change_stales_records_and_idempotency_reuse_conflicts(self):
        created = self.create()
        proposal_id = created["proposals"][0]["proposal_id"]
        result = self.store.for_source(self.source, "etag-2", "owner")
        self.assertTrue(all(item["status"] == "stale" for item in result["proposals"]))
        with self.assertRaises(HTTPException) as conflict:
            self.create(version="etag-other")
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(self.store.get(proposal_id)["status"], "stale")

    def test_vocabulary_revision_change_stales_saved_suggestions(self):
        created = self.create()
        result = self.store.for_source(self.source, "etag-1", "owner", vocabulary_version=5)
        self.assertTrue(all(item["status"] == "stale" for item in result["proposals"]))
        self.assertTrue(all(item["stale_reason"] == "source_or_vocabulary_version_changed"
                            for item in result["proposals"]))

    def test_unknown_terms_are_candidates_and_manual_removal_persists(self):
        initial = self.create()
        tags = next(item for item in initial["proposals"] if item["kind"] == "tags")
        self.assertEqual(tags["vocabulary_version"], 4)
        self.assertIn("newterm", tags["suggestion"]["current"]["unknown_candidates"])
        self.store.edit(tags["proposal_id"], {"values": [], "unknown_candidates": ["newterm"], "removed_by_user": [],
                                                "vocabulary_values": ["CRM", "SecondBrain"]},
                        1, "owner", "edit-tags", "etag-1")
        again = _mock_suggestions("#CRM #newterm", "", self.store.preferences(self.source), self.vocabulary)
        self.assertEqual(again["tags"]["values"], [])

    def test_suggestions_use_only_the_current_central_vocabulary(self):
        empty_catalog = {"revision": 9, "types": [{"name": "笔记", "enabled": True}], "tags": [], "synonyms": []}
        generated = _mock_suggestions("#CRM #brandnew", "", {}, empty_catalog)
        self.assertEqual(generated["type"]["value"], "笔记")
        self.assertEqual(generated["type"]["vocabulary_values"], ["笔记"])
        self.assertEqual(generated["tags"]["values"], [])
        self.assertEqual(generated["tags"]["unknown_candidates"], ["CRM", "brandnew"])

    def test_manual_type_correction_persists_across_regeneration(self):
        created = self.create()
        type_record = next(item for item in created["proposals"] if item["kind"] == "type")
        value = {"value": "头脑风暴", "vocabulary_values": [row["name"] for row in self.vocabulary["types"]]}
        self.store.edit(type_record["proposal_id"], value, 1, "owner", "edit-type", "etag-1")
        again = _mock_suggestions("会议纪要：下一步", "", self.store.preferences(self.source), self.vocabulary)
        self.assertEqual(again["type"]["value"], "头脑风暴")

    def test_corrupt_state_fails_closed(self):
        self.store.path.write_text('{"records": []}', encoding="utf-8")
        self.store.path.chmod(0o600)
        with self.assertRaises(HTTPException) as corrupt:
            self.store.get("missing")
        self.assertEqual(corrupt.exception.status_code, 500)

    def test_legacy_approved_recorded_rows_remain_history_only(self):
        import json
        created = self.create()
        journal = next(item for item in created["proposals"] if item["kind"] == "journal")
        data = json.loads(self.store.path.read_text(encoding="utf-8"))
        record = data["records"][journal["proposal_id"]]
        record.update(status="approved_recorded", target_execution_status="not_supported", version=2)
        record.pop("execution", None)
        self.store.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.store.path.chmod(0o600)
        reloaded = InboxProposalStore(self.root).get(journal["proposal_id"])
        self.assertEqual(reloaded["status"], "approved_recorded")
        self.assertEqual(reloaded["execution"]["status"], "not_executed")
        self.assertEqual(reloaded["target_execution_status"], "not_executed")

    def test_only_one_approved_execution_can_claim_a_source_target(self):
        first = self.create(key="first-suggestion")
        first_journal = next(row for row in first["proposals"] if row["kind"] == "journal")
        self.store.decide(first_journal["proposal_id"], "approved_recorded", 1, "owner", "approve-first", "etag-1")
        second = self.create(key="second-suggestion")
        second_journal = next(row for row in second["proposals"] if row["kind"] == "journal")
        self.store.decide(second_journal["proposal_id"], "approved_recorded", 1, "owner", "approve-second", "etag-1")
        target = {"date": "2026-10-18", "text": "合成目标"}
        summary = {"source_kind": "notes", "source_ref": "synthetic/note.md", "source_version": "etag-1",
                   "source_content_sha256": "b" * 64}
        first_started = self.store.begin_execution(first_journal["proposal_id"], 2, "owner", "a" * 64,
                                                    "etag-1", 4, "journal.append", target, summary)
        self.assertEqual(first_started["execution"]["status"], "executing")
        with self.assertRaises(HTTPException) as duplicate_target:
            self.store.begin_execution(second_journal["proposal_id"], 2, "owner", "c" * 64,
                                       "etag-1", 4, "journal.append", target, summary)
        self.assertEqual(duplicate_target.exception.status_code, 409)

    def test_router_auth_source_binding_and_refresh_recovery(self):
        from secondbrain_core.modules.inbox_proposals import create_inbox_proposal_router

        class Auth:
            denied = set()

            def require_action(self, request: Request, action: str):
                if action in self.denied:
                    raise HTTPException(status_code=403, detail=f"{action} denied")
                if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin") != "https://testserver":
                    raise HTTPException(status_code=403, detail="trusted origin required")
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="session required")
                return "owner"

        class Sources:
            version = "etag-synthetic"
            notes_store = type("NotesStore", (), {"roots": {"drafts": "/synthetic/drafts"}})()

            def resolve(self, source):
                if source.get("source_kind") != "notes" or source.get("path") != "synthetic.md":
                    raise HTTPException(status_code=404, detail="source unavailable")
                canonical = {"source_kind": "notes", "source_id": "drafts:synthetic.md",
                             "collection": "drafts", "path": "synthetic.md"}
                return canonical, self.version, "合成会议 #CRM", "合成会议"

        class Vocabulary:
            def read(self):
                return {"revision": 4, "types": [{"name": name, "enabled": True}
                                                    for name in ("日记", "笔记", "头脑风暴", "摘要", "会议纪要")],
                        "tags": [{"id": "crm", "name": "CRM", "enabled": True}], "synonyms": []}

        app = FastAPI()
        app.include_router(create_inbox_proposal_router(Auth(), self.store, Sources(), Vocabulary()))
        client = TestClient(app)
        source = {"source_kind": "notes", "source_id": "drafts:synthetic.md",
                  "collection": "drafts", "path": "synthetic.md"}
        self.assertEqual(client.post("/api/inbox/proposals", json=source, headers={"Origin": "https://testserver"}).status_code, 401)
        client.cookies.set("session", "owner")
        forbidden = client.post("/api/inbox/proposals", json=source, headers={"Origin": "https://untrusted.test", "Idempotency-Key": "forbidden"})
        self.assertEqual(forbidden.status_code, 403)
        generated = client.post("/api/inbox/proposals", json=source, headers={"Origin": "https://testserver", "Idempotency-Key": "http-create"})
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(len(generated.json()["proposals"]), 5)
        loaded = client.get("/api/inbox/proposals", params=source)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(len(loaded.json()["proposals"]), 5)
        unauthorized_collection = {**source, "source_kind": "notes", "source_id": "knowledge:synthetic.md",
                                   "collection": "knowledge", "path": "synthetic.md"}
        rejected_collection = client.post("/api/inbox/proposals", json=unauthorized_collection,
                                          headers={"Origin": "https://testserver", "Idempotency-Key": "bad-collection"})
        self.assertEqual(rejected_collection.status_code, 404)
        journal = next(item for item in loaded.json()["proposals"] if item["kind"] == "journal")
        body = {"decision": "approved_recorded", "expected_version": 1}
        first = client.post(f"/api/inbox/proposals/{journal['proposal_id']}/decision", json=body,
                            headers={"Origin": "https://testserver", "Idempotency-Key": "http-decision"})
        Sources.version = "etag-updated"
        replay = client.post(f"/api/inbox/proposals/{journal['proposal_id']}/decision", json=body,
                             headers={"Origin": "https://testserver", "Idempotency-Key": "http-decision"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 409)
        self.assertNotIn("proposal", replay.json())
        self.assertEqual(self.store.get(journal["proposal_id"])["status"], "stale")
        stale_history = client.get(f"/api/inbox/proposals/{journal['proposal_id']}/history")
        self.assertEqual(stale_history.status_code, 200)
        self.assertEqual(stale_history.json()["proposal"]["status"], "stale")
        Auth.denied.add("notes.read")
        denied_history = client.get(f"/api/inbox/proposals/{journal['proposal_id']}/history")
        denied_replay = client.post(f"/api/inbox/proposals/{journal['proposal_id']}/decision", json=body,
                                    headers={"Origin": "https://testserver", "Idempotency-Key": "http-decision"})
        self.assertEqual(denied_history.status_code, 403)
        self.assertEqual(denied_replay.status_code, 403)
        Auth.denied.remove("notes.read")
        self.assertEqual(client.get(f"/api/inbox/proposals/{journal['proposal_id']}/history").status_code, 200)
        changed = client.get("/api/inbox/proposals", params={**source, "path": "other.md"})
        self.assertEqual(changed.status_code, 404)

    def test_approved_decision_replay_after_vocabulary_revision_change_fails_closed(self):
        from secondbrain_core.modules.inbox_proposals import create_inbox_proposal_router

        class Auth:
            def require_action(self, request, action):
                return "owner"

        class Sources:
            version = "etag-vocabulary"
            notes_store = type("NotesStore", (), {"roots": {"drafts": "/synthetic/drafts"}})()

            def resolve(self, source):
                canonical = {"source_kind": "notes", "source_id": "drafts:synthetic.md",
                             "collection": "drafts", "path": "synthetic.md"}
                return canonical, self.version, "合成会议 #CRM", "合成会议"

        class Vocabulary:
            revision = 4

            def read(self):
                return {"revision": self.revision,
                        "types": [{"name": name, "enabled": True}
                                  for name in ("日记", "笔记", "头脑风暴", "摘要", "会议纪要")],
                        "tags": [{"id": "crm", "name": "CRM", "enabled": True}], "synonyms": []}

        vocabulary = Vocabulary()
        app = FastAPI()
        app.include_router(create_inbox_proposal_router(Auth(), self.store, Sources(), vocabulary))
        client = TestClient(app)
        source = {"source_kind": "notes", "source_id": "drafts:synthetic.md",
                  "collection": "drafts", "path": "synthetic.md"}
        generated = client.post("/api/inbox/proposals", json=source, headers={"Idempotency-Key": "vocabulary-create"})
        proposal = next(item for item in generated.json()["proposals"] if item["kind"] == "journal")
        body = {"decision": "approved_recorded", "expected_version": 1}
        decision = client.post(f"/api/inbox/proposals/{proposal['proposal_id']}/decision", json=body,
                               headers={"Idempotency-Key": "vocabulary-decision"})
        self.assertEqual(decision.status_code, 200)
        vocabulary.revision = 5
        replay = client.post(f"/api/inbox/proposals/{proposal['proposal_id']}/decision", json=body,
                             headers={"Idempotency-Key": "vocabulary-decision"})
        self.assertEqual(replay.status_code, 409)
        self.assertNotIn("proposal", replay.json())
        record = self.store.get(proposal["proposal_id"])
        self.assertEqual(record["status"], "stale")
        self.assertEqual(record["stale_reason"], "vocabulary_version_changed")
        history = client.get(f"/api/inbox/proposals/{proposal['proposal_id']}/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["proposal"]["status"], "stale")
        self.assertTrue(any(event["event"] == "approved_recorded" for event in history.json()["history"]))

    def test_history_does_not_disclose_records_when_source_collection_is_revoked(self):
        from secondbrain_core.modules.inbox_proposals import create_inbox_proposal_router

        class Auth:
            def require_action(self, request, action):
                if action in {"inbox.proposals.read", "inbox.proposals.write", "notes.read"}:
                    return "owner"
                raise HTTPException(status_code=403)

        class Sources:
            notes_store = type("NotesStore", (), {"roots": {}})()

            def resolve(self, source):
                raise AssertionError("revoked collection must fail before source resolution")

        app = FastAPI()
        app.include_router(create_inbox_proposal_router(Auth(), self.store, Sources()))
        created = self.create()
        proposal = next(item for item in created["proposals"] if item["kind"] == "journal")
        self.store.decide(proposal["proposal_id"], "approved_recorded", 1, "owner", "revoked-decision", "etag-1")
        client = TestClient(app)
        response = client.get(f"/api/inbox/proposals/{proposal['proposal_id']}/history")
        replay = client.post(f"/api/inbox/proposals/{proposal['proposal_id']}/decision",
                             json={"decision": "approved_recorded", "expected_version": 1},
                             headers={"Idempotency-Key": "revoked-decision"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(replay.status_code, 404)
        self.assertNotIn("history", response.json())
        self.assertNotIn("proposal", replay.json())

    def test_capture_source_requires_the_existing_inbox_original_read_gate(self):
        from secondbrain_core.modules.inbox_proposals import create_inbox_proposal_router

        class Auth:
            def require_action(self, request, action):
                if action in {"inbox.proposals.read", "inbox.proposals.write"}:
                    return "owner"
                raise HTTPException(status_code=403, detail="source read denied")

        class Sources:
            notes_store = type("NotesStore", (), {"roots": {"drafts": "/synthetic/drafts"}})()

            def resolve(self, source):
                raise AssertionError("Capture source resolution must not precede its read gate")

        app = FastAPI()
        app.include_router(create_inbox_proposal_router(Auth(), self.store, Sources()))
        response = TestClient(app).post("/api/inbox/proposals", json={"source_kind": "capture", "source_id": "a" * 32},
                                        headers={"Idempotency-Key": "capture-read-denied"})
        self.assertEqual(response.status_code, 403)

    def test_removed_canonical_tag_suppresses_casefolded_synonyms(self):
        vocabulary = {**self.vocabulary, "synonyms": [
            {"tag_id": "sb", "alias": "secondbrain", "enabled": True},
            {"tag_id": "sb", "alias": "SB", "enabled": True},
        ]}
        result = _mock_suggestions("#SECONDbrain #sB", "", {"removed_tags": ["SecondBrain"]}, vocabulary)
        self.assertEqual(result["tags"]["values"], [])
        self.assertEqual(result["tags"]["unknown_candidates"], [])

    def test_core_source_validation_binds_notes_etag_and_capture_raw_hash(self):
        from secondbrain_core.modules.notes import NotesStore

        drafts = Path(self.temp.name) / "drafts"
        drafts.mkdir(mode=0o700)
        note_store = NotesStore(drafts.resolve(), {})
        note = note_store.create("# Synthetic\n\nBody #CRM\n")
        raw_root = Path(self.temp.name) / "capture-raw"
        raw_root.mkdir(mode=0o700)
        raw_bytes = b"# Synthetic capture\nContent #SecondBrain\n"
        (raw_root / "safe.md").write_bytes(raw_bytes)
        (raw_root / "safe.md").chmod(0o600)
        raw_root_path = raw_root

        class Capture:
            raw_root = str(raw_root_path)

            def get(self, capture_id):
                return {"raw_path": "safe.md", "raw_sha256": __import__("hashlib").sha256(raw_bytes).hexdigest(),
                        "source_type": "text", "input_type": "markdown", "title": "Synthetic capture",
                        "content_preview": raw_bytes.decode()}

        sources = InboxProposalSources(Capture(), note_store)
        notes_source = {"source_kind": "notes", "source_id": f"drafts:{note['path']}",
                        "collection": "drafts", "path": note["path"]}
        canonical, version, content, _ = sources.resolve(notes_source)
        self.assertEqual(canonical["source_id"], f"drafts:{note['path']}")
        self.assertEqual(version, note["etag"])
        self.assertIn("Body", content)
        capture_source = {"source_kind": "capture", "source_id": "a" * 32}
        _, capture_version, capture_content, _ = sources.resolve(capture_source)
        self.assertEqual(capture_version, __import__("hashlib").sha256(
            __import__("json").dumps({"source_kind": "capture", "source_id": "a" * 32,
                                      "input_type": "markdown", "source_type": "text", "title": "Synthetic capture",
                                      "content_preview": raw_bytes.decode(), "raw_sha256": __import__("hashlib").sha256(raw_bytes).hexdigest()},
                                     ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        self.assertIn("Content", capture_content)
        (raw_root / "safe.md").write_text("tampered synthetic content", encoding="utf-8")
        with self.assertRaises(HTTPException) as tampered:
            sources.resolve(capture_source)
        self.assertEqual(tampered.exception.status_code, 409)

    def test_explicit_journal_and_review_execution_is_versioned_and_idempotent(self):
        from secondbrain_core.modules.capture import CaptureService
        from secondbrain_core.modules.journal import JournalStore
        from secondbrain_core.modules.notes import NotesStore
        from secondbrain_core.modules.vocabulary import VocabularyStore
        from secondbrain_core.modules.inbox_proposals import create_inbox_proposal_router

        root = Path(self.temp.name)
        drafts = root / "drafts"; drafts.mkdir(mode=0o700)
        raw = root / "raw"; raw.mkdir(mode=0o700)
        review = root / "review"; review.mkdir(mode=0o700)
        state = root / "capture-state"; state.mkdir(mode=0o700)
        journal_root = root / "journal"; journal_root.mkdir(mode=0o700)
        approval = root / "approval"; approval.mkdir(mode=0o700)
        notes = NotesStore(drafts.resolve(), {})
        journal = JournalStore(journal_root.resolve())
        capture = CaptureService(raw.resolve(), review.resolve(), state.resolve())
        proposals = InboxProposalStore(approval.resolve())
        vocabulary = VocabularyStore(approval.resolve())
        class Auth:
            denied = set()
            def require_action(self, request, action):
                if action in self.denied:
                    raise HTTPException(status_code=403, detail=f"{action} denied")
                return "synthetic-owner"
        auth = Auth()
        app = FastAPI()
        app.include_router(create_inbox_proposal_router(auth, proposals, InboxProposalSources(capture, notes),
                                                       vocabulary, journal_store=journal, capture_service=capture))
        client = TestClient(app)

        def suggest_and_approve(content, kind, suffix):
            note = notes.create(content)
            source = {"source_kind": "notes", "source_id": f"drafts:{note['path']}",
                      "collection": "drafts", "path": note["path"]}
            generated = client.post("/api/inbox/proposals", json=source,
                                    headers={"Idempotency-Key": f"create-{suffix}"})
            self.assertEqual(generated.status_code, 200, generated.text)
            record = next(row for row in generated.json()["proposals"] if row["kind"] == kind)
            decision = client.post(f"/api/inbox/proposals/{record['proposal_id']}/decision",
                                   json={"decision": "approved_recorded", "expected_version": 1},
                                   headers={"Idempotency-Key": f"approve-{suffix}"})
            self.assertEqual(decision.status_code, 200, decision.text)
            return record, source, note

        journal_record, journal_source, journal_note = suggest_and_approve("记一下：合成 Journal 原文\n\n保留空格尾部 \n", "journal", "journal")
        preview_response = client.post(f"/api/inbox/proposals/{journal_record['proposal_id']}/execution-preview", json={})
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["target"]["text"], notes.read("drafts", journal_note["path"])["content"])
        self.assertFalse(list(journal_root.glob("????-??-??.jsonl")), "preview or historical approval must not write Journal")
        body = {"target_text": preview["target"]["text"], "target_date": preview["target"]["date"],
                "preview_sha256": preview["preview_sha256"], "confirmed": True}
        unconfirmed = client.post(f"/api/inbox/proposals/{journal_record['proposal_id']}/execute", json={**body, "confirmed": False})
        self.assertEqual(unconfirmed.status_code, 400)
        auth.denied.add("journal.append")
        denied = client.post(f"/api/inbox/proposals/{journal_record['proposal_id']}/execute", json=body)
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(list(journal_root.glob("????-??-??.jsonl")))
        auth.denied.clear()
        executed = client.post(f"/api/inbox/proposals/{journal_record['proposal_id']}/execute", json=body)
        self.assertEqual(executed.status_code, 200, executed.text)
        self.assertEqual(executed.json()["proposal"]["execution"]["status"], "executed")
        self.assertEqual(executed.json()["proposal"]["execution"]["actor"], "synthetic-owner")
        self.assertEqual(len(journal.read(preview["target"]["date"])["entries"]), 1)
        replay = client.post(f"/api/inbox/proposals/{journal_record['proposal_id']}/execute", json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["duplicate"])
        self.assertEqual(len(journal.read(preview["target"]["date"])["entries"]), 1)
        self.assertEqual(replay.json()["proposal"]["execution"]["output_sha256"],
                         __import__("hashlib").sha256(body["target_text"].encode()).hexdigest())

        blocked_record, _, _ = suggest_and_approve("记一下：blocked collision source", "journal", "blocked")
        blocked_key = "c2c-" + blocked_record["proposal_id"]
        journal.append(JournalStore.today(), "记一下：preexisting different operation", blocked_key)
        blocked_preview = client.post(f"/api/inbox/proposals/{blocked_record['proposal_id']}/execution-preview", json={}).json()
        blocked_body = {"target_text": blocked_preview["target"]["text"], "target_date": blocked_preview["target"]["date"],
                        "preview_sha256": blocked_preview["preview_sha256"], "confirmed": True}
        first_conflict = client.post(f"/api/inbox/proposals/{blocked_record['proposal_id']}/execute", json=blocked_body)
        self.assertEqual(first_conflict.status_code, 409)
        self.assertEqual(proposals.get(blocked_record["proposal_id"])["execution"]["status"], "blocked")
        second_conflict = client.post(f"/api/inbox/proposals/{blocked_record['proposal_id']}/execute", json=blocked_body)
        self.assertEqual(second_conflict.status_code, 409)
        self.assertEqual(len(journal.read(preview["target"]["date"])["entries"]), 2)

        retry_record, _, _ = suggest_and_approve("记一下：retryable synthetic operation", "journal", "retry")
        retry_preview = client.post(f"/api/inbox/proposals/{retry_record['proposal_id']}/execution-preview", json={}).json()
        retry_body = {"target_text": retry_preview["target"]["text"], "target_date": retry_preview["target"]["date"],
                      "preview_sha256": retry_preview["preview_sha256"], "confirmed": True}
        append = journal.append_approved_proposal
        journal.append_approved_proposal = lambda *args, **kwargs: (_ for _ in ()).throw(HTTPException(503, "synthetic transient failure"))
        failed = client.post(f"/api/inbox/proposals/{retry_record['proposal_id']}/execute", json=retry_body)
        self.assertEqual(failed.status_code, 503)
        first_attempt_id = proposals.get(retry_record["proposal_id"])["execution"]["attempt_id"]
        self.assertEqual(proposals.get(retry_record["proposal_id"])["execution"]["status"], "failed_retryable")
        journal.append_approved_proposal = append
        retried = client.post(f"/api/inbox/proposals/{retry_record['proposal_id']}/execute", json=retry_body)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertNotEqual(retried.json()["proposal"]["execution"]["attempt_id"], first_attempt_id)
        self.assertEqual(len(retried.json()["proposal"]["execution"]["attempts"]), 2)
        self.assertEqual(retried.json()["proposal"]["execution"]["status"], "executed")

        review_record, _, review_note = suggest_and_approve("# Synthetic Review\n\nBody stays exact.\n", "review", "review")
        review_preview_response = client.post(f"/api/inbox/proposals/{review_record['proposal_id']}/execution-preview", json={})
        self.assertEqual(review_preview_response.status_code, 200, review_preview_response.text)
        review_preview = review_preview_response.json()
        review_body = {"target_text": review_preview["target"]["text"], "target_title": "Confirmed Review title",
                       "preview_sha256": review_preview["preview_sha256"], "confirmed": True}
        title_preview = client.post(f"/api/inbox/proposals/{review_record['proposal_id']}/execution-preview", json=review_body)
        self.assertEqual(title_preview.status_code, 200, title_preview.text)
        mismatch = client.post(f"/api/inbox/proposals/{review_record['proposal_id']}/execute", json=review_body)
        self.assertEqual(mismatch.status_code, 409, "an old preview hash cannot authorize edited target text")
        review_body["preview_sha256"] = title_preview.json()["preview_sha256"]
        review_body["confirmed"] = False
        unconfirmed_review = client.post(f"/api/inbox/proposals/{review_record['proposal_id']}/execute", json=review_body)
        self.assertEqual(unconfirmed_review.status_code, 400)
        review_body["confirmed"] = True
        executed_review = client.post(f"/api/inbox/proposals/{review_record['proposal_id']}/execute", json=review_body)
        self.assertEqual(executed_review.status_code, 200, executed_review.text)
        state_after = capture.get(executed_review.json()["proposal"]["execution"]["target_id"])
        self.assertEqual(state_after["status"], "completed")
        self.assertEqual((review / state_after["review_path"]).read_text(encoding="utf-8").endswith(review_body["target_text"]), True)
        self.assertEqual(len(list(review.glob("*.md"))), 1)
        repeated = client.post(f"/api/inbox/proposals/{review_record['proposal_id']}/execute", json=review_body)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertTrue(repeated.json()["duplicate"])
        self.assertEqual(len(list(review.glob("*.md"))), 1)

    def test_execution_blocks_stale_source_vocabulary_and_project_target(self):
        from secondbrain_core.modules.capture import CaptureService
        from secondbrain_core.modules.journal import JournalStore
        from secondbrain_core.modules.notes import NotesStore
        from secondbrain_core.modules.inbox_proposals import create_inbox_proposal_router

        root = Path(self.temp.name)
        drafts = root / "drafts"; drafts.mkdir(mode=0o700)
        raw = root / "raw"; raw.mkdir(mode=0o700)
        review = root / "review"; review.mkdir(mode=0o700)
        state = root / "capture-state"; state.mkdir(mode=0o700)
        journal_root = root / "journal"; journal_root.mkdir(mode=0o700)
        notes = NotesStore(drafts.resolve(), {})
        capture = CaptureService(raw.resolve(), review.resolve(), state.resolve())
        journal = JournalStore(journal_root.resolve())
        class Auth:
            def require_action(self, request, action): return "synthetic-owner"
        class Vocabulary:
            revision = 4
            def read(self):
                return {"revision": self.revision, "types": [{"name": "笔记", "enabled": True}], "tags": [], "synonyms": []}
        vocabulary = Vocabulary()
        proposals = InboxProposalStore((root / "approval").resolve())
        app = FastAPI()
        app.include_router(create_inbox_proposal_router(Auth(), proposals, InboxProposalSources(capture, notes),
                                                       vocabulary, journal_store=journal, capture_service=capture))
        client = TestClient(app)
        note = notes.create("记一下：synthetic stale test")
        source = {"source_kind": "notes", "source_id": f"drafts:{note['path']}", "collection": "drafts", "path": note["path"]}
        generated = client.post("/api/inbox/proposals", json=source, headers={"Idempotency-Key": "stale-create"})
        records = generated.json()["proposals"]
        journal_proposal = next(row for row in records if row["kind"] == "journal")
        project_proposal = next(row for row in records if row["kind"] == "project")
        for row, key in ((journal_proposal, "stale-approve"), (project_proposal, "project-approve")):
            self.assertEqual(client.post(f"/api/inbox/proposals/{row['proposal_id']}/decision",
                                         json={"decision": "approved_recorded", "expected_version": 1},
                                         headers={"Idempotency-Key": key}).status_code, 200)
        notes.update("drafts", note["path"], "记一下：changed synthetic source", note["etag"])
        stale = client.post(f"/api/inbox/proposals/{journal_proposal['proposal_id']}/execution-preview", json={})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(proposals.get(journal_proposal["proposal_id"])["status"], "stale")
        project = client.post(f"/api/inbox/proposals/{project_proposal['proposal_id']}/execution-preview", json={})
        self.assertEqual(project.status_code, 200)
        self.assertEqual(project.json()["status"], "not_implemented")
        attempt = client.post(f"/api/inbox/proposals/{project_proposal['proposal_id']}/execute",
                              json={"confirmed": True, "preview_sha256": "0" * 64})
        self.assertEqual(attempt.status_code, 501)
        vocabulary.revision = 5
        fresh_note = notes.create("记一下：synthetic vocabulary test")
        fresh_source = {"source_kind": "notes", "source_id": f"drafts:{fresh_note['path']}",
                        "collection": "drafts", "path": fresh_note["path"]}
        fresh = client.post("/api/inbox/proposals", json=fresh_source, headers={"Idempotency-Key": "vocab-create"})
        fresh_journal = next(row for row in fresh.json()["proposals"] if row["kind"] == "journal")
        self.assertEqual(client.post(f"/api/inbox/proposals/{fresh_journal['proposal_id']}/decision",
                                     json={"decision": "approved_recorded", "expected_version": 1},
                                     headers={"Idempotency-Key": "vocab-approve"}).status_code, 200)
        vocabulary.revision = 6
        stale_vocabulary = client.post(f"/api/inbox/proposals/{fresh_journal['proposal_id']}/execution-preview", json={})
        self.assertEqual(stale_vocabulary.status_code, 409)
        self.assertEqual(proposals.get(fresh_journal["proposal_id"])["status"], "stale")
        self.assertFalse(list(journal_root.glob("????-??-??.jsonl")))
