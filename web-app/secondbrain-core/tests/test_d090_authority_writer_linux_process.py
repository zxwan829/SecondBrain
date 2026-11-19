"""Real Linux UID/GID and SO_PEERCRED integration for synthetic D090 data."""
from __future__ import annotations

import os
import grp
import pwd
import select
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from secondbrain_core.modules import d090_authority_writer as d090


pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or os.geteuid() != 0
    or not hasattr(socket, "SO_PEERCRED") or not hasattr(os, "O_TMPFILE")
    or not Path("/proc/self/fd").is_dir(),
    reason="requires disposable Linux root runner, SO_PEERCRED and O_TMPFILE",
)

HELPER = Path(__file__).with_name("d090_linux_process_helper.py")


def test_committed_capture_source_detects_raw_review_and_target_drift():
    uid = _unused_block(41000, 3, pwd.getpwuid)
    gid = _unused_block(51000, 3, grp.getgrgid)
    roles = d090.D090RoleIds(uid, uid+1, uid+2, gid, gid+1, gid+2)
    with tempfile.TemporaryDirectory(prefix="d090-integrated-ipc-") as directory:
        base = Path(directory)
        ledger, knowledge, socket_path, private_key, public_key = _prepare(base, roles, "operation-1")
        helper = base / HELPER.name
        shutil.copyfile(HELPER, helper)
        module_root = base / "role_modules"
        module_root.mkdir(mode=0o755)
        package = module_root / "secondbrain_core"
        shutil.copytree(Path(__file__).parents[1] / "secondbrain_core", package)
        package.chmod(0o755)
        for path in package.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        writer = _spawn(_command("writer", roles, socket_path, helper,
            knowledge_root=knowledge, public_key=public_key), roles.writer_uid, roles.writer_gid, module_root)
        authority = None
        try:
            assert _readline(writer) == "READY"
            os.chown(socket_path, roles.authority_uid, roles.authority_gid)
            socket_path.chmod(0o660)
            test_module = base / Path(__file__).name
            shutil.copyfile(__file__, test_module)
            harness = (
                "import runpy, sys; "
                "runpy.run_path(sys.argv[1])['_exercise_committed_capture'](*sys.argv[2:])"
            )
            values = [getattr(roles, name) for name in (
                "core_uid", "authority_uid", "writer_uid", "core_gid", "authority_gid", "writer_gid")]
            authority = _spawn([sys.executable, "-c", harness, str(test_module),
                str(ledger), str(knowledge), str(socket_path), str(private_key),
                ",".join(map(str, values))], roles.authority_uid, roles.authority_gid, module_root)
            assert _readline(authority, timeout=20) == "PUBLISHED"
            # Provision read-only access to the disposable published snapshot.
            published = knowledge / "synthetic-note.md"
            published.chmod(0o444)
            knowledge.chmod(0o755)
            base.chmod(0o755)
            source_socket = base / "source.sock"
            # The Authority binds inside a private subdirectory and the harness
            # passes through a read-only rendezvous directory for the lab.
            source_dir = base / "readback"
            source_dir.mkdir(mode=0o755)
            os.chown(source_dir, roles.authority_uid, roles.authority_gid)
            source_socket = source_dir / source_socket.name
            (ledger / "readback-ready").touch()
            assert _readline(authority, timeout=20) == "SOURCE_READY"
            source_socket.chmod(0o666)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as outsider:
                outsider.settimeout(5)
                outsider.connect(str(source_socket))
                assert outsider.recv(1) == b""
            core_harness = (
                "import runpy, sys; "
                "runpy.run_path(sys.argv[1])['_exercise_core_readback'](*sys.argv[2:])"
            )
            core = _spawn([sys.executable, "-c", core_harness, str(test_module),
                str(knowledge), str(source_socket), str(ledger), ",".join(map(str, values))],
                roles.core_uid, roles.core_gid, module_root)
            stdout, stderr = core.communicate(timeout=20)
            assert core.returncode == 0, (stdout, stderr)
            stdout, stderr = authority.communicate(timeout=30)
            assert authority.returncode == 0, (stdout, stderr)
            assert writer.wait(timeout=5) == 0
        finally:
            if authority is not None and authority.poll() is None:
                authority.kill()
                authority.communicate(timeout=5)
            if writer.poll() is None:
                writer.kill()
            writer.communicate(timeout=5)


