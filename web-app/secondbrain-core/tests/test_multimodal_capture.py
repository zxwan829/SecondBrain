import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.hermes_api import HermesAPI
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
        self.assertEqual(done["status"], "completed")
        self.assertEqual(processors.pdf_calls, 1)
        self.assertEqual(done["processor"]["kind"], "pdf_ocr")
        self.assertIn("扫描件识别正文", (self.review / done["review_path"]).read_text())
        self.assertEqual(hashlib.sha256((self.raw / item["raw_path"]).read_bytes()).hexdigest(), original_hash)

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

    def test_pdf_ocr_page_limit_fails_without_creating_review(self):
        processors = MultimodalCaptureProcessors(tesseract="/usr/bin/tesseract",
                                                 pdftoppm="/usr/bin/pdftoppm")
        service = CaptureService(self.raw, self.review, self.state, processors)
        with patch("secondbrain_core.modules.capture.PdfReader") as reader_factory:
            reader = Mock(is_encrypted=False, pages=[Mock(extract_text=lambda: "")] * 11, metadata=None)
            reader_factory.return_value = reader
            # A syntactically valid PDF Raw is sufficient for the patched reader.
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
            return httpx.Response(200, json={"ok": True, "transcript": " 转写结果 ", "provider": "local"})
        api = HermesAPI("http://hermes.internal", "server-only-test-key", httpx.MockTransport(respond))
        result = api.transcribe_audio(b"RIFF-audio", "audio/wav")
        self.assertEqual(result, {"transcript": "转写结果", "provider": "local"})
        self.assertEqual(seen["path"], "/api/audio/transcribe")
        self.assertEqual(seen["auth"], "Bearer server-only-test-key")
        self.assertIn("data:audio/wav;base64,", seen["payload"])

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
