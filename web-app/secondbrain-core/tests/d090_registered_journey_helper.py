"""Disposable test process: registered source journey hosted by Authority UID."""
import base64
import contextlib
import json
import os
import secrets
import sys
import socket
import threading
import time
import uvicorn
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.d090_authority_service import create_authority_app
from secondbrain_core.modules.d090_authority_writer import D090Authority, D090RoleIds, Ed25519GrantSigner, UnixWriterClient
from secondbrain_core.modules.d090_browser_confirmation import BrowserConfirmation
from secondbrain_core.modules.d090_registration import TrustedSourceRegistry
from secondbrain_core.modules.d090_snapshots import CaptureSnapshots

root, knowledge, socket_path, private_path, roles_csv = sys.argv[1:]
roles = D090RoleIds(*map(int, roles_csv.split(',')))
private = serialization.load_pem_private_key(Path(private_path).read_bytes(), password=None)
signer = Ed25519GrantSigner('synthetic-test-key', private)
client = UnixWriterClient(socket_path, writer_uid=roles.writer_uid, writer_gid=roles.writer_gid)
password = Path(root) / 'authority-password'
password.write_text(secrets.token_urlsafe(32)); password.chmod(0o600)
origin = 'https://authority.test'
auth = AppSessionAuth(str(password), [origin])
confirmation = BrowserConfirmation(auth)

def publish(grant, content):
    print('DISPATCH', flush=True)
    assert sys.stdin.readline().strip() == 'CONTINUE'
    return client(grant, content)

authority = D090Authority(root, signer, publish, role_ids=roles, browser_confirmation=confirmation)
registry = TrustedSourceRegistry(authority)
base = Path(root).parent
class CaptureReadOnly:
    raw_root = base / 'core-raw'
    review_root = base / 'core-review'
    def get(self, capture_id):
        return json.loads((base / 'core-state' / 'captures' / (capture_id + '.json')).read_text())
capture = CaptureReadOnly()
# Core mutable copies are not consulted during approval.
snapshots = CaptureSnapshots(authority, capture, trusted_source_verifier=registry.verify,
                             registration_resolver=registry.read)
def build(capture_id, target_id, content):
    return snapshots.seal(capture_id=capture_id, approval_id='approval-1', operation_id='operation-1',
                          target_id=target_id, target_filename='synthetic-note.md', target_scope='knowledge-test', approved_bytes=content.encode())
app = create_authority_app(auth, authority, snapshots, registry, build, lambda: True, core_origin='https://core.test')
# A real loopback HTTPS listener is used only for the Core UID denial probe;
# its self-signed synthetic origin is not a production topology.
listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.bind(('127.0.0.1', 0)); listener.listen(16)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'authority.test')])
now = datetime.now(timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('authority.test')]), critical=False)
        .sign(private, algorithm=None))
cert_path = Path(root) / 'fixture-cert.pem'
cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM)); cert_path.chmod(0o600)
server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False,
                                       ssl_certfile=str(cert_path), ssl_keyfile=private_path))
thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
thread.start()
deadline = time.monotonic() + 10
while not server.started:
    if time.monotonic() > deadline:
        raise RuntimeError('test_http_listener_not_ready')
    time.sleep(0.01)
print('HTTP_PORT ' + str(listener.getsockname()[1]), flush=True)
assert sys.stdin.readline().strip() == 'CORE_ATTACK_DONE'
db = authority._connect()
try:
    assert db.execute('SELECT count(*) FROM trusted_sources').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM grants').fetchone()[0] == 0
finally:
    db.close()
with TestClient(app, base_url=origin, headers={'Origin': origin}) as user:
    # This ASGI call is an independent-credential negative test, not a real Core HTTP request.
    with TestClient(app, base_url=origin, headers={'Origin': origin}) as unauthenticated:
        assert unauthenticated.post('/sources', json={'intent':'register_source','raw_base64':'Zm9yZ2Vk'}).status_code == 401
    assert user.post('/login', json={'password': password.read_text()}).status_code == 200
    raw = b'# synthetic registered source\n\nwp61registration\n'
    result = user.post('/sources', json={'intent':'register_source', 'raw_base64':base64.b64encode(raw).decode()})
    assert result.status_code == 200, result.text
    item = result.json()
    print('REGISTERED ' + item['capture_id'], flush=True)
    assert sys.stdin.readline().strip() == 'CORE_READY'
    forged = dict(capture_id='0'*32, target_id='synthetic-target', content='forged')
    assert user.post('/candidates', json=forged).status_code == 409
    request = dict(capture_id=item['capture_id'], target_id='synthetic-target', content='# approved synthetic content\n')
    candidate = user.post('/candidates', json=request)
    assert candidate.status_code == 200, candidate.text
    first = candidate.json()
    print('PREVIEW', flush=True)
    assert sys.stdin.readline().strip() == 'DRIFTED'
    response = user.post('/confirm', json={'intent':'promote_exact_preview','snapshot_id':first['snapshot_id'],'binding':first['binding']})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'published'
    evidence = snapshots.provenance(first['snapshot_id'], operation_id='operation-1',
                                    target_id='synthetic-target', content=request['content'].encode())
    assert evidence['historical_snapshot'] == 'verified' and evidence['current_source'] == 'drift'
    print('VERIFIED_HISTORY_DRIFT', flush=True)

server.should_exit = True
thread.join(timeout=5)
assert not thread.is_alive()