def _exercise_core_readback(knowledge, source_socket, ledger, role_values):
    import hashlib
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from secondbrain_core.modules.app_auth import AppSessionAuth
    from secondbrain_core.modules.d090_provenance import UnixSourceClient
    from secondbrain_core.modules.knowledge_read import KnowledgeReadStore, create_knowledge_read_router

    roles = d090.D090RoleIds(*map(int, role_values.split(",")))
    for name in ("authority.sqlite3", "test-private.pem", "password"):
        with pytest.raises(PermissionError):
            (Path(ledger) / name).read_bytes()
    origin = "https://core.test"
    with tempfile.TemporaryDirectory() as directory:
        password = Path(directory) / "password"
        password.touch(mode=0o600)
        password.write_text("synthetic-core-login")
        auth = AppSessionAuth(str(password), [origin])
        app = FastAPI()
        resolver = UnixSourceClient(source_socket, roles.authority_uid, roles.authority_gid,
                                    "operation-1", "synthetic-note.md")
        store = KnowledgeReadStore(knowledge, resolver)
        app.include_router(create_knowledge_read_router(auth, store))
        from fastapi import Request

        # TestClient uses a dedicated Core login and never receives Authority cookies.
        token_request = Request({"type": "http", "scheme": "https", "method": "POST",
            "headers": [(b"host", b"core.test"), (b"origin", origin.encode())], "path": "/"})
        token = auth.login(token_request, password.read_text())
        with TestClient(app, base_url=origin, cookies={auth.COOKIE_NAME: token}) as client:
            result = client.get("/api/knowledge/search", params={"q": "wp61d090provenance"})
            assert result.status_code == 200, result.text
            row, = result.json()["items"]
            path = f"/api/knowledge/items/{row['id']}/source"
            response = client.get(path)
            assert response.status_code == 200, response.text
            assert response.json()["provenance_status"] == "verified"
            assert response.json()["source"]["raw"]["ref"]
            resolver.operation_id = "wrong-operation"
            assert client.get(path).json()["source"] is None
            resolver.operation_id = "operation-1"
            forged = b"synthetic forged target"
            assert resolver.verify("synthetic-note.md", forged, hashlib.sha256(forged).hexdigest()) is None
            assert client.get(path).json()["source"] is None
            resolver.path += ".unavailable"
            assert client.get(path).json()["source"] is None


