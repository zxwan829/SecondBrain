"""Journal source reads remain side-effect free and fail closed on races."""
import hashlib
import json
import os
import stat

import pytest
from fastapi import HTTPException

from secondbrain_core.modules import journal as journal_module
from secondbrain_core.modules.journal import JournalStore
from secondbrain_core.modules.source_reference_authority import SourceReferenceAuthority


DAY = "2026-10-20"


def _private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _store_with_rows(tmp_path, count=1, text="synthetic journal entry"):
    root = _private_dir(tmp_path / "journal")
    store = JournalStore(str(root))
    entries = [store.append(DAY, f"记一下 {text} {index}", f"synthetic-key-{index}")["entry"]
               for index in range(count)]
    # Date locks are write-path coordination files. Remove this one after
    # fixture setup to prove source verification has no dependency on it.
    (root / f".{DAY}.lock").unlink()
    return root, store, entries


def _file_state(path):
    info = path.lstat()
    return {
        "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
        "dev": info.st_dev, "ino": info.st_ino, "nlink": info.st_nlink,
        "size": info.st_size, "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns, "atime_ns": info.st_atime_ns,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_source_read_succeeds_in_nonwritable_root_without_lock_or_other_side_effects(tmp_path):
    root, store, entries = _store_with_rows(tmp_path)
    source = root / f"{DAY}.jsonl"
    os.chmod(source, 0o400)
    os.chmod(root, 0o500)
    assert os.geteuid() != 0
    assert not os.access(root, os.W_OK)

    # Exercise the actual filesystem create permission, rather than relying on
    # chmod alone (which root can bypass).
    probe = root / ".creation-permission-probe"
    with pytest.raises(PermissionError):
        os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    assert not probe.exists()

    root_entries_before = sorted(path.name for path in root.iterdir())
    before = _file_state(source)
    expected_row = json.loads(source.read_text(encoding="utf-8").splitlines()[0])
    result = store.read_source_day(DAY)
    assert result["available"] is True
    assert result["entries"][entries[0]["id"]]["version"] == hashlib.sha256(
        source.read_bytes().splitlines()[0]
    ).hexdigest()
    authority = SourceReferenceAuthority(journal_store=store,
                                         permission_checks={"journal": lambda: None})
    reference = {"kind": "journal", "id": f"{DAY}:{expected_row['id']}",
                 "version": result["entries"][expected_row["id"]]["version"]}
    assert authority.verify(reference) == "verified"
    assert sorted(path.name for path in root.iterdir()) == root_entries_before
    after = _file_state(source)
    for key in before:
        if key == "atime_ns" and not getattr(os, "O_NOATIME", 0):
            # Darwin and some other platforms lack O_NOATIME. A read may then
            # update only atime; bytes and all namespace/security metadata must
            # remain unchanged.
            continue
        assert after[key] == before[key], key


@pytest.mark.parametrize("mutation", ["truncate", "in_place_rewrite", "atomic_replace"])
def test_source_read_rejects_controlled_concurrent_file_changes(tmp_path, monkeypatch, mutation):
    root, store, _ = _store_with_rows(tmp_path, count=8, text="x" * 12_000)
    source = root / f"{DAY}.jsonl"
    real_read = os.read
    changed = False

    def racing_read(fd, size):
        nonlocal changed
        chunk = real_read(fd, size)
        if chunk and not changed:
            changed = True
            if mutation == "truncate":
                with source.open("r+b") as stream:
                    stream.truncate(0)
            elif mutation == "in_place_rewrite":
                with source.open("r+b") as stream:
                    stream.seek(0)
                    stream.write(b"X" * source.stat().st_size)
                    stream.flush()
                    os.fsync(stream.fileno())
            else:
                replacement = root / ".replacement"
                replacement.write_bytes(source.read_bytes())
                os.chmod(replacement, 0o600)
                os.replace(replacement, source)
        return chunk

    monkeypatch.setattr(journal_module.os, "read", racing_read)
    with pytest.raises(HTTPException) as raised:
        store.read_source_day(DAY)
    assert raised.value.status_code == 503
    assert changed is True


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_source_read_rejects_symlink_and_hardlink(tmp_path, kind):
    root, store, _ = _store_with_rows(tmp_path)
    source = root / f"{DAY}.jsonl"
    if kind == "symlink":
        source.unlink()
        source.symlink_to(root / "missing-target")
    else:
        os.link(source, root / "second-link")
    with pytest.raises(HTTPException) as raised:
        store.read_source_day(DAY)
    assert raised.value.status_code == 503


def test_source_read_missing_malformed_and_over_budget_fail_closed(tmp_path):
    root, store, _ = _store_with_rows(tmp_path)
    (root / f"{DAY}.jsonl").unlink()
    assert store.read_source_day(DAY)["entries"] == {}

    source = root / f"{DAY}.jsonl"
    source.write_text('{"id":"broken"}\n', encoding="utf-8")
    os.chmod(source, 0o600)
    with pytest.raises(HTTPException):
        store.read_source_day(DAY)
    with pytest.raises(HTTPException):
        store.read_source_day(DAY, max_bytes=1)


def test_daily_brief_source_authority_denial_is_not_verified(tmp_path):
    _, store, entries = _store_with_rows(tmp_path)
    result = store.read_source_day(DAY)
    ref = {"kind": "journal", "id": f"{DAY}:{entries[0]['id']}",
           "version": result["entries"][entries[0]["id"]]["version"]}
    authority = SourceReferenceAuthority(journal_store=store,
                                         permission_checks={"journal": lambda: (_ for _ in ()).throw(
                                             HTTPException(status_code=403))})
    assert authority.verify(ref) == "forbidden"
    assert authority.verify({**ref, "version": "0" * 64}) == "forbidden"
