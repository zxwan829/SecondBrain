"""Small, dependency-free helpers shared by the bounded PDF worker and tests."""


class _PDFTextLimitReached(Exception):
    """Internal control flow used to stop pypdf once the output budget is full."""


def extract_pdf_text_bounded(reader, max_chars=1_000_000):
    """Collect PDF text incrementally and stop parsing when the output budget is exceeded."""
    chunks = []
    collected = 0
    truncated = False

    for page_number, page in enumerate(reader.pages):
        def collect(text, *_context):
            nonlocal collected, truncated
            if not isinstance(text, str):
                raise ValueError("PDF text extractor returned an invalid chunk")
            if not text:
                return
            remaining = max_chars - collected
            if len(text) > remaining:
                if remaining:
                    chunks.append(text[:remaining])
                    collected += remaining
                truncated = True
                raise _PDFTextLimitReached
            chunks.append(text)
            collected += len(text)

        try:
            if page_number:
                collect("\n\n")
            page.extract_text(visitor_text=collect)
        except _PDFTextLimitReached:
            break

    return "".join(chunks).strip(), truncated