def _exercise_committed_capture(ledger, knowledge, socket_path, private_key, role_values):
    import hashlib
    from secondbrain_core.modules.capture import CaptureService
    from secondbrain_core.modules.d090_provenance import (
        CapturedCommitSource, capture_source_revision, serve_source_request, verify_committed_source,
    )
    from secondbrain_core.modules.knowledge_read import KnowledgeReadStore, create_knowledge_read_router

    roles = d090.D090RoleIds(*map(int, role_values.split(",")))
    with tempfile.TemporaryDirectory(prefix="d090-capture-", dir=ledger) as directory:
        root = Path(directory)
        for name in ("raw", "review", "capture"):
            (root / name).mkdir(mode=0o700)
        capture = CaptureService(root / "raw", root / "review", root / "capture")
        raw = b"# D090 linked capture\n\nwp61d090provenance\n"
        item = capture.accept_text(raw.decode())
        capture.process(item, raw)
        completed = capture.get(item["capture_id"])
        review = (root / "review" / completed["review_path"]).read_bytes()
        raw_path = root / "raw" / completed["raw_path"]
        source_refs = dict(capture_id=item["capture_id"], review_ref=completed["review_path"],
                           raw_ref=completed["raw_path"])
        key = serialization.load_pem_private_key(Path(private_key).read_bytes(), password=None)
        signer = d090.Ed25519GrantSigner("synthetic-test-key", key)
        writer = d090.UnixWriterClient(socket_path)
        try:
            from fastapi.testclient import TestClient
            from secondbrain_core.modules.app_auth import AppSessionAuth
            from secondbrain_core.modules.d090_approval_lab import create_lab_app

            password = root / "password"
            password.touch(mode=0o600)
            password.write_text("synthetic-d090-capture-password")
            origin = "https://authority.test"
            auth = AppSessionAuth(str(password), [origin])
            authorities = []

            def factory(confirmation):
                authority = d090.D090Authority(
                    ledger, signer, writer, role_ids=roles, browser_confirmation=confirmation)
                authorities.append(authority)
                return authority
            fields = dict(approval_id="approval-1", operation_id="operation-1",
                          source_revision=capture_source_revision(*source_refs.values(), raw),
                          source_sha256=hashlib.sha256(review).hexdigest(), target_id="synthetic-target")
            review_file = root / "review" / completed["review_path"]
            app = create_lab_app(auth, factory, dict(fields, approved_bytes=review),
                                 read_source=lambda: (review_file.read_bytes(),
                                     capture_source_revision(*source_refs.values(), raw_path.read_bytes())))
            with TestClient(app, base_url=origin, headers={"Origin": origin}) as browser:
                assert browser.post("/login", json={"password": password.read_text()}).status_code == 200
                preview = browser.post("/preview").json()
                raw_path.write_bytes(raw + b"changed")
                drift = browser.post("/confirm", json={
                    "intent": "promote_exact_preview", "binding": preview["binding"],
                })
                assert drift.status_code == 409
                raw_path.write_bytes(raw)
                preview = browser.post("/preview").json()
                response = browser.post("/confirm", json={
                    "intent": "promote_exact_preview", "binding": preview["binding"],
                })
                assert response.status_code == 200, response.text
                assert response.json()["status"] == "published"
            print("PUBLISHED", flush=True)
            import time
            deadline = time.monotonic() + 10
            while not (Path(ledger) / "readback-ready").is_file():
                assert time.monotonic() < deadline, "readback fixture was not provisioned"
                time.sleep(0.02)
            authority, = authorities
            resolver = CapturedCommitSource(authority, capture, operation_id="operation-1",
                capture_id=item["capture_id"], target_id="synthetic-target", filename="synthetic-note.md")
            knowledge_store = KnowledgeReadStore(knowledge, resolver)
            app.include_router(create_knowledge_read_router(auth, knowledge_store))
            with TestClient(app, base_url=origin, headers={"Origin": origin}) as reader:
                assert reader.post("/login", json={"password": password.read_text()}).status_code == 200
                result = reader.get("/api/knowledge/search", params={"q": "wp61d090provenance"})
                assert result.status_code == 200, result.text
                row, = result.json()["items"]
                result = reader.get(f"/api/knowledge/items/{row['id']}/source")
                assert result.status_code == 200, result.text
                resolved = result.json()
            assert resolved["provenance_status"] == "verified"
            assert resolved["source"]["ref"] == completed["review_path"]
            assert resolved["source"]["raw"] == {
                "ref": completed["raw_path"], "sha256": hashlib.sha256(raw).hexdigest(),
            }
            content = (Path(knowledge) / "synthetic-note.md").read_bytes()
            assert verify_committed_source(authority, "operation-1", "synthetic-target",
                                           content, review, raw_path.read_bytes(), **source_refs)
            for candidate in ((content+b"x", review, raw), (content, review+b"x", raw),
                              (content, review, raw+b"x")):
                assert not verify_committed_source(authority, "operation-1", "synthetic-target",
                                                   *candidate, **source_refs)
            assert not verify_committed_source(authority, "operation-1", "synthetic-target",
                content, review, raw, **{**source_refs, "raw_ref": "different.md"})
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(Path(ledger).parent / "readback/source.sock"))
                server.listen(4)
                server.settimeout(15)
                print("SOURCE_READY", flush=True)
                for index in range(5):
                    if index == 4:
                        raw_path.write_bytes(raw + b"readback drift")
                    conn, _ = server.accept()
                    with conn:
                        if index == 0:
                            with pytest.raises(d090.D090Rejected, match="peer_rejected"):
                                serve_source_request(conn, roles.core_uid, roles.core_gid, resolver, knowledge)
                        else:
                            serve_source_request(conn, roles.core_uid, roles.core_gid, resolver, knowledge)
        finally:
            pass


