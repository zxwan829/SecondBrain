"""Bounded local OCR and explicitly opted-in Hermes transcription adapters."""
import io
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from mutagen import File as MutagenFile

from .capture import ProcessorUnavailable


MAX_IMAGE_PIXELS = 12_000_000
OCR_TIMEOUT_SECONDS = 20
PDF_OCR_TOTAL_SECONDS = 75
PDF_OCR_MAX_PAGES = 10
PDF_OCR_DPI = 120
MAX_RENDERED_IMAGE_BYTES = 30 * 1024 * 1024
MAX_AUDIO_DURATION_SECONDS = 30 * 60


class MultimodalCaptureProcessors:
    def __init__(self, hermes=None, *, tesseract=None, pdftoppm=None,
                 audio_enabled=None):
        self.hermes = hermes
        self.tesseract = tesseract or shutil.which("tesseract")
        self.pdftoppm = pdftoppm or shutil.which("pdftoppm")
        self._ocr_lock = threading.RLock()
        raw_enabled = os.environ.get("SB_CAPTURE_HERMES_STT_ENABLED", "false")
        self.audio_enabled = (raw_enabled.strip().lower() == "true"
                              if audio_enabled is None else audio_enabled)

    def _ocr_image(self, image_bytes, timeout=OCR_TIMEOUT_SECONDS):
        if not self.tesseract:
            raise ProcessorUnavailable("Chinese/English OCR is unavailable: Tesseract is not installed")
        with self._ocr_lock:
            try:
                with Image.open(io.BytesIO(image_bytes)) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("Image exceeds the 12 megapixel OCR limit")
                    if image.width > 10000 or image.height > 10000:
                        raise ValueError("Image dimensions exceed the OCR limit")
                    image.load()
                    normalized = image.convert("RGB")
                    output = io.BytesIO()
                    normalized.save(output, format="PNG", optimize=False)
                    data = output.getvalue()
            except (UnidentifiedImageError, OSError) as exc:
                raise ValueError("Image could not be decoded for OCR") from exc
            try:
                result = subprocess.run(
                    [self.tesseract, "stdin", "stdout", "-l", "chi_sim+eng", "--psm", "3"],
                    input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise ValueError("Image OCR exceeded its time limit") from exc
        if result.returncode != 0:
            raise ProcessorUnavailable("Tesseract OCR could not run with chi_sim+eng language data")
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError("OCR completed but found no readable text")
        return text[:200_000]

    def ocr_image(self, image_bytes):
        return self._ocr_image(image_bytes)

    def ocr_pdf(self, pdf_bytes, pages, page_sizes=None):
        with self._ocr_lock:
            return self._ocr_pdf(pdf_bytes, pages, page_sizes)

    def _ocr_pdf(self, pdf_bytes, pages, page_sizes=None):
        if not self.pdftoppm:
            raise ProcessorUnavailable("Scanned PDF OCR is unavailable: Poppler is not installed")
        if not self.tesseract:
            raise ProcessorUnavailable("Scanned PDF OCR is unavailable: Tesseract is not installed")
        if pages < 1 or pages > PDF_OCR_MAX_PAGES:
            raise ValueError(f"Scanned PDF OCR is limited to {PDF_OCR_MAX_PAGES} pages")
        if page_sizes is None or len(page_sizes) != pages:
            raise ValueError("Scanned PDF page dimensions could not be verified")
        max_pixels = MAX_IMAGE_PIXELS
        for width_points, height_points in page_sizes:
            width = max(1, int(float(width_points) * PDF_OCR_DPI / 72))
            height = max(1, int(float(height_points) * PDF_OCR_DPI / 72))
            if width > 10000 or height > 10000 or width * height > max_pixels:
                raise ValueError("Scanned PDF page exceeds the 12 megapixel OCR limit")

        started = time.monotonic()
        extracted = []
        with tempfile.TemporaryDirectory(prefix="secondbrain-pdf-ocr-") as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            source.write_bytes(pdf_bytes)
            for page_number in range(1, pages + 1):
                remaining = PDF_OCR_TOTAL_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    raise ValueError("Scanned PDF OCR exceeded the 75 second limit")
                prefix = Path(temp_dir) / f"page-{page_number}"
                try:
                    result = subprocess.run(
                        [self.pdftoppm, "-f", str(page_number), "-l", str(page_number),
                         "-r", str(PDF_OCR_DPI), "-singlefile", "-png", str(source), str(prefix)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=min(15, remaining), check=False)
                except subprocess.TimeoutExpired as exc:
                    raise ValueError("Scanned PDF rendering exceeded its time limit") from exc
                rendered = prefix.with_suffix(".png")
                if result.returncode != 0 or not rendered.is_file():
                    raise ValueError("Scanned PDF page could not be rendered")
                if rendered.stat().st_size > MAX_RENDERED_IMAGE_BYTES:
                    raise ValueError("Rendered PDF page exceeds the 30 MiB limit")
                remaining = PDF_OCR_TOTAL_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    raise ValueError("Scanned PDF OCR exceeded the 75 second limit")
                text = self._ocr_image(rendered.read_bytes(), timeout=min(OCR_TIMEOUT_SECONDS, remaining))
                extracted.append(f"[Page {page_number}]\n{text}")
                if time.monotonic() - started > PDF_OCR_TOTAL_SECONDS:
                    raise ValueError("Scanned PDF OCR exceeded the 75 second limit")
        return "\n\n".join(extracted)

    def transcribe_audio(self, audio_bytes, suffix):
        if not self.audio_enabled:
            raise ProcessorUnavailable("Hermes audio transcription is disabled until its STT provider is authorized")
        if not self.hermes or not self.hermes.configured:
            raise ProcessorUnavailable("Hermes audio transcription is unavailable: server API is not configured")
        mime_types = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4",
                      "aac": "audio/aac", "ogg": "audio/ogg", "flac": "audio/flac"}
        mime_type = mime_types.get(suffix.lower().lstrip("."))
        if not mime_type:
            raise ValueError("Unsupported audio format for transcription")
        if len(audio_bytes) > 20 * 1024 * 1024:
            raise ValueError("Audio exceeds the 20 MiB processing limit")
        try:
            audio = MutagenFile(io.BytesIO(audio_bytes))
            duration = float(audio.info.length) if audio and audio.info else 0
        except Exception as exc:
            raise ValueError("Audio duration could not be verified") from exc
        if duration <= 0 or duration > MAX_AUDIO_DURATION_SECONDS:
            raise ValueError("Audio must be between 0 and 30 minutes")
        result = self.hermes.transcribe_audio(audio_bytes, mime_type, timeout=90)
        return result["transcript"], result.get("provider", "Hermes STT")
