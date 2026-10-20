import json
import os

from secondbrain_core.modules.projects_source_read import ProjectsSourceReadStore


def project(root, name, project_id):
    path = root / name
    path.write_text(json.dumps({"id": project_id, "title": "Synthetic"}, separators=(",", ":")),
                    encoding="utf-8")
    return path


def test_unconfigured_projects_source_does_not_scan_any_root(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "scandir", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("unconfigured source must not be scanned")))
    result = ProjectsSourceReadStore(None).read_snapshot()
    assert result.configured is False
    assert result.documents == ()


def test_projects_source_reads_only_explicit_root_and_returns_digest_not_path(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    first = project(root, "project.json", "proj-alpha")
    outside = tmp_path / "outside.json"
    outside.write_text('{"id":"outside"}', encoding="utf-8")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.configured is True
    assert result.complete is True
    assert [row.project_id for row in result.documents] == ["proj-alpha"]
    assert len(result.documents[0].sha256) == 64
    assert "path" not in result.documents[0].document
    assert str(first) not in repr(result.documents)


def test_projects_source_refuses_symlinks_hardlinks_and_bad_json(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    project(root, "good.json", "proj-good")
    hardlink_source = project(root, "hardlink-source.json", "proj-hardlink")
    (root / "linked.json").symlink_to(root / "good.json")
    os.link(hardlink_source, root / "hardlinked.json")
    (root / "bad.json").write_text('{"id":"broken","id":"duplicate"}', encoding="utf-8")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.complete is False
    assert [row.project_id for row in result.documents] == ["proj-good"]


def test_projects_source_duplicate_ids_are_not_silently_selected(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    project(root, "a.json", "proj-duplicate")
    project(root, "b.json", "proj-duplicate")

    result = ProjectsSourceReadStore(str(root)).read_snapshot()
    assert result.complete is False
    assert result.documents == ()


def test_projects_source_limits_file_bytes_entries_and_total_bytes(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    project(root, "a.json", "proj-a")
    project(root, "b.json", "proj-b")

    per_file = ProjectsSourceReadStore(str(root), max_file_bytes=8).read_snapshot()
    assert per_file.complete is False
    assert per_file.documents == ()

    total = ProjectsSourceReadStore(str(root), max_total_bytes=10).read_snapshot()
    assert total.complete is False
    assert len(total.documents) <= 1

    entry_cap = ProjectsSourceReadStore(str(root), max_entries=1).read_snapshot()
    assert entry_cap.complete is False
    assert len(entry_cap.documents) <= 1


def test_projects_source_root_symlink_is_unavailable(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)

    result = ProjectsSourceReadStore(str(alias)).read_snapshot()
    assert result.configured is True
    assert result.complete is False
    assert result.documents == ()