def test_writer_kernel_denies_changes_to_published_target():
    with tempfile.TemporaryDirectory(prefix="d090-writer-policy-") as directory:
        root = Path(directory)
        for path in (root / "publish", root / "protected"):
            path.mkdir(mode=0o700)
        sentinel = root / "protected/sentinel.txt"
        sentinel.write_text("synthetic protected sentinel")
        for path in (root, root / "publish", root / "protected", sentinel):
            os.chown(path, 31003, 31103)
        helper = Path(__file__).with_name("d090_seccomp_writer_process_helper.py")
        result = subprocess.run([sys.executable, str(helper), str(root)],
            env={**os.environ, "SB_D090_SECCOMP_WRITER": "synthetic-only",
                 "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert "PASS exact_writer_publish=1" in result.stdout
        assert (root / "publish/approved.md").read_bytes() == b"# synthetic approved bytes\n"
        assert sentinel.read_text() == "synthetic protected sentinel"


def test_approval_entry_separates_core_and_authority_uids():
    uid = _unused_block(31001, 3, pwd.getpwuid)
    gid = _unused_block(31101, 3, grp.getgrgid)
    with tempfile.TemporaryDirectory(prefix="d090-approval-") as directory:
        root = Path(directory)
        root.chmod(0o711)
        private = root / "authority"
        private.mkdir(mode=0o700)
        os.chown(private, uid + 1, gid + 1)
        module_root = root / "role_modules"
        module_root.mkdir(mode=0o755)
        shutil.copytree(Path(__file__).parents[1] / "secondbrain_core",
                        module_root / "secondbrain_core")
        test_path = module_root / "test_d090_browser_confirmation.py"
        shutil.copyfile(Path(__file__).with_name(test_path.name), test_path)
        code = '''
import runpy, sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
root = Path(sys.argv[2])
key = root / "signing.key"
key.touch(mode=0o600)
key.write_bytes(Ed25519PrivateKey.generate().private_bytes_raw())
runpy.run_path(sys.argv[1])["_exercise_lab_entry"](root, key, True)
'''
        probe = '''
import sys
from pathlib import Path
for relative in ("password", "signing.key", "ledger/authority.sqlite3"):
    try:
        (Path(sys.argv[1]) / relative).read_bytes()
    except PermissionError:
        continue
    raise AssertionError("Core could read Authority material")
'''
        commands = (
            ([sys.executable, "-c", code, str(test_path), str(private)], uid + 1, gid + 1),
            ([sys.executable, "-c", probe, str(private)], uid, gid),
        )
        for command, child_uid, child_gid in commands:
            process = _spawn(command, child_uid, child_gid, module_root)
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, (stdout, stderr)
        shutil.rmtree(private / "ledger")
        (private / "password").unlink()
        helper = module_root / "d090_http_probe.py"
        shutil.copyfile(Path(__file__).with_name(helper.name), helper)
        server = _spawn([sys.executable, str(helper), str(private)], uid+1, gid+1, module_root)
        try:
            port = int(_readline(server))
            attack = probe + '''
import urllib.request, urllib.error, json
login = urllib.request.Request("http://127.0.0.1:"+sys.argv[2]+"/login",
    data=json.dumps({"password":"synthetic-core-only-password"}).encode(),
    headers={"Host":"authority.test","Origin":"http://authority.test",
             "Content-Type":"application/json"})
try:
    urllib.request.urlopen(login, timeout=5)
except urllib.error.HTTPError as exc:
    assert exc.code == 401
else:
    raise AssertionError("Core credentials authenticated to Authority")
for cookie in ("", "sb_app_session=forged"):
    req = urllib.request.Request("http://127.0.0.1:"+sys.argv[2]+"/confirm",
        data=json.dumps({"intent":"promote_exact_preview","binding":{}}).encode(),
        headers={"Host":"authority.test","Origin":"http://authority.test",
                 "Content-Type":"application/json","Cookie":cookie})
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("forged confirmation accepted")
'''
            core = _spawn([sys.executable, "-c", attack, str(private), str(port)], uid, gid, module_root)
            stdout, stderr = core.communicate(timeout=15)
            assert core.returncode == 0, (stdout, stderr)
            import sqlite3
            with sqlite3.connect(private / "ledger/authority.sqlite3") as db:
                assert db.execute("SELECT count(*) FROM grants").fetchone() == (0,)
        finally:
            server.terminate()
            server.communicate(timeout=10)


def _unused_block(start: int, count: int, lookup) -> int:
    for base in range(start, start + 5000):
        all_unused = True
        for value in range(base, base + count):
            try:
                lookup(value)
                all_unused = False
                break
            except KeyError:
                pass
        if all_unused:
            return base
    raise RuntimeError("no unused synthetic role identity range")


def _drop_identity(uid: int, gid: int):
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


def _command(mode: str, roles: d090.D090RoleIds, socket_path: Path,
             helper: Path, **extra) -> list[str]:
    values = (roles.core_uid, roles.authority_uid, roles.writer_uid,
              roles.core_gid, roles.authority_gid, roles.writer_gid)
    command = [sys.executable, str(helper), mode, "--socket-path", str(socket_path),
               "--role-ids", ",".join(str(value) for value in values)]
    for key, value in extra.items():
        if isinstance(value, bool):
            if value:
                command.append("--" + key.replace("_", "-"))
        else:
            command.extend(("--" + key.replace("_", "-"), str(value)))
    return command


def _readline(process: subprocess.Popen, timeout: float = 10) -> str:
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    if not ready:
        raise AssertionError("synthetic child did not report progress before timeout")
    line = process.stdout.readline()
    if not line:
        raise AssertionError(f"synthetic child exited early: {process.stderr.read()}")
    return line.strip()


def _spawn(command: list[str], uid: int, gid: int, module_root: Path) -> subprocess.Popen:
    child_env = os.environ.copy()
    existing_pythonpath = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = str(module_root) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, close_fds=True, env=child_env,
        preexec_fn=lambda: _drop_identity(uid, gid),
    )


def _prepare(root: Path, roles: d090.D090RoleIds, operation_id: str):
    root.chmod(0o711)
    authority_root = root / "authority"
    authority_root.mkdir(mode=0o700)
    os.chown(authority_root, roles.authority_uid, roles.authority_gid)
    knowledge_root = root / "knowledge"
    knowledge_root.mkdir(mode=0o700)
    os.chown(knowledge_root, roles.writer_uid, roles.writer_gid)
    socket_root = root / "socket"
    socket_root.mkdir(mode=0o711)
    os.chown(socket_root, roles.writer_uid, roles.writer_gid)
    socket_path = socket_root / "writer.sock"

    private = Ed25519PrivateKey.generate()
    private_path = authority_root / "test-private.pem"
    private_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    private_path.chmod(0o600)
    os.chown(private_path, roles.authority_uid, roles.authority_gid)
    public_path = root / "test-public.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    public_path.chmod(0o644)
    return authority_root, knowledge_root, socket_path, private_path, public_path


def _run_case(*, drop_response: bool):
    base = Path(tempfile.mkdtemp(prefix="secondbrain-d090-linux-"))
    base.chmod(0o711)
    processes: list[subprocess.Popen] = []
    try:
        helper = base / "d090_linux_process_helper.py"
        shutil.copyfile(HELPER, helper)
        helper.chmod(0o644)
        module_root = base / "role_modules"
        module_root.mkdir(mode=0o755)
        shutil.copytree(Path(__file__).parents[1] / "secondbrain_core",
                        module_root / "secondbrain_core")
        for path in (module_root / "secondbrain_core").rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        (module_root / "secondbrain_core").chmod(0o755)
        uid0 = _unused_block(41000, 3, pwd.getpwuid)
        gid0 = _unused_block(51000, 3, grp.getgrgid)
        roles = d090.D090RoleIds(uid0, uid0 + 1, uid0 + 2,
                                 gid0, gid0 + 1, gid0 + 2)
        if any(value < 0 for value in (roles.core_uid, roles.authority_uid,
                                      roles.writer_uid, roles.core_gid,
                                      roles.authority_gid, roles.writer_gid)):
            raise AssertionError("invalid synthetic role IDs")
        authority_root, knowledge_root, socket_path, private_path, public_path = _prepare(
            base, roles, "synthetic-operation",
        )
        writer_proc = _spawn(_command(
            "writer", roles, socket_path, helper, knowledge_root=knowledge_root,
            public_key=public_path, drop_response=drop_response,
        ), roles.writer_uid, roles.writer_gid, module_root)
        processes.append(writer_proc)
        assert _readline(writer_proc) == "READY"
        os.chown(socket_path, roles.authority_uid, roles.authority_gid, follow_symlinks=False)
        os.chmod(socket_path, 0o660, follow_symlinks=False)

        if not drop_response:
            # Deliberately expose only the disposable test socket for one probe.
            # The Writer must reject the real, wrong UID/GID before reading its body.
            os.chmod(socket_path, 0o666, follow_symlinks=False)
            probe = _spawn(
                _command("probe", roles, socket_path, helper),
                roles.core_uid, roles.core_gid, module_root,
            )
            processes.append(probe)
            assert _readline(writer_proc) == "REJECTED authority_peer_rejected"
            assert probe.wait(timeout=5) == 0
            os.chown(socket_path, roles.authority_uid, roles.authority_gid, follow_symlinks=False)
            os.chmod(socket_path, 0o660, follow_symlinks=False)

        authority_cmd = _command(
            "authority", roles, socket_path, helper, ledger_root=authority_root,
            private_key=private_path, operation_id="synthetic-operation",
            expect_recovery=drop_response,
        )
        authority_proc = _spawn(authority_cmd, roles.authority_uid, roles.authority_gid, module_root)
        processes.append(authority_proc)
        result = _readline(authority_proc)
        assert authority_proc.wait(timeout=8) == 0, authority_proc.stderr.read()
        assert writer_proc.wait(timeout=8) == 0, writer_proc.stderr.read()
        if drop_response:
            assert '"result": "recovery_required"' in result
            assert '"state": "recovery_required"' in result
        else:
            assert '"result": "committed_and_replayed"' in result
            assert '"status": "published"' in result
        output = knowledge_root / "synthetic-note.md"
        assert output.read_bytes() == b"# Synthetic D090 process-boundary note\n"
        assert sorted(path.name for path in knowledge_root.iterdir()) == ["synthetic-note.md"]
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        shutil.rmtree(base, ignore_errors=True)


def test_authority_writer_real_uids_peer_credentials_replay_and_recovery():
    _run_case(drop_response=False)
    _run_case(drop_response=True)
