import hashlib
import io
import json
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.hermes_api import HermesAPI
from secondbrain_core.modules.pdf_text_worker import MAX_DECOMPRESSED_STREAM_BYTES
from secondbrain_core.modules.multimodal_capture import (
    MAX_IMAGE_PIXELS, PDF_OCR_TARGET_DPI, MultimodalCaptureProcessors, _pdf_page_dpi,
)
from pypdf import PdfWriter
import httpx


class ProcessorStub:
    def __init__(self, image_text="识别到的中文标题", pdf_text="扫描件识别正文",
                 transcript="测试音频中的真实转写内容"):
        self.image_text = image_text
        self.pdf_text = pdf_text
        self.transcript = transcript
        self.pdf_calls = 0

    def ocr_image(self, data):
        return self.image_text

    def ocr_pdf(self, data, pages, page_sizes):
        self.pdf_calls += 1
        return self.pdf_text

    def transcribe_audio(self, data, suffix):
        return self.transcript, "test-local-adapter"


class MultimodalCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.raw, self.review, self.state = (root / name for name in ("raw", "review", "state"))
        for path in (self.raw, self.review, self.state):
            path.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def test_pdf_render_dpi_increases_within_existing_pixel_and_side_limits(self):
        self.assertEqual(_pdf_page_dpi(595, 842), PDF_OCR_TARGET_DPI)
        dpi = _pdf_page_dpi(2000, 3000)
        self.assertLess(dpi, PDF_OCR_TARGET_DPI)
        self.assertLessEqual(int(2000 * dpi / 72), 10000)
        self.assertLessEqual(int(3000 * dpi / 72), 10000)
        self.assertLessEqual(int(2000 * dpi / 72) * int(3000 * dpi / 72), MAX_IMAGE_PIXELS)

    def test_pdf_renderer_receives_adaptive_higher_dpi(self):
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        source = io.BytesIO()
        writer.write(source)
        processors = MultimodalCaptureProcessors(tesseract="tesseract", pdftoppm="pdftoppm")
        commands = []

        def fake_render(command, **_kwargs):
            commands.append(command)
            Path(command[-1] + ".png").write_bytes(b"rendered")
            return Mock(returncode=0)

        with patch("secondbrain_core.modules.multimodal_capture.subprocess.run", side_effect=fake_render):
            with patch.object(processors, "_ocr_image", return_value="recognized text"):
                result = processors.ocr_pdf(source.getvalue(), 1, [(595, 842)])
        self.assertEqual(result, "[Page 1]\nrecognized text")
        dpi_index = commands[0].index("-r") + 1
        self.assertEqual(commands[0][dpi_index], "200")

    def test_scanned_pdf_falls_back_to_ocr_after_empty_pypdf_text_and_preserves_raw(self):
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        pdf = io.BytesIO()
        writer.write(pdf)
        raw = pdf.getvalue()
        processors = ProcessorStub()
        service = CaptureService(self.raw, self.review, self.state, processors)
        item = service.accept_file("扫描件.pdf", raw)
        original_hash = hashlib.sha256((self.raw / item["raw_path"]).read_bytes()).hexdigest()
        service.process(item, raw)
        done = service.get(item["capture_id"])
        if not sys.platform.startswith("linux"):
            self.assertEqual(done["status"], "partial_success")
            self.assertEqual(done["error"]["code"], "processing_failed")
            self.assertIn("resource limits", done["error"]["message"])
            self.assertIsNone(done["review_path"])
            self.assertEqual(hashlib.sha256((self.raw / done["raw_path"]).read_bytes()).hexdigest(), original_hash)
            self.assertEqual(processors.pdf_calls, 0)
            return
        self.assertEqual(done["status"], "completed")
        self.assertEqual(processors.pdf_calls, 1)
        self.assertEqual(done["processor"]["kind"], "pdf_ocr")
        self.assertIn("扫描件识别正文", (self.review / done["review_path"]).read_text())
        self.assertEqual(hashlib.sha256((self.raw / item["raw_path"]).read_bytes()).hexdigest(), original_hash)

    def test_pdf_text_budget_stops_extraction_and_reports_partial_with_raw_preserved(self):
        processors = Mock()
        service = CaptureService(self.raw, self.review, self.state, processors)
        raw = b"%PDF-1.7\nsynthetic bounded extraction fixture"
        item = service.accept_file("large-readable.pdf", raw)
        raw_digest = hashlib.sha256((self.raw / item["raw_path"]).read_bytes()).hexdigest()
        bounded_text = "A" * 600_000 + "\n\n" + "B" * 399_998
        parsed = {"status": "ok", "page_count": 2, "text": bounded_text, "truncated": True,
                  "page_sizes": [], "metadata_title": None}

        with patch("secondbrain_core.modules.capture._extract_pdf_text_in_limited_worker",
                   return_value=parsed) as worker:
            service.process(item, raw)

        result = service.get(item["capture_id"])
        review = (self.review / result["review_path"]).read_text()
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        self.assertIn("text extraction reached the 1,000,000-character limit", result["error"]["message"])
        self.assertIn("The original PDF is retained; extracted text is incomplete.", review)
        self.assertTrue(review.endswith(bounded_text +
                                        "\n\n[PDF text extraction stopped at the 1,000,000-character "
                                        "safety limit. The original PDF is retained; extracted text is incomplete.]\n"))
        worker.assert_called_once_with(raw)
        self.assertEqual(hashlib.sha256((self.raw / result["raw_path"]).read_bytes()).hexdigest(), raw_digest)
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)
        processors.ocr_pdf.assert_not_called()
        first_review_path = result["review_path"]
        first_review_digest = hashlib.sha256(review.encode("utf-8")).hexdigest()
        with patch("secondbrain_core.modules.capture._extract_pdf_text_in_limited_worker",
                   return_value=parsed):
            retried = service.retry(item["capture_id"])
        retry_review = (self.review / retried["review_path"]).read_bytes()
        self.assertEqual(retried["status"], "partial_success")
        self.assertEqual(retried["review_path"], first_review_path)
        self.assertEqual(hashlib.sha256(retry_review).hexdigest(), first_review_digest)
        self.assertEqual(hashlib.sha256((self.raw / retried["raw_path"]).read_bytes()).hexdigest(), raw_digest)
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)

    def test_real_pypdf_visitor_stops_after_crossing_the_text_budget(self):
        writer = PdfWriter()
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        font_ref = writer._add_object(font)
        for text in (b"A" * 600_000, b"B" * 600_000):
            page = writer.add_blank_page(width=300, height=300)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 10 Tf 1 0 0 1 10 10 Tm (" + text + b") Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        pdf = io.BytesIO()
        writer.write(pdf)

        from pypdf import PdfReader
        from secondbrain_core.modules.capture import _extract_pdf_text_bounded
        reader = PdfReader(io.BytesIO(pdf.getvalue()), strict=True)
        extracted, truncated = _extract_pdf_text_bounded(reader)

        self.assertTrue(truncated)
        self.assertEqual(len(extracted), 1_000_000)
        self.assertEqual(extracted[:600_000], "A" * 600_000)
        self.assertEqual(extracted[600_000:], "\n\n" + "B" * 399_998)

    def test_single_compressed_content_stream_cannot_exhaust_pdf_worker_memory(self):
        compressor = zlib.compressobj(level=1)
        compressed_parts = []
        block = b" " * (4 * 1024 * 1024)
        for _ in range(4):
            compressed_parts.append(compressor.compress(block))
        compressed_parts.append(compressor.flush())
        stream = b"".join(compressed_parts)
        font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
                   b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                   b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
                   b"<< /Length " + str(len(stream)).encode() +
                   b" /Filter /FlateDecode >>\nstream\n"
                   + stream + b"\nendstream",
                   font]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
        xref = len(pdf)
        pdf.extend(b"xref\n0 6\n0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode())
        pdf.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
        raw = bytes(pdf)
        self.assertLess(len(raw), 5 * 1024 * 1024)
        self.assertGreater(16 * 1024 * 1024, MAX_DECOMPRESSED_STREAM_BYTES)

        service = CaptureService(self.raw, self.review, self.state, ProcessorStub())
        item = service.accept_file("synthetic-expansion.pdf", raw)
        raw_digest = hashlib.sha256(raw).hexdigest()
        service.process(item, raw)
        result = service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        self.assertIn("resource limits", result["error"]["message"])
        self.assertIsNone(result["review_path"])
        self.assertEqual(hashlib.sha256((self.raw / result["raw_path"]).read_bytes()).hexdigest(), raw_digest)
        self.assertEqual(len(list(self.review.glob("*.md"))), 0)

    def test_image_ocr_review_separates_text_and_ai_description_unavailable(self):
        image = io.BytesIO()
        Image.new("RGB", (32, 32), "white").save(image, format="PNG")
        raw = image.getvalue()
        service = CaptureService(self.raw, self.review, self.state, ProcessorStub())
        item = service.accept_file("photo.png", raw)
        digest = item["raw_sha256"]
        service.process(item, raw)
        result = service.get(item["capture_id"])
        review = (self.review / result["review_path"]).read_text()
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processor_unavailable")
        self.assertIn("## OCR 识别文字", review)
        self.assertIn("识别到的中文标题", review)
        self.assertIn("## AI 画面描述", review)
        self.assertIn("尚未配置", review)
        self.assertEqual(hashlib.sha256((self.raw / result["raw_path"]).read_bytes()).hexdigest(), digest)

    def test_retry_reuses_identical_partial_image_review_without_creating_duplicate(self):
        image = io.BytesIO()
        Image.new("RGB", (32, 32), "white").save(image, format="PNG")
        raw = image.getvalue()
        service = CaptureService(self.raw, self.review, self.state, ProcessorStub())
        item = service.accept_file("retry-photo.png", raw)
        service.process(item, raw)
        first = service.get(item["capture_id"])
        first_review = first["review_path"]
        first_hash = first["review_sha256"]
        self.assertEqual(first["status"], "partial_success")
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)
        retried = service.retry(item["capture_id"])
        self.assertEqual(retried["status"], "partial_success")
        self.assertEqual(retried["review_path"], first_review)
        self.assertEqual(retried["review_sha256"], first_hash)
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)
        self.assertEqual(hashlib.sha256((self.raw / retried["raw_path"]).read_bytes()).hexdigest(), retried["raw_sha256"])

    def test_audio_adapter_creates_transcript_review_and_keeps_original(self):
        raw = b"RIFFxxxxWAVE" + b"voice-sample"
        service = CaptureService(self.raw, self.review, self.state, ProcessorStub())
        item = service.accept_file("voice.wav", raw)
        service.process(item, raw)
        result = service.get(item["capture_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["processor"]["name"], "hermes_stt")
        self.assertIn("测试音频中的真实转写内容", (self.review / result["review_path"]).read_text())
        self.assertEqual((self.raw / result["raw_path"]).read_bytes(), raw)

    def test_audio_response_limit_failure_keeps_raw_and_does_not_create_review(self):
        from fastapi import HTTPException

        processors = Mock()
        processors.transcribe_audio.side_effect = HTTPException(
            status_code=502, detail="Hermes transcription response exceeded the size limit")
        service = CaptureService(self.raw, self.review, self.state, processors)
        raw = b"RIFFxxxxWAVE" + b"synthetic-audio"
        item = service.accept_file("voice.wav", raw)
        original_digest = hashlib.sha256((self.raw / item["raw_path"]).read_bytes()).hexdigest()

        service.process(item, raw)

        result = service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        self.assertEqual(result["error"]["message"], "Hermes transcription response exceeded the size limit")
        self.assertIsNone(result["review_path"])
        self.assertEqual(hashlib.sha256((self.raw / result["raw_path"]).read_bytes()).hexdigest(), original_digest)
        self.assertEqual(len(list(self.review.glob("*.md"))), 0)

    def test_pdf_ocr_page_limit_fails_without_creating_review(self):
        processors = MultimodalCaptureProcessors(tesseract="/usr/bin/tesseract",
                                                 pdftoppm="/usr/bin/pdftoppm")
        service = CaptureService(self.raw, self.review, self.state, processors)
        with patch("secondbrain_core.modules.capture._extract_pdf_text_in_limited_worker",
                   return_value={"status": "page_limit", "page_count": 11}):
            # A syntactically valid Raw is sufficient for the patched worker result.
            item = service.accept_file("large-scan.pdf", b"%PDF-1.7\nfixture")
            service.process(item, b"%PDF-1.7\nfixture")
        result = service.get(item["capture_id"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["error"]["code"], "processing_failed")
        self.assertIsNone(result["review_path"])
        self.assertEqual(len(list(self.raw.iterdir())), 1)

    def test_audio_transcription_is_disabled_by_default_and_does_not_call_hermes(self):
        hermes = Mock(configured=True)
        processors = MultimodalCaptureProcessors(hermes, audio_enabled=False)
        with self.assertRaisesRegex(Exception, "disabled"):
            processors.transcribe_audio(b"audio", "wav")
        hermes.transcribe_audio.assert_not_called()

    def test_audio_duration_over_limit_is_rejected_before_hermes_call(self):
        from secondbrain_core.modules.multimodal_capture import MultimodalCaptureProcessors
        hermes = Mock(configured=True)
        hermes.transcribe_audio.return_value = {"transcript": "should not run", "provider": "test"}
        processors = MultimodalCaptureProcessors(hermes, audio_enabled=True)
        with patch("secondbrain_core.modules.multimodal_capture.MutagenFile",
                   return_value=Mock(info=Mock(length=1801))):
            with self.assertRaisesRegex(ValueError, "30 minutes"):
                processors.transcribe_audio(b"audio-bytes", "wav")
        hermes.transcribe_audio.assert_not_called()

    def test_audio_duration_validation_passes_bounded_sample_to_hermes(self):
        hermes = Mock(configured=True)
        hermes.transcribe_audio.return_value = {"transcript": "识别到的语音", "provider": "local"}
        processors = MultimodalCaptureProcessors(hermes, audio_enabled=True)
        with patch("secondbrain_core.modules.multimodal_capture.MutagenFile",
                   return_value=Mock(info=Mock(length=45.0))):
            transcript, provider = processors.transcribe_audio(b"sample-audio", "wav")
        self.assertEqual((transcript, provider), ("识别到的语音", "local"))
        hermes.transcribe_audio.assert_called_once_with(b"sample-audio", "audio/wav", timeout=90)

    def test_hermes_stt_adapter_uses_fixed_route_bearer_and_normalizes_response(self):
        seen = {}
        def respond(request):
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("authorization")
            seen["payload"] = request.read().decode("utf-8")
            return httpx.Response(200, stream=httpx.ByteStream(json.dumps(
                {"ok": True, "transcript": " 转写结果 ", "provider": "local"}).encode("utf-8")))
        api = HermesAPI("http://hermes.internal", "server-only-test-key", httpx.MockTransport(respond))
        result = api.transcribe_audio(b"RIFF-audio", "audio/wav")
        self.assertEqual(result, {"transcript": "转写结果", "provider": "local"})
        self.assertEqual(seen["path"], "/api/audio/transcribe")
        self.assertEqual(seen["auth"], "Bearer server-only-test-key")
        self.assertIn("data:audio/wav;base64,", seen["payload"])

    def test_hermes_stt_stream_rejects_oversized_response_without_reading_the_rest(self):
        from fastapi import HTTPException
        from secondbrain_core.modules.hermes_api import MAX_AUDIO_TRANSCRIPTION_RESPONSE_BYTES

        class CountingStream(httpx.SyncByteStream):
            def __init__(self):
                self.yielded = 0

            def __iter__(self):
                for _ in range(32):
                    self.yielded += 1
                    yield b"x" * 65_536

            def close(self):
                pass

        stream = CountingStream()
        api = HermesAPI("http://hermes.internal", "synthetic-key",
                        httpx.MockTransport(lambda _request: httpx.Response(200, stream=stream)))
        with self.assertRaises(HTTPException) as raised:
            api.transcribe_audio(b"synthetic audio", "audio/wav")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, "Hermes transcription response exceeded the size limit")
        self.assertEqual(stream.yielded, MAX_AUDIO_TRANSCRIPTION_RESPONSE_BYTES // 65_536 + 1)

    def test_hermes_stt_rejects_transcript_over_character_limit(self):
        from fastapi import HTTPException
        from secondbrain_core.modules.hermes_api import MAX_AUDIO_TRANSCRIPT_CHARS

        response = httpx.Response(200, stream=httpx.ByteStream(json.dumps(
            {"ok": True, "transcript": "x" * (MAX_AUDIO_TRANSCRIPT_CHARS + 1),
             "provider": "synthetic"}).encode("utf-8")))
        api = HermesAPI("http://hermes.internal", "synthetic-key",
                        httpx.MockTransport(lambda _request: response))
        with self.assertRaises(HTTPException) as raised:
            api.transcribe_audio(b"synthetic audio", "audio/wav")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, "Hermes transcription exceeded the text limit")

    def test_hermes_stt_rejects_compressed_response_before_decoding(self):
        from fastapi import HTTPException

        response = httpx.Response(200, stream=httpx.ByteStream(b"compressed-synthetic-body"),
                                  headers={"Content-Encoding": "gzip"})
        api = HermesAPI("http://hermes.internal", "synthetic-key",
                        httpx.MockTransport(lambda _request: response))
        with self.assertRaises(HTTPException) as raised:
            api.transcribe_audio(b"synthetic audio", "audio/wav")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, "Hermes transcription returned an unsupported encoding")

    def test_image_ocr_applies_chinese_language_and_timeout(self):
        image = io.BytesIO()
        Image.new("RGB", (24, 24), "white").save(image, format="PNG")
        completed = Mock(returncode=0, stdout="中文识别".encode(), stderr=b"")
        with patch("secondbrain_core.modules.multimodal_capture.subprocess.run", return_value=completed) as run:
            processors = MultimodalCaptureProcessors(tesseract="/usr/bin/tesseract", audio_enabled=False)
            self.assertEqual(processors.ocr_image(image.getvalue()), "中文识别")
        self.assertIn("chi_sim+eng", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"], 20)


if __name__ == "__main__":
    unittest.main()
