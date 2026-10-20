import os
import hashlib
import json
import multiprocessing
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


def _process_import(root, key, request_sha256, barrier, results):
    store = DailyBriefImportStore(
        root, clock=lambda: datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        id_factory=lambda: f"brief-process-{os.getpid()}",
    )
    barrier.wait(timeout=10)
    try:
        value = store.import_idempotent(
            candidate(), source_verifier_factory=lambda: (lambda _ref: True),
            idempotency_key=key, actor="owner", request_sha256=request_sha256,
        )
        results.put(("ok", value["status"], value["brief_id"], value["operation_id"]))
    except Exception as exc:
        results.put((type(exc).__name__, str(exc), ""))


def _process_crash_after_record(root, key, request_sha256, results):
    store = DailyBriefImportStore(
        root, clock=lambda: datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        id_factory=lambda: "brief-process-crash",
    )
    audit = DailyBriefAuditStore(os.path.join(root, "daily-brief-audit.jsonl"))
    original = store._write_operation

    def crash_on_commit(root_fd, name, operation, *, replace):
        if replace:
            os._exit(73)
        return original(root_fd, name, operation, replace=replace)

    store._write_operation = crash_on_commit
    try:
        store.import_idempotent(
            candidate(), source_verifier_factory=lambda: (lambda _ref: True),
            idempotency_key=key, actor="owner", request_sha256=request_sha256,
            before_commit=lambda value: audit.append({
                "event_type": "daily_brief_import", "request_id": "synthetic-crash-request",
                "brief_id": value["brief_id"], "date": DAY, "timezone": ZONE,
                "source_kind_counts": {"task": 1}, "outcome": "created",
                "recorded_at": "2026-10-20T00:00:00+08:00", "actor": "owner",
            }),
        )
    except Exception as exc:
        results.put((type(exc).__name__, "", ""))


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


