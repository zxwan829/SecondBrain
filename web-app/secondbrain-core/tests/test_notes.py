import tempfile
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

from secondbrain_core.modules.notes import NotesStore, configured_notes_store, create_notes_router, markdown_safety


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
