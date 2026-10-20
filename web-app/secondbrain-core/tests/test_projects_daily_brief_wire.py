import hashlib
import json
import os
import re
import time
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.daily_brief_agent_health import create_daily_brief_agent_health_router
from secondbrain_core.modules.daily_brief_store import DailyBriefRecordReadStore
from secondbrain_core.modules.projects_activity_read import create_projects_activity_router
from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore
from secondbrain_core.app import create_app


DAY = "2026-10-20"
ZONE = "Asia/Shanghai"
REF = {"kind": "note", "id": "note-synthetic", "version": "a" * 64}


class FakeHermes:
    configured = False


def private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def write_project(root, project_id, **extra):
    path = root / f"{project_id}.json"
    payload = {"id": project_id, "title": "Synthetic project", "status": "active", **extra}
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def write_brief(root, *, day=DAY, timezone=ZONE, **overrides):
    record = {
        "brief_id": "brief-synthetic",
        "date": day,
        "timezone": timezone,
        "generated_at": "2026-10-20T08:00:00+08:00",
        "generation_status": "generated",
        "categories": ["synthetic"],
        "summary": "Synthetic summary must not escape without trusted verifier",
        "source_refs": [REF],
    }
    record.update(overrides)
    path = root / f"{day}.json"
    path.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def make_client(tmp_path, *, projects_store=None, brief_store=None, deny_projects=False):
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-app-password-value\n")
    os.chmod(password_file, 0o600)
    auth = AppSessionAuth(str(password_file), ["https://app.test"])
    if deny_projects:
        require_action = auth.require_action

        def guarded_require_action(request, action):
            if action == "projects.read":
                raise HTTPException(status_code=403, detail="forbidden")
            return require_action(request, action)

        auth.require_action = guarded_require_action
    token = "synthetic-app-session"
    auth._sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time() + 600
    app = FastAPI()
    app.include_router(create_projects_activity_router(auth, projects_store=projects_store))
    app.include_router(create_daily_brief_agent_health_router(
        auth, FakeHermes(), brief_store=brief_store, projects_store=projects_store,
    ))
    client = TestClient(app, base_url="https://app.test")
    client.cookies.set(auth.COOKIE_NAME, token)
    return client


def assert_checked_at(value):
    assert isinstance(value, str)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)


def test_projects_wire_not_configured_empty_and_auth_contract(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/projects?limit=7&offset=2")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "items", "pagination", "source", "freshness"}
    assert body["status"] == "not_configured"
    assert body["items"] == [] and body["source"] is None
    assert body["pagination"] == {"limit": 7, "offset": 2, "has_more": False}
    assert_checked_at(body["freshness"]["checked_at"])

    client.cookies.clear()
    assert client.get("/api/projects").status_code == 401
    client.cookies.set(AppSessionAuth.COOKIE_NAME, "synthetic-app-session")
    assert client.get("/api/projects", headers={"Origin": "https://evil.test"}).status_code == 403


def test_projects_wire_verified_records_pagination_and_exact_item_allowlist(tmp_path):
    root = private_dir(tmp_path / "projects")
    write_project(root, "project-a", next_step="Synthetic next", updated_at="2026-10-20T08:00:00Z")
    write_project(root, "project-b")
    store = ProjectsSourceReadStore(str(root))
    client = make_client(tmp_path, projects_store=store)

    response = client.get("/api/projects?limit=1&offset=0")
    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"status", "items", "pagination", "source", "freshness"}
    assert body["status"] == "real"
    assert body["source"] == {"kind": "explicit-project-index"}
    assert body["pagination"] == {"limit": 1, "offset": 0, "has_more": True}
    item = body["items"][0]
    assert set(item) == {"id", "title", "status", "next_step", "updated_at", "source_ref"}
    assert item["source_ref"] == {"id": item["id"], "version": store.read_snapshot().documents[0].sha256}
    assert "path" not in response.text
    assert_checked_at(body["freshness"]["checked_at"])

    assert client.get("/api/projects?limit=51").status_code == 400
    assert client.get("/api/projects?offset=5001").status_code == 400


