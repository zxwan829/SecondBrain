"""Disposable Linux probe for the real long-lived Writer sandbox."""
import errno
import json
import os
import socket
import sys
from pathlib import Path
from secondbrain_core.modules import d090_writer_service as svc
from secondbrain_core.modules.d090_authority_writer import D090Rejected

with open(sys.argv[1], encoding='utf-8') as stream:
    config = json.load(stream)
writer, listener, abi = svc.initialize(config)
protected = Path(config['knowledge_root']) / 'existing.md'
for callback in (
    lambda: os.open(protected, os.O_WRONLY),
    lambda: os.open(protected, os.O_WRONLY | os.O_TRUNC),
    lambda: os.unlink(protected),
    lambda: os.rename(protected, protected.with_name('other.md')),
    lambda: os.chmod(protected, 0o600),
    lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
):
    try:
        callback()
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.EACCES):
            raise
    else:
        raise AssertionError('kernel failed to deny destructive action')
print(f'READY abi={abi}', flush=True)
count = 0
while count < 2:
    conn, _ = listener.accept()
    with conn:
        conn.settimeout(3)
        try:
            writer.handle_connection(conn)
        except (D090Rejected, OSError):
            continue
    count += 1
print('TWO_PUBLICATIONS', flush=True)
