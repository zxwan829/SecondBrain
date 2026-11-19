import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main():
    from secondbrain_core.modules.app_auth import AppSessionAuth
    from secondbrain_core.modules.d090_approval_lab import create_lab_app
    from secondbrain_core.modules.d090_authority_writer import (
        D090Authority, D090RoleIds, Ed25519GrantSigner,
    )
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import socket
    import uvicorn
    root = Path(sys.argv[1])
    os.umask(0o077)
    (root / "password").write_text("synthetic-password")
    key = Ed25519PrivateKey.generate()
    (root / "signing.key").write_bytes(key.private_bytes_raw())
    (root / "ledger").mkdir()
    uid, gid = os.geteuid(), os.getegid()
    auth = AppSessionAuth(str(root / "password"), ["http://authority.test"])
    def factory(confirmation):
        return D090Authority(str(root / "ledger"), Ed25519GrantSigner("lab", key), None,
            role_ids=D090RoleIds(uid-1, uid, uid+1, gid-1, gid, gid+1),
            browser_confirmation=confirmation)
    app = create_lab_app(auth, factory, dict(approval_id="approval-1",
        operation_id="operation-1", source_revision="revision-1", source_sha256="a"*64,
        target_id="target-1", approved_bytes=b"synthetic"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    @app.on_event("startup")
    def ready():
        print(sock.getsockname()[1], flush=True)
    uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False)).run(sockets=[sock])


if __name__ == "__main__":
    main()
