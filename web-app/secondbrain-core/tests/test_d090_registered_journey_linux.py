"""Synthetic cross-UID integration; registration-to-Core transport is a fixture."""
import grp
import importlib.util
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from secondbrain_core.modules import d090_authority_writer as d090
_spec = importlib.util.spec_from_file_location("d090_existing_linux_test", Path(__file__).with_name("test_d090_authority_writer_linux_process.py"))
_existing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_existing)
_unused_block, _prepare, _spawn, _command, _readline, _drop_identity = (
    _existing._unused_block, _existing._prepare, _existing._spawn, _existing._command,
    _existing._readline, _existing._drop_identity,
)

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='requires disposable Linux root runner')


def test_registered_source_user_confirmation_writer_and_drift():
    uid = _unused_block(43000, 3, pwd.getpwuid)
    gid = _unused_block(53000, 3, grp.getgrgid)
    roles = d090.D090RoleIds(uid, uid+1, uid+2, gid, gid+1, gid+2)
    with tempfile.TemporaryDirectory(prefix='d090-reg-journey-') as directory:
        base = Path(directory)
        ledger, knowledge, sock, key, public = _prepare(base, roles, 'operation-1')
        role_modules = base / 'role_modules'; role_modules.mkdir(mode=0o755)
        package = role_modules / 'secondbrain_core'
        shutil.copytree(Path(__file__).parents[1] / 'secondbrain_core', package)
        for path in (package, *package.rglob('*')):
            path.chmod(0o755 if path.is_dir() else 0o644)
        writer_helper = base / 'd090_linux_process_helper.py'
        shutil.copyfile(Path(__file__).with_name(writer_helper.name), writer_helper); writer_helper.chmod(0o644)
        authority_helper = base / 'd090_registered_journey_helper.py'
        shutil.copyfile(Path(__file__).with_name(authority_helper.name), authority_helper); authority_helper.chmod(0o644)
        for name in ('core-raw', 'core-review', 'core-state'):
            path = base / name; path.mkdir(mode=0o700); os.chown(path, roles.core_uid, roles.core_gid)
        writer = _spawn(_command('writer', roles, sock, writer_helper, knowledge_root=knowledge,
                                 public_key=public), roles.writer_uid, roles.writer_gid, role_modules)
        authority = None
        try:
            assert _readline(writer) == 'READY'
            os.chown(sock, roles.authority_uid, roles.authority_gid); sock.chmod(0o660)
            values = ','.join(map(str, (roles.core_uid, roles.authority_uid, roles.writer_uid,
                                       roles.core_gid, roles.authority_gid, roles.writer_gid)))
            env = dict(os.environ, PYTHONPATH=str(role_modules))
            authority = subprocess.Popen([sys.executable, str(authority_helper), str(ledger), str(knowledge),
                                          str(sock), str(key), values], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, env=env,
                                         preexec_fn=lambda: _drop_identity(roles.authority_uid, roles.authority_gid))
            line = _readline(authority, timeout=20)
            assert line.startswith('HTTP_PORT '), line
            port = line.split()[1]
            attacker = '''import json,sys,ssl,urllib.request,urllib.error
for cookie in ('','sb_app_session=forged'):
 for path,body in (('/sources',{'intent':'register_source','raw_base64':'Zm9yZ2Vk','capture_id':'0'*32,'sha256':'0'*64}),('/candidates',{'capture_id':'0'*32,'target_id':'synthetic-target','content':'forged'})):
  request=urllib.request.Request('https://127.0.0.1:'+sys.argv[1]+path,data=json.dumps(body).encode(),headers={'Host':'authority.test','Origin':'https://authority.test','Content-Type':'application/json','Cookie':cookie})
  try: urllib.request.urlopen(request,timeout=5,context=ssl._create_unverified_context())
  except urllib.error.HTTPError as exc: assert exc.code==401, exc.code
  else: raise AssertionError('Core spoof accepted')
'''
            attack = subprocess.run([sys.executable, '-c', attacker, port], env=env, capture_output=True,
                                    text=True, timeout=15,
                                    preexec_fn=lambda: _drop_identity(roles.core_uid, roles.core_gid))
            assert attack.returncode == 0, (attack.stdout, attack.stderr)
            authority.stdin.write('CORE_ATTACK_DONE\n'); authority.stdin.flush()
            line = _readline(authority, timeout=20)
            assert line.startswith('REGISTERED '), line
            capture_id = line.split()[1]
            code = '''import os,sys,json\nfrom pathlib import Path\nfrom secondbrain_core.modules.capture import CaptureService\nb=Path(sys.argv[1]); cid=sys.argv[2]; ledger=b/'authority'; raw=b'# synthetic registered source\\n\\nwp61registration\\n'\nfor name in ('authority.sqlite3','test-private.pem'):\n try: (ledger/name).read_bytes()\n except PermissionError: pass\n else: raise AssertionError('Core read Authority private data')\nc=CaptureService(b/'core-raw',b/'core-review',b/'core-state')\ns=c.accept_file(cid+'.md',raw,capture_id=cid,extra_state={'review_path_hint':cid+'.md'},exact_raw_name=True);c.process(s,raw);s=c.get(cid)\nassert s['status']=='completed'\nfor d in (c.raw_root,c.review_root,c.state_root):\n for p in d.iterdir(): p.chmod(0o644)\n d.chmod(0o755)\n'''
            core = subprocess.run([sys.executable, '-c', code, str(base), capture_id], env=env,
                                  capture_output=True, text=True, timeout=20,
                                  preexec_fn=lambda: _drop_identity(roles.core_uid, roles.core_gid))
            assert core.returncode == 0, (core.stdout, core.stderr)
            authority.stdin.write('CORE_READY\n'); authority.stdin.flush()
            assert _readline(authority, timeout=20) == 'PREVIEW'
            review = base / 'core-review' / (capture_id + '.md')
            raw = base / 'core-raw' / (capture_id + '.md')
            # Root invokes the Core-equivalent actor using the real Core UID.
            def mutate(path, action):
                script = 'from pathlib import Path;import sys;p=Path(sys.argv[1]);' + action
                child = subprocess.run([sys.executable, '-c', script, str(path)], env=env, capture_output=True,
                                       text=True, timeout=10,
                                       preexec_fn=lambda: _drop_identity(roles.core_uid, roles.core_gid))
                assert child.returncode == 0, child.stderr
            mutate(review, "p.with_suffix('.bak').write_bytes(p.read_bytes());p.write_bytes(b'drift')")
            authority.stdin.write('DRIFTED\n'); authority.stdin.flush()
            assert _readline(authority, timeout=20) == 'REJECTED_PRECONFIRM'
            mutate(review, "p.write_bytes(p.with_suffix('.bak').read_bytes())")
            authority.stdin.write('RESTORED\n'); authority.stdin.flush()
            assert _readline(authority, timeout=20) == 'DISPATCH'
            mutate(raw, "p.write_bytes(b'after approval drift')")
            authority.stdin.write('CONTINUE\n'); authority.stdin.flush()
            assert _readline(authority, timeout=20) == 'VERIFIED_HISTORY_DRIFT'
            out, err = authority.communicate(timeout=15)
            assert authority.returncode == 0, (out, err)
            assert writer.wait(timeout=10) == 0
            assert (knowledge / 'synthetic-note.md').read_bytes() == b'# approved synthetic content\n'
        finally:
            if authority and authority.poll() is None:
                authority.kill(); authority.communicate(timeout=5)
            if writer.poll() is None:
                writer.kill()
            writer.communicate(timeout=5)
