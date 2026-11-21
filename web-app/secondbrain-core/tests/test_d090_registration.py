import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.d090_authority_writer import (
    D090Authority, D090Rejected, D090RoleIds, Ed25519GrantSigner,
)
from secondbrain_core.modules.d090_registration import TrustedSourceRegistry


@pytest.fixture
def registry(tmp_path):
    ledger = tmp_path / 'ledger'
    ledger.mkdir(mode=0o700)
    authority = D090Authority(
        str(ledger), Ed25519GrantSigner('test-key', Ed25519PrivateKey.generate()), None,
        role_ids=D090RoleIds(31001, 31002, 31003, 31101, 31102, 31103),
        allow_synthetic_identities=True,
    )
    return TrustedSourceRegistry(authority)


def test_registered_source_uses_authority_ids_and_private_signed_bytes(registry, tmp_path):
    record = registry.register(b'synthetic independently received raw', authenticated_subject='owner')
    manifest, raw = registry.read(record['capture_id'])
    assert manifest == record
    assert raw == b'synthetic independently received raw'
    assert record['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert record['source_channel'] == 'authority-user-upload'
    assert record['source_identity'] == 'owner'
    assert record['capture_id'] != registry.register(raw, authenticated_subject='owner')['capture_id']
    for name in ('raw', 'review', 'state'):
        (tmp_path / name).mkdir(mode=0o700)
    capture = CaptureService(tmp_path / 'raw', tmp_path / 'review', tmp_path / 'state')
    state = capture.accept_file(record['raw_ref'], raw, capture_id=record['capture_id'],
                                extra_state={'review_path_hint': record['review_ref']}, exact_raw_name=True)
    capture.process(state, raw)
    state = capture.get(record['capture_id'])
    review = (capture.review_root / state['review_path']).read_bytes()
    assert registry.verify(record['capture_id'], state, raw, review)
    assert not registry.verify(record['capture_id'], state, b'forged raw', review)
    assert not registry.verify('0' * 32, state, raw, review)
    assert not registry.verify(record['capture_id'], {**state, 'raw_path': 'forged.md'}, raw, review)
    assert not registry.verify(record['capture_id'], {**state, 'review_path': 'forged.md'}, raw, review)


def test_raw_or_signed_manifest_corruption_fails_closed(registry):
    item = registry.register(b'authentic', authenticated_subject='owner')
    db = registry.authority._connect()
    try:
        db.execute('UPDATE trusted_sources SET raw=? WHERE capture_id=?', (b'forged', item['capture_id']))
    finally:
        db.close()
    with pytest.raises(D090Rejected, match='registration_corrupt'):
        registry.read(item['capture_id'])


def test_rejects_invalid_registration(registry):
    for data, subject in ((b'', 'owner'), (b'x' * (1024 * 1024 + 1), 'owner'), (b'x', '../bad')):
        with pytest.raises(D090Rejected):
            registry.register(data, authenticated_subject=subject)
    with pytest.raises(D090Rejected, match='registration_missing'):
        registry.read('0' * 32)
