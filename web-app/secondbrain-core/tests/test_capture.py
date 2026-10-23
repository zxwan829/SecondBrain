import io
import hashlib
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from secondbrain_core.app import create_app
from secondbrain_core.modules.capture import (CaptureService, create_capture_router, _public_http_url,
                                              _resolve_public_url, _fetch_url, _TextExtractor,
                                              MAX_WEB_EXTRACT_CHARS, MAX_WEB_EXTRACT_PARTS)
from secondbrain_core.modules.multimodal_capture import MultimodalCaptureProcessors


class CaptureServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.raw = self.root / "raw"
        self.review = self.root / "review"
        self.state = self.root / "state"
        for path in (self.raw, self.review, self.state):
            path.mkdir(mode=0o700)
        self.service = CaptureService(self.raw, self.review, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def _write_state_fixture(self, capture_id, payload=b'{"capture_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'):
        path = self.service.state_root / f"{capture_id}.json"
        path.write_bytes(payload)
        os.chmod(path, 0o600)
        return path

    def test_state_reader_rejects_symlink_hardlink_unsafe_mode_and_oversize(self):
        capture_id = "a" * 32
        path = self._write_state_fixture(capture_id)
        self.assertEqual(self.service._read_state(path)["capture_id"], capture_id)

        path.unlink()
        outside = self.root / "outside.json"
        outside.write_text('{"capture_id":"' + capture_id + '"}', encoding="utf-8")
        os.chmod(outside, 0o600)
        path.symlink_to(outside)
        self.assertIsNone(self.service._read_state(path))

        path.unlink()
        path = self._write_state_fixture(capture_id)
        hardlink = self.root / "state-hardlink.json"
        os.link(path, hardlink)
        self.assertIsNone(self.service._read_state(path))
        hardlink.unlink()

        os.chmod(path, 0o640)
        self.assertIsNone(self.service._read_state(path))
        path.unlink()
        path = self._write_state_fixture(capture_id, b" " * (1024 * 1024 + 1))
        self.assertIsNone(self.service._read_state(path))

    def test_state_reader_rejects_non_regular_and_replaced_state_roots(self):
        capture_id = "b" * 32
        fifo = self.service.state_root / f"{capture_id}.json"
        os.mkfifo(fifo, 0o600)
        self.assertIsNone(self.service._read_state(fifo))
        fifo.unlink()

        path = self._write_state_fixture(capture_id,
                                         ('{"capture_id":"' + capture_id + '"}').encode())
        state_bytes = path.read_bytes()
        original_root = self.service.state_root
        displaced_root = self.root / "captures-original"
        original_root.rename(displaced_root)
        original_root.mkdir(mode=0o700)
        os.chmod(original_root, 0o700)
        (original_root / path.name).write_bytes(state_bytes)
        os.chmod(original_root / path.name, 0o600)
        self.assertIsNone(self.service._read_state(original_root / path.name))

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

    def test_approved_review_execution_replays_after_service_restart_without_duplicate_files(self):
        text = "# Exact preview\n\nBody with preserved trailing whitespace. \n"
        kwargs = {"text": text, "title": "Approved synthetic Review", "execution_key": "c2c-" + "a" * 32,
                  "proposal_id": "a" * 32, "source_ref": "drafts/synthetic.md",
                  "source_version_sha256": hashlib.sha256(b"synthetic source").hexdigest(),
                  "captured_at": "2026-10-18T00:00:00+00:00"}
        first = self.service.create_approved_review(**kwargs)
        restarted = CaptureService(self.raw, self.review, self.state)
        replay = restarted.create_approved_review(**kwargs)
        self.assertEqual(first["capture_id"], replay["capture_id"])
        self.assertEqual(first["review_path"], replay["review_path"])
        self.assertEqual(first["review_sha256"], replay["review_sha256"])
        self.assertEqual((self.review / replay["review_path"]).read_text(encoding="utf-8").endswith(text), True)
        self.assertEqual(len(list(self.raw.glob("Inbox-Proposal-*.md"))), 1)
        self.assertEqual(len(list(self.review.glob("Inbox-Proposal-*.md"))), 1)

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

    def test_summary_is_a_pure_allowlisted_projection_and_does_not_recover_processing(self):
        item = self.service.accept_text("SYNTHETIC PRIVATE BODY MUST NOT APPEAR")
        state_path = self.state / "captures" / f"{item['capture_id']}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"capture_context": "SYNTHETIC CONTEXT MUST NOT APPEAR",
                      "source_url": "https://private.invalid/synthetic",
                      "error": {"code": "untrusted-sensitive-code", "message": "SECRET BODY"},
                      "review_path": "review/synthetic.md"})
        state_path.write_text(json.dumps(state), encoding="utf-8")
        before_hash = hashlib.sha256(state_path.read_bytes()).hexdigest()
        before_mtime = state_path.stat().st_mtime_ns

        summary = self.service.list_summary()

        self.assertEqual(len(summary), 1)
        self.assertEqual(set(summary[0]), {"capture_id", "source_type", "input_type", "captured_at",
                                           "display_filename", "status", "error_code", "has_review"})
        self.assertEqual(summary[0]["capture_id"], item["capture_id"])
        self.assertEqual(summary[0]["status"], "processing")
        self.assertIsNone(summary[0]["error_code"])
        self.assertTrue(summary[0]["has_review"])
        self.assertNotIn("SYNTHETIC", json.dumps(summary))
        self.assertNotIn("SECRET", json.dumps(summary))
        self.assertEqual(hashlib.sha256(state_path.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(state_path.stat().st_mtime_ns, before_mtime)

    def test_summary_skips_corrupt_state_without_exposing_parse_error(self):
        (self.state / "captures" / ("f" * 32 + ".json")).write_text("not json", encoding="utf-8")
        self.assertEqual(self.service.list_summary(), [])

    def test_summary_preserves_supported_pdf_and_capture_context_source_types(self):
        pdf = self.service.accept_file("synthetic.pdf", b"%PDF-1.4\nsynthetic", source_type=None)
        context = self.service.accept_text("synthetic context", source_type="capture_context")

        summaries = {item["capture_id"]: item for item in self.service.list_summary()}

        self.assertEqual(summaries[pdf["capture_id"]]["source_type"], "pdf")
        self.assertEqual(summaries[pdf["capture_id"]]["input_type"], "pdf")
        self.assertEqual(summaries[context["capture_id"]]["source_type"], "capture_context")
        self.assertEqual(set(summaries[pdf["capture_id"]]), {"capture_id", "source_type", "input_type", "captured_at",
                                                               "display_filename", "status", "error_code", "has_review"})

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
            def extract_text(self, *, visitor_text):
                visitor_text("Readable PDF body", None, None, None, None)
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

    def test_url_html_extraction_is_bounded_and_reports_partial_with_raw_preserved(self):
        url = "https://capture.example/large-html"
        page = "<html><title>" + ("T" * 5000) + "</title><p>" + \
               ("Readable " * (MAX_WEB_EXTRACT_CHARS // 5 + 200)) + "</p></html>"
        with patch("secondbrain_core.modules.capture._public_http_url", return_value=urlsplit(url)), \
             patch("secondbrain_core.modules.capture._fetch_url",
                   return_value=(url, page, "text/html; charset=utf-8")):
            item = self.service.accept_url(url)
            raw_path = self.raw / item["raw_path"]
            original_raw = raw_path.read_bytes()
            original_sha = hashlib.sha256(original_raw).hexdigest()
            self.service.process(item, original_raw)
        result = self.service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), original_sha)
        review = (self.review / result["review_path"]).read_text(encoding="utf-8")
        self.assertIn("[Content truncated at the safe extraction limit.]", review)
        self.assertIn("original URL was retained", result["error"]["message"])

    def test_url_text_plain_truncation_is_not_reported_as_complete(self):
        url = "https://capture.example/large-text"
        text = "x" * (MAX_WEB_EXTRACT_CHARS + 17)
        with patch("secondbrain_core.modules.capture._public_http_url", return_value=urlsplit(url)), \
             patch("secondbrain_core.modules.capture._fetch_url",
                   return_value=(url, text, "text/plain; charset=utf-8")):
            item = self.service.accept_url(url)
            self.service.process(item, (self.raw / item["raw_path"]).read_bytes())
        result = self.service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        review = (self.review / result["review_path"]).read_text(encoding="utf-8")
        self.assertIn("[Content truncated at the safe extraction limit.]", review)

    def test_html_extractor_bounds_many_tiny_nodes_and_title(self):
        parser = _TextExtractor()
        parser.feed("<html><title>" + ("T" * 5000) + "</title>" + "<p>x</p>" * 25_000 + "</html>")
        parser.close()
        self.assertTrue(parser.truncated)
        self.assertLessEqual(len(parser.parts), MAX_WEB_EXTRACT_PARTS)
        self.assertLessEqual(parser.part_chars, MAX_WEB_EXTRACT_CHARS)
        self.assertLessEqual(parser.title_chars, 300)

    def test_animated_image_is_explicitly_partial_and_preserves_raw_without_review(self):
        frame_one = Image.new("RGB", (12, 12), "white")
        frame_two = Image.new("RGB", (12, 12), "black")
        image = io.BytesIO()
        frame_one.save(image, format="GIF", save_all=True, append_images=[frame_two], duration=100, loop=0)
        original = image.getvalue()
        service = CaptureService(self.raw, self.review, self.state,
                                 processors=MultimodalCaptureProcessors(tesseract="synthetic-tesseract"))
        item = service.accept_file("animated.gif", original)
        service.process(item, original)
        result = service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        self.assertIn("Animated image OCR is unsupported", result["error"]["message"])
        self.assertIsNone(result["review_path"])
        self.assertEqual((self.raw / result["raw_path"]).read_bytes(), original)

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
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
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

    def test_summary_requires_existing_inbox_permission_and_valid_limit(self):
        self.assertEqual(self.client.get("/api/inbox/summary").status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/api/inbox/summary?limit=0").status_code, 400)
        self.assertEqual(self.client.get("/api/inbox/summary?limit=201").status_code, 400)
        self.assertEqual(self.client.get("/api/inbox/summary?limit=invalid").status_code, 422)
        self.assertEqual(self.client.get("/api/inbox/summary?limit=1").status_code, 200)
        self.assertEqual(self.client.get("/api/inbox/summary?limit=200").status_code, 200)

    def test_summary_requires_the_existing_inbox_read_action(self):
        class DenyAuth:
            def __init__(self):
                self.actions = []

            def require_action(self, request, action):
                self.actions.append(action)
                raise HTTPException(403, "forbidden")

        deny_auth = DenyAuth()
        app = FastAPI()
        app.include_router(create_capture_router(deny_auth, CaptureService(self.raw, self.review, self.state)))
        client = TestClient(app, base_url="https://testserver")
        try:
            response = client.get("/api/inbox/summary")
        finally:
            client.close()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(deny_auth.actions, ["inbox.read"])

    def test_summary_api_returns_fixed_projection_without_recovering_state(self):
        self.login()
        capture_id = "a" * 32
        state_path = self.state / "captures" / f"{capture_id}.json"
        state_path.parent.mkdir(mode=0o700, exist_ok=True)
        state_path.write_text(json.dumps({
            "capture_id": capture_id, "source_type": "text", "input_type": "text",
            "captured_at": "2026-10-18T00:00:00Z", "display_filename": "synthetic.txt",
            "status": "processing", "content_preview": "SYNTHETIC BODY",
            "capture_context": "SYNTHETIC CONTEXT", "source_url": "https://private.invalid",
            "raw_path": "private.txt", "review_path": "review.md",
            "error": {"code": "attacker-controlled", "message": "SECRET MESSAGE"},
        }), encoding="utf-8")
        os.chmod(state_path, 0o600)
        before_hash = hashlib.sha256(state_path.read_bytes()).hexdigest()
        before_mtime = state_path.stat().st_mtime_ns

        response = self.client.get("/api/inbox/summary?limit=100")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "real")
        self.assertEqual(len(payload["items"]), 1)
        summary = payload["items"][0]
        self.assertEqual(set(summary), {"capture_id", "source_type", "input_type", "captured_at",
                                        "display_filename", "status", "error_code", "has_review"})
        self.assertEqual(summary["capture_id"], capture_id)
        self.assertEqual(summary["status"], "processing")
        self.assertIsNone(summary["error_code"])
        self.assertTrue(summary["has_review"])
        self.assertNotIn("SYNTHETIC", response.text)
        self.assertNotIn("SECRET", response.text)
        self.assertEqual(hashlib.sha256(state_path.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(state_path.stat().st_mtime_ns, before_mtime)

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
