"""Real Core localhost regression for D086 fail-closed suggestion admission."""
import json
import os
import socket
import threading
import time

import httpx
import uvicorn

from secondbrain_core.app import create_app


def private_dir(path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_real_core_localhost_inbox_proposal_approval_and_untrusted_suggestion_fail_closed(
        tmp_path, monkeypatch):
    roots = {name: private_dir(tmp_path / name) for name in (
        "raw", "review", "knowledge", "state", "journal", "projects", "briefs", "tasks", "notes",
    )}
    password = tmp_path / "synthetic-app-password"
    password.write_text("synthetic-d086-localhost-password\n", encoding="utf-8")
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
        "SB_REVIEW_ROOT": str(roots["review"]),
        "SB_CAPTURE_RAW_ROOT": str(roots["raw"]),
        "SB_KNOWLEDGE_ROOT": str(roots["knowledge"]),
        "SB_PROMOTE_STATE_ROOT": str(roots["state"]),
        "SB_PROMOTE_UNLOCK_SECRET_FILE": str(secret),
        "SB_APP_PASSWORD_FILE": str(password),
        "SB_DASHBOARD_ORIGINS": origin,
        "SB_CORE_ALLOWED_HOSTS": host,
        "SB_HERMES_API_URL": "",
        "SB_HERMES_API_KEY": "",
        "SB_PROMOTE_ENABLED": "false",
        "SB_JOURNAL_ROOT": str(roots["journal"]),
        "SB_PROJECTS_INDEX_ROOT": str(roots["projects"]),
        "SB_DAILY_BRIEF_STORE_ROOT": str(roots["briefs"]),
        "SB_TASK_ROOT": str(roots["tasks"]),
        "SB_NOTES_DRAFTS_ROOT": str(roots["notes"]),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = create_app()
    assert app.state.capture_suggestion_binding_authority.resolve(
        source_event_id="synthetic-unbound-event", expected_text="synthetic text",
        expected_version="version-1", authenticated_subject="owner", consent_id="consent-1",
    ) is None
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical",
                                           lifespan="off", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    base = {
        "original_text": "记一下：Synthetic D086 approval chain source.",
        "source_channel": "web", "source_event_id": "synthetic-d086-localhost-source",
        "occurred_at": "2026-10-20T03:00:00Z", "intent": "explicit_capture",
        "attachment_refs": [],
    }
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=origin, trust_env=False, timeout=10) as client:
            anonymous = httpx.post(f"{origin}/api/inbox/entries", headers={"Origin": origin},
                                   json=base, trust_env=False, timeout=5)
            assert anonymous.status_code == 401
            assert not list(roots["raw"].iterdir())
            login = client.post("/api/auth/login", headers={"Origin": origin},
                                json={"password": "synthetic-d086-localhost-password"})
            assert login.status_code == 200
            headers = {"Origin": origin}
            wrong_origin = client.post("/api/inbox/entries",
                                       headers={"Origin": "http://attacker.invalid"}, json=base)
            assert wrong_origin.status_code == 403
            assert not list(roots["raw"].iterdir())

            # The Chat SSE event, proposal_id, client identity/session/run and
            # client consent fields cannot mint a Core approved_suggestion.
            no_proposal = client.post("/api/inbox/entries", headers=headers,
                                      json={**base, "intent": "approved_suggestion"})
            assert no_proposal.status_code == 409
            fake_proposal = client.post("/api/inbox/entries", headers=headers,
                                        json={**base, "intent": "approved_suggestion",
                                              "approved_proposal_id": "a" * 32,
                                              "approved_proposal_version": 1,
                                              "proposal_id": "b" * 32})
            assert fake_proposal.status_code == 400
            for field, value in (("session_id", "self-asserted-session"),
                                 ("run_id", "self-asserted-run"),
                                 ("hermes_session_id", "self-asserted-hermes-session"),
                                 ("hermes_run_id", "self-asserted-hermes-run"),
                                 ("consent_evidence", {"consented": True}),
                                 ("channel_identity", {"channel": "hermes", "subject": "owner"})):
                forged = client.post("/api/inbox/entries", headers=headers,
                                     json={**base, field: value})
                assert forged.status_code == 400
                assert "synthetic" not in forged.text or "Request" in forged.text
            unsupported_adapter = client.post("/api/inbox/entries", headers=headers,
                                              json={**base, "source_channel": "hermes"})
            assert unsupported_adapter.status_code == 501
            assert not list(roots["raw"].iterdir())
            assert not list((roots["state"] / "captures").glob("*.json"))

            # Current accepted path: explicit App action -> exact GET receipt.
            captured = client.post("/api/inbox/entries", headers=headers, json=base)
            assert captured.status_code == 202, captured.text
            entry = captured.json()
            assert entry["source"] == {"channel": "web", "event_id": base["source_event_id"]}
            assert entry["consent_evidence"]["kind"] == "authenticated_app_explicit_action"
            restored = client.get(f"/api/inbox/entries/{entry['inbox_id']}", headers=headers)
            assert restored.status_code == 200, restored.text
            assert restored.json()["inbox_id"] == entry["inbox_id"]
            assert restored.json()["consent_evidence"] == entry["consent_evidence"]

            # Existing proposals are deterministic Core records; user approval
            # is a separate persisted decision, not a Hermes event credential.
            proposed = client.post("/api/inbox/proposals", headers={**headers,
                                    "Idempotency-Key": "synthetic-d086-proposal-create"},
                                   json={"source_kind": "capture", "source_id": entry["inbox_id"]})
            assert proposed.status_code == 200, proposed.text
            journal = next(item for item in proposed.json()["proposals"] if item["kind"] == "journal")
            assert journal["status"] == "suggested"
            assert journal["suggestion"]["current"]["value"]
            decision = client.post(
                f"/api/inbox/proposals/{journal['proposal_id']}/decision",
                headers={**headers, "Idempotency-Key": "synthetic-d086-proposal-decision"},
                json={"decision": "approved_recorded", "expected_version": 1},
            )
            assert decision.status_code == 200, decision.text
            approved = decision.json()["proposal"]
            accepted = client.post(
                "/api/inbox/entries", headers=headers,
                json={**base, "source_event_id": f"approved:{journal['proposal_id']}:v{approved['version']}",
                      "intent": "approved_suggestion",
                      "approved_proposal_id": journal["proposal_id"],
                      "approved_proposal_version": approved["version"]},
            )
            assert accepted.status_code == 202, accepted.text
            assert accepted.json()["approved_proposal"]["proposal_id"] == journal["proposal_id"]
            assert accepted.json()["consent_evidence"]["kind"] == "authenticated_app_approved_proposal"
            exact_get = client.get(f"/api/inbox/entries/{accepted.json()['inbox_id']}", headers=headers)
            assert exact_get.status_code == 200
            assert exact_get.json()["approved_proposal"] == accepted.json()["approved_proposal"]

            # Approval is not execution: a separate current preview, explicit
            # confirmation, target action, and exact preview hash are required.
            preview_response = client.post(
                f"/api/inbox/proposals/{journal['proposal_id']}/execution-preview",
                headers=headers, json={},
            )
            assert preview_response.status_code == 200, preview_response.text
            preview = preview_response.json()
            assert preview["status"] == "ready" and preview["target_action"] == "journal.append"
            journal_path = roots["journal"] / f"{preview['target']['date']}.jsonl"
            assert not journal_path.exists()
            body = {"target_text": preview["target"]["text"],
                    "target_date": preview["target"]["date"],
                    "preview_sha256": preview["preview_sha256"], "confirmed": True}
            executed = client.post(f"/api/inbox/proposals/{journal['proposal_id']}/execute",
                                   headers=headers, json=body)
            assert executed.status_code == 200, executed.text
            assert executed.json()["proposal"]["execution"]["status"] == "executed"
            rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            assert len(rows) == 1 and rows[0]["original_text"] == preview["target"]["text"]
            replay = client.post(f"/api/inbox/proposals/{journal['proposal_id']}/execute",
                                 headers=headers, json=body)
            assert replay.status_code == 200 and replay.json()["duplicate"] is True
            assert len(journal_path.read_text(encoding="utf-8").splitlines()) == 1
            assert not list(roots["knowledge"].iterdir())
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if not thread.is_alive():
            listener.close()
