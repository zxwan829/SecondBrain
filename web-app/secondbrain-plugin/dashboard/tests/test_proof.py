from pathlib import Path

import plugin_api
import policy


def test_proof_does_not_depend_on_project_governance_files(tmp_path, monkeypatch):
    monkeypatch.setitem(plugin_api.ALLOW, "30-Projects", tmp_path)
    monkeypatch.setitem(policy.ALLOWED_AREAS, "30-Projects", tmp_path)

    expected = {
        "status": "ok",
        "area": "30-Projects",
        "title": "SecondBrain V1 — Current State",
        "source_type": "project",
    }
    assert plugin_api.proof() == expected
    assert policy.proof() == expected
