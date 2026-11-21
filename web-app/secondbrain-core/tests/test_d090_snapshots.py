import contextlib
import hashlib
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.d090_authority_writer import D090Authority, D090Rejected, D090RoleIds, Ed25519GrantSigner
from secondbrain_core.modules.d090_snapshots import CaptureSnapshots

class Proof:
    test_only = True
    def verify(self, value, binding):
        return value == binding

def fixture(tmp_path, publish):
    for name in ('raw', 'review', 'state', 'ledger'):
        (tmp_path / name).mkdir(mode=0o700)
    capture = CaptureService(tmp_path / 'raw', tmp_path / 'review', tmp_path / 'state')
    item = capture.accept_text('synthetic original')
    capture.process(item, b'synthetic original')
    state = capture.get(item['capture_id'])
    authority = D090Authority(str(tmp_path / 'ledger'),
        Ed25519GrantSigner('key', Ed25519PrivateKey.generate()), publish,
        role_ids=D090RoleIds(31001,31002,31003,31101,31102,31103),
        synthetic_proof_verifier=Proof(), allow_synthetic_proof=True, allow_synthetic_identities=True)
    # Test fixture only: a no-op guard is not a production writer boundary.
    store = CaptureSnapshots(authority, capture, trusted_source_verifier=lambda *_: True,
                             source_guard=lambda _: contextlib.nullcontext())
    snapshot = store.seal(capture_id=item['capture_id'], approval_id='approval-1',
        operation_id='operation-1', target_id='target-1', approved_bytes=b'approved output')
    return capture, state, authority, store, snapshot

def receipt(grant, content):
    return {'status': 'published', 'operation_id': grant['operation_id'],
            'content_sha256': hashlib.sha256(content).hexdigest()}

def confirm(store, snapshot):
    return store.confirm(snapshot, proof=store.binding(snapshot), nonce='nonce-1', expires_at=int(time.time()) + 120)

def test_before_confirmation_drift_fails_closed(tmp_path):
    calls = []
    capture, state, authority, store, snap = fixture(tmp_path, lambda *args: calls.append(args))
    (capture.review_root / state['review_path']).write_bytes(b'changed')
    with pytest.raises(D090Rejected):
        confirm(store, snap)
    assert not calls
    db = authority._connect()
    try:
        assert db.execute('select count(*) from grants').fetchone()[0] == 0
    finally:
        db.close()

def test_after_confirmation_publishes_snapshot_and_distinguishes_drift(tmp_path):
    published = []
    def publish(grant, content):
        published.append(content)
        (capture.review_root / state['review_path']).write_bytes(b'changed after approval')
        return receipt(grant, content)
    capture, state, authority, store, snap = fixture(tmp_path, publish)
    assert confirm(store, snap)['status'] == 'published'
    assert published == [b'approved output']
    source = store.provenance(snap, operation_id='operation-1', target_id='target-1', content=published[0])
    assert source['historical_snapshot'] == 'verified'
    assert source['current_source'] == 'drift'
    assert store.provenance(snap, operation_id='operation-1', target_id='target-1', content=b'forged') is None

def test_snapshot_corruption_is_not_replaced_by_live_source(tmp_path):
    capture, state, authority, store, snap = fixture(tmp_path, lambda *_: pytest.fail('writer called'))
    db = authority._connect()
    try:
        db.execute('update capture_snapshots set payload=? where id=?', (b'{}', snap))
    finally:
        db.close()
    with pytest.raises(D090Rejected, match='snapshot_missing_or_corrupt'):
        confirm(store, snap)

def test_untrusted_capture_source_is_rejected(tmp_path):
    capture, state, authority, store, snap = fixture(tmp_path, lambda *_: pytest.fail('writer called'))
    store.trusted_source_verifier = lambda *_: False
    with pytest.raises(D090Rejected, match='snapshot_source_untrusted'):
        confirm(store, snap)

def test_noncooperating_writer_exposes_guard_contract_gap(tmp_path, monkeypatch):
    """A no-op/advisory guard cannot enforce the confirmation boundary."""
    calls = []
    capture, state, authority, store, snap = fixture(tmp_path,
        lambda grant, content: (calls.append(content), receipt(grant, content))[1])
    original = authority.issue_grant
    def replace_before_proof(**kwargs):
        (capture.review_root / state['review_path']).write_bytes(b'rogue writer')
        return original(**kwargs)
    monkeypatch.setattr(authority, 'issue_grant', replace_before_proof)
    assert confirm(store, snap)['status'] == 'published'
    assert calls == [b'approved output']
    assert store.provenance(snap, operation_id='operation-1', target_id='target-1',
        content=calls[0])['current_source'] == 'drift'

def test_provenance_reports_unavailable_current_source(tmp_path):
    capture, state, authority, store, snap = fixture(tmp_path, receipt)
    assert confirm(store, snap)['status'] == 'published'
    (capture.raw_root / state['raw_path']).unlink()
    source = store.provenance(snap, operation_id='operation-1', target_id='target-1', content=b'approved output')
    assert source['historical_snapshot'] == 'verified'
    assert source['current_source'] == 'unavailable'
