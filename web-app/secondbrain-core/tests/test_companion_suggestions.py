import datetime as dt
import json
import multiprocessing
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from secondbrain_core.app import create_app
from secondbrain_core.modules.companion_suggestions import CompanionSuggestionStore
from secondbrain_core.modules.hermes_api import HermesAPI


def _private(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


async def _fake_session(self, session_id):
    return {"session_id": session_id}


def _app(tmp_path, monkeypatch, origin, host):
    roots = {name: _private(tmp_path / name) for name in
             ("review", "raw", "knowledge", "state", "memory", "projects", "briefs", "tasks", "journal", "notes")}
    password = tmp_path / "app-password"
    password.write_bytes(b"synthetic-companion-password\n")
    os.chmod(password, 0o600)
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]), "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password), "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host, "SB_HERMES_API_URL": "", "SB_PROMOTE_ENABLED": "false",
        "SB_PERSONAL_MEMORY_ENABLED": "false", "SB_PERSONAL_LEARNING_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]), "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]), "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(HermesAPI, "get_session", _fake_session)
    monkeypatch.setattr(HermesAPI, "_client", lambda self, timeout=30: httpx.AsyncClient(
        base_url="http://unused", transport=httpx.MockTransport(lambda req: httpx.Response(500))))
    return create_app(), roots


def _project_file(root, *, next_step="Review the synthetic milestone", updated="2026-10-22T00:00:00Z"):
    path = root / "project-one.json"
    payload = {"id": "project-one", "title": "Synthetic Project", "status": "active",
               "next_step": next_step, "updated_at": updated}
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _login(client, origin):
    result = client.post("/api/auth/login", headers={"Origin": origin},
                         json={"password": "synthetic-companion-password"})
    assert result.status_code == 200, result.text


def _process_pref_cas(root, key, result_queue):
    try:
        result_queue.put(CompanionSuggestionStore(root).set_preferences(
            enabled=True, categories=["task_due"], expected_revision=0,
            idempotency_key=key)["status"])
    except Exception as exc:
        result_queue.put(getattr(exc, "status_code", type(exc).__name__))


def test_companion_real_localhost_http_preferences_evaluate_feedback_and_source_drift(tmp_path, monkeypatch):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    app, roots = _app(tmp_path, monkeypatch, origin, host)
    _project_file(roots["projects"])
    task_store = app.state.task_store
    due = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    task_store.create("Synthetic due task", due, "synthetic-task-create")
    run_calls = []
    async def forbid_run(self, *args, **kwargs):
        run_calls.append(True)
        raise AssertionError("suggestions must not create a Hermes Run")
    monkeypatch.setattr(HermesAPI, "start_run", forbid_run)

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with httpx.Client(base_url=origin, timeout=3.0) as client:
            unauth = client.get("/api/companion/preferences")
            assert unauth.status_code == 401
            assert unauth.headers["cache-control"] == "private, no-store"
            assert not (roots["state"] / "companion-suggestions").exists()
            _login(client, origin)
            headers = {"Origin": origin}
            preferences = client.get("/api/companion/preferences", headers=headers)
            assert preferences.status_code == 200
            assert preferences.json() == {"event": "companion.preferences", "version": 1,
                                          "revision": 0, "enabled": False, "categories": []}
            assert preferences.headers["cache-control"] == "private, no-store"
            disabled = client.post("/api/companion/suggestions/evaluate", headers=headers, json={})
            assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
            assert not (roots["state"] / "companion-suggestions").exists()

            set_body = {"enabled": True, "categories": ["task_due", "project_next_step"],
                        "expected_revision": 0}
            saved = client.put("/api/companion/preferences", headers={**headers, "Idempotency-Key": "prefs-1"},
                               json=set_body)
            assert saved.status_code == 200, saved.text
            assert saved.json()["revision"] == 1 and saved.json()["settings"]["enabled"]
            replay = client.put("/api/companion/preferences", headers={**headers, "Idempotency-Key": "prefs-1"},
                                json=set_body)
            assert replay.status_code == 200 and replay.json()["status"] == "duplicate"
            conflict = client.put("/api/companion/preferences", headers={**headers, "Idempotency-Key": "prefs-1"},
                                  json={**set_body, "enabled": False})
            assert conflict.status_code == 409
            stale = client.put("/api/companion/preferences", headers={**headers, "Idempotency-Key": "prefs-stale"},
                               json=set_body)
            assert stale.status_code == 409

            evaluated = client.post("/api/companion/suggestions/evaluate", headers=headers, json={})
            assert evaluated.status_code == 200, evaluated.text
            assert evaluated.headers["cache-control"] == "private, no-store"
            body = evaluated.json()
            assert body["status"] == "available" and body["revision"] == 2
            assert len(body["items"]) == 2
            task_item = next(item for item in body["items"] if item["category"] == "task_due")
            project_item = next(item for item in body["items"] if item["category"] == "project_next_step")
            for item in body["items"]:
                assert set(item) == {"id", "category", "title", "reason", "source_ref", "state", "expires_at"}
                assert item["state"] == "shown"
                assert set(item["source_ref"]) == {"kind", "id", "version"}
                assert len(item["source_ref"]["version"]) == 64
            assert task_item["title"] == "Synthetic due task"
            assert task_item["source_ref"]["kind"] == "task"
            assert project_item["source_ref"]["kind"] == "project"
            assert "Review the synthetic milestone" not in evaluated.text

            repeated = client.post("/api/companion/suggestions/evaluate", headers=headers, json={})
            assert repeated.status_code == 200
            assert {item["id"] for item in repeated.json()["items"]} == {item["id"] for item in body["items"]}
            assert len(app.state.companion_suggestion_store.read()["suggestions"]) == 2

            listed = client.get("/api/companion/suggestions", headers=headers)
            assert listed.status_code == 200 and len(listed.json()["items"]) == 2
            assert listed.headers["cache-control"] == "private, no-store"
            receipt_url = f"/api/companion/suggestions/{task_item['id']}/feedback"
            feedback_headers = {**headers, "Idempotency-Key": "feedback-task-1"}
            feedback_body = {"decision": "accepted", "expected_revision": 1}
            accepted = client.post(receipt_url, headers=feedback_headers, json=feedback_body)
            assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
            replay = client.post(receipt_url, headers=feedback_headers, json=feedback_body)
            assert replay.status_code == 200 and replay.json()["status"] == "duplicate"
            changed_replay = client.post(receipt_url, headers=feedback_headers,
                                         json={"decision": "dismissed", "expected_revision": 1})
            assert changed_replay.status_code == 409

            _project_file(roots["projects"], next_step="Changed source version")
            listed = client.get("/api/companion/suggestions", headers=headers)
            assert listed.status_code == 200
            # The Task item was accepted above; only a still-shown, current
            # source may be returned, so the changed Project is also hidden.
            assert listed.json()["items"] == []
            assert run_calls == []

            disabled = client.put("/api/companion/preferences", headers={**headers, "Idempotency-Key": "prefs-off"},
                                  json={"enabled": False, "categories": [], "expected_revision": 4})
            assert disabled.status_code == 200, disabled.text
            empty = client.get("/api/companion/suggestions", headers=headers)
            assert empty.status_code == 200 and empty.json()["items"] == []
            assert empty.json()["status"] == "disabled"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


