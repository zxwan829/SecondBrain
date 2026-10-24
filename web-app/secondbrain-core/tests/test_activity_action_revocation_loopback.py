"""Real Core app/Uvicorn source-action grant and revocation regression."""
import hashlib
import json
import os
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx
import uvicorn

from secondbrain_core.app import create_app


def _private(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_real_core_source_action_grant_revoke_precedes_io_and_recovers(tmp_path, monkeypatch):
    roots = {name: _private(tmp_path / name) for name in (
        "raw", "review", "knowledge", "state", "journal", "projects", "briefs",
        "tasks", "notes", "memory",
    )}
    password = tmp_path / "synthetic-app-password"
    password.write_text("synthetic-action-revocation-password\n", encoding="utf-8")
    os.chmod(password, 0o600)
    secret = tmp_path / "synthetic-unused-promote-secret"
    secret.write_text("synthetic-unused-promote-secret-value-0000000000000000", encoding="utf-8")
    os.chmod(secret, 0o600)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    host, port = listener.getsockname()
    origin = f"http://{host}:{port}"
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]), "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]), "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_PROMOTE_UNLOCK_SECRET_FILE": str(secret), "SB_APP_PASSWORD_FILE": str(password),
        "SB_DASHBOARD_ORIGINS": origin, "SB_CORE_ALLOWED_HOSTS": host,
        "SB_HERMES_API_URL": "", "SB_HERMES_API_KEY": "", "SB_PROMOTE_ENABLED": "false",
        "SB_JOURNAL_ROOT": str(roots["journal"]), "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]),
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]), "SB_TASK_ROOT": str(roots["tasks"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]), "SB_PERSONAL_MEMORY_ENABLED": "true",
        "SB_PERSONAL_MEMORY_ROOT": str(roots["memory"]), "SB_PERSONAL_LEARNING_ENABLED": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = create_app()

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    day = stamp[:10]
    journal_store = app.state.journal_source_options_service.journal_store
    journal_store.append(day, "记一下 synthetic journal event", "synthetic-journal-op",
                         session_id="synthetic-session")
    app.state.task_store.create("Synthetic task event", day, "synthetic-task-op",
                                original_command="synthetic task command", session_id="synthetic-session")
    project = {"id": "project-synthetic", "title": "Synthetic Project", "status": "active",
               "updated_at": stamp}
    project_path = roots["projects"] / "project-synthetic.json"
    project_path.write_text(json.dumps(project, separators=(",", ":")), encoding="utf-8")
    os.chmod(project_path, 0o600)
    app.state.daily_brief_audit_store.append({
        "event_type": "daily_brief_import", "request_id": "synthetic-brief-request",
        "brief_id": "synthetic-brief-id", "date": day, "timezone": "UTC",
        "source_kind_counts": {"task": 1}, "outcome": "created", "recorded_at": stamp,
        "actor": "synthetic-owner",
    })
    app.state.personal_memory_store.create(
        content={"text": "Synthetic memory event"}, category="preference", fact_kind="user_stated",
        source_type="user_message", source_ref="synthetic-session:memory",
    )
    capture_id = "c" * 32
    capture_root = roots["state"] / "captures"
    capture_path = capture_root / (capture_id + ".json")
    capture_path.write_text(json.dumps({
        "capture_id": capture_id, "source_type": "text", "input_type": "txt",
        "captured_at": stamp, "updated_at": stamp, "status": "partial_success",
        "raw_path": "PRIVATE-raw.txt", "raw_sha256": "a" * 64,
        "review_path": "PRIVATE-review.md", "review_sha256": "b" * 64,
        "content_preview": "PRIVATE capture content", "capture_context": "PRIVATE context",
    }), encoding="utf-8")
    os.chmod(capture_path, 0o600)

    read_calls = {name: 0 for name in (
        "journal", "tasks", "projects", "daily_brief", "personal_memory", "capture",
    )}
    readers = {
        "journal": (journal_store, "read_source_day"),
        "tasks": (app.state.task_store, "list_for_projection_read_only"),
        "projects": (app.state.projects_source_store, "read_snapshot"),
        "daily_brief": (app.state.daily_brief_audit_store, "read_activity_events"),
        "personal_memory": (app.state.personal_memory_store, "read_activity_events"),
        "capture": (app.state.capture_service, "read_activity_events"),
    }
    for name, (store, method_name) in readers.items():
        original = getattr(store, method_name)

        def observed(*args, _name=name, _original=original, **kwargs):
            read_calls[_name] += 1
            return _original(*args, **kwargs)

        setattr(store, method_name, observed)

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False, proxy_headers=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as client:
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-action-revocation-password"})
            assert login.status_code == 200
            activity_url = f"/api/activity?from={day}&to={day}&timezone=UTC"
            expected_sources = {"journal", "tasks", "projects", "daily_brief", "personal_memory", "capture"}
            expected_kinds = {"journal", "task", "project", "daily_brief", "personal_memory", "capture"}
            baseline = client.get(activity_url, headers={"Origin": origin})
            assert baseline.status_code == 200, baseline.text
            assert baseline.json()["status"] == "ok", baseline.json()
            assert set(baseline.json()["source"]) == expected_sources
            assert {row["kind"] for row in baseline.json()["items"]} == expected_kinds

            for source, action in {
                "journal": "journal.read", "tasks": "task.read", "projects": "projects.read",
                "daily_brief": "daily_brief.read", "personal_memory": "personal_memory.read",
                "capture": "inbox.read",
            }.items():
                before = dict(read_calls)
                changed = client.patch("/api/auth/session/actions", headers={"Origin": origin},
                                       json={"action": action, "granted": False})
                assert changed.status_code == 200 and changed.json() == {
                    "status": "updated", "action": action, "granted": False,
                    "scope": "current_session",
                }
                denied = client.get(activity_url, headers={"Origin": origin})
                assert denied.status_code == 200, denied.text
                body = denied.json()
                assert body["status"] == "partial"
                assert source not in body["source"]
                denied_kind = {"tasks": "task", "projects": "project"}.get(source, source)
                assert {row["kind"] for row in body["items"]} == expected_kinds - {denied_kind}
                assert read_calls[source] == before[source]
                for allowed in expected_sources - {source}:
                    assert read_calls[allowed] == before[allowed] + 1

                restored = client.patch("/api/auth/session/actions", headers={"Origin": origin},
                                        json={"action": action, "granted": True})
                assert restored.status_code == 200 and restored.json()["granted"] is True
                recovered = client.get(activity_url, headers={"Origin": origin})
                assert recovered.status_code == 200
                assert set(recovered.json()["source"]) == expected_sources
                assert {row["kind"] for row in recovered.json()["items"]} == expected_kinds
                assert read_calls[source] == before[source] + 1

            denied_scope = client.patch("/api/auth/session/actions", headers={"Origin": origin},
                                        json={"action": "task.write", "granted": False})
            assert denied_scope.status_code == 400
            malformed = client.patch("/api/auth/session/actions", headers={"Origin": origin},
                                     json={"action": "journal.read", "granted": False, "extra": True})
            assert malformed.status_code == 400
            non_string = client.patch("/api/auth/session/actions", headers={"Origin": origin},
                                      json={"action": ["journal.read"], "granted": False})
            assert non_string.status_code == 400
            wrong_origin = client.patch("/api/auth/session/actions",
                                        headers={"Origin": "http://attacker.invalid"},
                                        json={"action": "journal.read", "granted": False})
            assert wrong_origin.status_code == 403

            # A valid session whose grant record disappears is inconsistent
            # authorization state. It must not silently recover the broad defaults.
            token = client.cookies.get(app.state.app_auth.COOKIE_NAME)
            session_id = hashlib.sha256(token.encode()).hexdigest()
            app.state.app_auth._session_actions.pop(session_id)
            before_missing_record = dict(read_calls)
            missing_record = client.get(activity_url, headers={"Origin": origin})
            assert missing_record.status_code == 403
            assert missing_record.json() == {"detail": "Action is not enabled"}
            assert read_calls == before_missing_record

            # Recovery requires a new authenticated login, which initializes the
            # exact documented login-time grant set; a PATCH cannot repair absence.
            cannot_regrant = client.patch("/api/auth/session/actions", headers={"Origin": origin},
                                          json={"action": "journal.read", "granted": True})
            assert cannot_regrant.status_code == 403
            assert read_calls == before_missing_record
            relogin = client.post("/api/auth/login", headers={"Origin": origin},
                                  json={"password": "synthetic-action-revocation-password"})
            assert relogin.status_code == 200
            recovered = client.get(activity_url, headers={"Origin": origin})
            assert recovered.status_code == 200
            assert recovered.json()["status"] == "ok"
            for name in read_calls:
                assert read_calls[name] == before_missing_record[name] + 1
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()
