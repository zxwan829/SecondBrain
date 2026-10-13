import hashlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secondbrain_core.modules.review_promote.http import create_router
from secondbrain_core.modules.review_promote.service import PromoteService


class CorePromoteHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.temp.name))
        self.review, self.knowledge, self.approvals, self.audit = [self.root / n for n in ("review", "knowledge", "approvals", "audit")]
        for path in (self.review, self.knowledge, self.approvals, self.audit):
            path.mkdir()
        self.content = (b"---\ntype: review\nstatus: pending\nsource_type: external-text\n"
                        b"captured_at: 2026-10-12T00:00:00Z\nreview_status: pending\n---\n"
                        b"# Core test\nPromoted through the Core module.\n")
        (self.review / "candidate.md").write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.body = {"request_id": "core-http-1", "review_path": "candidate.md",
                     "review_sha256": self.digest, "target_filename": "core-note.md"}
        self.service = PromoteService(str(self.review), str(self.knowledge), str(self.approvals), str(self.audit / "audit.jsonl"))
        app = FastAPI()
        app.state.auth_required = True

        @app.middleware("http")
        async def simulated_hermes_auth(request, call_next):
            if request.cookies.get("session") == "valid":
                request.state.session = SimpleNamespace(
                    user_id="joe", provider="basic",
                    expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(),
                )
            return await call_next(request)

        app.include_router(create_router(self.service, self.review), prefix="/api/plugins/secondbrain")
        self.client = TestClient(app)
        self.headers = {"Origin": "http://testserver"}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def post(self, body=None, logged_in=True, origin=None):
        if logged_in:
            self.client.cookies.set("session", "valid")
        else:
            self.client.cookies.delete("session")
        headers = dict(self.headers)
        if origin is not None:
            headers["Origin"] = origin
        return self.client.post("/api/plugins/secondbrain/review/approve", json=body or self.body, headers=headers)

    def test_authenticated_http_request_promotes_once(self):
        first = self.post(dict(self.body, approved=False, approver_subject="agent:fake"))
        second = self.post()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "promoted")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "already_promoted")
        self.assertTrue((self.knowledge / "core-note.md").is_file())
        self.assertIn('"approver_subject":"joe"', (self.audit / "audit.jsonl").read_text())

    def test_missing_login_and_wrong_origin_are_rejected(self):
        self.assertEqual(self.post(dict(self.body, approved=True), logged_in=False).status_code, 403)
        self.assertEqual(self.post(origin="https://attacker.invalid").status_code, 403)
        self.assertEqual(list(self.approvals.glob("*.json")), [])

    def test_digest_change_rejects_old_approval(self):
        response = self.post(dict(self.body, review_sha256="0" * 64))
        self.assertEqual(response.status_code, 409)
        self.assertFalse((self.knowledge / "core-note.md").exists())


if __name__ == "__main__":
    unittest.main()
