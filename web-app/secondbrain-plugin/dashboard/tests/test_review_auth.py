import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Router:
    def __init__(self):
        self.handlers = {}

    def get(self, path):
        def register(function):
            self.handlers[path] = function
            return function
        return register


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.APIRouter = Router
fastapi_stub.HTTPException = HTTPException
fastapi_stub.Request = object
_previous_fastapi = sys.modules.get("fastapi")
sys.modules["fastapi"] = fastapi_stub
plugin_path = Path(__file__).resolve().parents[1] / "plugin_api.py"
spec = importlib.util.spec_from_file_location("plugin_api_review_auth_test", plugin_path)
plugin_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin_api)
if _previous_fastapi is None:
    del sys.modules["fastapi"]
else:
    sys.modules["fastapi"] = _previous_fastapi


class ReviewAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review_root = self.root / "10-Review"
        self.review_root.mkdir()
        self.content = b"---\ntype: review\nstatus: pending\n---\n# Candidate\n\nRead-only body.\n"
        (self.review_root / "candidate.md").write_bytes(self.content)
        plugin_api.REVIEW_ROOT = self.review_root
        self.list_items = plugin_api.router.handlers["/review/items"]
        self.get_item = plugin_api.router.handlers["/review/items/{review_path:path}"]

    def tearDown(self):
        self.temp.cleanup()

    def request(self, *, user="joe", provider="basic", expires=None,
                origin="https://dashboard.example", auth_required=True,
                extra_headers=None):
        session = None if user is None else SimpleNamespace(
            user_id=user,
            provider=provider,
            expires_at=expires or datetime.now(timezone.utc).timestamp() + 300,
        )
        headers = {"origin": origin}
        headers.update(extra_headers or {})
        return SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(auth_required=auth_required)),
            state=SimpleNamespace(session=session),
            headers=headers,
            base_url="https://dashboard.example/",
        )

    def test_verified_session_can_read_list_and_detail(self):
        request = self.request()
        listing = self.list_items(request)
        self.assertEqual(listing["items"][0]["title"], "Candidate")
        self.assertEqual(listing["items"][0]["status"], "pending")
        detail = self.get_item(request, "candidate.md")
        self.assertEqual(detail["content"], self.content.decode())

    def test_missing_or_expired_session_is_denied_even_with_forged_header(self):
        requests = (
            self.request(user=None, extra_headers={"x-user-id": "joe"}),
            self.request(expires=1),
        )
        for request in requests:
            with self.subTest(request=request):
                with self.assertRaises(HTTPException) as raised:
                    self.list_items(request)
                self.assertEqual(raised.exception.status_code, 401)

    def test_non_basic_or_ungated_session_is_denied(self):
        for request in (self.request(provider="loopback"),
                        self.request(auth_required=False)):
            with self.subTest(request=request):
                with self.assertRaises(HTTPException):
                    self.list_items(request)

    def test_cross_origin_is_denied(self):
        with self.assertRaises(HTTPException) as raised:
            self.list_items(self.request(origin="https://attacker.example"))
        self.assertEqual(raised.exception.status_code, 403)

    def test_detail_rejects_traversal_and_symlinks(self):
        outside = self.root / "outside.md"
        outside.write_text("private")
        os.symlink(outside, self.review_root / "linked.md")
        request = self.request()
        for path in ("../outside.md", "linked.md"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPException) as raised:
                    self.get_item(request, path)
                self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
