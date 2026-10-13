"""Orchestrate trusted Review approval and the filesystem Promote worker."""
from .approval import ApprovalFileStore, FileApprovalSource, ReviewDecisionStore
from .approval import ApprovalRequestError, _read_review
import hashlib
from .worker import PromoteWorker


class PromoteService:
    """File-backed approval/audit service running inside SecondBrain Core.

    ``approval_dir`` is private Core state, not an Agent-writable queue. The
    API must pass a verified Hermes Dashboard request context; the worker reads
    only server-created records and writes only under the configured Knowledge
    root. Production filesystem isolation remains a deployment gate.
    """

    def __init__(self, review_root, knowledge_root, approval_dir, audit_path, decision_dir=None):
        self.approval_dir = approval_dir
        self.review_root = review_root
        self.approvals = ApprovalFileStore(approval_dir)
        self.decisions = ReviewDecisionStore(decision_dir or approval_dir)
        self.worker = PromoteWorker(
            review_root, knowledge_root, audit_path,
            FileApprovalSource(approval_dir),
        )

    def approve_and_promote_as(self, approver_subject, body, review_root=None):
        """Promote after a trusted Core-local adapter has authenticated the owner."""
        if review_root is None:
            review_root = self.worker.review_root
        review_path, digest = body.get("review_path"), body.get("review_sha256")
        current = self.decisions.get(review_path, digest)
        if current.get("status") == "promoted":
            if current.get("target_filename") != body.get("target_filename"):
                raise ApprovalRequestError("This Review version was already promoted to a different target")
            return self.worker.promote(current.get("request_id"), review_path, digest)
        if current.get("status") in {"approved", "promoting", "failed"} and \
                current.get("request_id") != body.get("request_id"):
            raise ApprovalRequestError("Retry must use the original approved request ID")
        accepted = self.approvals.approve_as(approver_subject, body, str(review_root))
        self.decisions.set(review_path, digest, "approved", request_id=body.get("request_id"),
                           approver_subject=approver_subject)
        self.decisions.set(review_path, digest, "promoting", request_id=body.get("request_id"),
                           approver_subject=approver_subject)
        try:
            result = self.worker.promote(body.get("request_id"), review_path, digest)
        except Exception as exc:
            self.decisions.set(review_path, digest, "failed", request_id=body.get("request_id"),
                               approver_subject=approver_subject, error_code=type(exc).__name__)
            raise
        self.decisions.set(review_path, digest, "promoted", request_id=body.get("request_id"),
                           approver_subject=approver_subject, target_filename=result.get("target_filename"))
        return {**accepted, **result}

    def defer(self, review_path, review_sha256, operator_subject):
        if not isinstance(operator_subject, str) or not operator_subject:
            raise ApprovalRequestError("A verified operator identity is required")
        actual = hashlib.sha256(_read_review(self.worker.review_root, review_path)).hexdigest()
        if actual != review_sha256:
            raise ApprovalRequestError("Review content changed; refresh before deferring")
        current = self.decisions.get(review_path, review_sha256)
        if current.get("status") in {"approved", "promoting", "promoted", "failed"} or \
                self.approvals.has_version(review_path, review_sha256):
            raise ApprovalRequestError("This Review version has an approval or promotion attempt and cannot be deferred")
        return self.decisions.set(review_path, review_sha256, "deferred", decided_by=operator_subject)

    def get_decision(self, review_path, review_sha256):
        actual = hashlib.sha256(_read_review(self.worker.review_root, review_path)).hexdigest()
        if actual != review_sha256:
            raise ApprovalRequestError("Review content changed; refresh before reading its decision")
        return self.decisions.get(review_path, review_sha256)
