import hashlib
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from secondbrain_core.app import create_app


ORIGIN = "https://testserver"


class D086InboxEntryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.raw, self.review, self.knowledge, self.state = [self.root / name
                                                               for name in ("raw", "review", "knowledge", "state")]
        for path in (self.raw, self.review, self.knowledge, self.state):
            path.mkdir(mode=0o700)
        self.password = self.root / "app.password"
        self.password.write_text("synthetic-d086-app-password")
        self.password.chmod(0o600)
        self.secret = self.root / "promote.secret"
        self.secret.write_text("synthetic-unused-promote-secret-" + "x" * 40)
        self.secret.chmod(0o600)
        self.env = {
            "SB_REVIEW_ROOT": str(self.review), "SB_CAPTURE_RAW_ROOT": str(self.raw),
            "SB_KNOWLEDGE_ROOT": str(self.knowledge), "SB_PROMOTE_STATE_ROOT": str(self.state),
            "SB_DASHBOARD_ORIGINS": ORIGIN, "SB_CORE_ALLOWED_HOSTS": "testserver",
            "SB_APP_PASSWORD_FILE": str(self.password), "SB_PROMOTE_UNLOCK_SECRET_FILE": str(self.secret),
            "SB_PROMOTE_ENABLED": "false", "SB_HERMES_API_URL": "", "SB_HERMES_API_KEY": "",
        }
        with patch.dict(os.environ, self.env, clear=True):
            self.app = create_app()
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.headers = {"Origin": ORIGIN}

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def login(self):
        result = self.client.post("/api/auth/login", headers=self.headers,
                                  json={"password": "synthetic-d086-app-password"})
        self.assertEqual(result.status_code, 200, result.text)

    def payload(self, **changes):
        result = {"original_text": "# Explicit synthetic capture\nKeep this exact text.",
                  "source_channel": "web", "source_event_id": "web-event-0001",
                  "occurred_at": "2026-10-20T03:00:00Z", "intent": "explicit_capture",
                  "attachment_refs": []}
        result.update(changes)
        return result

    def inbox_dependencies(self):
        route = next(route for included in self.app.routes
                     for route in getattr(getattr(included, "original_router", None), "routes", [])
                     if getattr(route, "name", None) == "create_entry")
        endpoint = route.endpoint
        return dict(zip(endpoint.__code__.co_freevars,
                        (cell.cell_contents for cell in endpoint.__closure__ or ())))

    def create_approved_suggestion(self, suffix=""):
        original = self.payload(original_text="记一下：approved synthetic journal content",
                                source_event_id="source-for-proposal" + suffix)
        captured = self.client.post("/api/inbox/entries", headers=self.headers, json=original)
        self.assertEqual(captured.status_code, 202, captured.text)
        proposal_response = self.client.post(
            "/api/inbox/proposals", headers={**self.headers, "Idempotency-Key": "proposal-create-1" + suffix},
            json={"source_kind": "capture", "source_id": captured.json()["inbox_id"]},
        )
        self.assertEqual(proposal_response.status_code, 200, proposal_response.text)
        proposal = next(item for item in proposal_response.json()["proposals"] if item["kind"] == "journal")
        approved = self.client.post(
            f"/api/inbox/proposals/{proposal['proposal_id']}/decision",
            headers={**self.headers, "Idempotency-Key": "proposal-approve-1" + suffix},
            json={"decision": "approved_recorded", "expected_version": 1},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        version = approved.json()["proposal"]["version"]
        request = self.payload(
            original_text=original["original_text"],
            source_event_id=f"proposal:{proposal['proposal_id']}:v{version}",
            intent="approved_suggestion", approved_proposal_id=proposal["proposal_id"],
            approved_proposal_version=version,
        )
        return request, proposal["proposal_id"], captured.json()["inbox_id"]

    def inject_after_initial_approval_read(self, request, mutation):
        deps = self.inbox_dependencies()
        service = deps["service"]
        original = service.accept_channel_text
        calls = 0

        def mutate_before_persist(**kwargs):
            nonlocal calls
            calls += 1
            mutation()
            return original(**kwargs)

        with patch.object(service, "accept_channel_text", side_effect=mutate_before_persist):
            response = self.client.post("/api/inbox/entries", headers=self.headers, json=request)
        self.assertEqual(calls, 1)
        return response

    def test_explicit_capture_is_authenticated_persisted_and_restorable(self):
        self.assertEqual(self.client.post("/api/inbox/entries", headers=self.headers,
                                          json=self.payload()).status_code, 401)
        self.login()
        response = self.client.post("/api/inbox/entries", headers=self.headers, json=self.payload())
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        first = response.json()
        self.assertEqual(first["source"], {"channel": "web", "event_id": "web-event-0001"})
        self.assertEqual(first["intent"], "explicit_capture")
        self.assertEqual(first["consent_evidence"]["kind"], "authenticated_app_explicit_action")
        self.assertEqual(first["consent_evidence"]["subject"], "owner")
        raw_files = list(self.raw.glob("*.md"))
        self.assertEqual(len(raw_files), 1)
        self.assertEqual(raw_files[0].read_text(), self.payload()["original_text"])
        state = json.loads((self.state / "captures" / (first["inbox_id"] + ".json")).read_text())
        self.assertEqual(state["original_text_sha256"], hashlib.sha256(self.payload()["original_text"].encode()).hexdigest())
        self.assertEqual(state["consent_evidence"], first["consent_evidence"])

        replay = self.client.post("/api/inbox/entries", headers=self.headers, json=self.payload())
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertEqual(replay.json()["inbox_id"], first["inbox_id"])
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(len(list(self.raw.glob("*.md"))), 1)
        restored = self.client.get(f"/api/inbox/entries/{first['inbox_id']}", headers=self.headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["source"], first["source"])
        self.assertEqual(restored.json()["intent"], "explicit_capture")
        self.assertEqual(restored.json()["source_ref"]["capture_id"], first["inbox_id"])
        self.assertEqual(len(list(self.review.glob("*.md"))), 1)
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_idempotency_conflict_and_untrusted_or_unsupported_channel_evidence_fail_closed(self):
        self.login()
        first = self.client.post("/api/inbox/entries", headers=self.headers, json=self.payload())
        self.assertEqual(first.status_code, 202, first.text)
        conflict = self.client.post("/api/inbox/entries", headers=self.headers,
                                    json=self.payload(original_text="different text"))
        self.assertEqual(conflict.status_code, 409, conflict.text)
        timestamp_conflict = self.client.post(
            "/api/inbox/entries", headers=self.headers,
            json=self.payload(occurred_at="2026-10-20T04:00:00Z"),
        )
        self.assertEqual(timestamp_conflict.status_code, 409, timestamp_conflict.text)
        forged_consent = self.client.post("/api/inbox/entries", headers=self.headers,
                                          json=self.payload(consent_evidence={"subject": "owner", "consent": True}))
        self.assertEqual(forged_consent.status_code, 400, forged_consent.text)
        forged_identity = self.client.post("/api/inbox/entries", headers=self.headers,
                                           json=self.payload(channel_identity={"channel": "web", "subject": "owner"}))
        self.assertEqual(forged_identity.status_code, 400, forged_identity.text)
        unsupported = self.client.post("/api/inbox/entries", headers=self.headers,
                                       json=self.payload(source_channel="hermes"))
        self.assertEqual(unsupported.status_code, 501, unsupported.text)
        approved = self.client.post("/api/inbox/entries", headers=self.headers,
                                    json=self.payload(intent="approved_suggestion"))
        self.assertEqual(approved.status_code, 409, approved.text)
        malformed_intent = self.client.post("/api/inbox/entries", headers=self.headers,
                                            json=self.payload(intent=["task_intent"]))
        self.assertEqual(malformed_intent.status_code, 400, malformed_intent.text)
        attachments = self.client.post("/api/inbox/entries", headers=self.headers,
                                       json=self.payload(attachment_refs=["/some/path"]))
        self.assertEqual(attachments.status_code, 400, attachments.text)
        self.assertEqual(len(list(self.raw.glob("*.md"))), 1)
        self.assertEqual(list(self.knowledge.iterdir()), [])

    def test_approved_suggestion_requires_live_core_decision_and_exact_source_version(self):
        self.login()
        original = self.payload(original_text="记一下：approved synthetic journal content", source_event_id="source-for-proposal")
        captured = self.client.post("/api/inbox/entries", headers=self.headers, json=original)
        self.assertEqual(captured.status_code, 202, captured.text)
        capture_id = captured.json()["inbox_id"]
        proposed = self.client.post(
            "/api/inbox/proposals", headers={**self.headers, "Idempotency-Key": "proposal-create-1"},
            json={"source_kind": "capture", "source_id": capture_id},
        )
        self.assertEqual(proposed.status_code, 200, proposed.text)
        journal = next(item for item in proposed.json()["proposals"] if item["kind"] == "journal")
        request = self.payload(
            original_text=original["original_text"], source_event_id=f"proposal:{journal['proposal_id']}:v2",
            intent="approved_suggestion", approved_proposal_id=journal["proposal_id"],
            approved_proposal_version=2,
        )
        denied = self.client.post("/api/inbox/entries", headers=self.headers, json=request)
        self.assertEqual(denied.status_code, 409, denied.text)

        approved = self.client.post(
            f"/api/inbox/proposals/{journal['proposal_id']}/decision",
            headers={**self.headers, "Idempotency-Key": "proposal-approve-1"},
            json={"decision": "approved_recorded", "expected_version": 1},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        request["approved_proposal_version"] = approved.json()["proposal"]["version"]
        request["source_event_id"] = f"proposal:{journal['proposal_id']}:v{request['approved_proposal_version']}"
        changed_text = dict(request, original_text="Forged content")
        self.assertEqual(self.client.post("/api/inbox/entries", headers=self.headers,
                                          json=changed_text).status_code, 409)
        accepted = self.client.post("/api/inbox/entries", headers=self.headers, json=request)
        self.assertEqual(accepted.status_code, 202, accepted.text)
        self.assertEqual(accepted.json()["intent"], "approved_suggestion")
        self.assertEqual(accepted.json()["approved_proposal"]["proposal_id"], journal["proposal_id"])
        self.assertEqual(accepted.json()["consent_evidence"]["kind"], "authenticated_app_approved_proposal")
        self.assertEqual(accepted.json()["consent_evidence"]["proposal_version"], request["approved_proposal_version"])
        replay = self.client.post("/api/inbox/entries", headers=self.headers, json=request)
        self.assertEqual(replay.status_code, 202, replay.text)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(replay.json()["inbox_id"], accepted.json()["inbox_id"])
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertFalse((self.state / "journal").exists())
        catalog = self.state / "vocabulary" / "catalog.json"
        catalog.write_text(json.dumps({"schema_version": 1, "revision": 1, "types": [],
                                       "tags": [], "synonyms": [], "audit": []}))
        catalog.chmod(0o600)
        stale_request = dict(request, source_event_id="stale-vocabulary-proposal")
        stale = self.client.post("/api/inbox/entries", headers=self.headers, json=stale_request)
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_approved_suggestion_rechecks_proposal_decision_before_first_persist(self):
        self.login()
        proposals = self.inbox_dependencies()["proposals"]
        for change in ("decision", "version"):
            with self.subTest(change=change):
                request, proposal_id, _ = self.create_approved_suggestion("-" + change)
                raw_count_before = len(list(self.raw.glob("*.md")))

                def mutate_approval():
                    def update(data):
                        record = data["records"][proposal_id]
                        if change == "decision":
                            record["status"] = "rejected"
                            record["decision_at"] = "2026-10-20T00:00:00Z"
                            record["updated_at"] = record["decision_at"]
                            record["target_execution_status"] = "not_executed"
                            record["execution"] = {"status": "not_executed"}
                            record["history"].append({"event": "rejected", "actor": "owner",
                                                      "at": record["decision_at"], "version": record["version"] + 1})
                        record["version"] += 1
                        return None, True
                    proposals._transaction(update)

                response = self.inject_after_initial_approval_read(request, mutate_approval)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(len(list(self.raw.glob("*.md"))), raw_count_before,
                                 "no approved-suggestion Raw may be written")
                capture_id = hashlib.sha256(("secondbrain-inbox-event\0web\0" + request["source_event_id"]).encode()).hexdigest()[:32]
                self.assertFalse((self.state / "captures" / (capture_id + ".json")).exists())

    def test_approved_suggestion_rechecks_source_and_vocabulary_before_first_persist(self):
        self.login()
        for changed in ("source", "vocabulary"):
            with self.subTest(changed=changed):
                request, _, source_capture_id = self.create_approved_suggestion("-" + changed)
                deps = self.inbox_dependencies()
                raw_count_before = len(list(self.raw.glob("*.md")))

                def mutate():
                    if changed == "source":
                        source = deps["service"].get(source_capture_id)
                        raw = self.raw / source["raw_path"]
                        raw.write_text("changed synthetic source after approval", encoding="utf-8")
                    else:
                        vocabulary = deps["vocabulary_store"]
                        catalog = vocabulary.read()
                        catalog["revision"] += 1
                        vocabulary.path.write_text(json.dumps(catalog), encoding="utf-8")
                        vocabulary.path.chmod(0o600)

                response = self.inject_after_initial_approval_read(request, mutate)
                self.assertEqual(response.status_code, 409, response.text)
                capture_id = hashlib.sha256(("secondbrain-inbox-event\0web\0" + request["source_event_id"]).encode()).hexdigest()[:32]
                self.assertFalse((self.state / "captures" / (capture_id + ".json")).exists())
                self.assertEqual(len(list(self.raw.glob("*.md"))), raw_count_before)

    def test_same_event_concurrent_identical_and_conflicting_payloads_are_serialized(self):
        self.login()

        def concurrent_posts(payloads):
            barrier = Barrier(len(payloads))

            def post(payload):
                with TestClient(self.app, base_url=ORIGIN) as client:
                    login = client.post("/api/auth/login", headers=self.headers,
                                        json={"password": "synthetic-d086-app-password"})
                    if login.status_code != 200:
                        return login.status_code, login.text
                    barrier.wait(timeout=5)
                    response = client.post("/api/inbox/entries", headers=self.headers, json=payload)
                    return response.status_code, response.json()

            with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
                return list(pool.map(post, payloads))

        identical = self.payload(source_event_id="parallel-identical")
        results = concurrent_posts([identical, identical])
        self.assertEqual([status for status, _ in results], [202, 202])
        self.assertEqual(len({body["inbox_id"] for _, body in results}), 1)
        self.assertEqual(sum(bool(body["replayed"]) for _, body in results), 1)
        self.assertEqual(len(list(self.raw.glob("*.md"))), 1)
        self.assertEqual(len(list((self.state / "captures").glob("*.json"))), 1)

        conflict_a = self.payload(source_event_id="parallel-conflict", original_text="candidate A")
        conflict_b = self.payload(source_event_id="parallel-conflict", original_text="candidate B")
        conflicts = concurrent_posts([conflict_a, conflict_b])
        self.assertEqual(sorted(status for status, _ in conflicts), [202, 409])
        self.assertEqual(len(list(self.raw.glob("*.md"))), 2)
        self.assertEqual(len(list((self.state / "captures").glob("*.json"))), 2)

        time_a = self.payload(source_event_id="parallel-time", occurred_at="2026-10-20T03:00:00Z")
        time_b = dict(time_a, occurred_at="2026-10-20T04:00:00Z")
        times = concurrent_posts([time_a, time_b])
        self.assertEqual(sorted(status for status, _ in times), [202, 409])
        self.assertEqual(len(list(self.raw.glob("*.md"))), 3)

        approved, _, _ = self.create_approved_suggestion("-parallel")
        approved["source_event_id"] += "-same-payload"
        approved_retries = concurrent_posts([approved, approved])
        self.assertEqual([status for status, _ in approved_retries], [202, 202])
        self.assertEqual(len({body["inbox_id"] for _, body in approved_retries}), 1)
        self.assertEqual(sum(bool(body["replayed"]) for _, body in approved_retries), 1)
        proposal_conflict = dict(approved, approved_proposal_version=approved["approved_proposal_version"] + 1)
        versions = concurrent_posts([approved, proposal_conflict])
        self.assertEqual(sorted(status for status, _ in versions), [202, 409])

        attachment_refs = []
        for event_id in ("parallel-attachment-source-a", "parallel-attachment-source-b"):
            source = self.client.post("/api/inbox/entries", headers=self.headers,
                                      json=self.payload(source_event_id=event_id))
            self.assertEqual(source.status_code, 202, source.text)
            source_state = json.loads((self.state / "captures" /
                                       (source.json()["inbox_id"] + ".json")).read_text())
            attachment_refs.append({"capture_id": source.json()["inbox_id"],
                                    "sha256": source_state["raw_sha256"]})
        attachment_event_a = dict(approved, source_event_id="parallel-attachment-event",
                                  attachment_refs=[attachment_refs[0]])
        attachment_event_b = dict(approved, source_event_id="parallel-attachment-event",
                                  attachment_refs=[attachment_refs[1]])
        attachments = concurrent_posts([attachment_event_a, attachment_event_b])
        self.assertEqual(sorted(status for status, _ in attachments), [202, 409])
        self.assertEqual(len(list(self.knowledge.iterdir())), 0)
        self.assertFalse((self.state / "journal").exists())
        self.assertFalse((self.state / "tasks").exists())

    def test_incomplete_event_state_never_replays_as_success_or_rewrites_raw(self):
        self.login()
        request = self.payload(source_event_id="interrupted-write")
        capture_id = hashlib.sha256(("secondbrain-inbox-event\0web\0" + request["source_event_id"]).encode()).hexdigest()[:32]
        raw_path = self.raw / f"Inbox-{capture_id}.md"
        service = self.inbox_dependencies()["service"]
        original_write_state = service._write_state

        def fail_state_write(state):
            if state.get("capture_id") == capture_id:
                raise OSError("synthetic state persistence interruption")
            return original_write_state(state)

        with TestClient(self.app, base_url=ORIGIN, raise_server_exceptions=False) as failing_client:
            failing_client.post("/api/auth/login", headers=self.headers,
                                json={"password": "synthetic-d086-app-password"})
            with patch.object(service, "_write_state", side_effect=fail_state_write):
                failed = failing_client.post("/api/inbox/entries", headers=self.headers, json=request)
        self.assertEqual(failed.status_code, 500)
        self.assertTrue(raw_path.is_file())
        raw_before_retry = raw_path.read_bytes()
        retry = self.client.post("/api/inbox/entries", headers=self.headers, json=request)
        self.assertEqual(retry.status_code, 503, retry.text)
        self.assertEqual(raw_path.read_bytes(), raw_before_retry)
        self.assertFalse((self.state / "captures" / (capture_id + ".json")).exists())

        complete = self.client.post("/api/inbox/entries", headers=self.headers,
                                    json=self.payload(source_event_id="corrupt-state"))
        self.assertEqual(complete.status_code, 202, complete.text)
        complete_id = complete.json()["inbox_id"]
        complete_state = self.state / "captures" / (complete_id + ".json")
        complete_raw = self.raw / json.loads(complete_state.read_text())["raw_path"]
        complete_raw_before = complete_raw.read_bytes()
        complete_state.write_text("{corrupt", encoding="utf-8")
        corrupt_retry = self.client.post("/api/inbox/entries", headers=self.headers,
                                         json=self.payload(source_event_id="corrupt-state"))
        self.assertEqual(corrupt_retry.status_code, 503, corrupt_retry.text)
        self.assertEqual(complete_raw.read_bytes(), complete_raw_before)
        self.assertEqual(complete_state.read_text(), "{corrupt")

    def test_missing_state_or_mismatched_raw_requires_manual_recovery(self):
        self.login()
        payload = self.payload(source_event_id="missing-state")
        created = self.client.post("/api/inbox/entries", headers=self.headers, json=payload)
        self.assertEqual(created.status_code, 202, created.text)
        capture_id = created.json()["inbox_id"]
        state_path = self.state / "captures" / (capture_id + ".json")
        state = json.loads(state_path.read_text())
        raw_path = self.raw / state["raw_path"]
        state_path.unlink()
        raw_before = raw_path.read_bytes()
        retry = self.client.post("/api/inbox/entries", headers=self.headers, json=payload)
        self.assertEqual(retry.status_code, 503, retry.text)
        self.assertEqual(raw_path.read_bytes(), raw_before)
        self.assertFalse(state_path.exists())

        second = self.payload(source_event_id="mismatched-raw")
        accepted = self.client.post("/api/inbox/entries", headers=self.headers, json=second)
        self.assertEqual(accepted.status_code, 202, accepted.text)
        state = json.loads((self.state / "captures" / (accepted.json()["inbox_id"] + ".json")).read_text())
        raw_path = self.raw / state["raw_path"]
        raw_path.write_text("tampered after accepted request", encoding="utf-8")
        tampered = raw_path.read_bytes()
        conflict = self.client.post("/api/inbox/entries", headers=self.headers, json=second)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(raw_path.read_bytes(), tampered)

    def test_attachment_refs_are_exact_capture_ids_and_hashes_and_restore_without_path_disclosure(self):
        self.login()
        attachment = self.payload(source_event_id="attachment-source", original_text="Synthetic attachment source")
        created = self.client.post("/api/inbox/entries", headers=self.headers, json=attachment)
        self.assertEqual(created.status_code, 202, created.text)
        capture_id = created.json()["inbox_id"]
        state = json.loads((self.state / "captures" / (capture_id + ".json")).read_text())
        reference = {"capture_id": capture_id, "sha256": state["raw_sha256"]}
        payload = self.payload(source_event_id="attachment-consumer", attachment_refs=[reference])
        accepted = self.client.post("/api/inbox/entries", headers=self.headers, json=payload)
        self.assertEqual(accepted.status_code, 202, accepted.text)
        self.assertEqual(accepted.json()["attachment_refs"], [reference])
        restored = self.client.get(f"/api/inbox/entries/{accepted.json()['inbox_id']}", headers=self.headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["attachment_refs"], [reference])
        self.assertNotIn("raw_path", restored.text)
        forged = self.payload(source_event_id="attachment-forged", attachment_refs=[{
            "capture_id": capture_id, "sha256": "0" * 64,
        }])
        rejected = self.client.post("/api/inbox/entries", headers=self.headers, json=forged)
        self.assertEqual(rejected.status_code, 409, rejected.text)
        state["source_channel"] = "unverified-external"
        state_path = self.state / "captures" / (capture_id + ".json")
        state_path.write_text(json.dumps(state))
        state_path.chmod(0o600)
        untrusted_source = self.payload(source_event_id="attachment-untrusted-channel", attachment_refs=[reference])
        rejected = self.client.post("/api/inbox/entries", headers=self.headers, json=untrusted_source)
        self.assertEqual(rejected.status_code, 409, rejected.text)

    def test_journal_and_task_intents_are_stored_in_inbox_without_execution(self):
        self.login()
        for intent, event_id in (("journal_intent", "journal-1"), ("task_intent", "task-1")):
            response = self.client.post("/api/inbox/entries", headers=self.headers,
                                        json=self.payload(source_event_id=event_id, intent=intent))
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["intent"], intent)
        self.assertEqual(len(list(self.raw.glob("*.md"))), 2)
        self.assertEqual(list(self.knowledge.iterdir()), [])
        self.assertFalse((self.state / "journal").exists())
        self.assertFalse((self.state / "tasks").exists())
