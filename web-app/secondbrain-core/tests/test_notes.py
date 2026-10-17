import tempfile
import unittest
import concurrent.futures
from io import BytesIO
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from PIL import Image

from secondbrain_core.modules.notes import NotesStore, create_notes_router, markdown_safety


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

    def test_notes_router_requires_the_core_session_and_fails_closed_when_unconfigured(self):
        class SessionAuth:
            def require_action(self, request: Request, action: str):
                if request.cookies.get("session") != "owner":
                    raise HTTPException(status_code=401, detail="App session required")

        app = FastAPI()
        app.include_router(create_notes_router(SessionAuth(), self.store))
        client = TestClient(app)
        self.assertEqual(client.get("/api/notes").status_code, 401)
        self.assertEqual(client.get("/api/notes", cookies={"session": "owner"}).status_code, 200)
        disabled = FastAPI()
        disabled.include_router(create_notes_router(SessionAuth(), None))
        self.assertEqual(TestClient(disabled).get("/api/notes", cookies={"session": "owner"}).status_code, 503)

    def test_atomic_save_failure_keeps_the_previous_file_intact(self):
        note = self.store.create("# Original\n")
        actual_write = NotesStore._atomic_write
        calls = 0

        def fail_document_write(path, data, exclusive=False):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic disk failure")
            return actual_write(path, data, exclusive)

        with patch.object(NotesStore, "_atomic_write", side_effect=fail_document_write):
            with self.assertRaises(OSError):
                self.store.update("drafts", note["path"], "# New\n", note["etag"])
        self.assertEqual(self.store.read("drafts", note["path"])["content"], "# Original\n")


if __name__ == "__main__":
    unittest.main()
