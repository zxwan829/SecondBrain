import os
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.daily_brief_agent_health import create_daily_brief_agent_health_router
from secondbrain_core.modules.daily_brief_import import (
    BriefImportConflict,
    BriefImportRejected,
    DailyBriefAuditStore,
    DailyBriefImportStore,
)
from secondbrain_core.modules.daily_brief_store import DailyBriefRecordReadStore
from secondbrain_core.modules.hermes_api import HermesAPI
from secondbrain_core.modules.tasks import TaskStore, task_source_version


DAY = "2026-10-20"
ZONE = "Asia/Shanghai"
REF = {"kind": "task", "id": "task-synthetic-1", "version": "a" * 64}


def private_root(tmp_path):
    root = tmp_path / "briefs"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def candidate(**overrides):
    value = {
        "date": DAY,
        "timezone": ZONE,
        "categories": ["synthetic"],
        "summary": "Synthetic approved import",
        "source_refs": [REF],
    }
    value.update(overrides)
    return value


def make_store(root, *, id="brief-synthetic-1"):
    return DailyBriefImportStore(
        str(root),
        clock=lambda: datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        id_factory=lambda: id,
    )


def test_import_is_create_only_private_atomic_and_readable_with_revalidation(tmp_path):
    root = private_root(tmp_path)
    calls = []
    result = make_store(root).import_record(
        candidate(), source_verifier=lambda ref: calls.append(ref) or ref == REF)

    target = root / f"{DAY}.json"
    assert result["status"] == "created"
    assert result["brief_id"] == "brief-synthetic-1"
    assert len(calls) == 2  # before and after atomic publication
    assert target.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in root.iterdir()) == [f"{DAY}.json"]

    snapshot = DailyBriefRecordReadStore(str(root)).read(
        DAY, ZONE, source_verifier=lambda ref: ref == REF)
    assert snapshot.available and snapshot.found
    assert snapshot.source_verification == "verified"
    assert snapshot.record["summary"] == "Synthetic approved import"


def test_same_content_is_idempotent_but_different_date_content_conflicts(tmp_path):
    root = private_root(tmp_path)
    first = make_store(root, id="brief-first").import_record(
        candidate(), source_verifier=lambda _ref: True)
    duplicate = make_store(root, id="brief-second").import_record(
        candidate(), source_verifier=lambda _ref: True)
    assert first["status"] == "created"
    assert duplicate["status"] == "duplicate"
    assert duplicate["brief_id"] == first["brief_id"]

    with pytest.raises(BriefImportConflict):
        make_store(root).import_record(
            candidate(summary="different synthetic content"), source_verifier=lambda _ref: True)
    assert len(list(root.iterdir())) == 1


def test_concurrent_same_content_import_publishes_one_create_and_one_duplicate(tmp_path):
    root = private_root(tmp_path)
    store = make_store(root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _n: store.import_record(candidate(), source_verifier=lambda _ref: True),
            range(2),
        ))
    assert sorted(result["status"] for result in results) == ["created", "duplicate"]
    assert results[0]["brief_id"] == results[1]["brief_id"]
    assert len(list(root.iterdir())) == 1


def test_source_verification_fails_closed_before_and_after_commit(tmp_path):
    root = private_root(tmp_path)
    calls = 0

    def changes_during_commit(_ref):
        nonlocal calls
        calls += 1
        return calls == 1

    with pytest.raises(BriefImportRejected, match="source verification failed"):
        make_store(root).import_record(candidate(), source_verifier=changes_during_commit)
    assert not (root / f"{DAY}.json").exists()
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("bad_ref", [
    {"kind": "note", "id": "note-1", "version": "a" * 64},
    {"kind": "journal", "id": "../outside", "version": "a" * 64},
    {"kind": "task", "id": "task-1", "version": "not-a-digest"},
])
def test_unsupported_or_unverifiable_source_refs_are_rejected(tmp_path, bad_ref):
    root = private_root(tmp_path)
    with pytest.raises(BriefImportRejected):
        make_store(root).import_record(candidate(source_refs=[bad_ref]), source_verifier=lambda _ref: True)
    assert list(root.iterdir()) == []


def test_missing_verifier_and_malformed_candidate_do_not_write(tmp_path):
    root = private_root(tmp_path)
    with pytest.raises(BriefImportRejected):
        make_store(root).import_record(candidate(), source_verifier=None)
    with pytest.raises(BriefImportRejected):
        make_store(root).import_record({**candidate(), "extra": "not accepted"},
                                       source_verifier=lambda _ref: True)
    assert list(root.iterdir()) == []


def test_bad_private_root_is_rejected_without_creating_files(tmp_path):
    root = tmp_path / "public"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    with pytest.raises(Exception, match="record root is not private"):
        make_store(root).import_record(candidate(), source_verifier=lambda _ref: True)
    assert list(root.iterdir()) == []


def test_idempotency_binds_key_actor_and_body_and_recovers_pending_commit(tmp_path, monkeypatch):
    root = private_root(tmp_path)
    store = make_store(root)
    kwargs = dict(source_verifier_factory=lambda: (lambda _ref: True),
                  idempotency_key="synthetic-key-0123456789", actor="owner",
                  request_sha256="b" * 64)
    original = store._write_operation
    calls = 0

    def crash_after_record(root_fd, name, operation, *, replace):
        nonlocal calls
        calls += 1
        if replace:
            raise OSError("synthetic crash before operation commit")
        return original(root_fd, name, operation, replace=replace)

    monkeypatch.setattr(store, "_write_operation", crash_after_record)
    with pytest.raises(Exception, match="idempotency state unavailable"):
        store.import_idempotent(candidate(), **kwargs)
    assert (root / f"{DAY}.json").is_file()
    monkeypatch.setattr(store, "_write_operation", original)
    recovered = store.import_idempotent(candidate(), **kwargs)
    assert recovered["status"] == "duplicate"
    assert recovered["brief_id"] == "brief-synthetic-1"

    with pytest.raises(BriefImportConflict):
        store.import_idempotent(candidate(summary="different"), **{**kwargs, "request_sha256": "c" * 64})
    with pytest.raises(BriefImportConflict):
        store.import_idempotent(candidate(), **{**kwargs, "actor": "different-owner"})


