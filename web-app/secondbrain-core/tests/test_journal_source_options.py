"""Synthetic unit and real-Core loopback coverage for D087 Journal options."""
import hashlib
import json
import os
import re
import socket
import stat
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.app import create_app
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.journal_source_options import JournalSourceOptionsService


DAY = "2026-10-20"
def private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def append_row(path, text, *, source="web_app_explicit_intent", key=None):
    row_id = hashlib.sha256((key or text).encode()).hexdigest()
    row = {"id": row_id, "date": DAY, "source": source,
           "original_text": text, "session_id": "synthetic-session",
           "operation_id": "synthetic-operation"}
    raw = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode()
    with path.open("ab") as stream:
        stream.write(raw + b"\n")
    os.chmod(path, 0o600)
    return row, raw


def setup(tmp_path, *, deny=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = private_dir(tmp_path / "journal")
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-journal-selector-password\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test", "http://127.0.0.1"])
    if deny:
        original = auth.require_action

        def guarded(request, action):
            if action in deny:
                raise HTTPException(status_code=403, detail="forbidden")
            return original(request, action)

        auth.require_action = guarded
    token = "synthetic-app-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 600
    store = JournalStore(str(root))
    service = JournalSourceOptionsService(store, auth)
    return root, auth, token, store, service


def test_read_only_selector_uses_allowlist_and_0500_0400_without_side_effects(tmp_path):
    root, auth, token, store, service = setup(tmp_path)
    journal_path = root / f"{DAY}.jsonl"
    allowed, raw = append_row(journal_path, "synthetic permitted row")
    append_row(journal_path, "synthetic untrusted source", source="legacy_import")
    os.chmod(journal_path, 0o400)
    os.chmod(root, 0o500)
    before_names = sorted(path.name for path in root.iterdir())
    before_row = journal_path.stat()
    before_bytes = journal_path.read_bytes()

    app = _test_app(service, auth)
    with _client(app, token, "https://app.test") as client:
        response = client.get(f"/__test/journal-source-options?date={DAY}&limit=20",
                              headers={"Origin": "https://app.test"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "items", "freshness"}
    assert set(body["freshness"]) == {"checked_at"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                        body["freshness"]["checked_at"])
    assert body["status"] == "real" and len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == {"kind", "id", "date", "version"}
    assert item == {"kind": "journal", "id": f"{DAY}:{allowed['id']}", "date": DAY,
                    "version": hashlib.sha256(raw).hexdigest()}
    assert "synthetic permitted row" not in response.text
    assert "synthetic-operation" not in response.text
    assert str(root) not in response.text
    assert (root / ".operations.lock").exists() is False
    assert (root / f".{DAY}.lock").exists() is False
    assert sorted(path.name for path in root.iterdir()) == before_names
    after_row = journal_path.stat()
    assert journal_path.read_bytes() == before_bytes
    for attr in ("st_mode", "st_uid", "st_gid", "st_dev", "st_ino", "st_nlink",
                 "st_size", "st_mtime_ns", "st_ctime_ns"):
        assert getattr(after_row, attr) == getattr(before_row, attr)


def test_empty_invalid_dates_and_limits_are_exact_and_fail_closed(tmp_path):
    root, auth, token, store, service = setup(tmp_path)
    app = _test_app(service, auth)
    with _client(app, token, "https://app.test") as client:
        empty = client.get("/__test/journal-source-options?date=2026-10-21&limit=5",
                           headers={"Origin": "https://app.test"})
        assert empty.status_code == 200 and empty.json()["status"] == "empty"
        assert empty.json()["items"] == []
        assert client.get("/__test/journal-source-options?date=2026-02-30",
                          headers={"Origin": "https://app.test"}).status_code == 400
        for limit in (0, 51):
            assert client.get(f"/__test/journal-source-options?date={DAY}&limit={limit}",
                              headers={"Origin": "https://app.test"}).status_code == 400
        assert client.get("/__test/journal-source-options",
                          headers={"Origin": "https://app.test"}).status_code == 422
        for query in (f"date={DAY}&extra=x", f"date={DAY}&date={DAY}",
                      f"date={DAY}&limit=1&limit=2", f"date={DAY}&limit=1.0"):
            assert client.get(f"/__test/journal-source-options?{query}",
                              headers={"Origin": "https://app.test"}).status_code == 400


def test_result_limit_is_capped_and_order_is_stable(tmp_path):
    root, auth, token, store, service = setup(tmp_path)
    path = root / f"{DAY}.jsonl"
    for index in range(55):
        append_row(path, f"synthetic row {index}", key=f"key-{index:02d}")
    expected_ids = sorted(hashlib.sha256(f"key-{index:02d}".encode()).hexdigest()
                          for index in range(55))[:50]
    app = _test_app(service, auth)
    with _client(app, token, "https://app.test") as client:
        response = client.get(f"/__test/journal-source-options?date={DAY}&limit=50",
                              headers={"Origin": "https://app.test"})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 50
    assert [item["id"].split(":", 1)[1] for item in response.json()["items"]] == expected_ids


def test_two_megabyte_aggregate_read_budget_allows_exact_boundary(tmp_path):
    root, auth, token, store, service = setup(tmp_path)
    path = root / f"{DAY}.jsonl"
    row = {"id": hashlib.sha256(b"boundary-row").hexdigest(), "date": DAY,
           "source": "web_app_explicit_intent", "original_text": ""}
    base_size = len(json.dumps(row, separators=(",", ":")).encode())
    row["original_text"] = "x" * (1024 * 1024 - base_size)
    raw = json.dumps(row, separators=(",", ":")).encode()
    assert len(raw) == 1024 * 1024
    path.write_bytes(raw)
    os.chmod(path, 0o600)
    app = _test_app(service, auth)
    with _client(app, token, "https://app.test") as client:
        response = client.get(f"/__test/journal-source-options?date={DAY}",
                              headers={"Origin": "https://app.test"})
    assert response.status_code == 200
    assert response.json()["status"] == "real"
    assert response.json()["items"] == [{
        "kind": "journal", "id": f"{DAY}:{row['id']}", "date": DAY,
        "version": hashlib.sha256(raw).hexdigest(),
    }]


@pytest.mark.parametrize("denied_action", ["daily_brief.read", "journal.read"])
def test_auth_and_origin_reject_before_journal_is_opened(tmp_path, monkeypatch, denied_action):
    root, auth, token, store, service = setup(tmp_path)
    calls = 0
    original = store.read_source_day

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "read_source_day", counted)
    app = _test_app(service, auth)
    with _client(app, None, "https://app.test") as client:
        assert client.get(f"/__test/journal-source-options?date={DAY}",
                          headers={"Origin": "https://app.test"}).status_code == 401
    with _client(app, token, "https://app.test") as client:
        assert client.get(f"/__test/journal-source-options?date={DAY}",
                          headers={"Origin": "https://evil.test"}).status_code == 403
    assert calls == 0

    _, denied_auth, denied_token, denied_store, denied_service = setup(
        tmp_path / "deny", deny={denied_action},
    )
    denied_store = denied_service.journal_store
    denied_original = denied_store.read_source_day
    def denied_counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return denied_original(*args, **kwargs)
    monkeypatch.setattr(denied_store, "read_source_day", denied_counted)
    denied_app = _test_app(denied_service, denied_auth)
    with _client(denied_app, denied_token, "https://app.test") as client:
        denied = client.get(f"/__test/journal-source-options?date={DAY}",
                            headers={"Origin": "https://app.test"})
    assert denied.status_code == 403 and calls == 0


def test_source_mutation_between_enumeration_and_verification_returns_unavailable(tmp_path, monkeypatch):
    root, auth, token, store, service = setup(tmp_path)
    path = root / f"{DAY}.jsonl"
    append_row(path, "synthetic before mutation")
    original = store.read_source_day
    calls = 0

    def mutate_then_read(day, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            row = json.loads(path.read_text(encoding="utf-8"))
            row["original_text"] = "synthetic changed in place"
            path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
        return original(day, **kwargs)

    monkeypatch.setattr(store, "read_source_day", mutate_then_read)
    app = _test_app(service, auth)
    with _client(app, token, "https://app.test") as client:
        response = client.get(f"/__test/journal-source-options?date={DAY}",
                              headers={"Origin": "https://app.test"})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable" and response.json()["items"] == []
    assert "synthetic" not in response.text and str(root) not in response.text


@pytest.mark.parametrize("overflow", ["bytes", "rows"])
def test_journal_day_budget_overflow_is_unavailable_without_candidates(tmp_path, overflow):
    root, auth, token, store, service = setup(tmp_path)
    path = root / f"{DAY}.jsonl"
    if overflow == "bytes":
        path.write_bytes(b" " * (1024 * 1024 + 1))
    else:
        row_id = hashlib.sha256(b"row").hexdigest()
        row = json.dumps({"id": row_id, "date": DAY, "source": "web_app_explicit_intent"},
                         separators=(",", ":")).encode() + b"\n"
        path.write_bytes(row * 5001)
    os.chmod(path, 0o600)
    app = _test_app(service, auth)
    with _client(app, token, "https://app.test") as client:
        response = client.get(f"/__test/journal-source-options?date={DAY}",
                              headers={"Origin": "https://app.test"})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable" and response.json()["items"] == []
    assert str(root) not in response.text


@pytest.mark.skipif(os.geteuid() == 0, reason="permission-denial assertion requires a non-root test UID")
def test_unreadable_journal_root_is_unavailable_and_does_not_leak(tmp_path):
    root, auth, token, store, service = setup(tmp_path)
    append_row(root / f"{DAY}.jsonl", "synthetic row")
    os.chmod(root, 0o000)
    try:
        app = _test_app(service, auth)
        with _client(app, token, "https://app.test") as client:
            response = client.get(f"/__test/journal-source-options?date={DAY}",
                                  headers={"Origin": "https://app.test"})
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable" and response.json()["items"] == []
        assert str(root) not in response.text and "synthetic row" not in response.text
    finally:
        os.chmod(root, 0o700)


def test_real_localhost_http_runs_frozen_source_options_route(tmp_path, monkeypatch):
    root = private_dir(tmp_path / "journal")
    journal_path = root / f"{DAY}.jsonl"
    rows = [append_row(journal_path, f"synthetic localhost source {index}",
                       key=f"loopback-{index:03d}") for index in range(65)]
    append_row(journal_path, "synthetic unsupported source", source="legacy_import",
               key="unsupported-source")
    os.chmod(journal_path, 0o400)
    os.chmod(root, 0o500)
    roots = {name: private_dir(tmp_path / name) for name in (
        "review", "raw", "knowledge", "state", "projects", "briefs", "tasks", "notes",
    )}
    password_file = tmp_path / "core-app-password"
    password_file.write_bytes(b"synthetic-journal-selector-password\n")
    os.chmod(password_file, 0o600)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]),
        "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
        "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password_file),
        "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host,
        "SB_HERMES_API_URL": "",
        "SB_PROMOTE_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]),
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]),
        "SB_JOURNAL_ROOT": str(root),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = create_app()
    assert hasattr(app.state, "journal_source_options_service")
    service = app.state.journal_source_options_service
    source_store = service.journal_store
    original_read = source_store.read_source_day
    read_calls = 0

    def count_reads(*args, **kwargs):
        nonlocal read_calls
        read_calls += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr(source_store, "read_source_day", count_reads)
    initial_names = sorted(path.name for path in root.iterdir())
    initial_root = root.stat()
    initial_file = journal_path.stat()
    initial_bytes = journal_path.read_bytes()
    # Match the Core entrypoint's default: proxy headers are parsed, but no
    # forwarding peer is trusted unless SB_TRUSTED_PROXY_IPS explicitly lists it.
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False,
                                           proxy_headers=True, forwarded_allow_ips=""))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, trust_env=False, timeout=3.0) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-journal-selector-password"})
            assert login.status_code == 200
            base_url = "/api/daily-brief/source-options/journal"
            # Real localhost HTTP: browser-style same-origin GET has no Origin.
            # The login above deliberately retains strict explicit Origin.
            originless = client.get(f"{base_url}?date={DAY}", headers={
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty",
            })
            assert originless.status_code == 200
            assert originless.json()["status"] == "real"
            assert read_calls > 0
            # An untrusted peer cannot rewrite the ASGI authority via forwarding
            # headers; the trusted Host/scheme remain authoritative.
            before = read_calls
            spoofed_forwarding = client.get(f"{base_url}?date={DAY}", headers={
                "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty", "X-Forwarded-Host": "evil.invalid",
                "X-Forwarded-Proto": "https",
            })
            assert spoofed_forwarding.status_code == 200
            assert spoofed_forwarding.json()["status"] == "real"
            assert read_calls > before

            # Invalid Host is rejected before routing by TrustedHostMiddleware
            # (400); a Host accepted by middleware but whose authority differs
            # from the configured Origin reaches the route and is denied (403).
            read_calls = 0
            for rejected_headers, expected_status in (
                ({"Sec-Fetch-Site": "cross-site"}, 403),
                ({"Sec-Fetch-Site": "same-site"}, 403),
                ({"Sec-Fetch-Site": "same-origin", "Host": "evil.invalid"}, 400),
                ({"Sec-Fetch-Site": "same-origin", "Host": f"{host}:1"}, 403),
                ({"Sec-Fetch-Site": "same-origin", "Origin": "null"}, 403),
                ({"Sec-Fetch-Site": "same-origin", "Origin": "http://evil.invalid"}, 403),
                ({"Sec-Fetch-Site": "same-origin", "X-Forwarded-Host": "evil.invalid",
                  "X-Forwarded-Proto": "https", "Host": "evil.invalid"}, 400),
            ):
                before = read_calls
                denied = client.get(f"{base_url}?date={DAY}", headers=rejected_headers)
                assert denied.status_code == expected_status, (rejected_headers, denied.status_code)
                assert read_calls == before, rejected_headers

            anonymous = httpx.get(f"{origin}{base_url}", headers={"Origin": origin},
                                  trust_env=False)
            assert anonymous.status_code == 401
            anonymous_bad_origin = httpx.get(
                f"{origin}{base_url}?date={DAY}", headers={"Origin": "http://attacker.invalid"},
                trust_env=False,
            )
            assert anonymous_bad_origin.status_code == 403
            assert read_calls == 0

            denied = client.get(f"{base_url}?date={DAY}", headers={"Origin": "http://attacker.invalid"})
            assert denied.status_code == 403 and read_calls == 0
            auth = service.auth
            original_action = auth.require_action
            for action in ("daily_brief.read", "journal.read"):
                def reject_action(request, current, denied_action=action):
                    if current == denied_action:
                        from fastapi import HTTPException
                        raise HTTPException(status_code=403, detail="forbidden")
                    return original_action(request, current)
                monkeypatch.setattr(auth, "require_action", reject_action)
                denied_action = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
                assert denied_action.status_code == 403 and read_calls == 0
                monkeypatch.setattr(auth, "require_action", original_action)

            # Authorization precedes syntax checks and Journal IO.
            for bad_query, expected in (("", 422), (f"date={DAY}&extra=x", 400),
                                        (f"date={DAY}&date={DAY}", 400),
                                        (f"date={DAY}&limit=1&limit=2", 400),
                                        (f"date=2026-02-30", 400),
                                        (f"date={DAY}&limit=0", 400),
                                        (f"date={DAY}&limit=51", 400),
                                        (f"date={DAY}&limit=00", 400),
                                        (f"date={DAY}&limit=%2B1", 400),
                                        (f"date={DAY}&limit=0x1", 400),
                                        (f"date={DAY}&limit=%31x", 400),
                                        (f"date={DAY}&limit={'9' * 5000}", 400),
                                        (f"date={DAY}&limit=1.0", 400)):
                suffix = f"?{bad_query}" if bad_query else ""
                invalid = client.get(f"{base_url}{suffix}", headers={"Origin": origin})
                assert invalid.status_code == expected
                if expected == 400:
                    assert invalid.json() == {"detail": "Invalid source selection request"}
                    assert "Traceback" not in invalid.text and str(root) not in invalid.text
            assert read_calls == 0
            leading_zero = client.get(f"{base_url}?date={DAY}&limit=01",
                                      headers={"Origin": origin})
            assert leading_zero.status_code == 200 and len(leading_zero.json()["items"]) == 1
            assert read_calls > 0
            read_calls = 0

            expected_ids = sorted(item[0]["id"] for item in rows)
            real = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert real.status_code == 200
            body = real.json()
            assert set(body) == {"status", "items", "freshness"}
            assert set(body["freshness"]) == {"checked_at"}
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                                body["freshness"]["checked_at"])
            assert body["status"] == "real" and len(body["items"]) == 20
            assert [item["id"].split(":", 1)[1] for item in body["items"]] == expected_ids[:20]
            assert all(set(item) == {"kind", "id", "date", "version"} for item in body["items"])
            assert all(item["kind"] == "journal" and item["date"] == DAY for item in body["items"])
            assert "synthetic localhost source" not in real.text
            assert "synthetic-operation" not in real.text
            assert str(root) not in real.text and "legacy_import" not in real.text
            current_root = root.stat()
            current_file = journal_path.stat()
            assert sorted(path.name for path in root.iterdir()) == initial_names
            assert (current_root.st_mode & 0o777, current_root.st_mtime_ns,
                    current_root.st_ctime_ns, current_root.st_uid, current_root.st_gid,
                    current_root.st_ino, current_root.st_nlink) == \
                   (initial_root.st_mode & 0o777, initial_root.st_mtime_ns,
                    initial_root.st_ctime_ns, initial_root.st_uid, initial_root.st_gid,
                    initial_root.st_ino, initial_root.st_nlink)
            assert (current_file.st_mode & 0o777, current_file.st_ino,
                    current_file.st_size, current_file.st_mtime_ns,
                    current_file.st_ctime_ns, current_file.st_uid, current_file.st_gid,
                    current_file.st_nlink) == \
                   (initial_file.st_mode & 0o777, initial_file.st_ino,
                    initial_file.st_size, initial_file.st_mtime_ns,
                    initial_file.st_ctime_ns, initial_file.st_uid, initial_file.st_gid,
                    initial_file.st_nlink)
            assert journal_path.read_bytes() == initial_bytes
            assert (root / ".operations.lock").exists() is False
            assert (root / f".{DAY}.lock").exists() is False
            fifty = client.get(f"{base_url}?date={DAY}&limit=50", headers={"Origin": origin})
            assert fifty.status_code == 200 and len(fifty.json()["items"]) == 50
            assert [item["id"].split(":", 1)[1] for item in fifty.json()["items"]] == expected_ids[:50]
            assert read_calls >= 2

            empty = client.get(f"{base_url}?date=2026-10-21", headers={"Origin": origin})
            assert empty.status_code == 200 and empty.json()["status"] == "empty"
            assert empty.json()["items"] == []

            # A missing store and a filesystem permission failure both map to
            # the exact 200/unavailable envelope without local detail.
            monkeypatch.setattr(service, "journal_store", None)
            unavailable = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert unavailable.status_code == 200 and unavailable.json()["status"] == "unavailable"
            assert unavailable.json()["items"] == [] and str(root) not in unavailable.text
            monkeypatch.setattr(service, "journal_store", source_store)
            if os.geteuid() != 0:
                os.chmod(journal_path, 0o000)
                permission_denied = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
                assert permission_denied.status_code == 200
                assert permission_denied.json()["status"] == "unavailable"
                assert permission_denied.json()["items"] == []
                os.chmod(journal_path, 0o400)

            # Restore a writable synthetic fixture for drift and boundary cases.
            os.chmod(root, 0o700)
            os.chmod(journal_path, 0o600)
            row_id = rows[0][0]["id"]
            version_row = {"id": row_id, "date": DAY, "source": "web_app_explicit_intent",
                           "original_text": "before-drift"}
            journal_path.write_text(json.dumps(version_row, separators=(",", ":")) + "\n")
            os.chmod(journal_path, 0o600)
            read_calls = 0

            def mutate_between_reads(day, **kwargs):
                nonlocal read_calls
                read_calls += 1
                if read_calls == 2:
                    version_row["original_text"] = "after-drift"
                    journal_path.write_text(json.dumps(version_row, separators=(",", ":")) + "\n")
                    os.chmod(journal_path, 0o600)
                return original_read(day, **kwargs)

            monkeypatch.setattr(source_store, "read_source_day", mutate_between_reads)
            drift = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert drift.status_code == 200 and drift.json()["status"] == "unavailable"
            assert drift.json()["items"] == [] and "after-drift" not in drift.text
            monkeypatch.setattr(source_store, "read_source_day", original_read)

            # Atomic replacement during the fd read must also fail closed.
            large_row = {"id": hashlib.sha256(b"atomic-race").hexdigest(), "date": DAY,
                         "source": "web_app_explicit_intent", "original_text": "x" * 130_000}
            journal_path.write_text(json.dumps(large_row, separators=(",", ":")) + "\n")
            os.chmod(journal_path, 0o600)
            original_inode = journal_path.stat().st_ino
            raw_read = os.read
            replaced = False

            def replace_during_read(fd, size):
                nonlocal replaced
                chunk = raw_read(fd, size)
                if chunk and not replaced and os.fstat(fd).st_ino == original_inode:
                    replacement = root / ".synthetic-replacement"
                    replacement.write_text(json.dumps({**large_row, "original_text": "replaced"},
                                                       separators=(",", ":")) + "\n")
                    os.chmod(replacement, 0o600)
                    os.replace(replacement, journal_path)
                    replaced = True
                return chunk

            monkeypatch.setattr(os, "read", replace_during_read)
            atomic = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert replaced and atomic.status_code == 200
            assert atomic.json()["status"] == "unavailable" and atomic.json()["items"] == []
            assert "replaced" not in atomic.text and str(root) not in atomic.text
            monkeypatch.setattr(os, "read", raw_read)

            # The exact 1 MiB first snapshot plus exact 1 MiB verifier snapshot
            # reaches, but does not exceed, the 2 MiB total request budget.
            boundary = {"id": hashlib.sha256(b"exact-budget").hexdigest(), "date": DAY,
                        "source": "web_app_explicit_intent", "original_text": ""}
            padding = 1024 * 1024 - len(json.dumps(boundary, separators=(",", ":")).encode())
            boundary["original_text"] = "x" * padding
            boundary_bytes = json.dumps(boundary, separators=(",", ":")).encode()
            assert len(boundary_bytes) == 1024 * 1024
            journal_path.write_bytes(boundary_bytes)
            os.chmod(journal_path, 0o600)
            exact_bytes = client.get(f"{base_url}?date={DAY}&limit=1", headers={"Origin": origin})
            assert exact_bytes.status_code == 200 and exact_bytes.json()["status"] == "real"
            assert exact_bytes.json()["items"][0]["version"] == hashlib.sha256(boundary_bytes).hexdigest()

            journal_path.write_bytes(boundary_bytes + b" ")
            os.chmod(journal_path, 0o600)
            over_bytes = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert over_bytes.status_code == 200 and over_bytes.json()["status"] == "unavailable"
            assert over_bytes.json()["items"] == [] and str(root) not in over_bytes.text

            exact_rows = []
            for index in range(5000):
                entry_id = hashlib.sha256(f"row-{index}".encode()).hexdigest()
                row_wire = json.dumps({"id": entry_id, "date": DAY,
                                      "source": "web_app_explicit_intent"},
                                     separators=(",", ":"))
                exact_rows.append((row_wire + "\n").encode())
            journal_path.write_bytes(b"".join(exact_rows))
            os.chmod(journal_path, 0o600)
            started = time.monotonic()
            five_thousand = client.get(f"{base_url}?date={DAY}&limit=50", headers={"Origin": origin})
            elapsed = time.monotonic() - started
            assert five_thousand.status_code == 200 and five_thousand.json()["status"] == "real"
            ids_5000 = sorted(hashlib.sha256(f"row-{index}".encode()).hexdigest()
                              for index in range(5000))
            assert [item["id"].split(":", 1)[1] for item in five_thousand.json()["items"]] == ids_5000[:50]
            assert len(five_thousand.json()["items"]) == 50
            print(f"D087 5000-row full-day verification: {elapsed:.3f}s")

            journal_path.write_bytes(b"".join(exact_rows) + exact_rows[-1])
            os.chmod(journal_path, 0o600)
            over_rows = client.get(f"{base_url}?date={DAY}&limit=1", headers={"Origin": origin})
            assert over_rows.status_code == 200 and over_rows.json()["status"] == "unavailable"
            assert over_rows.json()["items"] == []

            journal_path.write_bytes(b'{"id":')
            os.chmod(journal_path, 0o600)
            half_row = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert half_row.status_code == 200 and half_row.json()["status"] == "unavailable"
            assert half_row.json()["items"] == []

            journal_path.unlink()
            outside = tmp_path / "synthetic-outside.jsonl"
            outside.write_bytes(b"synthetic outside must not be read\n")
            os.chmod(outside, 0o600)
            journal_path.symlink_to(outside)
            unsafe = client.get(f"{base_url}?date={DAY}", headers={"Origin": origin})
            assert unsafe.status_code == 200 and unsafe.json()["status"] == "unavailable"
            assert unsafe.json()["items"] == [] and "synthetic outside" not in unsafe.text
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        os.chmod(root, 0o700)
        if (root / f"{DAY}.jsonl").is_symlink():
            (root / f"{DAY}.jsonl").unlink()
        if not thread.is_alive():
            listener.close()


