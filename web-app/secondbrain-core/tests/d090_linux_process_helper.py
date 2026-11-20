"""Subprocess helper for the synthetic D090 Linux process-boundary test.

This helper is invoked only by test_d090_authority_writer_linux_process.py.
All keys, grants, paths, and note content are synthetic and temporary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from secondbrain_core.modules import d090_authority_writer as d090


CONTENT = b"# Synthetic D090 process-boundary note\n"
SOURCE_SHA = hashlib.sha256(b"synthetic D090 source").hexdigest()


class SyntheticProof:
    test_only = True

    def verify(self, proof, binding):
        return proof == binding


class DropResponse:
    """Forward a real socket while simulating a lost Writer response."""

    def __init__(self, conn):
        self._conn = conn

    def getsockopt(self, *args):
        return self._conn.getsockopt(*args)

    def recvmsg(self, *args):
        return self._conn.recvmsg(*args)

    def sendall(self, _data):
        # Intentional synthetic transport failure after successful publish.
        return None


def writer(args):
    roles = role_ids(args)
    public = serialization.load_pem_public_key(Path(args.public_key).read_bytes())
    instance = d090.StrictCreateOnlyWriter(
        args.knowledge_root, public, "synthetic-test-key",
        {"synthetic-target": "synthetic-note.md"}, roles,
    )
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(args.socket_path)
        listener.listen(1)
        print("READY", flush=True)
        while True:
            conn, _ = listener.accept()
            with conn:
                try:
                    if args.drop_response:
                        instance.handle_connection(DropResponse(conn))
                    else:
                        instance.handle_connection(conn)
                except d090.D090Rejected as exc:
                    print(f"REJECTED {exc}", flush=True)
                    continue
                break
    finally:
        listener.close()
        instance.close()


def authority(args):
    roles = role_ids(args)
    private = serialization.load_pem_private_key(Path(args.private_key).read_bytes(), password=None)
    signer = d090.Ed25519GrantSigner("synthetic-test-key", private)
    client = d090.UnixWriterClient(args.socket_path, timeout_seconds=3)
    core = d090.D090Authority(
        args.ledger_root, signer, client, role_ids=roles,
        synthetic_proof_verifier=SyntheticProof(), allow_synthetic_proof=True,
    )
    digest = hashlib.sha256(CONTENT).hexdigest()
    binding = {
        "approval_id": "synthetic-approval", "operation_id": args.operation_id,
        "source_revision": "synthetic-rev-1", "source_sha256": SOURCE_SHA,
        "target_id": "synthetic-target", "content_sha256": digest,
        "content_length": len(CONTENT),
    }
    grant = core.issue_grant(
        proof=binding, approval_id=binding["approval_id"],
        operation_id=args.operation_id, source_revision=binding["source_revision"],
        source_sha256=SOURCE_SHA, approved_bytes=CONTENT,
        target_id=binding["target_id"], expires_at=int(time.time()) + 120,
        nonce="synthetic-nonce",
    )
    if args.expect_recovery:
        try:
            core.commit(grant, CONTENT)
        except d090.D090RecoveryRequired:
            reopened = d090.D090Authority(
                args.ledger_root, signer, client, role_ids=roles,
            )
            try:
                reopened.commit(grant, CONTENT)
            except d090.D090RecoveryRequired:
                db = reopened._connect()
                try:
                    state = db.execute(
                        "SELECT state FROM grants WHERE operation_id=?", (args.operation_id,),
                    ).fetchone()[0]
                finally:
                    db.close()
                print(json.dumps({"result": "recovery_required", "state": state}))
                return
        raise AssertionError("uncertain Writer result did not fail closed")

    first = core.commit(grant, CONTENT)
    replay = core.commit(grant, CONTENT)
    if first != replay:
        raise AssertionError("Authority replay changed its durable receipt")
    print(json.dumps({"result": "committed_and_replayed", "status": first["status"]}))


def probe(args):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(args.socket_path)
        conn.sendall(b"{\"synthetic_probe\":true}\n")
        conn.settimeout(3)
        try:
            response = conn.recv(1)
        except ConnectionResetError:
            # Linux may reset a stream when the peer closes with our unread probe body queued.
            response = b""
        if response:
            raise AssertionError("Writer responded to a rejected peer")
    finally:
        conn.close()
    print("PROBE_REJECTED", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("writer", "authority", "probe"))
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--role-ids", required=True, help="synthetic uid/gid tuple")
    parser.add_argument("--knowledge-root")
    parser.add_argument("--public-key")
    parser.add_argument("--private-key")
    parser.add_argument("--ledger-root")
    parser.add_argument("--operation-id", default="synthetic-operation")
    parser.add_argument("--drop-response", action="store_true")
    parser.add_argument("--expect-recovery", action="store_true")
    args = parser.parse_args()
    if args.mode == "writer":
        writer(args)
    elif args.mode == "authority":
        authority(args)
    else:
        probe(args)


def role_ids(args):
    values = [int(value) for value in args.role_ids.split(",")]
    if len(values) != 6:
        raise ValueError("expected six synthetic role IDs")
    return d090.D090RoleIds(*values)


if __name__ == "__main__":
    main()
