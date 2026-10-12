import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


class ProxyHeaderTrustTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()

        @app.get("/")
        def request_facts(request: Request):
            return {
                "scheme": request.url.scheme,
                "host": request.headers.get("host"),
                "client": request.client.host if request.client else None,
            }

        self.app = ProxyHeadersMiddleware(app, trusted_hosts="192.0.2.10")

    def test_untrusted_forwarded_proto_and_host_are_ignored(self):
        client = TestClient(self.app, base_url="http://core.test", client=("198.51.100.8", 4000))
        response = client.get("/", headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "attacker.invalid",
            "X-Forwarded-For": "203.0.113.7",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "scheme": "http", "host": "core.test", "client": "198.51.100.8",
        })
        client.close()

    def test_trusted_peer_sets_scheme_but_forwarded_host_does_not_replace_host(self):
        client = TestClient(self.app, base_url="http://core.test", client=("192.0.2.10", 4000))
        response = client.get("/", headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "attacker.invalid",
            "X-Forwarded-For": "203.0.113.7",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "scheme": "https", "host": "core.test", "client": "203.0.113.7",
        })
        client.close()


if __name__ == "__main__":
    unittest.main()
