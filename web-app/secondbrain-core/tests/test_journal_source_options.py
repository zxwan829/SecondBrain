"""Synthetic coverage for the internal D087 Journal source selector.

The loopback endpoint below exists only in this test harness. The production
Core app does not register a Journal source-options route before A freezes D087.
"""
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


def test_real_localhost_http_runs_core_with_test_only_internal_selector_route(tmp_path, monkeypatch):
    root = private_dir(tmp_path / "journal")
    row, raw = append_row(root / f"{DAY}.jsonl", "synthetic localhost source")
    os.chmod(root / f"{DAY}.jsonl", 0o600)
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
    assert not any(getattr(route, "path", None) ==
                   "/api/daily-brief/source-options/journal" for route in app.routes)
    test_router = APIRouter()

    @test_router.get("/__test/journal-source-options")
    def internal_test_projection(request: Request, date: str, limit: int = 20):
        return app.state.journal_source_options_service.select(request, date, limit)

    # The only source-options HTTP route is test-local and is attached after
    # create_app() to exercise Core auth, middleware and storage over loopback.
    app.include_router(test_router)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False))
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
            good = client.get(f"/__test/journal-source-options?date={DAY}",
                              headers={"Origin": origin})
            assert good.status_code == 200 and good.json()["status"] == "real"
            assert good.json()["items"] == [{
                "kind": "journal", "id": f"{DAY}:{row['id']}", "date": DAY,
                "version": hashlib.sha256(raw).hexdigest(),
            }]
            assert "synthetic localhost source" not in good.text
            assert str(root) not in good.text
            denied = client.get(f"/__test/journal-source-options?date={DAY}",
                                headers={"Origin": "http://attacker.invalid"})
            assert denied.status_code == 403
            unauth = httpx.get(f"{origin}/__test/journal-source-options?date={DAY}",
                               headers={"Origin": origin}, trust_env=False)
            assert unauth.status_code == 401
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if not thread.is_alive():
            listener.close()


def _test_app(service, auth, host="app.test"):
    router = APIRouter()

    @router.get("/__test/journal-source-options")
    def internal_test_projection(request: Request, date: str, limit: int = 20):
        return service.select(request, date, limit)

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
