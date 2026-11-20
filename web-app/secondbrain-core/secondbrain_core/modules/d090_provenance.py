"""Readback against the Authority ledger, without exposing it to Core."""

import base64
import hashlib
import json
import socket
from pathlib import Path

from cryptography.exceptions import InvalidSignature

from .d090_authority_writer import _canonical, authority_peer_before_body


def _read_message(conn):
    with conn.makefile("rb") as stream:
        line = stream.readline(2049)
    if len(line) > 2048 or not line.endswith(b"\n"):
        raise ValueError("invalid source message framing")
    return json.loads(line)


def serve_source_request(conn, core_uid, core_gid, resolver, knowledge_root):
    """Answer only for the locally configured capture and published target."""
    conn.settimeout(2)
    authority_peer_before_body(conn, core_uid, core_gid)
    request = _read_message(conn)
    result = None
    if (isinstance(request, dict) and set(request) == {"operation_id", "sha256"}
            and request["operation_id"] == resolver.operation_id):
        content = resolver._read(knowledge_root, resolver.filename)
        result = resolver.verify(resolver.filename, content, request["sha256"])
    conn.sendall(_canonical(result) + b"\n")


class UnixSourceClient:
    def __init__(self, path, authority_uid, authority_gid, operation_id, filename):
        self.path = path
        self.peer = authority_uid, authority_gid
        self.operation_id = operation_id
        self.filename = filename

    def verify(self, relative, content, digest):
        if relative != self.filename or hashlib.sha256(content).hexdigest() != digest:
            return None
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(2)
            conn.connect(self.path)
            authority_peer_before_body(conn, *self.peer)
            conn.sendall(_canonical({"operation_id": self.operation_id, "sha256": digest}) + b"\n")
            result = _read_message(conn)
        if isinstance(result, dict) and result.get("request_id") == self.operation_id:
            return result
        return None


class CapturedCommitSource:
    """Resolve one known Authority operation through the existing Capture store."""

    def __init__(self, authority, capture, *, operation_id, capture_id, target_id, filename):
        self.authority = authority
        self.capture = capture
        self.operation_id = operation_id
        self.capture_id = capture_id
        self.target_id = target_id
        self.filename = filename

    def verify(self, relative, content, digest):
        if relative != self.filename or hashlib.sha256(content).hexdigest() != digest:
            return None
        record = self.capture.get(self.capture_id)
        if not record or record.get("status") != "completed":
            return None
        review_ref, raw_ref = record.get("review_path"), record.get("raw_path")
        if any(not isinstance(ref, str) or ref in {"", ".", ".."} or Path(ref).name != ref
               for ref in (review_ref, raw_ref)):
            return None
        review = self._read(self.capture.review_root, review_ref)
        raw = self._read(self.capture.raw_root, raw_ref)
        if verify_committed_source(
            self.authority, self.operation_id, self.target_id, content, review, raw,
            capture_id=self.capture_id, review_ref=review_ref, raw_ref=raw_ref,
        ):
            return {"kind": "review", "ref": review_ref,
                    "sha256": hashlib.sha256(review).hexdigest(),
                    "request_id": self.operation_id,
                    "raw": {"ref": raw_ref, "sha256": hashlib.sha256(raw).hexdigest()}}
        return None

    @staticmethod
    def _read(root, ref):
        import os
        import stat
        fd = os.open(Path(root) / ref, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError("source is not a regular file")
            payload = stream.read(8 * 1024 * 1024 + 1)
            if len(payload) > 8 * 1024 * 1024:
                raise OSError("source exceeds readback limit")
            return payload


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
