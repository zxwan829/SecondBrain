"""One-shot, resource-limited pypdf worker. Input/output are bounded pipe payloads."""

import io
import json
import os
import resource
import sys
from pathlib import Path

MEMORY_LIMIT_BYTES = 384 * 1024 * 1024
CPU_LIMIT_SECONDS = 12
MAX_DECOMPRESSED_STREAM_BYTES = 8 * 1024 * 1024
MAX_DECOMPRESSION_RECOVERY_INPUT_BYTES = 1024 * 1024
MAX_PAGES = 500
MAX_TEXT_CHARS = 1_000_000


def _emit(value):
    sys.stdout.buffer.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _install_limits():
    required = ("RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_NOFILE", "RLIMIT_CORE", "RLIMIT_FSIZE")
    if any(not hasattr(resource, name) for name in required):
        raise RuntimeError("required process resource limit is unavailable")
    caps = {
        resource.RLIMIT_AS: MEMORY_LIMIT_BYTES,
        resource.RLIMIT_CPU: CPU_LIMIT_SECONDS,
        resource.RLIMIT_NOFILE: 32,
        resource.RLIMIT_CORE: 0,
        resource.RLIMIT_FSIZE: 0,
    }
    for limit, cap in caps.items():
        _soft, hard = resource.getrlimit(limit)
        hard_cap = cap if hard == resource.RLIM_INFINITY else min(cap, hard)
        soft_cap = min(cap, hard_cap)
        resource.setrlimit(limit, (soft_cap, hard_cap))


def main():
    try:
        _install_limits()
    except Exception:
        _emit({"status": "resource_limits_unavailable"})
        return 2

    try:
        from pypdf import PdfReader, filters
        # pypdf's default FlateDecode output ceiling (75 MB) is too large for
        # this one-shot worker's memory budget. Set the legacy configuration
        # before constructing PdfReader; pypdf applies it to its per-context
        # Configuration during reader initialization. The dependency is
        # constrained to pypdf < 7, where these compatibility names exist.
        filters.ZLIB_MAX_OUTPUT_LENGTH = MAX_DECOMPRESSED_STREAM_BYTES
        filters.ZLIB_MAX_RECOVERY_INPUT_LENGTH = MAX_DECOMPRESSION_RECOVERY_INPUT_BYTES
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from secondbrain_core.modules.pdf_text_extraction import extract_pdf_text_bounded

        raw = sys.stdin.buffer.read(20 * 1024 * 1024 + 1)
        if len(raw) > 20 * 1024 * 1024:
            _emit({"status": "input_too_large"})
            return 2
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            _emit({"status": "encrypted"})
            return 0
        page_count = len(reader.pages)
        if page_count > MAX_PAGES:
            _emit({"status": "page_limit", "page_count": page_count})
            return 0
        text, truncated = extract_pdf_text_bounded(reader, MAX_TEXT_CHARS)
        page_sizes = []
        if not text:
            for page in reader.pages:
                page_sizes.append([float(page.mediabox.width), float(page.mediabox.height)])
        metadata_title = None
        if reader.metadata and reader.metadata.title:
            metadata_title = str(reader.metadata.title).strip()[:300] or None
        _emit({"status": "ok", "page_count": page_count, "text": text,
               "truncated": truncated, "page_sizes": page_sizes,
               "metadata_title": metadata_title})
        return 0
    except MemoryError:
        _emit({"status": "resource_limit"})
        return 0
    except Exception:
        _emit({"status": "parse_failed"})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
