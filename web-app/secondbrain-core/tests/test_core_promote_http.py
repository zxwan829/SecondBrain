"""Guard against restoring the retired Hermes-session Knowledge write path."""
import unittest

from secondbrain_core.modules.review_promote import service
from secondbrain_core.modules.review_promote import http


class RetiredHermesApprovalRouteTests(unittest.TestCase):
    def test_no_hermes_session_write_router_or_service_entrypoint_exists(self):
        self.assertFalse(hasattr(http, "create_router"))
        self.assertFalse(hasattr(service.PromoteService, "approve_and_promote"))


if __name__ == "__main__":
    unittest.main()
