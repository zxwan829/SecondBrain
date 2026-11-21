"""Synthetic HTTP tests; real boundaries need independent Linux evidence."""
import base64
import contextlib
import hashlib
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.d090_authority_service import create_authority_app
from secondbrain_core.modules.d090_authority_writer import D090Authority, D090RoleIds, Ed25519GrantSigner
from secondbrain_core.modules.d090_browser_confirmation import BrowserConfirmation
from secondbrain_core.modules.d090_snapshots import CaptureSnapshots


def test_authority_session_preview_exact_confirmation_and_recovery(tmp_path):
    for name in ('raw', 'review', 'state', 'ledger'):
        (tmp_path / name).mkdir(mode=0o700)
    secret = tmp_path / 'password'
    secret.touch(mode=0o600)
    secret.write_text('synthetic-secret-password')
    origin = 'https://authority.example'
    auth = AppSessionAuth(str(secret), [origin])
    confirmation = BrowserConfirmation(auth)
    capture = CaptureService(tmp_path / 'raw', tmp_path / 'review', tmp_path / 'state')
    item = capture.accept_text('synthetic raw')
    capture.process(item, b'synthetic raw')
    records = []
    def publish(grant, content):
        records.append(content)
        return {'operation_id': grant['operation_id'], 'content_sha256': hashlib.sha256(content).hexdigest(), 'status': 'published'}
    authority = D090Authority(str(tmp_path / 'ledger'), Ed25519GrantSigner('key', Ed25519PrivateKey.generate()),
        publish, role_ids=D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
        browser_confirmation=confirmation, allow_synthetic_identities=True)
    # Test-only fake provider, not evidence of source authenticity.
    snapshots = CaptureSnapshots(authority, capture, trusted_source_verifier=lambda *_: True,
                                  source_guard=lambda _: contextlib.nullcontext())
    class Registry:
        def register(self, raw, *, authenticated_subject):
            assert authenticated_subject == 'owner'
            return {'capture_id': 'registered-1', 'length': len(raw)}
    def builder(capture_id, target_id, content):
        return snapshots.seal(capture_id=capture_id, approval_id='approval-1', operation_id='operation-1',
                              target_id=target_id, approved_bytes=content.encode())
    ready = [False]
    with pytest.raises(ValueError, match='hostname_must_be_independent'):
        create_authority_app(auth, authority, snapshots, Registry(), builder, lambda: True, core_origin='https://authority.example:8443')
    with pytest.raises(ValueError, match='https_origin_required'):
        create_authority_app(auth, authority, snapshots, Registry(), builder, lambda: True, core_origin='http://core.example')
    app = create_authority_app(auth, authority, snapshots, Registry(), builder, lambda: ready[0], core_origin='https://core.example')
    with TestClient(app, base_url=origin, headers={'Origin': origin}) as c:
        assert c.get('/', headers={'Host': 'core.example'}).status_code == 400
        page = c.get('/')
        assert page.status_code == 200 and "script-src 'self'" in page.headers['Content-Security-Policy']
        assert 'textContent=preview.content' in c.get('/authority.js').text
        assert c.get('/health').status_code == 503
        ready[0] = True
        assert c.get('/health').json() == {'status': 'ready'}
        assert c.post('/sources', json={'intent': 'register_source', 'raw_base64': 'YQ=='}).status_code == 401
        assert c.post('/login', json={'password': 'synthetic-secret-password'}).status_code == 200
        r = c.post('/sources', json={'intent': 'register_source', 'raw_base64': base64.b64encode(b'raw').decode()})
        assert r.json()['capture_id'] == 'registered-1'
        assert c.post('/sources', headers={'Origin': 'https://core.example'}, json={'intent': 'register_source', 'raw_base64': 'YQ=='}).status_code == 403
        candidate = c.post('/candidates', json={'capture_id': item['capture_id'], 'target_id': 'target-1', 'content': 'approved output'})
        assert candidate.status_code == 200, candidate.text
        preview = candidate.json()
        assert preview['content'] == 'approved output'
        forged = dict(preview['binding'], target_id='target-2')
        assert c.post('/confirm', json={'intent': 'promote_exact_preview', 'snapshot_id': preview['snapshot_id'], 'binding': forged}).status_code == 409
        approved = c.post('/confirm', json={'intent': 'promote_exact_preview', 'snapshot_id': preview['snapshot_id'], 'binding': preview['binding']})
        assert approved.status_code == 200, approved.text
        assert records == [b'approved output']
        assert c.post('/operation', json={'operation_id': 'operation-1'}).json()['state'] == 'committed'
        assert c.post('/confirm', json={'intent': 'promote_exact_preview', 'snapshot_id': preview['snapshot_id'], 'binding': preview['binding']}).status_code == 409
        db = authority._connect()
        try:
            db.execute("UPDATE grants SET state='committing' WHERE operation_id='operation-1'")
        finally:
            db.close()
        assert c.post('/operation', json={'operation_id': 'operation-1'}).json()['state'] == 'recovery_required'
        assert records == [b'approved output']