def test_projects_wire_downgrades_unverified_associations_and_read_budget(tmp_path):
    root = private_dir(tmp_path / "projects")
    write_project(root, "project-a", linked_notes=[{"id": "note-x", "version": "b" * 64}],
                  recent_activity={"kind": "task", "occurred_at": "2026-10-20T08:00:00Z"})
    response = make_client(tmp_path, projects_store=ProjectsSourceReadStore(str(root))).get("/api/projects")
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert "linked_notes" not in response.json()["items"][0]
    assert "recent_activity" not in response.json()["items"][0]

    write_project(root, "project-b")
    capped = make_client(tmp_path, projects_store=ProjectsSourceReadStore(str(root), max_entries=1))
    page = capped.get("/api/projects?limit=50").json()
    assert page["status"] == "partial"
    assert page["pagination"]["has_more"] is True


def test_projects_wire_empty_and_unavailable_are_distinct(tmp_path):
    empty_root = private_dir(tmp_path / "empty")
    empty = make_client(tmp_path, projects_store=ProjectsSourceReadStore(str(empty_root))).get("/api/projects").json()
    assert empty["status"] == "empty"
    assert empty["source"] == {"kind": "explicit-project-index"}

    unavailable_root = tmp_path / "unavailable"
    unavailable = make_client(tmp_path, projects_store=ProjectsSourceReadStore(str(unavailable_root))).get(
        "/api/projects").json()
    assert unavailable["status"] == "unavailable"
    assert unavailable["items"] == [] and unavailable["source"] is None


def test_daily_brief_wire_not_configured_and_auth_contract(tmp_path):
    client = make_client(tmp_path)
    response = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "items", "source", "freshness"}
    assert body["status"] == "not_configured"
    assert body["items"] == [] and body["source"] is None
    assert_checked_at(body["freshness"]["checked_at"])
    client.cookies.clear()
    assert client.get(f"/api/daily-brief?date={DAY}").status_code == 401
    client.cookies.set(AppSessionAuth.COOKIE_NAME, "synthetic-app-session")
    assert client.get(f"/api/daily-brief?date={DAY}", headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.get("/api/daily-brief?date=2026-02-30").status_code == 400
    assert client.get(f"/api/daily-brief?date={DAY}&timezone=NoSuch/Zone").status_code == 400


def test_daily_brief_wire_withholds_unverified_summary_and_never_claims_real(tmp_path):
    root = private_dir(tmp_path / "briefs")
    write_brief(root)
    client = make_client(tmp_path, brief_store=DailyBriefRecordReadStore(str(root)))
    response = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}")
    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"status", "items", "source", "freshness"}
    assert body["status"] == "partial"
    assert body["items"] == []
    assert body["source"] == {"kind": "core-daily-brief-store"}
    assert "Synthetic summary" not in response.text
    assert_checked_at(body["freshness"]["checked_at"])


def test_daily_brief_verifies_exact_project_source_and_withholds_stale_or_unknown_refs(tmp_path):
    projects_root = private_dir(tmp_path / "projects")
    project_path = write_project(projects_root, "project-source")
    project_version = hashlib.sha256(project_path.read_bytes()).hexdigest()
    project_store = ProjectsSourceReadStore(str(projects_root))
    briefs_root = private_dir(tmp_path / "briefs")
    client = make_client(tmp_path, projects_store=project_store,
                         brief_store=DailyBriefRecordReadStore(str(briefs_root)))

    write_brief(briefs_root, source_refs=[{"kind": "project", "id": "project-source",
                                           "version": project_version}])
    verified = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()
    assert verified["status"] == "real"
    assert len(verified["items"]) == 1
    assert verified["items"][0]["source_refs"] == [{
        "kind": "project", "id": "project-source", "version": project_version,
    }]

    write_brief(briefs_root, source_refs=[{"kind": "project", "id": "project-source",
                                           "version": "0" * 64}])
    stale = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()
    assert stale["status"] == "stale" and stale["items"] == []
    assert "Synthetic summary" not in json.dumps(stale)

    for reference in (
        {"kind": "project", "id": "missing-project", "version": "a" * 64},
    ):
        write_brief(briefs_root, source_refs=[reference])
        body = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()
        assert body["items"] == []
        assert "Synthetic summary" not in json.dumps(body)
        assert body["status"] == "partial"

    for kind in ("task", "note", "capture", "review", "journal"):
        write_brief(briefs_root, source_refs=[{"kind": kind, "id": f"{kind}-id",
                                               "version": "b" * 64}])
        body = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()
        assert body["status"] == "partial" and body["items"] == []
        assert "Synthetic summary" not in json.dumps(body)