@pytest.mark.parametrize("process_count", [2, 4, 8], ids=["2-process-cold", "4-process-cold", "8-process-cold"])
def test_cross_process_cold_start_replays_converge_without_lost_lock_creation(tmp_path, process_count):
    root = private_root(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(process_count)
    results = ctx.Queue()
    keys = ["synthetic-process-key-123456"] * process_count
    request_hashes = ["a" * 64] * process_count
    processes = [ctx.Process(target=_process_import,
                             args=(str(root), key, request_hashes[i],
                                   barrier, results))
                 for i, key in enumerate(keys)]
    for process in processes:
        process.start()
    values = [results.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert (root / f"{DAY}.json").is_file()
    assert [value[1] for value in values].count("created") == 1, values
    assert [value[1] for value in values].count("duplicate") == process_count - 1, values
    assert len({value[2] for value in values}) == 1
    assert len({value[3] for value in values}) == 1


def test_different_process_keys_for_same_day_conflict_create_only(tmp_path):
    root = private_root(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    results = ctx.Queue()
    processes = [ctx.Process(target=_process_import,
                             args=(str(root), key, request_hash, barrier, results))
                 for key, request_hash in (("synthetic-process-key-123456", "a" * 64),
                                           ("synthetic-process-key-other-789", "b" * 64))]
    for process in processes:
        process.start()
    values = [results.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert sorted(value[0] for value in values) == ["BriefImportConflict", "ok"]
    assert sum(value[1] == "created" for value in values) == 1
    assert len(list(root.glob("20??-??-??.json"))) == 1


def test_process_death_after_record_publish_recovers_after_restart(tmp_path):
    root = private_root(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    results = ctx.Queue()
    process = ctx.Process(target=_process_crash_after_record,
                          args=(str(root), "synthetic-crash-key-123456", "f" * 64, results))
    process.start()
    process.join(timeout=20)
    assert process.exitcode == 73
    assert (root / f"{DAY}.json").is_file()

    recovery_store = DailyBriefImportStore(
        str(root), clock=lambda: datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        id_factory=lambda: "brief-new-process",
    )
    assert recovery_store.has_pending_for_date(DAY) is True
    recovered = recovery_store.import_idempotent(
        candidate(), source_verifier_factory=lambda: (lambda _ref: True),
        idempotency_key="synthetic-crash-key-123456", actor="owner", request_sha256="f" * 64,
        before_commit=lambda value: DailyBriefAuditStore(
            os.path.join(root, "daily-brief-audit.jsonl")).append({
                "event_type": "daily_brief_import", "request_id": "synthetic-retry-request",
                "brief_id": value["brief_id"], "date": DAY, "timezone": ZONE,
                "source_kind_counts": {"task": 1}, "outcome": "created",
                "recorded_at": "2026-10-20T00:00:01+08:00", "actor": "owner",
            }),
    )
    assert recovered["status"] == "duplicate"
    assert recovered["brief_id"] == "brief-process-crash"
    assert recovery_store.has_pending_for_date(DAY) is False
    audit_lines = (root / "daily-brief-audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 1
    assert json.loads(audit_lines[0])["outcome"] == "created"


class _NoopHermes:
    configured = False


class _SwitchAuditStore:
    def __init__(self, path):
        self.store = DailyBriefAuditStore(path)
        self.fail = False
        self.fail_open = False
        self.fail_fsync = False
        self.fail_short_write = False
        self.fail_published_fsync = False

    def append(self, event):
        if self.fail:
            raise OSError("synthetic audit fsync failure")
        if self.fail_open:
            original_open = os.open
            def fail_audit_open(path, *args, **kwargs):
                name = os.path.basename(os.fspath(path))
                if name in {".daily-brief-audit.lock", "daily-brief-audit.jsonl"} \
                        or name.startswith(".daily-brief-audit-tmp-"):
                    raise PermissionError("synthetic audit open failure")
                return original_open(path, *args, **kwargs)
            os.open = fail_audit_open
            try:
                return self.store.append(event)
            finally:
                os.open = original_open
        if self.fail_fsync:
            original_fsync = os.fsync
            def fail_fsync_once(_fd):
                raise OSError("synthetic audit fsync failure")
            os.fsync = fail_fsync_once
            try:
                return self.store.append(event)
            finally:
                os.fsync = original_fsync
        if self.fail_published_fsync:
            original_fsync = os.fsync
            calls = 0
            def fail_after_replace(fd):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("synthetic audit directory fsync failure")
                return original_fsync(fd)
            os.fsync = fail_after_replace
            try:
                return self.store.append(event)
            finally:
                os.fsync = original_fsync
        if self.fail_short_write:
            original_write = os.write
            calls = 0
            def fail_after_prefix(fd, data):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return original_write(fd, data[:max(1, len(data) // 2)])
                raise OSError("synthetic audit short write")
            os.write = fail_after_prefix
            try:
                return self.store.append(event)
            finally:
                os.write = original_write
        return self.store.append(event)


def make_http_client(tmp_path, *, audit_store=None):
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
    audit_store = audit_store or DailyBriefAuditStore(str(audit_root / "daily-brief-audit.jsonl"))
    app = FastAPI()
    app.include_router(create_daily_brief_agent_health_router(
        auth, _NoopHermes(), brief_store=DailyBriefRecordReadStore(str(brief_root)),
        task_store=tasks,
        brief_import_store=DailyBriefImportStore(str(brief_root)),
        brief_audit_store=audit_store,
    ))
    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    day = datetime.now(ZoneInfo(ZONE)).date().isoformat()
    body = {
        "mode": "manual_generate", "date": day, "timezone": ZONE,
        "idempotency_key": "synthetic-key-0123456789", "categories": ["synthetic"],
        "summary": "User-approved synthetic summary", "source_refs": [source_ref], "approved": True,
    }
    return client, body, source_ref, brief_root, audit_root, tasks, created["task"], audit_store


def test_http_manual_import_verifies_authoritative_task_then_get_rereads(tmp_path):
    client, body, _source_ref, root, audit_root, tasks, task, _audit_store = make_http_client(tmp_path)
    headers = {"Origin": "https://app.test"}
    response = client.post("/api/daily-brief", json=body, headers=headers)
    assert response.status_code == 201
    assert set(response.json()) == {
        "status", "brief_id", "date", "timezone", "record_version", "operation_id",
    }
    assert response.json()["status"] == "created"
    assert response.json()["record_version"] == hashlib.sha256(
        (root / f"{body['date']}.json").read_bytes()).hexdigest()
    assert response.json()["operation_id"].startswith("dbi-")
    assert "summary" not in response.text and str(root) not in response.text

    get = client.get(f"/api/daily-brief?date={body['date']}&timezone=Asia%2FShanghai")
    assert get.status_code == 200
    assert set(get.json()) == {"status", "items", "source", "freshness"}
    assert get.json()["status"] == "real"
    assert get.json()["source"] == {"kind": "core-daily-brief-store"}
    assert set(get.json()["freshness"]) == {"checked_at"}
    assert set(get.json()["items"][0]) == {
        "brief_id", "date", "timezone", "generated_at", "generation_status",
        "categories", "summary", "source_refs",
    }
    assert get.json()["items"][0]["summary"] == body["summary"]

    changed_key = {**body, "idempotency_key": "synthetic-key-different-6789"}
    changed_key_conflict = client.post("/api/daily-brief", json=changed_key, headers=headers)
    assert changed_key_conflict.status_code == 409
    assert changed_key_conflict.json() == {"detail": "Daily Brief conflict"}

    tasks.update(task["id"], {"expected_updated_at": task["updated_at"],
                               "title": "Synthetic task changed after approval"})
    stale = client.get(f"/api/daily-brief?date={body['date']}&timezone=Asia%2FShanghai")
    assert stale.status_code == 200
    assert stale.json()["status"] == "stale"
    assert stale.json()["items"] == []

    duplicate = client.post("/api/daily-brief", json=body, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json() == {"status": "duplicate", "brief_id": response.json()["brief_id"],
                                "date": body["date"], "timezone": "Asia/Shanghai",
                                "record_version": response.json()["record_version"],
                                "operation_id": response.json()["operation_id"]}
    changed = {**body, "summary": "Different approved text"}
    conflict = client.post("/api/daily-brief", json=changed, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Daily Brief conflict"}

    audit_text = (audit_root / "daily-brief-audit.jsonl").read_text(encoding="utf-8")
    assert body["summary"] not in audit_text
    assert body["source_refs"][0]["id"] not in audit_text
    assert str(root) not in audit_text


def test_http_manual_import_rejects_auth_origin_schema_and_unsupported_import(tmp_path):
    client, body, _ref, _root, _audit, _tasks, _task, _audit_store = make_http_client(tmp_path)
    denied_origin = client.post("/api/daily-brief", json=body, headers={"Origin": "https://evil.test"})
    assert denied_origin.status_code == 403
    assert denied_origin.json() == {"detail": "Trusted App Origin required"}
    client.cookies.clear()
    unauthenticated = client.post("/api/daily-brief", json=body, headers={"Origin": "https://app.test"})
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {"detail": "App session required"}
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
    assert client.post("/api/daily-brief", json={**body, "mode": []},
                       headers={"Origin": "https://app.test"}).status_code == 422
    nested = '{"mode":' + "[" * 2000 + "0" + "]" * 2000 + "}"
    assert client.post("/api/daily-brief", content=nested,
                       headers={"Origin": "https://app.test", "Content-Type": "application/json"}).status_code == 422


@pytest.mark.parametrize("failure", ["open", "append", "fsync", "short_write", "directory_fsync"])
def test_http_audit_failure_rolls_back_uncommitted_record_then_retry_succeeds(tmp_path, failure):
    audit = _SwitchAuditStore(str(tmp_path / "audit" / "daily-brief-audit.jsonl"))
    client, body, _ref, root, audit_root, _tasks, _task, _audit = make_http_client(
        tmp_path, audit_store=audit)
    audit.store.append({
        "event_type": "daily_brief_import", "request_id": "synthetic-seed-request",
        "brief_id": "", "date": body["date"], "timezone": "Asia/Shanghai",
        "source_kind_counts": {"task": 1}, "outcome": "rejected",
        "recorded_at": "2026-10-20T00:00:00+08:00", "actor": "owner",
    })
    audit_before = (audit_root / "daily-brief-audit.jsonl").read_bytes()
    audit.fail_open = failure == "open"
    audit.fail = failure == "append"
    audit.fail_fsync = failure == "fsync"
    audit.fail_short_write = failure == "short_write"
    audit.fail_published_fsync = failure == "directory_fsync"
    failed = client.post("/api/daily-brief", json=body, headers={"Origin": "https://app.test"})
    assert failed.status_code == 503
    assert failed.json() == {"detail": "Daily Brief unavailable"}
    assert body["summary"] not in failed.text and str(root) not in failed.text
    pending = failure == "directory_fsync"
    if not pending:
        assert (audit_root / "daily-brief-audit.jsonl").read_bytes() == audit_before
    assert (root / f"{body['date']}.json").exists() is pending
    assert bool(list(root.glob(".op-*.json"))) is pending
    first_get = client.get(f"/api/daily-brief?date={body['date']}&timezone=Asia%2FShanghai")
    assert first_get.status_code == 200
    assert first_get.json()["items"] == []
    assert first_get.json()["status"] == ("unavailable" if pending else "empty")

    audit.fail = False
    audit.fail_open = False
    audit.fail_fsync = False
    audit.fail_short_write = False
    audit.fail_published_fsync = False
    retried = client.post("/api/daily-brief", json=body, headers={"Origin": "https://app.test"})
    assert retried.status_code == (200 if pending else 201)
    assert retried.json()["status"] == ("duplicate" if pending else "created")
    assert set(retried.json()) == {
        "status", "brief_id", "date", "timezone", "record_version", "operation_id",
    }
    assert (root / f"{body['date']}.json").is_file()
    audit_text = (audit_root / "daily-brief-audit.jsonl").read_text(encoding="utf-8")
    assert '"outcome":"created"' in audit_text
    audit_rows = [json.loads(line) for line in audit_text.splitlines()]
    assert all(set(row) == DailyBriefAuditStore._FIELDS for row in audit_rows)
    assert sum(row["outcome"] == "created" for row in audit_rows) == 1
    assert body["summary"] not in audit_text and body["source_refs"][0]["id"] not in audit_text
