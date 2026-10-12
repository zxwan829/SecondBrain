"""Compatibility entry point; implementation lives in SecondBrain Core."""
from secondbrain_core.modules.review_promote.approval import (
    ApprovalFileStore, ApprovalRequestError, DashboardAuthorizationError,
    FileApprovalSource, _read_review, require_dashboard_operator,
)

__all__ = ["ApprovalFileStore", "ApprovalRequestError", "DashboardAuthorizationError", "FileApprovalSource"]
