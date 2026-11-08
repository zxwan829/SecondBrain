import tempfile
import asyncio
import base64
import os
import unittest
import concurrent.futures
import json
import stat
from io import BytesIO
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from PIL import Image

from secondbrain_core.modules.notes import (NotesStore, _read_bounded_json_request, configured_notes_store,
                                            create_notes_router, markdown_safety, _note_properties,
                                            _replace_note_properties)
from secondbrain_core.modules.vocabulary import VocabularyStore


class NotesStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.drafts = base / "drafts"
        self.drafts.mkdir(mode=0o700)
        self.ordinary = base / "ordinary"
        self.ordinary.mkdir(mode=0o700)
        self.store = NotesStore(self.drafts.resolve(), {"personal": self.ordinary.resolve()})

    def tearDown(self):
        self.temp.cleanup()

    def test_markdown_safety_rejects_nested_obsidian_callouts(self):
        for content in ("> [!NOTE]\n> text\n", "> > [!NOTE]\n> > text\n", ">> [!NOTE]\n>> text\n"):
            with self.subTest(content=content):
                self.assertIn("callouts", markdown_safety(content))

    def test_create_edit_reload_and_history_are_markdown_authoritative(self):
        note = self.store.create("# Synthetic\n\nHello **world**.\n")
        self.assertEqual((self.drafts / note["path"] / "note.md").read_text(), note["content"])
        updated = self.store.update("drafts", note["path"], "# Synthetic\n\nChanged.\n", note["etag"])
        self.assertEqual(self.store.read("drafts", note["path"])["content"], updated["content"])
        self.assertEqual(self.store.history("drafts", note["path"])["versions"][0]["content"], note["content"])
        self.assertEqual((self.drafts / note["path"] / "note.md").stat().st_mode & 0o777, 0o600)

    def test_authorized_ordinary_markdown_is_explicitly_scoped(self):
        path = self.ordinary / "folder"
        path.mkdir(mode=0o700)
        note = path / "existing.md"
        note.write_text("# Existing\n\nPlain Markdown.\n")
        note.chmod(0o600)
        loaded = self.store.read("personal", "folder/existing.md")
        changed = self.store.update("personal", "folder/existing.md", "# Existing\n\nEdited.\n", loaded["etag"])
        self.assertEqual(changed["content"], "# Existing\n\nEdited.\n")
        with self.assertRaises(HTTPException) as denied:
            self.store.read("knowledge", "secret.md")
        self.assertEqual(denied.exception.status_code, 404)

    def test_unicode_filename_and_opaque_frontmatter_round_trip_without_metadata_changes(self):
        initial = '\ufeff---\r\n类型: 摘要\r\ntags: [CRM, SecondBrain]\r\ncustom: 保持原样\r\nupdated: 2026-01-01\r\n---\r\n\r\n# 标题\r\n\r\n正文。\r\n'
        path = self.ordinary / '中文笔记.md'
        with path.open('w', encoding='utf-8', newline='') as stream:
            stream.write(initial)
        path.chmod(0o600)
        self.assertEqual(_note_properties(initial), ('摘要', ['CRM', 'SecondBrain']))
        metadata_edit = _replace_note_properties(initial, '笔记', ['NewTag'])
        self.assertTrue(metadata_edit.startswith('\ufeff---\r\n'))
        self.assertIn('custom: 保持原样\r\nupdated: 2026-01-01\r\n', metadata_edit)
        self.assertIn('tags: ["NewTag"]\r\n', metadata_edit)
        self.assertTrue(metadata_edit.endswith('# 标题\r\n\r\n正文。\r\n'))
        loaded = self.store.read('personal', '中文笔记.md')
        self.assertFalse(loaded['read_only'])
        edited = initial.replace('正文。', '更新后的正文。')
        saved = self.store.update('personal', '中文笔记.md', edited, loaded['etag'])
        self.assertEqual(saved['content'], edited)
        self.assertEqual(path.read_bytes().decode('utf-8'), edited)
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get('session') != 'owner':
                    raise HTTPException(status_code=401, detail='App session required')
        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        client.cookies.set('session', 'owner')
        route = '/api/notes/personal/%E4%B8%AD%E6%96%87%E7%AC%94%E8%AE%B0.md'
        read_response = client.get(route)
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()['content'], edited)
        api_edit = edited.replace('更新后的正文。', 'API 回读后的正文。')
        api_saved = client.put(route, json={'content': api_edit}, headers={'If-Match': read_response.headers['etag']})
        self.assertEqual(api_saved.status_code, 200)
        self.assertEqual(client.get(route).json()['content'], api_edit)
        with self.assertRaises(HTTPException) as stale:
            self.store.update('personal', '中文笔记.md', edited + '再次编辑\r\n', loaded['etag'])
        self.assertEqual(stale.exception.status_code, 412)

    def test_frontmatter_is_opaque_and_cannot_be_changed_by_body_editor(self):
        initial = '---\n类型: 摘要\ntags:\n  - CRM\ncustom_field: Keep\n---\n\n# Body\n'
        note = self.store.create(initial)
        changed_metadata = initial.replace('类型: 摘要', '类型: 笔记').replace('custom_field: Keep', 'custom_field: Lost')
        with self.assertRaises(HTTPException) as blocked:
            self.store.update('drafts', note['path'], changed_metadata, note['etag'])
        self.assertEqual(blocked.exception.status_code, 422)
        self.assertEqual(self.store.read('drafts', note['path'])['content'], initial)

    def test_conflict_and_unsupported_markdown_never_overwrite(self):
        note = self.store.create("# Original\n")
        with self.assertRaises(HTTPException) as stale:
            self.store.update("drafts", note["path"], "# Stale\n", "0" * 64)
        self.assertEqual(stale.exception.status_code, 412)
        target = self.ordinary / "complex.md"
        target.write_text("---\ntags: [x]\n---\n\n[[Wiki]]\n")
        target.chmod(0o600)
        etag = self.store._digest(target.read_text())
        self.assertTrue(markdown_safety(target.read_text()))
        with self.assertRaises(HTTPException) as blocked:
            self.store.update("personal", "complex.md", "lost\n", etag)
        self.assertEqual(blocked.exception.status_code, 422)
        self.assertIn("[[Wiki]]", target.read_text())

    def test_concurrent_writers_with_one_etag_produce_one_success_and_one_conflict(self):
        note = self.store.create("# Before\n")

        def write(value):
            try:
                self.store.update("drafts", note["path"], f"# {value}\n", note["etag"])
                return "saved"
            except HTTPException as error:
                return error.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(write, ["Left", "Right"]))
        self.assertCountEqual(outcomes, ["saved", 412])
        self.assertIn(self.store.read("drafts", note["path"])["content"], ["# Left\n", "# Right\n"])

    def test_traversal_and_symlinks_are_rejected(self):
        with self.assertRaises(HTTPException):
            self.store.read("personal", "../outside.md")
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("# Outside\n")
        outside.chmod(0o600)
        (self.ordinary / "linked.md").symlink_to(outside)
        with self.assertRaises(HTTPException):
            self.store.read("personal", "linked.md")
        self.assertEqual(outside.read_text(), "# Outside\n")

    def test_attachment_uses_random_relative_name_and_rejects_mismatch(self):
        note = self.store.create("# Image\n")
        buffer = BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buffer, format="PNG")
        image = buffer.getvalue()
        result = self.store.upload_image("drafts", note["path"], "../../unsafe.png", image)
        self.assertTrue(result["path"].startswith("attachments/"))
        self.assertTrue((self.drafts / note["path"] / result["path"]).exists())
        with self.assertRaises(HTTPException):
            self.store.upload_image("drafts", note["path"], "bad.png", b"not png")

    def test_visual_assets_are_note_bound_validated_and_independently_versioned(self):
        note = self.store.create("# Visuals\n")
        mindmap = json.dumps({"data": {"text": "Root"}, "children": [], "layout": "mindMap"})
        created = self.store.create_visual_asset("drafts", note["path"], "mindmap", mindmap, note["etag"])
        self.assertRegex(created["filename"], r"^[0-9a-f]{32}\.mindmap\.json$")
        data, suffix = self.store.read_attachment("drafts", note["path"], created["filename"])
        self.assertEqual(suffix, ".json")
        self.assertEqual(json.loads(data), json.loads(mindmap))

        canvas = json.dumps({"type": "excalidraw", "elements": [
            {"type": "arrow", "id": "a1"}, {"type": "text", "id": "t1", "text": "Label"}
        ], "appState": {"viewBackgroundColor": "#ffffff"}})
        drawing = self.store.create_visual_asset("drafts", note["path"], "excalidraw", canvas, note["etag"])
        canvas_data, canvas_suffix = self.store.read_attachment("drafts", note["path"], drawing["filename"])
        self.assertEqual(canvas_suffix, ".json")
        self.assertEqual(json.loads(canvas_data), json.loads(canvas))

        updated_content = json.dumps({"data": {"text": "Edited"}, "children": [], "layout": "mindMap"})
        updated = self.store.update_visual_asset("drafts", note["path"], created["filename"], updated_content,
                                                 note["etag"], created["etag"])
        self.assertNotEqual(updated["etag"], created["etag"])
        with self.assertRaises(HTTPException) as stale:
            self.store.update_visual_asset("drafts", note["path"], created["filename"], mindmap,
                                           note["etag"], created["etag"])
        self.assertEqual(stale.exception.status_code, 412)
        with self.assertRaises(HTTPException) as unsafe:
            self.store.create_visual_asset("drafts", note["path"], "excalidraw",
                                           json.dumps({"type": "excalidraw", "elements": [{"type": "image"}]}),
                                           note["etag"])
        self.assertEqual(unsafe.exception.status_code, 422)
        too_many_nodes = {"data": {"text": "Root"}, "children": [
            {"data": {"text": "Child"}, "children": []} for _ in range(5000)
        ]}
        with self.assertRaises(HTTPException) as oversized:
            self.store.create_visual_asset("drafts", note["path"], "mindmap", json.dumps(too_many_nodes), note["etag"])
        self.assertEqual(oversized.exception.status_code, 422)
        with self.assertRaises(HTTPException) as missing_etag:
            self.store.create_visual_asset("drafts", note["path"], "mindmap", mindmap, "wrong")
        self.assertEqual(missing_etag.exception.status_code, 412)

    def test_blocksuite_resources_are_note_bound_versioned_and_dual_etag_protected(self):
        note = self.store.create("# Page with a separate BlockSuite resource\n")
        update = b"synthetic-yjs-update"
        initial = {"schemaVersion": 1, "resourceKind": "database", "docId": "doc_table_1",
                   "updateB64": base64.b64encode(update).decode("ascii"),
                   "snapshot": {"type": "page", "blocks": {"table": ["a", "b"]}}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], initial, note["etag"])
        self.assertRegex(created["filename"], r"^[0-9a-f]{32}\.blocksuite\.json$")
        self.assertEqual(created["reference"], f"[BlockSuite resource](attachments/{created['filename']})")
        resource_id = created["resource_id"]
        resource_path = self.drafts / note["path"] / "attachments" / created["filename"]
        self.assertEqual(resource_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(resource_path.parent.stat().st_mode & 0o777, 0o700)
        first = self.store.read_blocksuite_resource("drafts", note["path"], resource_id)
        self.assertEqual(first["updateB64"], initial["updateB64"])
        self.assertEqual(first["etag"], created["etag"])

        changed = {**first, "etag": None, "note_etag": None, "filename": None,
                   "updateB64": base64.b64encode(b"updated-yjs-update").decode("ascii")}
        changed.pop("etag")
        changed.pop("note_etag")
        changed.pop("filename")
        changed.pop("artifact_set_etag")
        saved = self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                      changed, note["etag"], first["etag"],
                                                      first["artifact_set_etag"])
        self.assertNotEqual(saved["etag"], first["etag"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], resource_id)["updateB64"],
                         changed["updateB64"])
        with self.assertRaises(HTTPException) as stale_asset:
            self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                  changed, note["etag"], first["etag"],
                                                  saved["artifact_set_etag"])
        self.assertEqual(stale_asset.exception.status_code, 412)
        with self.assertRaises(HTTPException) as stale_note:
            self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                  changed, "0" * 64, saved["etag"],
                                                  saved["artifact_set_etag"])
        self.assertEqual(stale_note.exception.status_code, 412)
        for identity_change in ({"resourceKind": "edgeless-canvas"}, {"docId": "different_doc"}):
            with self.subTest(identity_change=identity_change):
                candidate = {**changed, **identity_change}
                with self.assertRaises(HTTPException) as immutable:
                    self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                          candidate, note["etag"], saved["etag"],
                                                          saved["artifact_set_etag"])
                self.assertEqual(immutable.exception.status_code, 409)
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], resource_id)["docId"],
                         "doc_table_1")

    def test_blocksuite_snapshots_capture_resource_only_changes(self):
        note = self.store.create("# Snapshot closure\n")
        initial = {"schemaVersion": 1, "resourceKind": "database", "docId": "snapshot_doc",
                   "updateB64": base64.b64encode(b"state-one").decode("ascii"), "snapshot": {"blocks": []}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], initial, note["etag"])
        reference_content = note["content"] + "\n" + created["reference"] + "\n"
        saved_note = self.store.update("drafts", note["path"], reference_content, note["etag"],
                                       expected_artifacts=created["artifact_set_etag"])
        before_resource_change = self.store.list_blocksuite_snapshots("drafts", note["path"])
        current = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        replacement = {key: value for key, value in current.items()
                       if key not in {"etag", "note_etag", "filename", "artifact_set_etag"}}
        replacement["updateB64"] = base64.b64encode(b"state-two").decode("ascii")
        self.store.update_blocksuite_resource("drafts", note["path"], created["resource_id"], replacement,
                                              saved_note["etag"], current["etag"],
                                              current["artifact_set_etag"])
        after_resource_change = self.store.list_blocksuite_snapshots("drafts", note["path"])
        self.assertEqual(after_resource_change["note_etag"], saved_note["etag"])
        self.assertNotEqual(after_resource_change["artifact_set_etag"], before_resource_change["artifact_set_etag"])
        after = {item["artifact_set_etag"]: item for item in after_resource_change["snapshots"]}
        self.assertIn(before_resource_change["artifact_set_etag"], after)
        self.assertTrue(any(item["note_sha256"] == saved_note["etag"]
                            and item["artifact_set_etag"] == current["artifact_set_etag"]
                            for item in after_resource_change["snapshots"]))
        self.assertTrue(all(item["artifact_count"] == 1 for item in after.values()
                            if item["note_sha256"] == saved_note["etag"]))

        other_note = self.store.create("# Different note\n")
        with self.assertRaises(HTTPException) as unbound:
            self.store.read_blocksuite_resource("drafts", other_note["path"], created["resource_id"])
        self.assertEqual(unbound.exception.status_code, 404)

    def test_blocksuite_snapshot_restore_replaces_managed_resource_set_and_is_idempotent(self):
        note = self.store.create("# Restore closure\n")
        first_body = {"schemaVersion": 1, "resourceKind": "database", "docId": "restore_a",
                      "updateB64": base64.b64encode(b"A-one").decode("ascii"), "snapshot": {"blocks": []}}
        first = self.store.create_blocksuite_resource("drafts", note["path"], first_body, note["etag"])
        content = note["content"] + "\n" + first["reference"] + "\n"
        saved_note = self.store.update("drafts", note["path"], content, note["etag"],
                                       expected_artifacts=first["artifact_set_etag"])
        first_current = self.store.read_blocksuite_resource("drafts", note["path"], first["resource_id"])
        changed_a = {key: value for key, value in first_current.items()
                     if key not in {"etag", "note_etag", "filename", "artifact_set_etag"}}
        changed_a["updateB64"] = base64.b64encode(b"A-two").decode("ascii")
        self.store.update_blocksuite_resource("drafts", note["path"], first["resource_id"], changed_a,
                                              saved_note["etag"], first_current["etag"],
                                              first_current["artifact_set_etag"])
        snapshots = self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
        target_a_one = next(item for item in snapshots if item["note_sha256"] == saved_note["etag"]
                            and item["artifact_set_etag"] == first_current["artifact_set_etag"])

        second_body = {"schemaVersion": 1, "resourceKind": "database", "docId": "restore_b",
                       "updateB64": base64.b64encode(b"B-one").decode("ascii"), "snapshot": {"blocks": []}}
        second = self.store.create_blocksuite_resource("drafts", note["path"], second_body,
                                                       saved_note["etag"],
                                                       self.store.read("drafts", note["path"])["artifact_set_etag"])
        second_current = self.store.read_blocksuite_resource("drafts", note["path"], second["resource_id"])
        second_changed = {key: value for key, value in second_current.items()
                          if key not in {"etag", "note_etag", "filename", "artifact_set_etag"}}
        second_changed["updateB64"] = base64.b64encode(b"B-two").decode("ascii")
        self.store.update_blocksuite_resource("drafts", note["path"], second["resource_id"], second_changed,
                                              saved_note["etag"], second_current["etag"],
                                              second_current["artifact_set_etag"])
        after_add = self.store.read("drafts", note["path"])
        restored = self.store.restore_blocksuite_snapshot("drafts", note["path"], target_a_one["snapshot_id"],
                                                          after_add["etag"], after_add["artifact_set_etag"])
        self.assertTrue(restored["restored"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], first["resource_id"])["updateB64"],
                         first_body["updateB64"])
        with self.assertRaises(HTTPException) as removed_resource:
            self.store.read_blocksuite_resource("drafts", note["path"], second["resource_id"])
        self.assertEqual(removed_resource.exception.status_code, 404)

        duplicate = self.store.restore_blocksuite_snapshot("drafts", note["path"], target_a_one["snapshot_id"],
                                                           after_add["etag"], after_add["artifact_set_etag"])
        self.assertTrue(duplicate["duplicate"])

        target_a_two_b_two = next(item for item in self.store.list_blocksuite_snapshots(
            "drafts", note["path"])["snapshots"] if item["artifact_set_etag"] == after_add["artifact_set_etag"])
        current = self.store.read("drafts", note["path"])
        self.store.restore_blocksuite_snapshot("drafts", note["path"], target_a_two_b_two["snapshot_id"],
                                               current["etag"], current["artifact_set_etag"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], second["resource_id"])["updateB64"],
                         second_changed["updateB64"])

    def test_blocksuite_snapshot_restore_resumes_after_markdown_write_failure(self):
        note = self.store.create("# Restore retry\n")
        body = {"schemaVersion": 1, "resourceKind": "database", "docId": "retry_doc",
                "updateB64": base64.b64encode(b"old").decode("ascii"), "snapshot": {"blocks": []}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], body, note["etag"])
        content = note["content"] + "\n" + created["reference"] + "\n"
        saved_note = self.store.update("drafts", note["path"], content, note["etag"],
                                       expected_artifacts=created["artifact_set_etag"])
        current_resource = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        changed = {key: value for key, value in current_resource.items()
                   if key not in {"etag", "note_etag", "filename", "artifact_set_etag"}}
        changed["updateB64"] = base64.b64encode(b"new").decode("ascii")
        self.store.update_blocksuite_resource("drafts", note["path"], created["resource_id"], changed,
                                              saved_note["etag"], current_resource["etag"],
                                              current_resource["artifact_set_etag"])
        target = next(item for item in self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
                      if item["note_sha256"] == saved_note["etag"]
                      and item["artifact_set_etag"] == current_resource["artifact_set_etag"])
        current = self.store.read("drafts", note["path"])
        current = self.store.update("drafts", note["path"], current["content"] + "\n# Newer text\n",
                                    current["etag"], expected_artifacts=current["artifact_set_etag"])
        original_atomic_write = self.store._atomic_write
        fail_once = {"value": True}

        def injected_write(path, data, exclusive=False, directory_fd=None):
            if path.name == "note.md" and fail_once["value"]:
                fail_once["value"] = False
                raise OSError("injected markdown phase failure")
            return original_atomic_write(path, data, exclusive=exclusive, directory_fd=directory_fd)

        with patch.object(self.store, "_atomic_write", side_effect=injected_write):
            with self.assertRaises(OSError):
                self.store.restore_blocksuite_snapshot("drafts", note["path"], target["snapshot_id"],
                                                       current["etag"], current["artifact_set_etag"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])["updateB64"],
                         body["updateB64"])
        resumed = self.store.restore_blocksuite_snapshot("drafts", note["path"], target["snapshot_id"],
                                                         current["etag"], current["artifact_set_etag"])
        self.assertTrue(resumed["restored"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])["updateB64"],
                         body["updateB64"])

    def test_corrupt_same_size_snapshot_object_blocks_repeat_write_without_changing_live_data(self):
        note = self.store.create("# Corrupt recovery object\n")
        body = {"schemaVersion": 1, "resourceKind": "database", "docId": "integrity_doc",
                "updateB64": base64.b64encode(b"still-live").decode("ascii"), "snapshot": {"blocks": []}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], body, note["etag"])
        content = note["content"] + "\n" + created["reference"] + "\n"
        saved = self.store.update("drafts", note["path"], content, note["etag"],
                                  expected_artifacts=created["artifact_set_etag"])
        saved = self.store.update("drafts", note["path"], saved["content"], saved["etag"],
                                  expected_artifacts=saved["artifact_set_etag"])
        rows = self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
        snapshot = next(item for item in rows if item["note_sha256"] == saved["etag"])
        manifest_path = self.drafts / note["path"] / ".history" / "blocksuite" / "snapshots" / f"{snapshot['snapshot_id']}.json"
        manifest = json.loads(manifest_path.read_text())
        digest = manifest["artifacts"][0]["sha256"]
        object_path = self.drafts / ".blocksuite-history" / "objects" / digest
        original = object_path.read_bytes()
        corrupted = bytes([original[0] ^ 1]) + original[1:]
        self.assertEqual(len(corrupted), len(original))
        object_path.write_bytes(corrupted)
        before_note = self.store.read("drafts", note["path"])
        before_resource = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        with self.assertRaises(HTTPException) as blocked:
            self.store.update("drafts", note["path"], before_note["content"], before_note["etag"],
                              expected_artifacts=before_note["artifact_set_etag"])
        self.assertEqual(blocked.exception.status_code, 503)
        after_note = self.store.read("drafts", note["path"])
        after_resource = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        self.assertEqual(after_note["etag"], before_note["etag"])
        self.assertEqual(after_resource["etag"], before_resource["etag"])
        self.assertEqual(after_resource["updateB64"], body["updateB64"])

    def test_corrupt_retained_snapshot_blocks_pruning_and_new_history_write(self):
        note = self.store.create("# Version zero\n")
        current = note
        for title in ("Version one", "Version two", "Version three"):
            current = self.store.update("drafts", note["path"], f"# {title}\n", current["etag"],
                                        expected_artifacts=current["artifact_set_etag"])
        before_rows = self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
        self.assertEqual(len(before_rows), 3)
        retained = before_rows[-1]
        manifest_path = self.drafts / note["path"] / ".history" / "blocksuite" / "snapshots" / f"{retained['snapshot_id']}.json"
        manifest = json.loads(manifest_path.read_text())
        digest = manifest["note_sha256"]
        object_path = self.drafts / ".blocksuite-history" / "objects" / digest
        original = object_path.read_bytes()
        object_path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        with self.assertRaises(HTTPException) as blocked:
            self.store.update("drafts", note["path"], "# Version four\n", current["etag"],
                              expected_artifacts=current["artifact_set_etag"])
        self.assertEqual(blocked.exception.status_code, 503)
        snapshots_dir = self.drafts / note["path"] / ".history" / "blocksuite" / "snapshots"
        after_ids = {path.stem for path in snapshots_dir.glob("[0-9a-f]*.json")}
        self.assertEqual(after_ids, {item["snapshot_id"] for item in before_rows})
        self.assertEqual(self.store.read("drafts", note["path"])["etag"], current["etag"])

    def test_history_keeps_latest_three_distinct_closures_in_order(self):
        note = self.store.create("# Version zero\n")
        current = note
        history = {current["etag"]: current["content"]}
        for index in range(1, 6):
            current = self.store.update("drafts", note["path"], f"# Version {index}\n", current["etag"],
                                        expected_artifacts=current["artifact_set_etag"])
            history[current["etag"]] = current["content"]
        snapshots = self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
        self.assertEqual(len(snapshots), 3)
        expected = {self.store._digest(f"# Version {index}\n") for index in (2, 3, 4)}
        self.assertEqual({item["note_sha256"] for item in snapshots}, expected)
        self.assertEqual(sorted(item["created_at"] for item in snapshots),
                         [item["created_at"] for item in snapshots])

    def test_completed_snapshot_retry_finishes_prune_and_collects_orphan(self):
        note = self.store.create("# Version zero\n")
        current = note
        for index in range(1, 5):
            current = self.store.update("drafts", note["path"], f"# Version {index}\n", current["etag"],
                                        expected_artifacts=current["artifact_set_etag"])
        history = self.store._history_store()
        original_prune = history._prune_local
        fail_once = {"value": True}

        def injected_prune(*args, **kwargs):
            if fail_once["value"]:
                fail_once["value"] = False
                raise OSError("injected prune interruption")
            return original_prune(*args, **kwargs)

        with patch.object(history, "_prune_local", side_effect=injected_prune):
            with self.assertRaises(HTTPException) as interrupted:
                self.store.update("drafts", note["path"], "# Version five\n", current["etag"],
                                  expected_artifacts=current["artifact_set_etag"])
            self.assertEqual(interrupted.exception.status_code, 507)
        snapshots_dir = self.drafts / note["path"] / ".history" / "blocksuite" / "snapshots"
        self.assertEqual(len(list(snapshots_dir.glob("[0-9a-f]*.json"))), 4)
        orphan_data = b"orphaned generated history block"
        orphan_hash = __import__("hashlib").sha256(orphan_data).hexdigest()
        with history._global(create=False) as global_fds:
            history._write_object(global_fds["objects_fd"], orphan_hash, orphan_data)
        retried = self.store.update("drafts", note["path"], "# Version five\n", current["etag"],
                                    expected_artifacts=current["artifact_set_etag"])
        self.assertEqual(retried["content"], "# Version five\n")
        after_rows = self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
        self.assertEqual(len(after_rows), 3)
        self.assertFalse((self.drafts / ".blocksuite-history" / "objects" / orphan_hash).exists())

    def test_snapshot_directory_creation_fsyncs_parent_directories(self):
        note = self.store.create("# Durable snapshot directories\n")
        original_fsync = os.fsync
        observed_directory_sync = {"value": False}

        def track_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                observed_directory_sync["value"] = True
            return original_fsync(fd)

        with patch("os.fsync", side_effect=track_fsync):
            body = {"schemaVersion": 1, "resourceKind": "database", "docId": "durable_doc",
                    "updateB64": base64.b64encode(b"durable").decode("ascii"), "snapshot": {"blocks": []}}
            self.store.create_blocksuite_resource("drafts", note["path"], body, note["etag"])
        self.assertTrue(observed_directory_sync["value"])

    def test_blocksuite_resource_schema_and_payload_limits_fail_closed(self):
        note = self.store.create("# Resource bounds\n")
        valid = {"schemaVersion": 1, "resourceKind": "edgeless-canvas", "docId": "canvas_1",
                 "updateB64": base64.b64encode(b"yjs").decode("ascii"), "snapshot": {"blocks": []}}
        with self.assertRaises(HTTPException) as unknown:
            self.store.create_blocksuite_resource("drafts", note["path"], {**valid, "unexpected": True}, note["etag"])
        self.assertEqual(unknown.exception.status_code, 422)
        with self.assertRaises(HTTPException) as bad_b64:
            self.store.create_blocksuite_resource("drafts", note["path"], {**valid, "updateB64": "%%%%"}, note["etag"])
        self.assertEqual(bad_b64.exception.status_code, 422)
        with self.assertRaises(HTTPException) as bad_kind:
            self.store.create_blocksuite_resource("drafts", note["path"], {**valid, "resourceKind": "anything"}, note["etag"])
        self.assertEqual(bad_kind.exception.status_code, 422)
        with self.assertRaises(HTTPException) as invalid_unicode:
            self.store.create_blocksuite_resource("drafts", note["path"],
                                                  {**valid, "snapshot": {"text": chr(0xD800)}}, note["etag"])
        self.assertEqual(invalid_unicode.exception.status_code, 422)
        nested = {"value": "leaf"}
        for _ in range(66):
            nested = {"nested": nested}
        with self.assertRaises(HTTPException) as too_deep:
            self.store.create_blocksuite_resource("drafts", note["path"], {**valid, "snapshot": nested}, note["etag"])
        self.assertEqual(too_deep.exception.status_code, 422)
        too_large = base64.b64encode(b"x" * (7 * 1024 * 1024 + 1)).decode("ascii")
        with self.assertRaises(HTTPException) as oversized:
            self.store.create_blocksuite_resource("drafts", note["path"], {**valid, "updateB64": too_large}, note["etag"])
        self.assertEqual(oversized.exception.status_code, 413)
        self.assertEqual(list((self.drafts / note["path"] / "attachments").glob("*.blocksuite.json"))
                         if (self.drafts / note["path"] / "attachments").exists() else [], [])

    def test_blocksuite_resource_per_note_quotas_reject_without_changing_existing_resources(self):
        note = self.store.create("# Resource quota bounds\n")
        valid = {"schemaVersion": 1, "resourceKind": "database", "docId": "doc_1",
                 "updateB64": base64.b64encode(b"yjs").decode("ascii"), "snapshot": {"blocks": []}}

        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_RESOURCES_PER_NOTE", 2):
            first = self.store.create_blocksuite_resource("drafts", note["path"], valid, note["etag"])
            second = self.store.create_blocksuite_resource("drafts", note["path"], valid, note["etag"],
                                                           first["artifact_set_etag"])
            before_count_limit = [self.store.read_blocksuite_resource("drafts", note["path"], item["resource_id"])
                                  for item in (first, second)]
            with self.assertRaises(HTTPException) as count_limited:
                self.store.create_blocksuite_resource("drafts", note["path"], valid, note["etag"],
                                                      second["artifact_set_etag"])
            self.assertEqual(count_limited.exception.status_code, 413)
            after_count_limit = [self.store.read_blocksuite_resource("drafts", note["path"], item["resource_id"])
                                 for item in (first, second)]
            self.assertEqual([(item["etag"], item["updateB64"]) for item in after_count_limit],
                             [(item["etag"], item["updateB64"]) for item in before_count_limit])

        another_note = self.store.create("# Aggregate resource quota bounds\n")
        first = self.store.create_blocksuite_resource("drafts", another_note["path"], valid, another_note["etag"])
        first_data = self.store.read_blocksuite_resource("drafts", another_note["path"], first["resource_id"])
        first_path = self.drafts / another_note["path"] / "attachments" / first["filename"]
        first_size = first_path.stat().st_size
        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE",
                   first_size + 1):
            with self.assertRaises(HTTPException) as aggregate_limited:
                self.store.create_blocksuite_resource("drafts", another_note["path"], valid, another_note["etag"],
                                                      first["artifact_set_etag"])
            self.assertEqual(aggregate_limited.exception.status_code, 413)
            after_create_limit = self.store.read_blocksuite_resource("drafts", another_note["path"],
                                                                     first["resource_id"])
            self.assertEqual((after_create_limit["etag"], after_create_limit["updateB64"]),
                             (first_data["etag"], first_data["updateB64"]))

            replacement = {**valid, "resourceId": first["resource_id"],
                           "updateB64": base64.b64encode(b"larger replacement").decode("ascii")}
            with self.assertRaises(HTTPException) as update_limited:
                self.store.update_blocksuite_resource("drafts", another_note["path"], first["resource_id"],
                                                      replacement, another_note["etag"], first["etag"],
                                                      first_data["artifact_set_etag"])
            self.assertEqual(update_limited.exception.status_code, 413)
            after_update_limit = self.store.read_blocksuite_resource("drafts", another_note["path"],
                                                                     first["resource_id"])
            self.assertEqual((after_update_limit["etag"], after_update_limit["updateB64"]),
                             (first_data["etag"], first_data["updateB64"]))

    def test_blocksuite_resource_rejects_symlinked_resource_files(self):
        note = self.store.create("# Symlink resource test\n")
        body = {"schemaVersion": 1, "resourceKind": "database", "docId": "doc_1",
                "updateB64": base64.b64encode(b"state").decode("ascii"), "snapshot": {"blocks": []}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], body, note["etag"])
        target = self.drafts / note["path"] / "attachments" / created["filename"]
        outside = Path(self.temp.name) / "outside-resource.json"
        outside.write_text('{"synthetic":"outside"}')
        outside.chmod(0o600)
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaises(HTTPException) as blocked:
            self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        self.assertEqual(blocked.exception.status_code, 403)
        self.assertEqual(outside.read_text(), '{"synthetic":"outside"}')

    def test_blocksuite_resource_http_routes_require_notes_scope_and_use_both_etags(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")
                if request.headers.get("x-deny") == action:
                    raise HTTPException(status_code=403, detail=f"{action} denied")

        note = self.store.create("# HTTP BlockSuite resource\n")
        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        base = f"/api/notes/drafts/{note['path']}/blocksuite/resources"
        body = {"schemaVersion": 1, "resourceKind": "database", "docId": "table_doc",
                "updateB64": base64.b64encode(b"synthetic-state").decode("ascii"),
                "snapshot": {"type": "page", "blocks": []}}
        self.assertEqual(client.post(base, json=body, headers={"If-Match": f'"{note["etag"]}"'}).status_code, 401)
        client.cookies.set("session", "owner")
        self.assertEqual(client.post(base, json=body, headers={"If-Match": f'"{note["etag"]}"', "x-deny": "notes.write"}).status_code, 403)
        empty_set = f'"{note["artifact_set_etag"]}"'
        created = client.post(base, json=body,
                              headers={"If-Match": f'"{note["etag"]}"', "If-Artifact-Set-Match": empty_set})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.headers["x-note-etag"], f'"{note["etag"]}"')
        resource_url = f"{base}/{created.json()['resource_id']}"
        self.assertEqual(client.get(resource_url, headers={"x-deny": "notes.read"}).status_code, 403)
        fetched = client.get(resource_url)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.headers["etag"], f'"{created.json()["etag"]}"')
        self.assertEqual(fetched.headers["x-artifact-set-etag"],
                         f'"{created.json()["artifact_set_etag"]}"')
        replacement = {**body, "resourceId": created.json()["resource_id"],
                       "updateB64": base64.b64encode(b"replacement").decode("ascii")}
        stale = client.put(resource_url, json=replacement,
                           headers={"If-Match": f'"{note["etag"]}"', "If-Resource-Match": '"stale"',
                                    "If-Artifact-Set-Match": fetched.headers["x-artifact-set-etag"]})
        self.assertEqual(stale.status_code, 412)
        saved = client.put(resource_url, json=replacement,
                           headers={"If-Match": f'"{note["etag"]}"', "If-Resource-Match": fetched.headers["etag"],
                                    "If-Artifact-Set-Match": fetched.headers["x-artifact-set-etag"]})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(client.get(resource_url).json()["updateB64"], replacement["updateB64"])
        identity_change = {**replacement, "docId": "other_doc"}
        rejected_identity_change = client.put(resource_url, json=identity_change,
                                              headers={"If-Match": f'"{note["etag"]}"',
                                                       "If-Resource-Match": saved.headers["etag"],
                                                       "If-Artifact-Set-Match": saved.headers["x-artifact-set-etag"]})
        self.assertEqual(rejected_identity_change.status_code, 409)
        self.assertEqual(client.get(resource_url).json()["docId"], "table_doc")

    def test_rich_page_reuses_note_versions_blob_snapshot_and_quota_without_migrating_markdown(self):
        original = "# Ordinary Markdown\n\nKeep this readable source.\n"
        note = self.store.create(original)
        body = {"schemaVersion": 1, "resourceKind": "rich-page", "docId": "rich_page_1",
                "updateB64": base64.b64encode(b"synthetic-yjs-page-v1").decode("ascii"),
                "snapshot": {"blocks": {"textAlign": "center", "mergeRegions": {"region": [1, 2]}}}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], body, note["etag"])
        # Creating a native Page never rewrites or migrates its ordinary Markdown owner.
        self.assertEqual(self.store.read("drafts", note["path"])["content"], original)
        png = self._png_blob("blue")
        blob_id = self._blob_id(png)
        blob = self.store.put_blocksuite_blob("drafts", note["path"], blob_id, png, "image/png",
                                              note["etag"], created["artifact_set_etag"])
        projection = original + "\n" + created["reference"] + "\n"
        owner = self.store.update("drafts", note["path"], projection, note["etag"],
                                  expected_artifacts=blob["artifact_set_etag"])
        first = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        replacement = {**body, "resourceId": created["resource_id"],
                       "updateB64": base64.b64encode(b"synthetic-yjs-page-v2").decode("ascii"),
                       "snapshot": {"blocks": {"textAlign": "right", "sourceId": blob_id}}}
        saved = self.store.update_blocksuite_resource("drafts", note["path"], created["resource_id"],
                                                      replacement, owner["etag"], first["etag"],
                                                      first["artifact_set_etag"])
        target = next(row for row in self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
                      if row["note_sha256"] == owner["etag"]
                      and row["artifact_set_etag"] == first["artifact_set_etag"])
        # An external Markdown writer retains its source; stale rich-page writes cannot overwrite it.
        external = self.store.update("drafts", note["path"], projection + "\nExternal edit.\n", owner["etag"],
                                     expected_artifacts=saved["artifact_set_etag"])
        with self.assertRaises(HTTPException) as conflict:
            self.store.update_blocksuite_resource("drafts", note["path"], created["resource_id"], replacement,
                                                  owner["etag"], saved["etag"], saved["artifact_set_etag"])
        self.assertEqual(conflict.exception.status_code, 412)
        self.assertEqual(self.store.read("drafts", note["path"])["content"], external["content"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])["updateB64"],
                         replacement["updateB64"])
        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_RESOURCES_PER_NOTE", 2):
            with self.assertRaises(HTTPException) as limited:
                self.store.create_blocksuite_resource("drafts", note["path"], {**body, "docId": "second_rich_page"},
                                                      external["etag"], saved["artifact_set_etag"])
        self.assertEqual(limited.exception.status_code, 413)
        # Recovery is explicit and guarded by the latest owner and artifact-set versions.
        restored = self.store.restore_blocksuite_snapshot("drafts", note["path"], target["snapshot_id"],
                                                          external["etag"], saved["artifact_set_etag"])
        self.assertTrue(restored["restored"])
        self.assertEqual(self.store.read("drafts", note["path"])["content"], projection)
        reloaded = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        self.assertEqual(reloaded["resourceKind"], "rich-page")
        self.assertEqual(reloaded["snapshot"], body["snapshot"])
        self.assertEqual(self.store.read_blocksuite_blob("drafts", note["path"], blob_id)["data"], png)

    def test_managed_property_update_rebinds_rich_page_receipt_without_changing_yjs(self):
        initial = '---\ncustom: keep\n类型: "摘要"\ntags: ["SecondBrain"]\n---\n\n# Property-bound Page\n'
        note = self.store.create("# Placeholder\n")
        note_path = self.drafts / note["path"] / "note.md"
        note_path.write_text(initial, encoding="utf-8")
        note_path.chmod(0o600)
        note = self.store.read("drafts", note["path"])
        update = base64.b64encode(b"synthetic-yjs-preserved").decode("ascii")
        body = {"schemaVersion": 1, "resourceKind": "rich-page", "docId": "property_bound_page",
                "updateB64": update,
                "snapshot": {"blocks": {}, "secondbrainRichPage": {"schemaVersion": 1,
                    "markdownSha256": note["etag"]}}}
        created = self.store.create_blocksuite_resource("drafts", note["path"], body, note["etag"])
        projection = f'{initial.rstrip()}\n\n{created["reference"]}\n'
        note = self.store.update("drafts", note["path"], projection, note["etag"],
                                 expected_artifacts=created["artifact_set_etag"])
        resource = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        bound_body = {key: resource[key] for key in ("schemaVersion", "resourceId", "resourceKind", "docId", "updateB64", "snapshot")}
        bound_body["snapshot"] = {**bound_body["snapshot"], "secondbrainRichPage": {
            **bound_body["snapshot"]["secondbrainRichPage"], "markdownSha256": note["etag"]}}
        saved_resource = self.store.update_blocksuite_resource("drafts", note["path"], created["resource_id"],
            bound_body, note["etag"], resource["etag"], resource["artifact_set_etag"])

        saved_note = self.store.update_properties("drafts", note["path"], "笔记", ["SecondBrain"], note["etag"])
        rebound = self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])
        self.assertNotEqual(saved_note["etag"], note["etag"])
        self.assertEqual(rebound["note_etag"], saved_note["etag"])
        self.assertEqual(rebound["snapshot"]["secondbrainRichPage"]["markdownSha256"], saved_note["etag"])
        self.assertEqual(rebound["updateB64"], update)
        self.assertNotEqual(rebound["etag"], saved_resource["etag"])
        self.assertIn('custom: keep', saved_note["content"])
        self.assertIn('# Property-bound Page', saved_note["content"])
        stale_receipt = {key: rebound[key] for key in (
            "schemaVersion", "resourceId", "resourceKind", "docId", "updateB64", "snapshot")}
        stale_receipt["snapshot"] = {**stale_receipt["snapshot"], "secondbrainRichPage": {
            **stale_receipt["snapshot"]["secondbrainRichPage"], "markdownSha256": "f" * 64}}
        corrupted = self.store.update_blocksuite_resource("drafts", note["path"], created["resource_id"],
            stale_receipt, saved_note["etag"], rebound["etag"], rebound["artifact_set_etag"])
        before = self.store.read("drafts", note["path"])
        with self.assertRaises(HTTPException) as stale_binding:
            self.store.update_properties("drafts", note["path"], "摘要", [], before["etag"])
        self.assertEqual(stale_binding.exception.status_code, 412)
        self.assertEqual(self.store.read("drafts", note["path"])["content"], before["content"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], created["resource_id"])["etag"],
                         corrupted["etag"])

    def test_blocksuite_snapshot_routes_expose_read_and_dual_etag_restore(self):
        self._check_blocksuite_snapshot_routes("database")

    def test_rich_page_http_routes_reuse_auth_and_dual_etag_snapshot_restore(self):
        self._check_blocksuite_snapshot_routes("rich-page")

    def _check_blocksuite_snapshot_routes(self, resource_kind):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")
                if request.headers.get("x-deny") == action:
                    raise HTTPException(status_code=403, detail=f"{action} denied")

        note = self.store.create("# Snapshot route\n")
        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        client.cookies.set("session", "owner")
        base = f"/api/notes/drafts/{note['path']}/blocksuite"
        create_body = {"schemaVersion": 1, "resourceKind": resource_kind, "docId": "route_doc",
                       "updateB64": base64.b64encode(b"before").decode("ascii"), "snapshot": {"blocks": []}}
        created = client.post(f"{base}/resources", json=create_body,
                              headers={"If-Match": f'"{note["etag"]}"',
                                       "If-Artifact-Set-Match": f'"{note["artifact_set_etag"]}"'})
        self.assertEqual(created.status_code, 200)
        note_ref = note["content"] + "\n" + created.json()["reference"] + "\n"
        saved = client.put(f"/api/notes/drafts/{note['path']}", json={"content": note_ref},
                           headers={"If-Match": f'"{note["etag"]}"',
                                    "If-Artifact-Set-Match": created.headers["x-artifact-set-etag"]})
        self.assertEqual(saved.status_code, 200)
        current_resource = client.get(f"{base}/resources/{created.json()['resource_id']}")
        replacement = {key: value for key, value in current_resource.json().items()
                       if key not in {"etag", "note_etag", "artifact_set_etag", "filename"}}
        replacement["updateB64"] = base64.b64encode(b"after").decode("ascii")
        current = client.put(f"{base}/resources/{created.json()['resource_id']}", json=replacement,
                             headers={"If-Match": saved.headers["etag"],
                                      "If-Resource-Match": current_resource.headers["etag"],
                                      "If-Artifact-Set-Match": current_resource.headers["x-artifact-set-etag"]})
        self.assertEqual(current.status_code, 200)
        listing = client.get(f"{base}/snapshots")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.headers["x-note-etag"], saved.headers["etag"])
        target = next(item for item in listing.json()["snapshots"]
                      if item["note_sha256"] == saved.json()["etag"]
                      and item["artifact_set_etag"] == current_resource.json()["artifact_set_etag"])
        snapshot = client.get(f"{base}/snapshots/{target['snapshot_id']}")
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["note"]["content"], note_ref)
        self.assertEqual(snapshot.json()["artifacts"][0]["resource"]["updateB64"], create_body["updateB64"])
        restore_url = f"{base}/snapshots/{target['snapshot_id']}/restore"
        stale = client.post(restore_url, headers={"If-Match": '"stale"',
                                                  "If-Artifact-Set-Match": current.headers["x-artifact-set-etag"]})
        self.assertEqual(stale.status_code, 412)
        denied = client.post(restore_url, headers={"If-Match": current.headers["x-note-etag"],
                                                   "If-Artifact-Set-Match": current.headers["x-artifact-set-etag"],
                                                   "x-deny": "notes.write"})
        self.assertEqual(denied.status_code, 403)
        restored = client.post(restore_url, headers={"If-Match": current.headers["x-note-etag"],
                                                      "If-Artifact-Set-Match": current.headers["x-artifact-set-etag"]})
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.headers["x-note-etag"], saved.headers["etag"])
        self.assertEqual(client.get(f"{base}/resources/{created.json()['resource_id']}").json()["updateB64"],
                         create_body["updateB64"])

    @staticmethod
    def _png_blob(color):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color=color).save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def _blob_id(data):
        return base64.urlsafe_b64encode(__import__("hashlib").sha256(data).digest()).decode("ascii")

    def test_blocksuite_blob_hash_validation_idempotency_and_combined_quotas(self):
        note = self.store.create("# Blob note\n")
        png = self._png_blob("blue")
        blob_id = self._blob_id(png)
        created = self.store.put_blocksuite_blob("drafts", note["path"], blob_id, png, "image/png",
                                                 note["etag"], note["artifact_set_etag"])
        self.assertTrue(created["created"])
        self.assertEqual(created["etag"], __import__("hashlib").sha256(png).hexdigest())
        fetched = self.store.read_blocksuite_blob("drafts", note["path"], blob_id)
        self.assertEqual(fetched["data"], png)
        self.assertEqual(fetched["content_type"], "image/png")
        repeated = self.store.put_blocksuite_blob("drafts", note["path"], blob_id, png, "image/png",
                                                  note["etag"], fetched["artifact_set_etag"])
        self.assertFalse(repeated["created"])
        for bad_id, expected_status in ((blob_id[:-1], 400), ("A" + blob_id[1:], 422)):
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(HTTPException) as invalid:
                    self.store.put_blocksuite_blob("drafts", note["path"], bad_id, png, "image/png",
                                                   note["etag"], fetched["artifact_set_etag"])
                self.assertEqual(invalid.exception.status_code, expected_status)
        with self.assertRaises(HTTPException) as bad_type:
            self.store.put_blocksuite_blob("drafts", note["path"], blob_id, png, "image/jpeg",
                                            note["etag"], fetched["artifact_set_etag"])
        self.assertEqual(bad_type.exception.status_code, 415)
        with self.assertRaises(HTTPException) as bad_image:
            self.store.put_blocksuite_blob("drafts", note["path"], self._blob_id(b"not image"), b"not image",
                                            "image/png", note["etag"], fetched["artifact_set_etag"])
        self.assertEqual(bad_image.exception.status_code, 415)

        next_png = self._png_blob("red")
        next_id = self._blob_id(next_png)
        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_RESOURCES_PER_NOTE", 1):
            with self.assertRaises(HTTPException) as over_count:
                self.store.put_blocksuite_blob("drafts", note["path"], next_id, next_png, "image/png",
                                               note["etag"], fetched["artifact_set_etag"])
            self.assertEqual(over_count.exception.status_code, 413)
        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_RESOURCES_TOTAL_BYTES_PER_NOTE", len(png) + 1):
            with self.assertRaises(HTTPException) as over_bytes:
                self.store.put_blocksuite_blob("drafts", note["path"], next_id, next_png, "image/png",
                                               note["etag"], fetched["artifact_set_etag"])
            self.assertEqual(over_bytes.exception.status_code, 413)
        self.assertEqual(self.store.read_blocksuite_blob("drafts", note["path"], blob_id)["data"], png)
        with self.assertRaises(HTTPException) as stale:
            self.store.put_blocksuite_blob("drafts", note["path"], next_id, next_png, "image/png",
                                           note["etag"], "0" * 64)
        self.assertEqual(stale.exception.status_code, 412)

    def test_blocksuite_blob_is_in_snapshot_read_restore_closure(self):
        note = self.store.create("# Blob restore closure\n")
        blue = self._png_blob("blue")
        blue_id = self._blob_id(blue)
        first = self.store.put_blocksuite_blob("drafts", note["path"], blue_id, blue, "image/png",
                                               note["etag"], note["artifact_set_etag"])
        resource_body = {"schemaVersion": 1, "resourceKind": "database", "docId": "blob_closure",
                         "updateB64": base64.b64encode(b"resource").decode("ascii"), "snapshot": {"blocks": []}}
        resource = self.store.create_blocksuite_resource("drafts", note["path"], resource_body, note["etag"],
                                                         first["artifact_set_etag"])
        red = self._png_blob("red")
        red_id = self._blob_id(red)
        second = self.store.put_blocksuite_blob("drafts", note["path"], red_id, red, "image/png",
                                                note["etag"], resource["artifact_set_etag"])
        target = next(item for item in self.store.list_blocksuite_snapshots("drafts", note["path"])["snapshots"]
                      if item["artifact_set_etag"] == resource["artifact_set_etag"])
        detail = self.store.read_blocksuite_snapshot("drafts", note["path"], target["snapshot_id"])
        self.assertEqual({(item["kind"], item["id"]) for item in detail["artifacts"]},
                         {("blob", blue_id), ("resource", resource["resource_id"])})
        current = self.store.read("drafts", note["path"])
        restored = self.store.restore_blocksuite_snapshot("drafts", note["path"], target["snapshot_id"],
                                                          current["etag"], current["artifact_set_etag"])
        self.assertTrue(restored["restored"])
        self.assertEqual(self.store.read_blocksuite_blob("drafts", note["path"], blue_id)["data"], blue)
        with self.assertRaises(HTTPException) as removed:
            self.store.read_blocksuite_blob("drafts", note["path"], red_id)
        self.assertEqual(removed.exception.status_code, 404)
        duplicate = self.store.restore_blocksuite_snapshot("drafts", note["path"], target["snapshot_id"],
                                                           current["etag"], current["artifact_set_etag"])
        self.assertTrue(duplicate["duplicate"])

    def test_blocksuite_blob_http_routes_use_auth_caps_and_dual_etag(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")
                if request.headers.get("x-deny") == action:
                    raise HTTPException(status_code=403, detail=f"{action} denied")

        note = self.store.create("# Blob HTTP\n")
        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        data = self._png_blob("green")
        blob_id = self._blob_id(data)
        url = f"/api/notes/drafts/{note['path']}/blocksuite/blobs/{blob_id}"
        headers = {"Content-Type": "image/png", "If-Match": f'"{note["etag"]}"',
                   "If-Artifact-Set-Match": f'"{note["artifact_set_etag"]}"'}
        self.assertEqual(client.put(url, content=data, headers=headers).status_code, 401)
        client.cookies.set("session", "owner")
        self.assertEqual(client.put(url, content=data, headers={**headers, "x-deny": "notes.write"}).status_code, 403)
        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_BLOB_BYTES", len(data) - 1):
            oversized = client.put(url, content=data, headers=headers)
        self.assertEqual(oversized.status_code, 413)
        with patch("secondbrain_core.modules.notes.MAX_BLOCKSUITE_BLOB_BYTES", 5 * 1024 * 1024):
            created = client.put(url, content=data, headers=headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.headers["x-artifact-set-etag"], f'"{created.json()["artifact_set_etag"]}"')
        fetched = client.get(url)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.content, data)
        self.assertEqual(fetched.headers["content-type"], "image/png")
        self.assertEqual(fetched.headers["etag"], created.headers["etag"])
        self.assertEqual(client.put(url, content=data, headers={**headers,
                         "If-Artifact-Set-Match": created.headers["x-artifact-set-etag"]}).status_code, 200)

    def test_blocksuite_http_body_limit_catches_chunked_body_with_forged_length(self):
        limit = 1024
        chunks = [b'{"payload":"' + b"a" * 800, b"b" * 800 + b'"}']
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/", "raw_path": b"/",
                 "query_string": b"", "headers": [(b"content-length", b"1")],
                 "server": ("test", 80), "client": ("test", 1)}

        async def receive():
            if chunks:
                chunk = chunks.pop(0)
                return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(scope, receive)
        with self.assertRaises(HTTPException) as too_large:
            asyncio.run(_read_bounded_json_request(request, limit))
        self.assertEqual(too_large.exception.status_code, 413)

    def test_notes_router_uses_etag_and_routes_attachment_endpoints(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        client.cookies.set("session", "owner")
        created_response = client.post("/api/notes", json={"content": "# API note\n"})
        created = created_response.json()
        self.assertEqual(created_response.headers["x-artifact-set-etag"], f'"{created["artifact_set_etag"]}"')
        target = f"/api/notes/drafts/{created['path']}"
        loaded = client.get(target)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.headers["x-artifact-set-etag"], f'"{loaded.json()["artifact_set_etag"]}"')
        etag = loaded.headers["etag"]
        saved = client.put(target, json={"content": "# Updated\n"}, headers={"If-Match": etag})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.headers["x-artifact-set-etag"], f'"{saved.json()["artifact_set_etag"]}"')
        stale = client.put(target, json={"content": "# Stale\n"}, headers={"If-Match": etag})
        self.assertEqual(stale.status_code, 412)
        history = client.get(f"{target}/history")
        self.assertEqual(history.status_code, 200)
        buffer = BytesIO()
        Image.new("RGB", (1, 1), color="blue").save(buffer, format="PNG")
        uploaded = client.post(f"{target}/attachments", files={"file": ("input.png", buffer.getvalue(), "image/png")})
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(client.get(uploaded.json()["url"]).status_code, 200)
        mindmap = json.dumps({"data": {"text": "Root"}, "children": []})
        visual = client.post(f"{target}/visual-assets/mindmap", json={"content": mindmap},
                             headers={"If-Match": f'"{saved.json()["etag"]}"'})
        self.assertEqual(visual.status_code, 200)
        source_url = f"{target}/attachments/{visual.json()['filename']}"
        fetched = client.get(source_url)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.headers["content-type"], "application/json")
        self.assertEqual(json.loads(fetched.text), json.loads(mindmap))
        replaced = client.put(source_url,
                              json={"content": json.dumps({"data": {"text": "Changed"}, "children": []})},
                              headers={"If-Match": f'"{saved.json()["etag"]}"',
                                       "If-Asset-Match": fetched.headers["etag"]})
        self.assertEqual(replaced.status_code, 200)

    def test_confirmed_properties_update_only_managed_frontmatter_with_etag_and_history(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")
                if action == "notes.write" and request.headers.get("x-deny-write") == "true":
                    raise HTTPException(status_code=403, detail="Notes write permission required")

        initial = '---\ncustom: "keep me"\n类型: "摘要"\ntags:\n  - "CRM"\n---\n\n[[Wiki Link]]\n'
        draft = self.store.create("# Temporary\n")
        note_path = self.drafts / draft["path"] / "note.md"
        note_path.write_text(initial)
        note_path.chmod(0o600)
        draft = self.store.read("drafts", draft["path"])
        approval_root = Path(self.temp.name) / "approval"
        approval_root.mkdir(mode=0o700)
        vocab = VocabularyStore(approval_root)
        vocabulary_state = vocab.add_type("中文自定义类型", 0, True)
        vocabulary_state = vocab.add_tag("SecondBrain", vocabulary_state["revision"], True)
        vocabulary_state = vocab.add_tag("中文标签", vocabulary_state["revision"], True)
        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store, vocab))
        client = TestClient(app)
        url = f"/api/notes/drafts/{draft['path']}/properties"
        self.assertEqual(client.get(url).status_code, 401)
        client.cookies.set("session", "owner")
        properties = client.get(url)
        self.assertEqual(properties.status_code, 200)
        self.assertEqual(properties.json()["type"], "摘要")
        self.assertEqual(properties.json()["tags"], ["CRM"])
        revision = properties.headers["etag"]
        denied = client.put(url, json={"type": "笔记", "tags": [], "confirmed": True},
                            headers={"If-Match": revision, "x-deny-write": "true"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.store.read("drafts", draft["path"])["content"], initial)
        unconfirmed = client.put(url, json={"type": "笔记", "tags": [], "confirmed": False},
                                 headers={"If-Match": revision})
        self.assertEqual(unconfirmed.status_code, 400)
        unknown = client.put(url, json={"type": "笔记", "tags": ["not-approved"], "confirmed": True},
                             headers={"If-Match": revision})
        self.assertEqual(unknown.status_code, 409)
        saved = client.put(url, json={"type": "中文自定义类型", "tags": ["SecondBrain", "中文标签", "CRM"], "confirmed": True},
                           headers={"If-Match": revision})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.headers["etag"], f'"{saved.json()["etag"]}"')
        content = saved.json()["content"]
        self.assertIn('custom: "keep me"', content)
        self.assertIn('类型: "中文自定义类型"', content)
        self.assertIn('tags: ["SecondBrain", "中文标签", "CRM"]', content)
        self.assertTrue(content.endswith("\n\n[[Wiki Link]]\n"))
        self.assertEqual(self.store.history("drafts", draft["path"])["versions"][0]["content"], initial)
        stale = client.put(url, json={"type": "摘要", "tags": [], "confirmed": True},
                           headers={"If-Match": revision})
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(self.store.read("drafts", draft["path"])["content"], content)

    def test_multiline_managed_type_is_rejected_without_changing_note_bytes(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        initial = '---\n类型: |\n  multiline value\ntags: []\n---\n\n# Body\n'
        draft = self.store.create("# Temporary\n")
        note_path = self.drafts / draft["path"] / "note.md"
        note_path.write_text(initial)
        note_path.chmod(0o600)
        vocab_root = Path(self.temp.name) / "approval-multiline"
        vocab_root.mkdir(mode=0o700)
        vocab = VocabularyStore(vocab_root)
        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store, vocab))
        client = TestClient(app)
        client.cookies.set("session", "owner")
        url = f"/api/notes/drafts/{draft['path']}/properties"
        self.assertEqual(client.get(url).status_code, 422)
        etag = self.store.read("drafts", draft["path"])["etag"]
        updated = client.put(url, json={"type": "笔记", "tags": [], "confirmed": True},
                             headers={"If-Match": f'"{etag}"'})
        self.assertEqual(updated.status_code, 422)
        self.assertEqual(note_path.read_text(), initial)

    def test_history_http_distinguishes_empty_history_missing_note_and_auth_failure(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        note = client.post("/api/notes", json={"content": "# Synthetic history\n"}, cookies={"session": "owner"}).json()
        history_url = f"/api/notes/drafts/{note['path']}/history"
        self.assertEqual(client.get(history_url).status_code, 401)
        empty = client.get(history_url, cookies={"session": "owner"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), {"versions": []})

        path = f"/api/notes/drafts/{note['path']}"
        first = client.put(path, json={"content": "# Revision 1\n"}, headers={"If-Match": f'"{note["etag"]}"'}, cookies={"session": "owner"})
        second = client.put(path, json={"content": "# Revision 2\n"}, headers={"If-Match": f'"{first.json()["etag"]}"'}, cookies={"session": "owner"})
        self.assertEqual(second.status_code, 200)
        versions = client.get(history_url, cookies={"session": "owner"})
        self.assertEqual(versions.status_code, 200)
        self.assertEqual([entry["content"] for entry in versions.json()["versions"]], ["# Synthetic history\n", "# Revision 1\n"])

        missing = client.get("/api/notes/drafts/00000000-0000-4000-8000-000000000099/history", cookies={"session": "owner"})
        self.assertEqual(missing.status_code, 404)
        history_directory = self.drafts / note["path"] / ".history"
        history_directory.chmod(0o755)
        unsafe = client.get(history_url, cookies={"session": "owner"})
        self.assertEqual(unsafe.status_code, 403)

    def test_authorized_ordinary_note_history_is_per_file_over_http(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")
                if action == "notes.read" and request.headers.get("x-deny-read") == "true":
                    raise HTTPException(status_code=403, detail="Notes read permission required")

        folder = self.ordinary / "folder"
        folder.mkdir(mode=0o700)
        note_a_path = folder / "a.md"
        note_a_path.write_text("# Original A\n")
        note_a_path.chmod(0o600)
        note_b_path = folder / "b.md"
        note_b_path.write_text("# Original B\n")
        note_b_path.chmod(0o600)

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        history_a_url = "/api/notes/personal/folder/a.md/history"
        history_b_url = "/api/notes/personal/folder/b.md/history"
        self.assertEqual(client.get(history_a_url).status_code, 401)
        self.assertEqual(client.get(history_a_url, cookies={"session": "owner"}, headers={"x-deny-read": "true"}).status_code, 403)

        empty_a = client.get(history_a_url, cookies={"session": "owner"})
        empty_b = client.get(history_b_url, cookies={"session": "owner"})
        self.assertEqual(empty_a.status_code, 200)
        self.assertEqual(empty_a.json(), {"versions": []})
        self.assertEqual(empty_b.status_code, 200)
        self.assertEqual(empty_b.json(), {"versions": []})

        note_a_url = "/api/notes/personal/folder/a.md"
        note_b_url = "/api/notes/personal/folder/b.md"
        loaded_b = client.get(note_b_url, cookies={"session": "owner"})
        first_b = client.put(note_b_url, json={"content": "# Revision B1\n"}, headers={"If-Match": loaded_b.headers["etag"]}, cookies={"session": "owner"})
        second_b = client.put(note_b_url, json={"content": "# Revision B2\n"}, headers={"If-Match": first_b.headers["etag"]}, cookies={"session": "owner"})
        self.assertEqual(second_b.status_code, 200)
        self.assertEqual(client.get(history_a_url, cookies={"session": "owner"}).json(), {"versions": []})
        history_b = client.get(history_b_url, cookies={"session": "owner"})
        self.assertEqual(history_b.status_code, 200)
        self.assertEqual([entry["content"] for entry in history_b.json()["versions"]], ["# Original B\n", "# Revision B1\n"])

        loaded_a = client.get(note_a_url, cookies={"session": "owner"})
        first_a = client.put(note_a_url, json={"content": "# Revision A1\n"}, headers={"If-Match": loaded_a.headers["etag"]}, cookies={"session": "owner"})
        second_a = client.put(note_a_url, json={"content": "# Revision A2\n"}, headers={"If-Match": first_a.headers["etag"]}, cookies={"session": "owner"})
        self.assertEqual(second_a.status_code, 200)
        history_a = client.get(history_a_url, cookies={"session": "owner"})
        self.assertEqual(history_a.status_code, 200)
        self.assertEqual([entry["content"] for entry in history_a.json()["versions"]], ["# Original A\n", "# Revision A1\n"])
        self.assertEqual([entry["content"] for entry in client.get(history_b_url, cookies={"session": "owner"}).json()["versions"]], ["# Original B\n", "# Revision B1\n"])

        missing = client.get("/api/notes/personal/folder/missing.md/history", cookies={"session": "owner"})
        self.assertEqual(missing.status_code, 404)

    def test_ambiguous_legacy_shared_history_fails_closed_without_moving_or_deleting_files(self):
        folder = self.ordinary / "legacy"
        folder.mkdir(mode=0o700)
        for name in ("a.md", "b.md"):
            path = folder / name
            path.write_text(f"# {name}\n")
            path.chmod(0o600)
        history = folder / ".history"
        history.mkdir(mode=0o700)
        legacy_content = "# Could belong to either note\n"
        legacy_entry = history / f"{NotesStore._digest(legacy_content)}.md"
        legacy_entry.write_text(legacy_content)
        legacy_entry.chmod(0o600)

        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        for note_name in ("a.md", "b.md"):
            response = client.get(f"/api/notes/personal/legacy/{note_name}/history", cookies={"session": "owner"})
            self.assertEqual(response.status_code, 409)
        self.assertEqual(legacy_entry.read_text(), legacy_content)
        self.assertEqual(list(history.iterdir()), [legacy_entry])

    def test_notes_router_requires_the_core_session_and_fails_closed_when_unconfigured(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        self.assertEqual(client.get("/api/notes").status_code, 401)
        note = self.store.create("# Session-bound visual\n")
        visual_path = f"/api/notes/drafts/{note['path']}/visual-assets/mindmap"
        self.assertEqual(client.post(visual_path, json={"content": json.dumps({"data": {"text": "Root"}, "children": []})},
                                     headers={"If-Match": f'"{note["etag"]}"'}).status_code, 401)
        self.assertEqual(client.get("/api/notes", cookies={"session": "owner"}).status_code, 200)
        disabled = FastAPI()
        disabled.include_router(create_notes_router(SessionAuth(), None))
        self.assertEqual(TestClient(disabled).get("/api/notes", cookies={"session": "owner"}).status_code, 503)

    def test_atomic_save_failure_keeps_the_previous_file_intact(self):
        note = self.store.create("# Original\n")
        actual_write = NotesStore._atomic_write
        calls = 0

        def fail_document_write(path, data, exclusive=False, directory_fd=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic disk failure")
            return actual_write(path, data, exclusive, directory_fd)

        with patch.object(NotesStore, "_atomic_write", side_effect=fail_document_write):
            with self.assertRaises(OSError):
                self.store.update("drafts", note["path"], "# New\n", note["etag"])
        self.assertEqual(self.store.read("drafts", note["path"])["content"], "# Original\n")

    def test_authorized_roots_fail_closed_without_knowledge_root_and_reject_overlap(self):
        drafts = Path(self.temp.name) / "draft-config"
        drafts.mkdir(mode=0o700)
        knowledge = Path(self.temp.name) / "knowledge"
        knowledge.mkdir(mode=0o700)
        ordinary = Path(self.temp.name) / "ordinary-config"
        ordinary.mkdir(mode=0o700)
        with patch.dict(os.environ, {"SB_KNOWLEDGE_ROOT": ""}):
            with self.assertRaises(RuntimeError):
                configured_notes_store(str(drafts.resolve()), '{"personal": "' + str(ordinary.resolve()) + '"}')
        with patch.dict(os.environ, {"SB_KNOWLEDGE_ROOT": str(knowledge)}):
            with self.assertRaises(RuntimeError):
                configured_notes_store(str(drafts.resolve()), '{"personal": "' + str(knowledge.resolve()) + '"}')
            self.assertIsNotNone(configured_notes_store(str(drafts.resolve()), '{"personal": "' + str(ordinary.resolve()) + '"}'))

    def test_history_symlink_is_rejected_without_reading_external_content(self):
        note = self.store.create("# History\n")
        self.store.update("drafts", note["path"], "# Changed\n", note["etag"])
        history = self.drafts / note["path"] / ".history"
        target = Path(self.temp.name) / "external-history"
        target.mkdir(mode=0o700)
        (target / (note["etag"] + ".md")).write_text("# Outside\n")
        (target / (note["etag"] + ".md")).chmod(0o600)
        history.rename(history.with_name(".history-old"))
        history.symlink_to(target, target_is_directory=True)
        with self.assertRaises(HTTPException) as blocked:
            self.store.history("drafts", note["path"])
        self.assertEqual(blocked.exception.status_code, 403)
        self.assertEqual((target / (note["etag"] + ".md")).read_text(), "# Outside\n")

    def test_attachment_symlink_is_rejected_for_upload_and_read(self):
        note = self.store.create("# Attachments\n")
        directory = self.drafts / note["path"]
        external = Path(self.temp.name) / "external-attachments"
        external.mkdir(mode=0o700)
        filename = "a" * 32 + ".png"
        outside = external / filename
        outside.write_bytes(b"synthetic")
        outside.chmod(0o600)
        (directory / "attachments").symlink_to(external, target_is_directory=True)
        with self.assertRaises(HTTPException) as read_blocked:
            self.store.read_attachment("drafts", note["path"], filename)
        self.assertEqual(read_blocked.exception.status_code, 403)
        buffer = BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buffer, format="PNG")
        with self.assertRaises(HTTPException) as upload_blocked:
            self.store.upload_image("drafts", note["path"], "input.png", buffer.getvalue())
        self.assertEqual(upload_blocked.exception.status_code, 403)
        self.assertEqual(outside.read_bytes(), b"synthetic")


if __name__ == "__main__":
    unittest.main()
