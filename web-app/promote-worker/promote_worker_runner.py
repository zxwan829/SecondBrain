"""Filesystem-only queue consumer for the isolated Promote Worker service."""
import logging
import os
import time

from dashboard_approval import FileApprovalSource
from promote_worker import PromoteWorker, _open_dir_chain


class ApprovalQueueConsumer:
    def __init__(self, review_root, knowledge_root, approval_queue, audit_path):
        self.approval_queue = os.path.abspath(approval_queue)
        self.approvals = FileApprovalSource(self.approval_queue)
        self.worker = PromoteWorker(review_root, knowledge_root, audit_path, self.approvals)

    def run_once(self):
        queue_fd = _open_dir_chain(self.approval_queue)
        try:
            names = sorted(os.listdir(queue_fd))
        finally:
            os.close(queue_fd)

        results = []
        for name in names:
            if not name.endswith(".json"):
                continue
            request_id = name[:-5]
            try:
                approval = self.approvals.get_approved(request_id)
                if approval is None:
                    continue
                result = self.worker.promote(
                    request_id, approval.review_path, approval.review_sha256
                )
                logging.info("Promote request %s: %s", request_id, result["status"])
                results.append(result)
            except Exception as exc:
                # Fail closed; leave the immutable approval and Review intact.
                logging.error("Promote request %s rejected: %s", request_id, exc)
        return results


def main():
    logging.basicConfig(level=os.environ.get("PROMOTE_LOG_LEVEL", "INFO"))
    consumer = ApprovalQueueConsumer(
        os.environ.get("PROMOTE_REVIEW_ROOT", "/data/review"),
        os.environ.get("PROMOTE_KNOWLEDGE_ROOT", "/data/knowledge"),
        os.environ.get("PROMOTE_APPROVAL_QUEUE", "/data/approvals"),
        os.environ.get("PROMOTE_AUDIT_PATH", "/data/audit/promote.jsonl"),
    )
    interval = max(1.0, min(float(os.environ.get("PROMOTE_POLL_SECONDS", "3")), 60.0))
    while True:
        consumer.run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