def test_concurrent_idempotent_requests_are_single_create_and_different_key_conflicts(tmp_path):
    root = private_root(tmp_path)
    store = make_store(root)
    args = dict(source_verifier_factory=lambda: (lambda _ref: True),
                idempotency_key="synthetic-key-concurrent-123", actor="owner",
                request_sha256="d" * 64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _n: store.import_idempotent(candidate(), **args), range(2)))
    assert sorted(result["status"] for result in results) == ["created", "duplicate"]
    with pytest.raises(BriefImportConflict):
        store.import_idempotent(candidate(), **{**args,
            "idempotency_key": "synthetic-key-other-123456", "request_sha256": "e" * 64})


class _NoopHermes:
    configured = False


def make_http_client(tmp_path):
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-app-password\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    token = "synthetic-app-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 600

    task_root = tmp_path / "tasks"
    task_root.mkdir(mode=0o700)
    os.chmod(task_root, 0o700)
    tasks = TaskStore(str(task_root))
    created = tasks.create("Synthetic authoritative task", None, "source-task-key")
    source_rows = tasks.list_for_projection()["tasks"]
    source_ref = {"kind": "task", "id": created["task"]["id"],
                  "version": task_source_version(source_rows[0])}

    brief_root = private_root(tmp_path)
    audit_root = tmp_path / "audit"
    audit_root.mkdir(mode=0o700)
    os.chmod(audit_root, 0o700)
    app = FastAPI()
    app.include_router(create_daily_brief_agent_health_router(
        auth, _NoopHermes(), brief_store=DailyBriefRecordReadStore(str(brief_root)),
        task_store=tasks,
        brief_import_store=DailyBriefImportStore(str(brief_root)),
        brief_audit_store=DailyBriefAuditStore(str(audit_root / "daily-brief-audit.jsonl")),
    ))
    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    day = datetime.now(ZoneInfo(ZONE)).date().isoformat()
    body = {
        "mode": "manual_generate", "date": day, "timezone": ZONE,
        "idempotency_key": "synthetic-key-0123456789", "categories": ["synthetic"],
        "summary": "User-approved synthetic summary", "source_refs": [source_ref], "approved": True,
    }
    return client, body, source_ref, brief_root, audit_root, tasks, created["task"]


def test_http_manual_import_verifies_authoritative_task_then_get_rereads(tmp_path):
    client, body, _source_ref, root, audit_root, tasks, task = make_http_client(tmp_path)
    headers = {"Origin": "https://app.test"}
    response = client.post("/api/daily-brief", json=body, headers=headers)
    assert response.status_code == 201
    assert set(response.json()) == {"status", "brief_id", "date", "timezone"}
    assert response.json()["status"] == "created"
    assert "summary" not in response.text and str(root) not in response.text

    get = client.get(f"/api/daily-brief?date={body['date']}&timezone=Asia%2FShanghai")
    assert get.status_code == 200
    assert get.json()["status"] == "real"
    assert get.json()["items"][0]["summary"] == body["summary"]

    tasks.update(task["id"], {"expected_updated_at": task["updated_at"],
                               "title": "Synthetic task changed after approval"})
    stale = client.get(f"/api/daily-brief?date={body['date']}&timezone=Asia%2FShanghai")
    assert stale.status_code == 200
    assert stale.json()["status"] == "stale"
    assert stale.json()["items"] == []

    duplicate = client.post("/api/daily-brief", json=body, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    changed = {**body, "summary": "Different approved text"}
    assert client.post("/api/daily-brief", json=changed, headers=headers).status_code == 409
    changed_key = {**body, "idempotency_key": "synthetic-key-different-6789"}
    assert client.post("/api/daily-brief", json=changed_key, headers=headers).status_code in {409, 422}

    audit_text = (audit_root / "daily-brief-audit.jsonl").read_text(encoding="utf-8")
    assert body["summary"] not in audit_text
    assert body["source_refs"][0]["id"] not in audit_text
    assert str(root) not in audit_text


def test_http_manual_import_rejects_auth_origin_schema_and_unsupported_import(tmp_path):
    client, body, _ref, _root, _audit, _tasks, _task = make_http_client(tmp_path)
    assert client.post("/api/daily-brief", json=body, headers={"Origin": "https://evil.test"}).status_code == 403
    client.cookies.clear()
    assert client.post("/api/daily-brief", json=body, headers={"Origin": "https://app.test"}).status_code == 401
    client.cookies.set("sb_app_session", "synthetic-app-session")
    assert client.post("/api/daily-brief", json={**body, "extra": True},
                       headers={"Origin": "https://app.test"}).status_code == 422
    imported = {**body, "mode": "approved_import",
                "import_ref": {"kind": "existing_brief", "id": "brief-source",
                               "version": "c" * 64}}
    response = client.post("/api/daily-brief", json=imported, headers={"Origin": "https://app.test"})
    assert response.status_code == 501
    assert "brief-source" not in response.text
    duplicate_keys = '{"mode":"manual_generate","mode":"manual_generate"}'
    assert client.post("/api/daily-brief", content=duplicate_keys,
                       headers={"Origin": "https://app.test", "Content-Type": "application/json"}).status_code == 422