def test_companion_permission_denial_precedes_source_io_and_reads_are_side_effect_free(tmp_path, monkeypatch):
    app, roots = _app(tmp_path, monkeypatch, "https://testserver", "testserver")
    store = app.state.companion_suggestion_store
    assert store.read()["settings"] == {"enabled": False, "categories": []}
    assert not (roots["state"] / "companion-suggestions").exists()
    reads = []
    original = app.state.task_store.list_for_projection
    monkeypatch.setattr(app.state.task_store, "list_for_projection",
                        lambda: reads.append("task") or original())
    denied_action = {"action": "task.read"}
    original_auth = app.state.app_auth.require_action
    def guarded(request, action):
        if action == denied_action["action"]:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Action is not enabled")
        return original_auth(request, action)
    monkeypatch.setattr(app.state.app_auth, "require_action", guarded)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client, "https://testserver")
        headers = {"Origin": "https://testserver"}
        saved = client.put("/api/companion/preferences", headers={**headers, "Idempotency-Key": "prefs"},
                           json={"enabled": True, "categories": ["task_due"], "expected_revision": 0})
        assert saved.status_code == 200
        denied = client.post("/api/companion/suggestions/evaluate", headers=headers, json={})
        assert denied.status_code == 200 and denied.json()["status"] == "partial"
        assert denied.json()["items"] == [] and reads == []
        assert denied.headers["cache-control"] == "private, no-store"
        denied_action["action"] = None
        malformed = client.post("/api/companion/suggestions/evaluate", headers=headers,
                                json={"automatic": True})
        assert malformed.status_code == 400 and reads == []


def test_companion_preferences_compare_and_swap_race_has_one_winner(tmp_path):
    store = CompanionSuggestionStore(tmp_path / "companion")
    def write(name):
        try:
            return store.set_preferences(enabled=True, categories=["task_due"], expected_revision=0,
                                         idempotency_key=name)["status"]
        except Exception as exc:
            return (getattr(exc, "status_code", type(exc).__name__), getattr(exc, "detail", str(exc)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("cas-a", "cas-b")))
    assert [item[0] for item in results if isinstance(item, tuple)] == [409], results
    assert results.count("saved") == 1
    assert store.read()["revision"] == 1


def test_companion_preferences_cross_process_cas_has_one_winner(tmp_path):
    root = str(tmp_path / "companion")
    context = multiprocessing.get_context("fork")
    output = context.Queue()
    workers = [context.Process(target=_process_pref_cas, args=(root, key, output))
               for key in ("process-a", "process-b")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0
    results = sorted((str(output.get(timeout=2)) for _ in workers))
    assert results == ["409", "saved"]
    assert CompanionSuggestionStore(root).read()["revision"] == 1


def test_companion_store_corruption_and_unsafe_permissions_fail_closed(tmp_path):
    root = tmp_path / "companion"
    root.mkdir(mode=0o700)
    path = root / "companion-suggestions.json"
    path.write_text("{bad json", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(Exception):
        CompanionSuggestionStore(root).read()
    path.unlink()
    malformed = CompanionSuggestionStore._empty()
    malformed["suggestions"] = [{"id": "a" * 32, "category": "task_due", "title": "x", "reason": "y",
        "source_ref": {"kind": "task", "id": "id", "version": "b" * 64}, "state": [],
        "created_at": "2026-10-22T00:00:00Z", "expires_at": "2026-10-23T00:00:00Z",
        "revision": 1, "feedback": []}]
    path.write_bytes(json.dumps(malformed).encode("utf-8"))
    os.chmod(path, 0o600)
    with pytest.raises(Exception) as error:
        CompanionSuggestionStore(root).read()
    assert getattr(error.value, "status_code", None) == 503
    path.unlink()
    os.chmod(root, 0o750)
    with pytest.raises(Exception):
        CompanionSuggestionStore(root).read()