def _test_app(service, auth, host="app.test"):
    router = APIRouter()

    @router.get("/__test/journal-source-options")
    def internal_test_projection(request: Request):
        return service.select_from_request(request)

    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host])
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def safe_http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": "Request rejected"})

    return app


def _client(app, token, host):
    from fastapi.testclient import TestClient

    client = TestClient(app, base_url=host)
    if token:
        client.cookies.set(AppSessionAuth.COOKIE_NAME, token)
    return client


def test_d089_originless_browser_get_exact_authority_and_fail_closed(tmp_path, monkeypatch):
    root, auth, token, store, service = setup(tmp_path)
    append_row(root / f"{DAY}.jsonl", "synthetic d089 row")
    reads = 0
    original = store.read_source_day

    def counted(*args, **kwargs):
        nonlocal reads
        reads += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "read_source_day", counted)
    app = _test_app(service, auth)
    url = f"/__test/journal-source-options?date={DAY}"
    with _client(app, token, "https://app.test") as client:
        allowed = client.get(url, headers={
            "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        })
        assert allowed.status_code == 200 and allowed.json()["status"] == "real"
        assert reads > 0
        for headers in (
            {},
            {"Sec-Fetch-Site": "same-site"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Sec-Fetch-Site": "none"},
            {"Sec-Fetch-Site": "same-origin, cross-site"},
            {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate"},
            {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Dest": "document"},
            {"Sec-Fetch-Site": "same-origin", "Origin": "null"},
            {"Sec-Fetch-Site": "same-origin", "Origin": ""},
            {"Sec-Fetch-Site": "same-origin", "Origin": "https://evil.test"},
            {"Sec-Fetch-Site": "same-origin", "Origin": "https://app.test:444"},
            {"Sec-Fetch-Site": "same-origin", "Host": "evil.test"},
            {"Sec-Fetch-Site": "same-origin", "X-Forwarded-Host": "evil.test",
             "X-Forwarded-Proto": "http", "Host": "evil.test"},
        ):
            before = reads
            response = client.get(url, headers=headers)
            assert response.status_code in ({400, 403} if headers.get("Host") == "evil.test" else {403}), headers
            assert reads == before, headers
        before = reads
        assert client.get(url, headers={"Origin": "https://app.test"}).status_code == 200
        assert reads > before
    with _client(app, None, "https://app.test") as client:
        before = reads
        assert client.get(url, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 401
        assert reads == before
    for action in ("daily_brief.read", "journal.read"):
        _, deny_auth, deny_token, deny_store, deny_service = setup(
            tmp_path / f"deny-{action}", deny={action})
        denied_app = _test_app(deny_service, deny_auth)
        with _client(denied_app, deny_token, "https://app.test") as client:
            assert client.get(url, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 403


def test_d089_rejects_duplicated_origin_and_fetch_metadata(tmp_path):
    _, auth, token, _, service = setup(tmp_path)
    from fastapi.testclient import TestClient
    with _client(_test_app(service, auth), token, "https://app.test") as client:
        url = f"/__test/journal-source-options?date={DAY}"
        for pairs in (
            [("Sec-Fetch-Site", "same-origin"), ("Sec-Fetch-Site", "same-origin")],
            [("Origin", "https://app.test"), ("Origin", "https://app.test")],
            [("Sec-Fetch-Site", "same-origin"), ("Sec-Fetch-Mode", "cors"),
             ("Sec-Fetch-Mode", "cors")],
            [("Sec-Fetch-Site", "same-origin"), ("Host", "app.test"),
             ("Host", "app.test")],
        ):
            response = client.get(url, headers=pairs)
            assert response.status_code == 403, pairs
