import io
import hashlib
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from secondbrain_core.app import create_app
from secondbrain_core.modules.capture import CaptureService, _public_http_url, _resolve_public_url, _fetch_url


class CaptureServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.review = self.root / "review"
        self.state = self.root / "state"
        for path in (self.raw, self.review, self.state):
            path.mkdir(mode=0o700)
        self.service = CaptureService(self.raw, self.review, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def test_text_capture_preserves_raw_and_creates_schema_compatible_review(self):
        item = self.service.accept_text("# A captured idea\nKeep this exact body.")
        raw = (self.raw / item["raw_path"]).read_bytes()
        self.service.process(item, raw)
        complete = self.service.get(item["capture_id"])
        self.assertEqual(complete["status"], "completed")
        self.assertEqual(raw, b"# A captured idea\nKeep this exact body.")
        review = (self.review / complete["review_path"]).read_text()
        for field in ("type:", "status:", "source_type:", "captured_at:", "original_asset:",
                      "capture_context:", "tags:", "review_status:"):
            self.assertIn(field, review)
        self.assertIn("Keep this exact body.", review)
        self.assertTrue(complete["original_asset"].startswith("/knowledge-assets/00-Inbox/"))
        self.assertEqual(complete["display_filename"], "capture.md")

    def test_collision_does_not_overwrite_raw_or_review_and_retry_uses_suffix(self):
        first = self.service.accept_file("same.txt", b"first")
        self.service.process(first, b"first")
        second = self.service.accept_file("same.txt", b"second")
        self.service.process(second, b"second")
        self.assertNotEqual(first["raw_path"], second["raw_path"])
        self.assertEqual((self.raw / first["raw_path"]).read_bytes(), b"first")
        self.assertEqual((self.raw / second["raw_path"]).read_bytes(), b"second")
        self.assertNotEqual(first["review_path"], second["review_path"])
        self.assertEqual(len(list(self.review.glob("*.md"))), 2)

    def test_interrupted_processing_is_recovered_from_persisted_state(self):
        item = self.service.accept_file("restart.txt", b"recover me")
        self.service.mark_scheduled(item)
        recovered_service = CaptureService(self.raw, self.review, self.state)
        recovered = recovered_service.get(item["capture_id"])
        self.assertEqual(recovered["status"], "partial_success")
        self.assertEqual(recovered["error"]["code"], "processing_interrupted")
        retried = recovered_service.retry(item["capture_id"])
        self.assertEqual(retried["status"], "completed")
        self.assertEqual((self.raw / item["raw_path"]).read_bytes(), b"recover me")

    def test_image_audio_preserve_raw_and_report_missing_real_processor(self):
        for name, data in (("photo.png", b"\x89PNG\r\n\x1a\nimage"), ("voice.wav", b"RIFFxxxxWAVEdata")):
            item = self.service.accept_file(name, data)
            self.service.process(item, data)
            result = self.service.get(item["capture_id"])
            self.assertEqual(result["status"], "partial_success")
            self.assertEqual(result["error"]["code"], "processor_unavailable")
            self.assertEqual(result["display_filename"], name)
            self.assertEqual((self.raw / result["raw_path"]).read_bytes(), data)
            self.assertIsNone(result["review_path"])

    def test_pdf_extraction_failure_keeps_raw_and_can_be_retried(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buffer = io.BytesIO()
        writer.write(buffer)
        data = buffer.getvalue()
        item = self.service.accept_file("scan.pdf", data)
        self.service.process(item, data)
        partial = self.service.get(item["capture_id"])
        self.assertEqual(partial["status"], "partial_success")
        self.assertEqual((self.raw / partial["raw_path"]).read_bytes(), data)
        self.assertIsNone(partial["review_path"])
        retried = self.service.retry(item["capture_id"])
        self.assertEqual(retried["status"], "partial_success")
        self.assertEqual((self.raw / partial["raw_path"]).read_bytes(), data)

    def test_pdf_text_is_extracted_without_replacing_original(self):
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"]
        stream = b"BT /F1 12 Tf 72 720 Td (hello PDF capture) Tj ET"
        objects += [b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
                    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        data = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
        xref = len(data)
        data.extend(b"xref\n0 6\n0000000000 65535 f \n")
        for offset in offsets[1:]:
            data.extend(f"{offset:010d} 00000 n \n".encode())
        data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
        original = bytes(data)
        item = self.service.accept_file("readable.pdf", original)
        self.service.process(item, original)
        complete = self.service.get(item["capture_id"])
        self.assertEqual(complete["status"], "completed")
        self.assertEqual((self.raw / complete["raw_path"]).read_bytes(), original)
        self.assertIn("hello PDF capture", (self.review / complete["review_path"]).read_text())

    def test_pdf_metadata_title_does_not_replace_unicode_upload_filename(self):
        class Page:
            def extract_text(self):
                return "Readable PDF body"
        class Metadata:
            title = "(anonymous)"
        class Reader:
            is_encrypted = False
            pages = [Page()]
            metadata = Metadata()

        data = b"%PDF-1.4\nfixture"
        with patch("secondbrain_core.modules.capture.PdfReader", return_value=Reader()):
            item = self.service.accept_file("C:\\fakepath\\会议纪要.pdf", data)
            self.service.process(item, data)
        complete = self.service.get(item["capture_id"])
        self.assertEqual(complete["display_filename"], "会议纪要.pdf")
        self.assertEqual(complete["document_title"], "(anonymous)")
        self.assertNotEqual(complete["title"], "(anonymous)")
        self.assertEqual((self.raw / complete["raw_path"]).read_bytes(), data)
        self.assertEqual(complete["raw_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(complete["status"], "completed")

    def test_display_filename_is_bounded_and_removes_controls_without_affecting_raw_name(self):
        supplied = "../../\u0000" + ("计划" * 150) + ".txt"
        item = self.service.accept_file(supplied, b"text")
        display = item["display_filename"]
        self.assertEqual(len(display), 255)
        self.assertNotIn("\x00", display)
        self.assertTrue(display.endswith(".txt"))
        self.assertEqual(Path(item["raw_path"]).name, item["raw_path"])
        self.assertNotIn("计划", item["raw_path"])

    def test_url_capture_stores_url_time_body_and_html_extraction(self):
        with patch("secondbrain_core.modules.capture._public_http_url", return_value=urlsplit("https://capture.example/page")), \
             patch("secondbrain_core.modules.capture._fetch_url", return_value=("https://capture.example/page", "<html><title>Real title</title><script>ignored</script><p>Readable body</p></html>", "text/html")):
            item = self.service.accept_url("https://capture.example/page")
            self.service.process(item, (self.raw / item["raw_path"]).read_bytes())
        complete = self.service.get(item["capture_id"])
        raw_bytes = (self.raw / complete["raw_path"]).read_bytes()
        raw = raw_bytes.decode()
        review = (self.review / complete["review_path"]).read_text()
        self.assertIn("Original URL: https://capture.example/page", raw)
        self.assertIn("Captured at:", raw)
        self.assertEqual(hashlib.sha256(raw_bytes).hexdigest(), item["raw_sha256"])
        self.assertNotIn("Readable body", raw)
        self.assertIn("Readable body", review)
        self.assertNotIn("ignored", review)

    def test_url_extraction_failure_preserves_initial_raw_hash(self):
        url = "https://capture.example/empty"
        with patch("secondbrain_core.modules.capture._public_http_url", return_value=urlsplit(url)), \
             patch("secondbrain_core.modules.capture._fetch_url", return_value=(url, "<html><script>only script</script></html>", "text/html")):
            item = self.service.accept_url(url)
            raw_path = self.raw / item["raw_path"]
            initial_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            self.service.process(item, raw_path.read_bytes())
        result = self.service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), initial_hash)
        self.assertEqual(result["raw_sha256"], initial_hash)
        self.assertIsNone(result["review_path"])

    def test_url_retry_uses_saved_original_url_and_preserves_raw_hash(self):
        url = "https://capture.example/retry"
        page = "<html><title>Retry page</title><p>Still processable</p></html>"
        with patch("secondbrain_core.modules.capture._public_http_url", return_value=urlsplit(url)), \
             patch("secondbrain_core.modules.capture._fetch_url", return_value=(url, page, "text/html")):
            item = self.service.accept_url(url)
            raw_path = self.raw / item["raw_path"]
            initial_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            with patch.object(self.service, "_write_review", side_effect=OSError("Review unavailable")):
                self.service.process(item, raw_path.read_bytes())
        partial = self.service.get(item["capture_id"])
        self.assertEqual(partial["status"], "partial_success")
        self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), initial_hash)
        self.assertEqual(partial["raw_sha256"], initial_hash)
        with patch("secondbrain_core.modules.capture._fetch_url", return_value=(url, page, "text/html")):
            retried = self.service.retry(item["capture_id"])
        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["source_url"], url)
        self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), initial_hash)
        self.assertEqual(retried["raw_sha256"], initial_hash)

    def test_fetch_uses_pinned_address_and_revalidates_redirect_without_external_network(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1/metadata")
                    self.end_headers()
                    return
                body = b"<html><title>fixture</title><p>page text</p></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://capture.example:{server.server_port}/page"
            with patch("secondbrain_core.modules.capture._resolve_public_url", return_value=(urlsplit(url), "127.0.0.1")):
                final, body, content_type = _fetch_url(url)
            self.assertEqual(final, url)
            self.assertIn("page text", body)
            self.assertIn("text/html", content_type)

            redirect_url = f"http://capture.example:{server.server_port}/redirect"
            def resolve_each(value):
                if value == redirect_url:
                    return urlsplit(value), "127.0.0.1"
                return _resolve_public_url(value)
            with patch("secondbrain_core.modules.capture._resolve_public_url", side_effect=resolve_each):
                with self.assertRaises(ValueError):
                    _fetch_url(redirect_url)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ssrf_validation_rejects_local_addresses_and_non_http_schemes(self):
        for value in ("http://127.0.0.1/", "http://10.0.0.1/", "http://localhost/", "file:///etc/passwd", "http://router.local/"):
            with self.assertRaises(ValueError, msg=value):
                _public_http_url(value)

    def test_path_traversal_filename_is_reduced_to_safe_basename(self):
        item = self.service.accept_file("../../escape.txt", b"safe")
        self.assertEqual(Path(item["raw_path"]).name, item["raw_path"])
        self.assertFalse((self.root / "escape.txt").exists())


class CaptureApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.raw, self.review, self.knowledge, self.state = [self.root / name for name in ("raw", "review", "knowledge", "state")]
        for path in (self.raw, self.review, self.knowledge, self.state):
            path.mkdir(mode=0o700)
        self.password = self.root / "password"
        self.password.write_text("capture-api-test-password", encoding="utf-8")
        self.password.chmod(0o600)
        self.env = {"SB_REVIEW_ROOT": str(self.review), "SB_CAPTURE_RAW_ROOT": str(self.raw),
                    "SB_KNOWLEDGE_ROOT": str(self.knowledge), "SB_PROMOTE_STATE_ROOT": str(self.state),
                    "SB_DASHBOARD_ORIGINS": "https://testserver", "SB_CORE_ALLOWED_HOSTS": "testserver",
                    "SB_APP_PASSWORD_FILE": str(self.password), "SB_HERMES_API_URL": "",
                    "SB_HERMES_API_KEY": "", "SB_PROMOTE_ENABLED": "false"}
        with patch.dict(os.environ, self.env):
            self.app = create_app()
        self.client = TestClient(self.app, base_url="https://testserver")

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def login(self):
        return self.client.post("/api/auth/login", json={"password": "capture-api-test-password"},
                                headers={"Origin": "https://testserver"})

    def test_auth_required_and_capture_writes_only_raw_and_review(self):
        unauth = self.client.post("/api/capture/text", json={"text": "secret"}, headers={"Origin": "https://testserver"})
        self.assertEqual(unauth.status_code, 401)
        self.login()
        response = self.client.post("/api/capture/text", json={"text": "web intake"}, headers={"Origin": "https://testserver"})
        self.assertEqual(response.status_code, 202, response.text)
        item = self.client.get("/api/capture/" + response.json()["capture_id"]).json()
        self.assertEqual(item["status"], "completed")
        self.assertEqual(len(list(self.raw.iterdir())), 1)
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertEqual(self.client.get("/api/inbox").json()["status"], "real")
        review_items = self.client.get("/api/promote/review/items").json()["items"]
        self.assertTrue(any(row["review_path"] == item["review_path"] for row in review_items))
        review_items = self.client.get("/api/promote/review/items").json()["items"]
        self.assertTrue(any(row["review_path"] == item["review_path"] for row in review_items))
        raw = self.client.get("/api/inbox/" + item["capture_id"] + "/raw")
        self.assertEqual(raw.content, b"web intake")

    def test_preview_requires_session_uses_safe_mime_and_keeps_download_separate(self):
        unauth = self.client.get("/api/inbox/" + ("0" * 32) + "/preview")
        self.assertEqual(unauth.status_code, 401)
        self.login()
        accepted = self.client.post("/api/capture/files", files={"file": ("guide.md", b"# Plain text\n<script>not executable</script>", "text/markdown")}, headers={"Origin": "https://testserver"})
        item = accepted.json()
        preview = self.client.get(f"/api/inbox/{item['capture_id']}/preview")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(preview.headers["x-content-type-options"], "nosniff")
        self.assertIn("inline", preview.headers["content-disposition"])
        self.assertEqual(preview.content, b"# Plain text\n<script>not executable</script>")
        download = self.client.get(f"/api/inbox/{item['capture_id']}/raw")
        self.assertEqual(download.headers["content-type"], "application/octet-stream")
        self.assertIn("attachment", download.headers["content-disposition"])

    def test_preview_mime_allowlist_and_unsafe_paths(self):
        self.login()
        response = self.client.post("/api/capture/files", files={"file": ("pixel.png", b"\x89PNG\r\n\x1a\npixel", "image/png")}, headers={"Origin": "https://testserver"})
        image = response.json()
        image_preview = self.client.get(f"/api/inbox/{image['capture_id']}/preview")
        self.assertEqual(image_preview.status_code, 200)
        self.assertEqual(image_preview.headers["content-type"], "image/png")
        self.assertEqual(image_preview.headers["x-content-type-options"], "nosniff")
        state_path = next(self.state.glob(f"**/{image['capture_id']}.json"))
        import json
        state = json.loads(state_path.read_text())
        state["raw_path"] = "../secret.txt"
        state_path.write_text(json.dumps(state))
        unsafe = self.client.get(f"/api/inbox/{image['capture_id']}/preview")
        self.assertEqual(unsafe.status_code, 404)

    def test_multipart_file_capture_signature_and_size_checks(self):
        self.login()
        headers = {"Origin": "https://testserver"}
        accepted = self.client.post("/api/capture/files", files={"file": ("note.txt", b"from file", "text/plain")}, headers=headers)
        self.assertEqual(accepted.status_code, 202, accepted.text)
        rejected = self.client.post("/api/capture/files", files={"file": ("fake.pdf", b"not pdf", "application/pdf")}, headers=headers)
        self.assertEqual(rejected.status_code, 400)
        unsupported = self.client.post("/api/capture/files", files={"file": ("thing.exe", b"x", "application/octet-stream")}, headers=headers)
        self.assertEqual(unsupported.status_code, 400)


if __name__ == "__main__":
    unittest.main()
