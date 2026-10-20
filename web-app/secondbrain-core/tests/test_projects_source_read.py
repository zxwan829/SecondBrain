import json
import os

from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore


def make_root(path):
    path.mkdir()
    os.chmod(path, 0o700)
    return path


def project(root, name, project_id, **extra):
    path = root / name
    payload = {"id": project_id, "title": "Synthetic", "status": "active", **extra}
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def test_unconfigured_projects_source_does_not_scan_any_root(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "scandir", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("unconfigured source must not be scanned")))
    result = ProjectsSourceReadStore(None).read_snapshot()
    assert result.configured is False
    assert result.status == "not_configured"
    assert result.documents == ()


def test_projects_source_reads_only_explicit_root_and_returns_digest_not_path(tmp_path):
    root = make_root(tmp_path / "projects")
    first = project(root, "project.json", "proj-alpha")
    outside = tmp_path / "outside.json"
    outside.write_text('{"id":"outside"}', encoding="utf-8")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.configured is True
    assert result.available is True
    assert result.complete is True
    assert result.status == "complete"
    assert [row.project_id for row in result.documents] == ["proj-alpha"]
    assert len(result.documents[0].sha256) == 64
    assert "path" not in result.documents[0].document
    assert str(first) not in repr(result.documents)


def test_projects_source_refuses_symlinks_hardlinks_and_bad_json(tmp_path):
    root = make_root(tmp_path / "projects")
    project(root, "good.json", "proj-good")
    hardlink_source = project(root, "hardlink-source.json", "proj-hardlink")
    (root / "linked.json").symlink_to(root / "good.json")
    os.link(hardlink_source, root / "hardlinked.json")
    (root / "bad.json").write_text('{"id":"broken","id":"duplicate"}', encoding="utf-8")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.available is True
    assert result.complete is False
    assert result.status == "partial"
    assert [row.project_id for row in result.documents] == ["proj-good"]


def test_projects_source_duplicate_ids_are_not_silently_selected(tmp_path):
    root = make_root(tmp_path / "projects")
    project(root, "a.json", "proj-duplicate")
    project(root, "b.json", "proj-duplicate")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.complete is False
    assert result.documents == ()


def test_projects_source_limits_file_bytes_entries_and_total_bytes(tmp_path):
    root = make_root(tmp_path / "projects")
    project(root, "a.json", "proj-a")
    project(root, "b.json", "proj-b")

    per_file = ProjectsSourceReadStore(str(root), max_file_bytes=8).read_snapshot()
    assert per_file.status == "partial"
    assert per_file.documents == ()

    total = ProjectsSourceReadStore(str(root), max_total_bytes=10).read_snapshot()
    assert total.status == "partial"
    assert len(total.documents) <= 1

    entry_cap = ProjectsSourceReadStore(str(root), max_entries=1).read_snapshot()
    assert entry_cap.status == "partial"
    assert len(entry_cap.documents) <= 1


def test_projects_source_root_symlink_is_unavailable(tmp_path):
    root = make_root(tmp_path / "projects")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)

    result = ProjectsSourceReadStore(str(alias)).read_snapshot()
    assert result.configured is True
    assert result.available is False
    assert result.status == "unavailable"
    assert result.documents == ()


def test_projects_source_rejects_unknown_fields_and_untrusted_root_mode(tmp_path):
    root = make_root(tmp_path / "projects")
    project(root, "good.json", "proj-good")
    project(root, "extra.json", "proj-extra", private_body="must not pass")

    partial = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert partial.status == "partial"
    assert [row.project_id for row in partial.documents] == ["proj-good"]

    os.chmod(root, 0o750)
    unavailable = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert unavailable.available is False
    assert unavailable.status == "unavailable"
    assert unavailable.documents == ()


def test_projects_source_rejects_malformed_allowed_fields_as_partial(tmp_path):
    root = make_root(tmp_path / "projects")
    project(root, "bad.json", "proj-bad", status="invented")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.available is True
    assert result.status == "partial"
    assert result.documents == ()