def test_daily_brief_does_not_disclose_project_existence_without_projects_permission(tmp_path):
    projects_root = private_dir(tmp_path / "projects")
    project_path = write_project(projects_root, "project-private")
    version = hashlib.sha256(project_path.read_bytes()).hexdigest()
    briefs_root = private_dir(tmp_path / "briefs")
    write_brief(briefs_root, source_refs=[
        {"kind": "project", "id": "project-private", "version": version},
        {"kind": "project", "id": "project-private", "version": "0" * 64},
    ])
    client = make_client(tmp_path, projects_store=ProjectsSourceReadStore(str(projects_root)),
                         brief_store=DailyBriefRecordReadStore(str(briefs_root)),
                         deny_projects=True)
    response = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}")
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["items"] == []
    assert "project-private" not in response.text
    assert "Synthetic summary" not in response.text


def test_daily_brief_does_not_verify_absence_from_incomplete_project_snapshot(tmp_path):
    projects_root = private_dir(tmp_path / "projects")
    write_project(projects_root, "project-present")
    store = ProjectsSourceReadStore(str(projects_root), max_entries=0)
    briefs_root = private_dir(tmp_path / "briefs")
    write_brief(briefs_root, source_refs=[{"kind": "project", "id": "not-enumerated",
                                           "version": "a" * 64}])
    response = make_client(tmp_path, projects_store=store,
                           brief_store=DailyBriefRecordReadStore(str(briefs_root))).get(
                               f"/api/daily-brief?date={DAY}&timezone={ZONE}")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["items"] == []


def test_daily_brief_wire_distinguishes_empty_unavailable_failed_stale_and_generation_failure(tmp_path):
    root = private_dir(tmp_path / "briefs")
    store = DailyBriefRecordReadStore(str(root))
    client = make_client(tmp_path, brief_store=store)
    assert client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()["status"] == "empty"

    write_brief(root, generation_status="stale")
    assert client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()["status"] == "stale"
    write_brief(root, generation_status="failed", source_refs=[])
    assert client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()["status"] == "failed"
    write_brief(root, extra_field="must-fail")
    assert client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()["status"] == "failed"

    unavailable = make_client(tmp_path, brief_store=DailyBriefRecordReadStore(str(tmp_path / "missing")))
    unavailable_body = unavailable.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}").json()
    assert unavailable_body["status"] == "unavailable"
    assert unavailable_body["source"] == {"kind": "core-daily-brief-store"}


def test_daily_brief_same_date_timezone_mismatch_never_falls_back(tmp_path):
    root = private_dir(tmp_path / "briefs")
    write_brief(root)
    client = make_client(tmp_path, brief_store=DailyBriefRecordReadStore(str(root)))
    body = client.get(f"/api/daily-brief?date={DAY}&timezone=UTC").json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["source"] == {"kind": "core-daily-brief-store"}


def test_create_app_wires_only_explicit_synthetic_roots_and_keeps_brief_unverified(tmp_path):
    roots = {name: private_dir(tmp_path / name) for name in
             ("review", "raw", "knowledge", "state", "projects", "briefs")}
    password_file = tmp_path / "app-password"
    password_file.write_bytes(b"synthetic-app-password-value\n")
    os.chmod(password_file, 0o600)
    write_project(roots["projects"], "project-from-app")
    write_brief(roots["briefs"])
    env = {
        "SB_REVIEW_ROOT": str(roots["review"]),
        "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
        "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_APP_PASSWORD_FILE": str(password_file),
        "SB_DASHBOARD_ORIGINS": "https://testserver",
        "SB_CORE_ALLOWED_HOSTS": "testserver",
        "SB_HERMES_API_URL": "",
        "SB_PROMOTE_ENABLED": "false",
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]),
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
    }
    with patch.dict(os.environ, env, clear=True):
        app = create_app()
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/auth/login", headers={"Origin": "https://testserver"},
                            json={"password": "synthetic-app-password-value"})
        assert login.status_code == 200
        projects = client.get("/api/projects?limit=5&offset=0")
        brief = client.get(f"/api/daily-brief?date={DAY}&timezone={ZONE}")
        assert projects.status_code == brief.status_code == 200
        assert projects.json()["status"] == "real"
        assert projects.json()["items"][0]["id"] == "project-from-app"
        assert brief.json()["status"] == "partial"
        assert brief.json()["items"] == []
        assert "Synthetic summary" not in brief.text
