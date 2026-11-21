import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.requests import Request

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.d090_authority_writer import HumanProofUnavailable
from secondbrain_core.modules.d090_browser_confirmation import BrowserConfirmation
from secondbrain_core.modules.d090_approval_lab import create_lab_app
from secondbrain_core.modules.d090_authority_writer import (
    D090Authority, D090RoleIds, Ed25519GrantSigner,
)


def request(token="", origin="https://testserver"):
    return Request({
        "type": "http", "method": "POST", "scheme": "https", "path": "/confirm",
        "headers": [(b"host", b"testserver"), (b"origin", origin.encode()),
                    (b"cookie", f"sb_app_session={token}".encode())],
    })


def test_confirmation_requires_same_live_session_and_exact_one_use_binding(tmp_path):
    password = "synthetic-password"
    secret = tmp_path / "password"
    secret.touch(mode=0o600)
    secret.write_text(password)
    auth = AppSessionAuth(str(secret), ["https://testserver"])
    owner = request(auth.login(request(), password))
    other = request(auth.login(request(), password))
    confirmation = BrowserConfirmation(auth)
    exact = confirmation.prepare(owner, {"target_id": "approved", "source_revision": "v1"})
    with pytest.raises(HTTPException):
        confirmation.consume(request(), exact)
    with pytest.raises(HumanProofUnavailable):
        confirmation.consume(other, exact)
    with pytest.raises(HumanProofUnavailable):
        confirmation.consume(owner, {**exact, "target_id": "changed"})
    confirmation.consume(owner, exact)
    with pytest.raises(HumanProofUnavailable):
        confirmation.consume(owner, exact)
    next_exact = confirmation.prepare(owner, {"target_id": "approved"})
    auth.logout(owner)
    with pytest.raises(HTTPException):
        confirmation.consume(owner, next_exact)


def test_lab_entry_issues_real_grant_only_after_explicit_confirmation(tmp_path):
    _exercise_lab_entry(tmp_path)


def _exercise_lab_entry(tmp_path, key=None, real_identity=False):
    password = "synthetic-authority-password"
    secret = tmp_path / "password"
    secret.touch(mode=0o600)
    secret.write_text(password)
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700)
    origin = "https://testserver"
    auth = AppSessionAuth(str(secret), [origin])
    import os
    private_key = Ed25519PrivateKey.from_private_bytes(key.read_bytes()) if key else Ed25519PrivateKey.generate()
    signer = Ed25519GrantSigner("test-key", private_key)
    authorities = []

    def factory(confirmation):
        authority = D090Authority(
            str(root), signer, lambda *_: pytest.fail("Writer must not run"),
            role_ids=D090RoleIds(os.geteuid()-1, os.geteuid(), os.geteuid()+1,
                                os.getegid()-1, os.getegid(), os.getegid()+1)
            if real_identity else D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
            browser_confirmation=confirmation, allow_synthetic_identities=not real_identity,
        )
        authorities.append(authority)
        return authority

    app = create_lab_app(auth, factory, {
        "approval_id": "approval-1", "operation_id": "operation-1",
        "source_revision": "revision-1", "source_sha256": "a" * 64,
        "target_id": "target-1", "target_filename": "approved.md", "target_scope": "knowledge-test", "approved_bytes": b"synthetic text",
    })
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as browser:
        assert browser.post("/login", json={"password": password}).status_code == 200
        preview = browser.post("/preview").json()
        assert preview["content"] == "synthetic text"
        body = {"intent": "promote_exact_preview", "binding": preview["binding"]}
        with TestClient(app, base_url=origin, headers={"Origin": origin}) as core:
            assert core.post("/confirm", json=body).status_code == 401
        assert browser.post("/confirm", json={"binding": preview["binding"]}).status_code == 403
        assert browser.post("/confirm", json=body).json()["status"] == "issued"
        assert browser.post("/confirm", json=body).status_code == 403
    db = authorities[0]._connect()
    try:
        assert db.execute("SELECT state FROM grants").fetchall() == [("issued",)]
    finally:
        db.close()
