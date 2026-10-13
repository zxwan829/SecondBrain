"""Compatibility entry point; implementation lives in SecondBrain Core."""
from secondbrain_core.modules.review_promote.review_adapter import ReviewFormatError, adapt_review_markdown

__all__ = ["ReviewFormatError", "adapt_review_markdown"]
