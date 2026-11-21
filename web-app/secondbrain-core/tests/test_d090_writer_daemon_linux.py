"""Real Linux UIDs and kernel confinement of a persistent Writer candidate."""
import ctypes
import grp
import json
import os
import pwd
import select
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='requires disposable root Linux runner')

def _unused(start, lookup):
    for value in range(start, start + 1000):
        try: lookup(value)
        except KeyError: return value
    raise RuntimeError('no free synthetic uid or gid')

def _drop(uid, gid, groups):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0): raise OSError(ctypes.get_errno(), 'no_new_privs')
    last = int(Path('/proc/sys/kernel/cap_last_cap').read_text())
    for cap in range(last + 1):
        if libc.prctl(24, cap, 0, 0, 0): raise OSError(ctypes.get_errno(), 'capbset_drop')
    os.setgroups(groups)
    os.setgid(gid)
    os.setuid(uid)

@pytest.fixture
def isolated_dir():
    with tempfile.TemporaryDirectory(prefix='d090-service-') as directory:
        yield Path(directory)

def test_confined_daemon_handles_multiple_writes_and_blocks_mutation(isolated_dir):
    tmp_path = isolated_dir
    uid = _unused(42000, pwd.getpwuid)
    gid = _unused(52000, grp.getgrgid)
    core_uid, authority_uid, writer_uid = uid, uid + 1, uid + 2
    core_gid, authority_gid, writer_gid, read_gid = gid, gid + 1, gid + 2, gid + 3
    tmp_path.chmod(0o711)
    pkg = tmp_path / 'secondbrain_core'
    shutil.copytree(Path(__file__).parents[1] / 'secondbrain_core', pkg)
    for path in [pkg, *pkg.rglob('*')]: path.chmod(0o755 if path.is_dir() else 0o644)
    root = tmp_path / 'knowledge'
    root.mkdir(); os.chown(root, writer_uid, read_gid); root.chmod(0o2750)
    existing = root / 'existing.md'
    existing.write_bytes(b'protected existing'); os.chown(existing, writer_uid, read_gid); existing.chmod(0o660)
    sockdir = tmp_path / 'socket'
    sockdir.mkdir(); os.chown(sockdir, writer_uid, authority_gid); sockdir.chmod(0o710)
    key = Ed25519PrivateKey.generate()
    public = tmp_path / 'public.pem'
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)); public.chmod(0o644)
    config = {'role_ids': dict(core_uid=core_uid, authority_uid=authority_uid, writer_uid=writer_uid,
                core_gid=core_gid, authority_gid=authority_gid, writer_gid=writer_gid),
              'knowledge_root': str(root), 'knowledge_read_gid': read_gid, 'public_key_path': str(public),
              'key_id': 'test-key', 'target_map': {'one': 'one.md', 'two': 'two.md'},
              'socket_path': str(sockdir / 'writer.sock'), 'socket_gid': authority_gid}
    config_path = tmp_path / 'config.json'; config_path.write_text(json.dumps(config)); config_path.chmod(0o644)
    helper = tmp_path / 'daemon.py'; shutil.copyfile(Path(__file__).with_name('d090_writer_daemon_probe.py'), helper); helper.chmod(0o644)
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    daemon = subprocess.Popen([sys.executable, str(helper), str(config_path)], stdin=subprocess.DEVNULL,
             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
             preexec_fn=lambda: _drop(writer_uid, writer_gid, [authority_gid, read_gid]))
    try:
        available, _, _ = select.select([daemon.stdout], [], [], 15)
        if not available:
            daemon.kill()
            out, err = daemon.communicate(timeout=5)
            pytest.fail(f'writer did not become ready: {out} {err}')
        ready = daemon.stdout.readline()
        if not ready.startswith('READY abi='):
            daemon.kill()
            out, err = daemon.communicate(timeout=5)
            pytest.fail(f'writer startup failed: {ready} {out} {err}')
        # The client is the real Authority UID/GID and sends two individually signed grants.
        private = tmp_path / 'private.pem'
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.chown(private, authority_uid, authority_gid); private.chmod(0o600)
        code = '''import hashlib, time, sys\nfrom cryptography.hazmat.primitives import serialization\nfrom secondbrain_core.modules.d090_authority_writer import Ed25519GrantSigner, UnixWriterClient, PROTOCOL\nkey=serialization.load_pem_private_key(open(sys.argv[2], "rb").read(),password=None)\ns=Ed25519GrantSigner("test-key",key)\nc=UnixWriterClient(sys.argv[1],writer_uid=int(sys.argv[3]),writer_gid=int(sys.argv[4]))\nfor n in ("one", "two"):\n b=("approved-"+n).encode(); g=dict(protocol=PROTOCOL,key_id="test-key",approval_id="approval-"+n,operation_id="operation-"+n,source_revision="rev-"+n,source_sha256="a"*64,content_sha256=hashlib.sha256(b).hexdigest(),content_length=len(b),target_id=n,create_only=True,expires_at=int(time.time())+120,nonce="nonce-"+n,audience="secondbrain-knowledge-writer"); r=c({**g,"signature":s.sign(g)},b); assert r["status"]=="published"\n'''
        result = subprocess.run([sys.executable, '-c', code, config['socket_path'], str(private), str(writer_uid), str(writer_gid)],
                    capture_output=True, text=True, timeout=15, env=env,
                    preexec_fn=lambda: (os.setgroups([]), os.setgid(authority_gid), os.setuid(authority_uid)))
        assert result.returncode == 0, (result.stdout, result.stderr)
        out, err = daemon.communicate(timeout=15)
        assert daemon.returncode == 0 and 'TWO_PUBLICATIONS' in out, (out, err)
        assert existing.read_bytes() == b'protected existing'
        for n in ('one', 'two'):
            file = root / (n + '.md')
            assert file.read_bytes() == ('approved-' + n).encode()
            assert file.stat().st_gid == read_gid and file.stat().st_mode & 0o777 == 0o440
    finally:
        if daemon.poll() is None:
            daemon.kill(); daemon.communicate(timeout=5)
