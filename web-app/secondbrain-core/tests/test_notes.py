import tempfile
import base64
import os
import unittest
import concurrent.futures
import json
from io import BytesIO
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from PIL import Image

from secondbrain_core.modules.notes import NotesStore, configured_notes_store, create_notes_router, markdown_safety, _note_properties, _replace_note_properties
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
        saved = self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                      changed, note["etag"], first["etag"])
        self.assertNotEqual(saved["etag"], first["etag"])
        self.assertEqual(self.store.read_blocksuite_resource("drafts", note["path"], resource_id)["updateB64"],
                         changed["updateB64"])
        with self.assertRaises(HTTPException) as stale_asset:
            self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                  changed, note["etag"], first["etag"])
        self.assertEqual(stale_asset.exception.status_code, 412)
        with self.assertRaises(HTTPException) as stale_note:
            self.store.update_blocksuite_resource("drafts", note["path"], resource_id,
                                                  changed, "0" * 64, saved["etag"])
        self.assertEqual(stale_note.exception.status_code, 412)

        other_note = self.store.create("# Different note\n")
        with self.assertRaises(HTTPException) as unbound:
            self.store.read_blocksuite_resource("drafts", other_note["path"], resource_id)
        self.assertEqual(unbound.exception.status_code, 404)

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
        created = client.post(base, json=body, headers={"If-Match": f'"{note["etag"]}"'})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.headers["x-note-etag"], f'"{note["etag"]}"')
        resource_url = f"{base}/{created.json()['resource_id']}"
        self.assertEqual(client.get(resource_url, headers={"x-deny": "notes.read"}).status_code, 403)
        fetched = client.get(resource_url)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.headers["etag"], f'"{created.json()["etag"]}"')
        replacement = {**body, "resourceId": created.json()["resource_id"],
                       "updateB64": base64.b64encode(b"replacement").decode("ascii")}
        stale = client.put(resource_url, json=replacement,
                           headers={"If-Match": f'"{note["etag"]}"', "If-Resource-Match": '"stale"'})
        self.assertEqual(stale.status_code, 412)
        saved = client.put(resource_url, json=replacement,
                           headers={"If-Match": f'"{note["etag"]}"', "If-Resource-Match": fetched.headers["etag"]})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(client.get(resource_url).json()["updateB64"], replacement["updateB64"])

    def test_notes_router_uses_etag_and_routes_attachment_endpoints(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        client.cookies.set("session", "owner")
        created = client.post("/api/notes", json={"content": "# API note\n"}).json()
        target = f"/api/notes/drafts/{created['path']}"
        loaded = client.get(target)
        self.assertEqual(loaded.status_code, 200)
        etag = loaded.headers["etag"]
        saved = client.put(target, json={"content": "# Updated\n"}, headers={"If-Match": etag})
        self.assertEqual(saved.status_code, 200)
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
