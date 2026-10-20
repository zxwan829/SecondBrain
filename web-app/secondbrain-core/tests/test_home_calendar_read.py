import hashlib
import os
import time
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.calendar_read import create_calendar_read_router
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.tasks import TaskStore
from secondbrain_core.modules.web_app import create_web_app_router


class FakeHermes:
    configured = True

    async def capabilities(self):
        return {"features": {"session_api": True}}


class FakePromote:
    def get_decision(self, path, digest):
        return None


def make_auth(tmp_path):
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-password-value\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    token = "synthetic-app-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 600
    return auth, token


def make_client(auth, token, router):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    return client


def test_home_has_bounded_sections_and_module_provenance(tmp_path):
    review = tmp_path / "review"
    knowledge = tmp_path / "knowledge"
    review.mkdir(mode=0o700)
    knowledge.mkdir(mode=0o700)
    (review / "synthetic.md").write_text("# Synthetic review\nbody", encoding="utf-8")
    (knowledge / "synthetic.md").write_text("# Synthetic knowledge\nbody", encoding="utf-8")
    auth, token = make_auth(tmp_path)
    router = create_web_app_router(auth, FakeHermes(), FakePromote(), str(review), str(knowledge))
    body = make_client(auth, token, router).get("/api/home").json()

    assert body["review"]["items"][0]["title"] == "Synthetic review"
    assert body["knowledge"]["items"][0]["title"] == "Synthetic knowledge"
    for key in ("review", "knowledge", "projects", "today", "agent"):
        module = body[key]
        assert {"status", "items", "source", "freshness"} <= set(module)
        assert "checked_at" in module["freshness"]
    assert body["projects"]["status"] == "not_configured"
    assert body["today"]["status"] == "not_configured"


def test_home_file_walk_stops_at_fixed_candidate_cap(tmp_path):
    review = tmp_path / "review"
    review.mkdir(mode=0o700)
    for index in range(60):
        (review / f"{index:03}.md").write_text("# Synthetic\n", encoding="utf-8")
    auth, token = make_auth(tmp_path)
    router = create_web_app_router(auth, FakeHermes(), FakePromote(), str(review), str(tmp_path / "missing"))
    body = make_client(auth, token, router).get("/api/home").json()
    assert len(body["review"]["items"]) <= 50
    assert body["review"]["status"] == "partial"


def test_calendar_projects_only_journal_and_task_metadata(tmp_path):
    auth, token = make_auth(tmp_path)
    journal_root = tmp_path / "journal"
    task_root = tmp_path / "tasks"
    journal_root.mkdir(mode=0o700)
    task_root.mkdir(mode=0o700)
    journal = JournalStore(str(journal_root))
    tasks = TaskStore(str(task_root))
    day = date.today().isoformat()
    journal.append(day, "记一下 PRIVATE synthetic journal body", "synthetic-journal-key",
                   session_id="private-session-id")
    tasks.create("PRIVATE synthetic task title", day, "synthetic-task-key",
                 original_command="PRIVATE original task command", session_id="private-session-id")
    response = make_client(auth, token, create_calendar_read_router(auth, journal, tasks)).get(
        f"/api/calendar?from={day}&to={day}&timezone=Asia%2FShanghai")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "items", "source", "freshness"}
    assert body["status"] == "ok"
    assert body["source"] == ["journal", "tasks"]
    assert {row["kind"] for row in body["items"]} == {"journal", "task"}
    assert all(set(row) <= {"id", "kind", "date", "occurred_at", "status"}
               for row in body["items"])
    assert "PRIVATE" not in response.text
    assert "private-session-id" not in response.text
    assert "synthetic-journal-key" not in response.text
    assert "synthetic-task-key" not in response.text
    refreshed = make_client(auth, token, create_calendar_read_router(auth, journal, tasks)).get(
        f"/api/calendar?from={day}&to={day}&timezone=Asia%2FShanghai")
    assert [row["id"] for row in refreshed.json()["items"]] == [
        row["id"] for row in body["items"]
    ]


def test_calendar_requires_auth_and_rejects_unbounded_or_invalid_ranges(tmp_path):
    auth, token = make_auth(tmp_path)
    client = make_client(auth, token, create_calendar_read_router(auth))
    assert client.get("/api/calendar").status_code == 422
    assert client.get("/api/calendar?from=2026-10-01&to=2026-11-01").status_code == 400
    assert client.get("/api/calendar?from=2026-10-31&to=2026-11-01").status_code == 400
    assert client.get("/api/calendar?from=2026-02-30&to=2026-03-01").status_code == 400
    assert client.get("/api/calendar?from=2026-10-01&to=2026-10-01&timezone=NoSuch/Zone").status_code == 400
    client.cookies.clear()
    assert client.get("/api/calendar?from=2026-10-01&to=2026-10-01").status_code == 401


def test_calendar_task_projection_refuses_store_over_fixed_read_budget(tmp_path, monkeypatch):
    auth, token = make_auth(tmp_path)
    task_root = tmp_path / "tasks"
    task_root.mkdir(mode=0o700)
    tasks = TaskStore(str(task_root))
    tasks.path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    os.chmod(tasks.path, 0o600)
    monkeypatch.setattr(tasks, "list", lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("unbounded Task list must not be used by Calendar")))

    day = date.today().isoformat()
    response = make_client(auth, token, create_calendar_read_router(auth, task_store=tasks)).get(
        f"/api/calendar?from={day}&to={day}&timezone=Asia%2FShanghai")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["source"] == []
    assert body["items"] == []


def test_home_truncated_candidates_remain_partial_across_enumeration_orders(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from secondbrain_core.modules import web_app

    review = tmp_path / "review"
    review.mkdir(mode=0o700)
    for index in range(60):
        (review / f"{index:03}.md").write_text("# Synthetic\n", encoding="utf-8")

    real_scandir = os.scandir
    entries = list(real_scandir(review))
    monkeypatch.setattr(web_app.os, "scandir", lambda _path: nullcontext(iter(reversed(entries))))
    paths, truncated = web_app._bounded_markdown_paths(review, max_entries=500, max_depth=4, max_files=50)
    assert len(paths) == 50
    assert truncated is True
