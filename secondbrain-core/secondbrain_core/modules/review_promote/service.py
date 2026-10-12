"""Orchestrate trusted Review approval and the filesystem Promote worker."""
from .approval import ApprovalFileStore, FileApprovalSource
from .worker import PromoteWorker


class PromoteService:
    """File-backed approval/audit service running inside SecondBrain Core.

    ``approval_dir`` is private Core state, not an Agent-writable queue. The
    API must pass a verified Hermes Dashboard request context; the worker reads
    only server-created records and writes only under the configured Knowledge
    root. Production filesystem isolation remains a deployment gate.
    """

    def __init__(self, review_root, knowledge_root, approval_dir, audit_path):
        self.approval_dir = approval_dir
        self.approvals = ApprovalFileStore(approval_dir)
        self.worker = PromoteWorker(
            review_root, knowledge_root, audit_path,
            FileApprovalSource(approval_dir),
        )

    def approve_and_promote(self, request, body, review_root=None):
        """Persist a session-bound approval, then promote that pinned version."""
        if review_root is None:
            review_root = self.worker.review_root
        accepted = self.approvals.approve(request, body, str(review_root))
        result = self.worker.promote(
            body.get("request_id"), body.get("review_path"), body.get("review_sha256")
        )
        return {**accepted, **result}
