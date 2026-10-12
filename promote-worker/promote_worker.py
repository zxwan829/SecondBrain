"""Compatibility entry point; implementation lives in SecondBrain Core."""
from secondbrain_core.modules.review_promote.worker import (
    ApprovalRecord, ApprovalSource, NoApprovalSource, PromotionError, PromoteWorker,
    _open_dir_chain, _validate_relative_review_path,
)

__all__ = ["ApprovalRecord", "ApprovalSource", "NoApprovalSource", "PromotionError", "PromoteWorker"]
