"""Narrow Authority-owned registration of newly received user source bytes.

Only an Authority-controlled, independently authenticated ingress may invoke
``register``. A Core request, user-supplied ID/hash, or a Core-hosted page is
not an authentication provider. This module is not itself an HTTP endpoint.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time

from cryptography.exceptions import InvalidSignature

from .d090_authority_writer import D090Rejected, _canonical, _valid_id

_MAX_RAW_BYTES = 1024 * 1024


class TrustedSourceRegistry:
    """Durable registrations owned by the Authority, not by Core.

    The signed record attests only to bytes received through the caller's
    authenticated ingress. It makes no claim that arbitrary external statements
    in the source are true, or that Core-generated Review content is trusted.
    """

    def __init__(self, authority):
        self.authority = authority
        db = authority._connect()
        try:
            db.execute('CREATE TABLE IF NOT EXISTS trusted_sources '
                       '(capture_id TEXT PRIMARY KEY, manifest BLOB NOT NULL, '
                       'signature TEXT NOT NULL, raw BLOB NOT NULL)')
        finally:
            db.close()

    def register(self, raw: bytes, *, authenticated_subject: str):
        """Record bytes after Authority ingress has authenticated the user.

        This method must not be exposed as a Core-callable registration API;
        ``authenticated_subject`` must be derived from the Authority session.
        Source IDs, paths, version and digests are always generated here.
        """
        if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_RAW_BYTES:
            raise D090Rejected('registration_raw_invalid')
        if not _valid_id(authenticated_subject):
            raise D090Rejected('registration_identity_invalid')
        capture_id = secrets.token_hex(16)
        manifest = {
            'schema': 'd090.trusted-source.v1', 'capture_id': capture_id,
            'source_identity': authenticated_subject,
            'source_channel': 'authority-user-upload',
            'raw_ref': capture_id + '.md', 'review_ref': capture_id + '.md',
            'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'raw_length': len(raw), 'registered_at': int(time.time()),
            'key_id': self.authority.signer.key_id,
        }
        version = hashlib.sha256(_canonical(manifest)).hexdigest()
        manifest['source_version'] = version
        encoded = _canonical(manifest)
        signature = self.authority.signer.sign(manifest)
        db = self.authority._begin()
        try:
            db.execute('INSERT INTO trusted_sources VALUES(?,?,?,?)',
                       (capture_id, encoded, signature, raw))
            db.execute('COMMIT')
        except Exception:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()
        return dict(manifest)

    def read(self, capture_id):
        if not _valid_id(capture_id):
            raise D090Rejected('registration_invalid')
        db = self.authority._connect()
        try:
            row = db.execute('SELECT manifest,signature,raw FROM trusted_sources '
                             'WHERE capture_id=?', (capture_id,)).fetchone()
        finally:
            db.close()
        if row is None:
            raise D090Rejected('registration_missing')
        encoded, signature, raw = row
        try:
            manifest = json.loads(encoded)
            if not isinstance(manifest, dict) or set(manifest) != {
                'schema', 'capture_id', 'source_identity', 'source_channel',
                'raw_ref', 'review_ref', 'raw_sha256', 'raw_length',
                'registered_at', 'key_id', 'source_version',
            } or _canonical(manifest) != encoded:
                raise ValueError('manifest')
            self.authority.signer.public_key.verify(
                base64.b64decode(signature, validate=True), encoded)
            version = manifest['source_version']
            original = {key: value for key, value in manifest.items() if key != 'source_version'}
            if (manifest['schema'] != 'd090.trusted-source.v1'
                    or manifest['capture_id'] != capture_id
                    or manifest['source_channel'] != 'authority-user-upload'
                    or not _valid_id(manifest['source_identity'])
                    or manifest['key_id'] != self.authority.signer.key_id
                    or manifest['raw_ref'] != capture_id + '.md'
                    or manifest['review_ref'] != capture_id + '.md'
                    or version != hashlib.sha256(_canonical(original)).hexdigest()
                    or not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_RAW_BYTES
                    or manifest['raw_length'] != len(raw)
                    or manifest['raw_sha256'] != hashlib.sha256(raw).hexdigest()):
                raise ValueError('binding')
        except (InvalidSignature, ValueError, TypeError, KeyError) as exc:
            raise D090Rejected('registration_corrupt') from exc
        return dict(manifest), raw

    def verify(self, capture_id, record, raw, review):
        """Verify the registered Raw and server-generated paths; Review is a candidate.

        Snapshot and confirmation must separately bind the actual Review bytes.
        This verifies no external origin and does not trust Core assertions.
        """
        try:
            manifest, registered_raw = self.read(capture_id)
            return (record.get('capture_id') == capture_id
                    and record.get('raw_path') == manifest['raw_ref']
                    and record.get('review_path') == manifest['review_ref']
                    and raw == registered_raw and isinstance(review, bytes) and bool(review))
        except (D090Rejected, AttributeError):
            return False
