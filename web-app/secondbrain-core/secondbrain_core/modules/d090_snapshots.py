"""Authority-owned, content-addressed Capture snapshots for D090.

The Authority ledger is private to the Authority OS identity. Snapshots are
stored there before preview; their digest is the signed source revision. Live
source is checked once at confirmation, before the proof is consumed. After
confirmation the Writer receives only the authenticated snapshot bytes.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .d090_authority_writer import D090Rejected, _canonical, _valid_id
from .d090_provenance import CapturedCommitSource

_MAX_BYTES = 8 * 1024 * 1024


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _ref(value):
    return isinstance(value, str) and value not in ('', '.', '..') and Path(value).name == value


class CaptureSnapshots:
    """Persist and authenticate exactly one Capture revision per snapshot ID."""

    def __init__(self, authority, capture, *, trusted_source_verifier, source_guard):
        # These are mandatory integration contracts, not assurances from Core.
        # A production provider must independently authenticate Capture records
        # and enforce the guard against every source writer, including open FDs.
        if not callable(trusted_source_verifier) or not callable(source_guard):
            raise D090Rejected('trusted_source_provider_required')
        self.authority, self.capture = authority, capture
        self.trusted_source_verifier, self.source_guard = trusted_source_verifier, source_guard
        db = authority._connect()
        try:
            db.execute('CREATE TABLE IF NOT EXISTS capture_snapshots (id TEXT PRIMARY KEY, payload BLOB NOT NULL)')
        finally:
            db.close()

    def _current(self, capture_id):
        if not _valid_id(capture_id):
            raise D090Rejected('snapshot_invalid_capture')
        try:
            record = self.capture.get(capture_id)
        except Exception as exc:
            raise D090Rejected('snapshot_source_unavailable') from exc
        if not record or record.get('capture_id') != capture_id or record.get('status') != 'completed':
            raise D090Rejected('snapshot_source_unavailable')
        review_ref, raw_ref = record.get('review_path'), record.get('raw_path')
        if not _ref(review_ref) or not _ref(raw_ref):
            raise D090Rejected('snapshot_source_invalid')
        try:
            review = CapturedCommitSource._read(self.capture.review_root, review_ref)
            raw = CapturedCommitSource._read(self.capture.raw_root, raw_ref)
        except OSError as exc:
            raise D090Rejected('snapshot_source_unavailable') from exc
        if (not raw or not review or len(raw) > _MAX_BYTES or len(review) > _MAX_BYTES
                or record.get('raw_sha256') != _digest(raw)
                or record.get('review_sha256') != _digest(review)):
            raise D090Rejected('snapshot_source_invalid')
        if self.trusted_source_verifier(capture_id, record, raw, review) is not True:
            raise D090Rejected('snapshot_source_untrusted')
        return {'capture_id': capture_id, 'review_ref': review_ref, 'raw_ref': raw_ref,
                'review_sha256': _digest(review), 'raw_sha256': _digest(raw),
                'review': base64.b64encode(review).decode('ascii'),
                'raw': base64.b64encode(raw).decode('ascii')}

    def seal(self, *, capture_id, approval_id, operation_id, target_id, approved_bytes):
        if not all(_valid_id(v) for v in (approval_id, operation_id, target_id)):
            raise D090Rejected('snapshot_binding_invalid')
        if not isinstance(approved_bytes, bytes) or not approved_bytes or len(approved_bytes) > _MAX_BYTES:
            raise D090Rejected('snapshot_content_invalid')
        with self.source_guard(capture_id):
            source = self._current(capture_id)
        payload = {'schema': 'd090-capture-snapshot-v1', **source, 'approval_id': approval_id,
                   'operation_id': operation_id, 'target_id': target_id,
                   'content_sha256': _digest(approved_bytes),
                   'content': base64.b64encode(approved_bytes).decode('ascii')}
        encoded = _canonical(payload)
        snapshot_id = _digest(encoded)
        db = self.authority._begin()
        try:
            db.execute('INSERT OR IGNORE INTO capture_snapshots(id,payload) VALUES (?,?)', (snapshot_id, encoded))
            row = db.execute('SELECT payload FROM capture_snapshots WHERE id=?', (snapshot_id,)).fetchone()
            if row is None or row[0] != encoded:
                raise D090Rejected('snapshot_collision')
            db.execute('COMMIT')
        except Exception:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()
        return snapshot_id

    def load(self, snapshot_id):
        if not isinstance(snapshot_id, str) or len(snapshot_id) != 64 or any(c not in '0123456789abcdef' for c in snapshot_id):
            raise D090Rejected('snapshot_id_invalid')
        db = self.authority._connect()
        try:
            row = db.execute('SELECT payload FROM capture_snapshots WHERE id=?', (snapshot_id,)).fetchone()
        finally:
            db.close()
        if row is None or not isinstance(row[0], bytes) or _digest(row[0]) != snapshot_id:
            raise D090Rejected('snapshot_missing_or_corrupt')
        try:
            snapshot = json.loads(row[0])
            if _canonical(snapshot) != row[0] or set(snapshot) != {'schema', 'capture_id', 'review_ref', 'raw_ref', 'review_sha256', 'raw_sha256', 'review', 'raw', 'approval_id', 'operation_id', 'target_id', 'content_sha256', 'content'}:
                raise ValueError('schema')
            if snapshot['schema'] != 'd090-capture-snapshot-v1':
                raise ValueError('schema')
            for kind in ('raw', 'review', 'content'):
                value = base64.b64decode(snapshot[kind], validate=True)
                if not value or len(value) > _MAX_BYTES or _digest(value) != snapshot[kind + '_sha256']:
                    raise ValueError('digest')
            if not all(_valid_id(snapshot[k]) for k in ('capture_id', 'approval_id', 'operation_id', 'target_id')) or not all(_ref(snapshot[k]) for k in ('raw_ref', 'review_ref')):
                raise ValueError('identity')
        except (ValueError, TypeError, KeyError) as exc:
            raise D090Rejected('snapshot_missing_or_corrupt') from exc
        return snapshot

    def binding(self, snapshot_id):
        s = self.load(snapshot_id)
        content = base64.b64decode(s['content'])
        return {'approval_id': s['approval_id'], 'operation_id': s['operation_id'],
                'source_revision': snapshot_id, 'source_sha256': s['review_sha256'],
                'target_id': s['target_id'], 'content_length': len(content),
                'content_sha256': s['content_sha256']}

    def confirm(self, snapshot_id, *, proof, nonce, expires_at):
        s = self.load(snapshot_id)
        # The provider must exclude all untrusted writers until the approved
        # grant is durable. Advisory locks alone do not meet this contract.
        with self.source_guard(s['capture_id']):
            live = self._current(s['capture_id'])
            if any(live[k] != s[k] for k in live):
                raise D090Rejected('snapshot_source_changed')
            content = base64.b64decode(s['content'], validate=True)
            grant = self.authority.issue_grant(
                proof=proof, approval_id=s['approval_id'], operation_id=s['operation_id'],
                source_revision=snapshot_id, source_sha256=s['review_sha256'],
                target_id=s['target_id'], approved_bytes=content, nonce=nonce, expires_at=expires_at)
        # Re-read after issuance: a damaged or replaced snapshot never publishes.
        verified = self.load(snapshot_id)
        if verified != s:
            raise D090Rejected('snapshot_missing_or_corrupt')
        return self.authority.commit(grant, base64.b64decode(verified['content'], validate=True))

    def provenance(self, snapshot_id, *, operation_id, target_id, content):
        """Historical verification is separate from current-path consistency."""
        s = self.load(snapshot_id)
        if s['operation_id'] != operation_id or s['target_id'] != target_id or _digest(content) != s['content_sha256']:
            return None
        db = self.authority._connect()
        try:
            row = db.execute("SELECT grant_json,signature,receipt_json FROM grants WHERE operation_id=? AND state='committed'", (operation_id,)).fetchone()
        finally:
            db.close()
        if not row:
            return None
        try:
            grant, receipt = json.loads(row[0]), json.loads(row[2])
            self.authority.signer.public_key.verify(base64.b64decode(row[1], validate=True), _canonical(grant))
            if (grant['source_revision'] != snapshot_id or grant['source_sha256'] != s['review_sha256']
                or grant['approval_id'] != s['approval_id'] or grant['operation_id'] != operation_id
                or grant['target_id'] != target_id or grant['content_sha256'] != s['content_sha256']
                or grant['content_length'] != len(content) or receipt['operation_id'] != operation_id
                or receipt['content_sha256'] != s['content_sha256'] or receipt['status'] != 'published'):
                return None
        except Exception:
            return None
        try:
            live = self._current(s['capture_id'])
            current = 'matches' if all(live[k] == s[k] for k in live) else 'drift'
        except D090Rejected as exc:
            current = {'snapshot_source_unavailable': 'unavailable',
                       'snapshot_source_invalid': 'drift'}.get(str(exc), 'unverified')
        return {'historical_snapshot': 'verified', 'current_source': current,
                'snapshot_id': snapshot_id, 'capture_id': s['capture_id'], 'review_ref': s['review_ref'],
                'review_sha256': s['review_sha256'], 'raw_ref': s['raw_ref'], 'raw_sha256': s['raw_sha256'],
                'request_id': operation_id}
