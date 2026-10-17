import json
import threading
import unittest

from fastapi import HTTPException

from secondbrain_core.modules.run_approvals import APPROVAL_PREFIX, FILE_WRITE_APPROVAL_PREFIX, RunApprovalRegistry


def event(request_id="approval-1", command="pwd"):
    request = {"schema": 1, "tool": "terminal", "arguments": {"command": command, "workdir": "/private/tmp/synthetic"}}
    return {"event": "approval.request", "run_id": "run-1", "request_id": request_id,
            "description": APPROVAL_PREFIX + json.dumps(request, sort_keys=True, separators=(",", ":"))}


class RunApprovalRegistryTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.registry = RunApprovalRegistry(clock=lambda: self.now[0])
        self.registry.register_run("run-1", "session-1", "owner")

    def card(self):
        return self.registry.bind_event("run-1", "owner", event())

    def test_event_is_bound_to_authenticated_run_session_and_digest(self):
        card = self.card()
        self.assertEqual(card["session_id"], "session-1")
        self.assertEqual(card["command"], "pwd")
        self.assertEqual(card["workdir"], "/private/tmp/synthetic")
        with self.assertRaises(HTTPException) as wrong_session:
            self.registry.begin_resolution(run_id="run-1", session_id="session-2", request_id="approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="once")
        self.assertEqual(wrong_session.exception.status_code, 404)
        with self.assertRaises(HTTPException) as wrong_digest:
            self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="approval-1",
                                           owner="owner", digest="0" * 64, choice="once")
        self.assertEqual(wrong_digest.exception.status_code, 409)

    def test_only_once_and_deny_are_supported_and_replay_fails(self):
        card = self.card()
        with self.assertRaises(HTTPException):
            self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="session")
        self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="approval-1",
                                       owner="owner", digest=card["command_sha256"], choice="once")
        with self.assertRaises(HTTPException) as replay:
            self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="once")
        self.assertEqual(replay.exception.status_code, 409)

    def test_concurrent_double_click_has_one_winner(self):
        card = self.card()
        barrier = threading.Barrier(3)
        outcomes = []

        def resolve():
            barrier.wait()
            try:
                self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="approval-1",
                                               owner="owner", digest=card["command_sha256"], choice="once")
                outcomes.append("won")
            except HTTPException:
                outcomes.append("replay")

        threads = [threading.Thread(target=resolve) for _ in range(2)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join()
        self.assertCountEqual(outcomes, ["won", "replay"])

    def test_expired_request_and_changed_reused_id_are_rejected(self):
        card = self.card()
        self.now[0] += 241
        with self.assertRaises(HTTPException) as expired:
            self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="once")
        self.assertEqual(expired.exception.status_code, 409)
        changed = self.registry.bind_event("run-1", "owner", event(command="id"))
        self.assertIsNone(changed)

    def test_invalid_events_never_create_approval_cards(self):
        for malformed in ({"request_id": "x", "description": "bad"},
                          {"request_id": "x", "description": APPROVAL_PREFIX + "{}"},
                          {"request_id": "x", "description": APPROVAL_PREFIX + json.dumps({"schema": 1, "tool": "terminal", "arguments": {}})}):
            self.assertIsNone(self.registry.bind_event("run-1", "owner", malformed))

    def test_terminal_card_rejects_missing_or_noncanonical_execution_context(self):
        for args in ({"command": "pwd"}, {"command": "pwd", "workdir": "relative"},
                     {"command": "pwd", "workdir": "/tmp/x", "cwd": "/tmp/y"}):
            request = {"schema": 1, "tool": "terminal", "arguments": args}
            malformed = {"request_id": "approval-1", "description": APPROVAL_PREFIX + json.dumps(request)}
            self.assertIsNone(self.registry.bind_event("run-1", "owner", malformed))

    def test_file_write_card_is_run_session_owner_and_exact_argument_bound(self):
        args = {"path": "/knowledge-assets/00-Inbox/synthetic.md", "content": "synthetic content"}
        request = {"schema": 1, "tool": "write_file", "arguments": args}
        incoming = {"event": "approval.request", "run_id": "run-1", "request_id": "file-approval-1", "description": FILE_WRITE_APPROVAL_PREFIX +
                    json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}
        card = self.registry.bind_event("run-1", "owner", incoming)
        self.assertEqual(card["tool"], "write_file")
        self.assertEqual(card["command"], "write_file → /knowledge-assets/00-Inbox/synthetic.md")
        self.assertEqual(card["arguments"], args)
        self.assertIn("one file mutation", card["scope"].lower())
        with self.assertRaises(HTTPException) as wrong_run:
            self.registry.begin_resolution(run_id="run-2", session_id="session-1", request_id="file-approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="once")
        self.assertEqual(wrong_run.exception.status_code, 404)
        with self.assertRaises(HTTPException) as wrong_session:
            self.registry.begin_resolution(run_id="run-1", session_id="session-2", request_id="file-approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="once")
        self.assertEqual(wrong_session.exception.status_code, 404)
        with self.assertRaises(HTTPException) as changed:
            self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="file-approval-1",
                                           owner="owner", digest="0" * 64, choice="once")
        self.assertEqual(changed.exception.status_code, 409)
        self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="file-approval-1",
                                       owner="owner", digest=card["command_sha256"], choice="once")
        with self.assertRaises(HTTPException) as replay:
            self.registry.begin_resolution(run_id="run-1", session_id="session-1", request_id="file-approval-1",
                                           owner="owner", digest=card["command_sha256"], choice="once")
        self.assertEqual(replay.exception.status_code, 409)

    def test_file_write_rejects_unscoped_or_ambiguous_targets(self):
        malformed_requests = (
            {"schema": 1, "tool": "write_file", "arguments": {"path": "relative.md", "content": "x"}},
            {"schema": 1, "tool": "write_file", "arguments": {"path": "/safe/a.md", "content": "x", "cross_profile": True}},
            {"schema": 1, "tool": "patch", "arguments": {"mode": "patch", "patch": "*** Begin Patch"}},
            {"schema": 1, "tool": "delete_file", "arguments": {"path": "/safe/a.md"}},
        )
        for index, request in enumerate(malformed_requests):
            incoming = {"request_id": f"file-invalid-{index}", "description": FILE_WRITE_APPROVAL_PREFIX +
                        json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}
            incoming.update({"event": "approval.request", "run_id": "run-1"})
            self.assertIsNone(self.registry.bind_event("run-1", "owner", incoming))

    def test_file_write_event_from_different_run_is_rejected(self):
        request = {"schema": 1, "tool": "write_file", "arguments": {
            "path": "/knowledge-assets/00-Inbox/synthetic.md", "content": "synthetic"}}
        incoming = {"event": "approval.request", "run_id": "run-other", "request_id": "file-other-run",
                    "description": FILE_WRITE_APPROVAL_PREFIX + json.dumps(request, sort_keys=True,
                                                                          separators=(",", ":"))}
        self.assertIsNone(self.registry.bind_event("run-1", "owner", incoming))


if __name__ == "__main__":
    unittest.main()
