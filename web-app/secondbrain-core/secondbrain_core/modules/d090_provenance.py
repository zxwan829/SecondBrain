"""Readback against the Authority ledger, without exposing it to Core."""

import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature

from .d090_authority_writer import _canonical


def capture_source_revision(capture_id, review_ref, raw_ref, raw):
    return hashlib.sha256(_canonical([
        "d090-capture-v1", capture_id, review_ref, raw_ref, hashlib.sha256(raw).hexdigest(),
    ])).hexdigest()


def verify_committed_source(authority, operation_id, target_id, content, review, raw,
                            *, capture_id, review_ref, raw_ref):
    """Verify bytes independently read from the pinned target, Review and Raw."""
    digest = hashlib.sha256(content).hexdigest()
    review_digest = hashlib.sha256(review).hexdigest()
    revision = capture_source_revision(capture_id, review_ref, raw_ref, raw)
    db = authority._connect()
    try:
        row = db.execute(
            "SELECT grant_json, signature, receipt_json FROM grants "
            "WHERE operation_id=? AND state='committed'", (operation_id,),
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return False
    encoded, signature, receipt_json = row
    try:
        grant = json.loads(encoded)
        receipt = json.loads(receipt_json)
        authority.signer.public_key.verify(base64.b64decode(signature, validate=True), _canonical(grant))
        return (
            grant["operation_id"] == receipt["operation_id"] == operation_id
            and receipt["status"] == "published"
            and grant["target_id"] == target_id
            and grant["content_length"] == len(content)
            and grant["content_sha256"] == receipt["content_sha256"] == digest
            and grant["source_sha256"] == review_digest
            and grant["source_revision"] == revision
        )
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False
