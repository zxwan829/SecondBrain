"""Orchestrate version-locked Review approval and filesystem Promote work."""
import hashlib

from .approval import ApprovalFileStore, FileApprovalSource, ReviewDecisionStore
from .approval import ApprovalRequestError, _read_review
from .worker import PromoteWorker


class PromoteService:
    """File-backed service using private Core state for durable decisions/claims."""

    def __init__(self, review_root, knowledge_root, approval_dir, audit_path, decision_dir=None):
        self.approval_dir = approval_dir
        self.review_root = review_root
        self.approvals = ApprovalFileStore(approval_dir)
        self.decisions = ReviewDecisionStore(decision_dir or approval_dir)
        self.worker = PromoteWorker(
            review_root, knowledge_root, audit_path,
            FileApprovalSource(approval_dir),
        )

    @staticmethod
    def _claim_matches(claim, request_id, target_filename, approver_subject, review_path, digest):
        return all((
            claim.get("request_id") == request_id,
            claim.get("target_filename") == target_filename,
            claim.get("approver_subject") == approver_subject,
            claim.get("review_path") == review_path,
            claim.get("review_sha256") == digest,
        ))

    def approve_and_promote_as(self, approver_subject, body, review_root=None,
                               approved_at=None, operation_callback=None):
        """Bind one request and target to a Review version, then recover idempotently."""
        if review_root is None:
            review_root = self.worker.review_root
        review_path = self.decisions.canonical_review_path(body.get("review_path"))
        digest = body.get("review_sha256")
        request_id = body.get("request_id")
        target_filename = body.get("target_filename")

        try:
            # Global lock order is version -> request ID -> worker audit.
            with self.decisions.lock_version(review_path, digest):
                with self.decisions.lock_request_id(request_id):
                    return self._approve_under_locks(
                        approver_subject, body, str(review_root), review_path,
                        digest, request_id, target_filename, approved_at, operation_callback,
                    )
        except ApprovalRequestError:
            raise
        except Exception as exc:
            # Keep filesystem paths and low-level details out of the HTTP boundary.
            raise ApprovalRequestError(
                "Promotion operation requires recovery; retry only with the same request ID",
            ) from exc

    def _approve_under_locks(self, approver_subject, body, review_root, review_path,
                             digest, request_id, target_filename, approved_at=None,
                             operation_callback=None):
        actual = hashlib.sha256(_read_review(review_root, review_path)).hexdigest()
        if actual != digest:
            raise ApprovalRequestError("Review content changed; refresh before approving")

        current = self.decisions.get(review_path, digest)
        claim = self.decisions.read_claim(review_path, digest)
        if claim is None:
            if current.get("status") in {"approved", "promoting", "promoted", "failed"}:
                raise ApprovalRequestError("Review version state has no durable claim; recovery required")
            if self.approvals.records_for_version(review_path, digest):
                raise ApprovalRequestError("Review version has an orphan approval; recovery required")
            if self.decisions.claims_for_request_id(request_id):
                raise ApprovalRequestError("Request ID is already bound to another Review version; recovery required")
            if self.approvals.read(request_id) is not None:
                raise ApprovalRequestError("Request ID is already bound; recovery required")
            claim = self.decisions.create_claim(
                review_path, digest, request_id, target_filename, approver_subject,
                approved_at=approved_at,
            )
        elif not self._claim_matches(
            claim, request_id, target_filename, approver_subject, review_path, digest,
        ):
            raise ApprovalRequestError("Review version is already claimed; recovery required")
        if approved_at is not None and claim.get("approved_at") != approved_at:
            raise ApprovalRequestError("Review claim does not match the confirmed preview timestamp")
        if operation_callback:
            operation_callback("claimed")

        records = self.approvals.records_for_version(review_path, digest)
        if any(record.get("request_id") != claim.get("request_id") for record in records):
            raise ApprovalRequestError("Review version claim conflicts with approval state; recovery required")

        accepted = self.approvals.approve_as(
            approver_subject,
            {**body, "review_path": review_path},
            review_root,
            approved_at=claim["approved_at"],
        )
        current = self.decisions.get(review_path, digest)
        if current.get("status") == "promoted":
            if current.get("request_id") != claim["request_id"] or \
                    current.get("target_filename") != claim["target_filename"]:
                raise ApprovalRequestError("Promoted decision conflicts with its durable claim; recovery required")
            result = {**accepted, **self.worker.promote(claim["request_id"], review_path, digest)}
            if operation_callback:
                operation_callback("already_promoted")
            return result
        if current.get("status") in {"approved", "promoting", "failed"} and \
                current.get("request_id") not in (None, claim["request_id"]):
            raise ApprovalRequestError("Review version decision conflicts with its durable claim; recovery required")

        self.decisions.set(review_path, digest, "approved", request_id=claim["request_id"],
                           approver_subject=approver_subject, target_filename=claim["target_filename"])
        self.decisions.set(review_path, digest, "promoting", request_id=claim["request_id"],
                           approver_subject=approver_subject, target_filename=claim["target_filename"])
        if operation_callback:
            operation_callback("promoting")
        try:
            result = self.worker.promote(claim["request_id"], review_path, digest)
        except Exception as exc:
            try:
                self.decisions.set(review_path, digest, "failed", request_id=claim["request_id"],
                                   approver_subject=approver_subject,
                                   target_filename=claim["target_filename"], error_code=type(exc).__name__)
            except Exception as state_exc:
                raise ApprovalRequestError(
                    "Promotion outcome requires recovery; retry only with the same request ID",
                ) from state_exc
            raise ApprovalRequestError(
                "Promotion failed; retry only with the same request ID or seek recovery",
            ) from exc

        self.decisions.set(review_path, digest, "promoted", request_id=claim["request_id"],
                           approver_subject=approver_subject,
                           target_filename=result.get("target_filename"))
        if operation_callback:
            operation_callback("promoted" if result.get("status") == "promoted" else "already_promoted")
        return {**accepted, **result}

    def defer(self, review_path, review_sha256, operator_subject):
        if not isinstance(operator_subject, str) or not operator_subject:
            raise ApprovalRequestError("A verified operator identity is required")
        canonical_path = self.decisions.canonical_review_path(review_path)
        try:
            with self.decisions.lock_version(canonical_path, review_sha256):
                actual = hashlib.sha256(_read_review(self.worker.review_root, canonical_path)).hexdigest()
                if actual != review_sha256:
                    raise ApprovalRequestError("Review content changed; refresh before deferring")
                current = self.decisions.get(canonical_path, review_sha256)
                claim = self.decisions.read_claim(canonical_path, review_sha256)
                if claim or current.get("status") in {"approved", "promoting", "promoted", "failed"} or \
                        self.approvals.has_version(canonical_path, review_sha256):
                    raise ApprovalRequestError(
                        "This Review version has an approval or promotion attempt and cannot be deferred",
                    )
                return self.decisions.set(canonical_path, review_sha256, "deferred", decided_by=operator_subject)
        except ApprovalRequestError:
            raise
        except Exception as exc:
            raise ApprovalRequestError("Review version could not be deferred safely") from exc

    def get_decision(self, review_path, review_sha256):
        canonical_path = self.decisions.canonical_review_path(review_path)
        actual = hashlib.sha256(_read_review(self.worker.review_root, canonical_path)).hexdigest()
        if actual != review_sha256:
            raise ApprovalRequestError("Review content changed; refresh before reading its decision")
        return self.decisions.get(canonical_path, review_sha256)
