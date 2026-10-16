#!/usr/bin/env python3
"""Offline contract tests for safe D077 Harness failure diagnostics."""
from __future__ import annotations

import json
import contextlib
import io
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import hermes_v0215_core_stub_ci as harness  # noqa: E402


class HarnessDiagnosticTests(unittest.TestCase):
    def test_hermes_message_orders_keep_chronological_lists_and_page_boundaries(self):
        oldest = [{"id": message_id} for message_id in (1, 2, 3)]
        latest = [{"id": message_id} for message_id in (1, 2, 3)]
        oldest_page = [{"id": 1}]
        latest_page = [{"id": 3}]

        harness.assert_message_order_contract(latest, oldest, latest_page, oldest_page)

    def test_default_core_origin_is_sent_on_login_session_and_run_posts(self):
        origins = []

        def respond(request):
            origins.append((request.url.path, request.headers.get("origin")))
            if request.url.path == "/api/chat/sessions":
                return harness.httpx.Response(200, json={"session_id": "synthetic-session"})
            if request.url.path.endswith("/runs"):
                return harness.httpx.Response(200, json={"run_id": "synthetic-run"})
            return harness.httpx.Response(200, json={"ok": True})

        with harness.core_client(transport=harness.httpx.MockTransport(respond)) as client:
            client.post("/api/auth/login", json={"password": "synthetic"}).raise_for_status()
            session = client.post("/api/chat/sessions", json={}).json()["session_id"]
            client.post(f"/api/chat/sessions/{session}/runs", json={"input": "synthetic"})

        self.assertEqual([path for path, _ in origins], [
            "/api/auth/login", "/api/chat/sessions", "/api/chat/sessions/synthetic-session/runs"
        ])
        self.assertEqual([origin for _, origin in origins], [harness.CORE_ORIGIN] * 3)

    def test_failure_record_reports_stage_exception_and_http_status_only(self):
        request = harness.httpx.Request("GET", "https://private.example/token=secret-value")
        response = harness.httpx.Response(503, request=request)
        error = harness.httpx.HTTPStatusError(
            "Bearer secret-value raw prompt", request=request, response=response
        )

        record = harness.failure_record("--enabled-scenario", "cross_session_recall", error)
        encoded = json.dumps(record)

        self.assertEqual(record, {
            "mode": "--enabled-scenario",
            "stage": "cross_session_recall",
            "exception_class": "HTTPStatusError",
            "http_status": 503,
            "failure_code": None,
            "exit_code": 1,
        })
        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("private.example", encoded)
        self.assertNotIn("raw prompt", encoded)

    def test_run_input_association_accepts_all_calls_and_ignores_other_run_interference(self):
        question = "How should you format my summaries and units?"
        requests = [
            {"messages": [{"role": "system", "content": question},
                          {"role": "user", "content": "another Run input"}]},
            {"messages": [{"role": "user", "content": question},
                          {"role": "assistant", "content": "tool call"}]},
            {"messages": [{"role": "user", "content": "earlier turn"},
                          {"role": "user", "content": question},
                          {"role": "system", "content": "<personal_memory_json>synthetic</personal_memory_json>"}]},
        ]

        selected = harness.model_requests_for_run_input(requests, question)

        self.assertEqual(selected, [requests[1], requests[2]])
        with self.assertRaisesRegex(harness.HarnessAssertionError, "input_was_rewritten_or_missing"):
            harness.model_requests_for_run_input(requests, "missing synthetic input")

    def test_hermes_v0215_provider_failure_and_stop_status_contracts_are_strict(self):
        self.assertTrue(harness.is_provider_failure_status("failed"))
        self.assertFalse(harness.is_provider_failure_status("interrupted"))
        self.assertFalse(harness.is_provider_failure_status("completed"))
        self.assertTrue(harness.is_user_stop_status("cancelled"))
        self.assertFalse(harness.is_user_stop_status("failed"))
        self.assertFalse(harness.is_user_stop_status("interrupted"))

    def test_inactive_memory_filter_checks_only_tagged_system_memory_block(self):
        question = "Which metric units, imaginary unit labels, and project names do I prefer?"
        candidates = ("metric units", "imaginary unit labels", "cobalt project names")
        request = {"messages": [
            {"role": "system", "content": "Framework context may mention metric units."},
            {"role": "user", "content": question},
            {"role": "system", "content": "<personal_memory_json>{}</personal_memory_json>"},
        ]}

        harness.assert_memory_candidates_filtered(request, question, candidates)

        for candidate in candidates:
            with self.subTest(candidate=candidate):
                request["messages"][-1]["content"] = (
                    f"<personal_memory_json>{{'candidate': '{candidate}'}}</personal_memory_json>"
                )
                with self.assertRaisesRegex(
                    harness.HarnessAssertionError, "revoked_expired_inference_filter_failed"
                ):
                    harness.assert_memory_candidates_filtered(request, question, candidates)

    def test_inactive_memory_filter_requires_exact_original_user_input(self):
        question = "Which metric units, imaginary unit labels, and project names do I prefer?"
        request = {"messages": [
            {"role": "user", "content": question + " Please also infer more."},
            {"role": "system", "content": "<personal_memory_json>{}</personal_memory_json>"},
        ]}

        with self.assertRaisesRegex(harness.HarnessAssertionError, "input_was_rewritten_or_missing"):
            harness.assert_memory_candidates_filtered(
                request, question, ("metric units", "imaginary unit labels", "cobalt project names")
            )

    def test_inactive_filter_fails_if_only_one_of_multiple_run_requests_leaks(self):
        question = "Which metric units, imaginary unit labels, and project names do I prefer?"
        candidates = ("metric units", "imaginary unit labels", "cobalt project names")
        requests = [
            {"messages": [{"role": "user", "content": question},
                          {"role": "system", "content": "<personal_memory_json>{}</personal_memory_json>"}]},
            {"messages": [{"role": "user", "content": "unrelated run"},
                          {"role": "system", "content": "<personal_memory_json>metric units</personal_memory_json>"}]},
            {"messages": [{"role": "user", "content": question},
                          {"role": "system", "content": "<personal_memory_json>{'inference':'cobalt project names'}</personal_memory_json>"}]},
        ]

        with self.assertRaisesRegex(
            harness.HarnessAssertionError, "revoked_expired_inference_filter_failed"
        ):
            harness.assert_run_memory_candidates_filtered(requests, question, candidates)

    def test_failure_record_exposes_only_allowlisted_cross_session_code(self):
        error = harness.HarnessAssertionError("cross_session_instructions_not_observed_by_stub")
        record = harness.failure_record("--enabled-scenario", "cross_session_recall", error)
        self.assertEqual(record["failure_code"], "cross_session_instructions_not_observed_by_stub")
        self.assertEqual(set(record), {
            "mode", "stage", "exception_class", "http_status", "failure_code", "exit_code"
        })
        self.assertNotIn("secret", json.dumps(record))

    def test_failure_record_discards_unrecognized_failure_code(self):
        error = RuntimeError("secret prompt")
        error.failure_code = "secret prompt"
        record = harness.failure_record("--enabled-scenario", "cross_session_recall", error)
        self.assertIsNone(record["failure_code"])

    def test_scenario_runner_continues_independent_case_and_blocks_dependents(self):
        results = {}
        executed = []

        def fail_case():
            executed.append("first")
            raise harness.HarnessAssertionError("cross_session_run_failed")

        def independent_case():
            executed.append("independent")

        def dependent_case():
            executed.append("dependent")

        harness.run_scenario(results, "cross_session_recall", fail_case)
        harness.run_scenario(results, "failed_run_no_learning", independent_case)
        harness.run_scenario(results, "corrected_recall", dependent_case,
                             requires=("cross_session_recall",))

        self.assertEqual(executed, ["first", "independent"])
        self.assertEqual(results, {
            "cross_session_recall": {"status": "FAIL", "failure_code": "cross_session_run_failed"},
            "failed_run_no_learning": {"status": "PASS", "failure_code": None},
            "corrected_recall": {"status": "BLOCKED", "failure_code": "prerequisite_not_passed"},
        })
        self.assertEqual(harness.scenario_status(results), "FAIL")

    def test_scenario_exceptions_map_to_fixed_safe_codes(self):
        provider_error = harness.httpx.HTTPStatusError(
            "private prompt and token", request=harness.httpx.Request("GET", "http://core/private"),
            response=harness.httpx.Response(503),
        )
        flags_off_error = harness.httpx.HTTPStatusError(
            "private prompt and token", request=harness.httpx.Request("POST", "http://core/private"),
            response=harness.httpx.Response(403),
        )
        cases = [
            ("failed_run_no_learning", provider_error, "scenario_http_5xx"),
            ("flags_off", flags_off_error, "scenario_http_4xx"),
            ("network", harness.httpx.ConnectError("private prompt"), "scenario_http_transport_error"),
            ("stub", harness.urllib.error.URLError("secret host"), "stub_transport_error"),
            ("container", subprocess.TimeoutExpired("docker", 5), "scenario_container_lifecycle_error"),
            ("shape", KeyError("private field"), "scenario_response_shape_error"),
            ("unknown", RuntimeError("secret prompt"), "scenario_unexpected_exception"),
        ]

        for name, error, expected_code in cases:
            with self.subTest(name=name):
                results = {}

                def fail(error=error):
                    raise error

                harness.run_scenario(results, name, fail)
                self.assertEqual(results[name], {"status": "FAIL", "failure_code": expected_code})
                self.assertNotIn("private", json.dumps(results))
                self.assertNotIn("secret", json.dumps(results))

    def test_stub_state_and_control_failures_have_safe_fixed_codes(self):
        error = harness.urllib.error.URLError("private host and credentials")
        with patch.object(harness.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(harness.HarnessAssertionError, "stub_state_unavailable"):
                harness.stub_state()
            with self.assertRaisesRegex(harness.HarnessAssertionError, "stub_control_unavailable"):
                harness.control_stub({"release": True})

    def test_scenario_result_parser_fails_closed_without_leaking_output(self):
        parsed = harness.scenario_result_from_output("secret prompt", "D077_ENABLED_RESULT")
        encoded = json.dumps(parsed)
        self.assertEqual(parsed["status"], "FAIL")
        self.assertEqual(parsed["scenarios"]["scenario_result"]["failure_code"],
                         "scenario_result_missing")
        self.assertNotIn("secret", encoded)

    def test_scenario_result_parser_whitelists_fields_and_codes(self):
        output = 'D077_ENABLED_RESULT {"status":"PASS","scenarios":{"cross_session_recall":' \
                 '{"status":"FAIL","failure_code":"secret","prompt":"secret prompt"}}}'
        parsed = harness.scenario_result_from_output(output, "D077_ENABLED_RESULT")
        encoded = json.dumps(parsed)
        self.assertEqual(parsed["status"], "FAIL")
        self.assertEqual(parsed["scenarios"]["scenario_result"]["failure_code"],
                         "scenario_result_missing")
        self.assertNotIn("secret", encoded)
        self.assertNotIn("prompt", encoded)

    def test_transport_failure_has_exception_class_without_http_status(self):
        error = harness.httpx.ConnectTimeout("sensitive url and prompt")

        record = harness.failure_record("--network-preflight", "network_health_probes", error)

        self.assertEqual(record["exception_class"], "ConnectTimeout")
        self.assertIsNone(record["http_status"])

    def test_invalid_mode_and_stage_are_replaced_with_safe_labels(self):
        record = harness.failure_record("--enabled-scenario secret", "Bearer secret", RuntimeError("do not log"))

        self.assertEqual(record["mode"], "unknown_mode")
        self.assertEqual(record["stage"], "unknown_stage")
        self.assertNotIn("secret", json.dumps(record))
        self.assertNotIn("do not log", json.dumps(record))

    def test_http_status_is_limited_to_valid_status_codes(self):
        request = harness.httpx.Request("GET", "http://stub/health")
        response = harness.httpx.Response(700, request=request)
        error = harness.httpx.HTTPStatusError("ignored", request=request, response=response)

        self.assertIsNone(harness.http_status_from_exception(error))

    def test_http_probe_error_preserves_status_without_response_body(self):
        error = harness.ProbeHTTPStatusError(404)

        record = harness.failure_record("--network-preflight", "network_preflight_assertions", error)

        self.assertEqual(record["exception_class"], "ProbeHTTPStatusError")
        self.assertEqual(record["http_status"], 404)

    def test_configured_egress_target_parser_rejects_noncanonical_values(self):
        with patch.dict("os.environ", {"D077_DENY_EGRESS_TARGETS": "192.168.3.1:443,192.168.3.27:5001"}):
            self.assertEqual(harness.configured_egress_targets(),
                             [("192.168.3.1", 443), ("192.168.3.27", 5001)])
        for value in ("https://192.168.3.1:443", "192.168.3.999:443", "192.168.3.1:0", "host:443"):
            with patch.dict("os.environ", {"D077_DENY_EGRESS_TARGETS": value}):
                with self.assertRaises(ValueError):
                    harness.configured_egress_targets()

    def test_scenario_wrapper_emits_marker_without_exception_message(self):
        output = io.StringIO()

        def fail_in_named_stage():
            harness.set_scenario_stage("initial_run_learning")
            raise RuntimeError("Bearer secret-value raw prompt")

        with contextlib.redirect_stdout(output):
            result = harness.run_diagnostic_mode("--enabled-scenario", fail_in_named_stage)

        lines = output.getvalue().splitlines()
        self.assertEqual(result, 1)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("D077_HARNESS_FAILURE "))
        record = json.loads(lines[0].removeprefix("D077_HARNESS_FAILURE "))
        self.assertEqual(record["stage"], "initial_run_learning")
        self.assertEqual(record["exception_class"], "RuntimeError")
        self.assertNotIn("secret-value", lines[0])
        self.assertNotIn("raw prompt", lines[0])

    def test_peer_exit_without_marker_emits_bounded_fallback(self):
        failed = subprocess.CompletedProcess(
            args=["docker"], returncode=7, stdout="", stderr="Bearer secret-value raw prompt"
        )
        output = io.StringIO()

        with patch.object(harness, "run", return_value=failed), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "isolated_peer_failed"):
                harness.run_in_container("core-test", "--enabled-scenario")

        record = json.loads(output.getvalue().removeprefix("D077_HARNESS_FAILURE "))
        self.assertEqual(record["stage"], "peer_process_exit")
        self.assertIsNone(record["exception_class"])
        self.assertEqual(record["exit_code"], 7)
        self.assertNotIn("secret-value", output.getvalue())
        self.assertNotIn("raw prompt", output.getvalue())

    def test_peer_timeout_emits_only_timeout_class_and_mode(self):
        timeout = subprocess.TimeoutExpired(
            cmd=["docker", "exec"], timeout=900, output="secret-value", stderr="raw prompt"
        )
        output = io.StringIO()

        with patch.object(harness, "run", side_effect=timeout), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "isolated_peer_timeout"):
                harness.run_in_container("core-test", "--flags-off")

        record = json.loads(output.getvalue().removeprefix("D077_HARNESS_FAILURE "))
        self.assertEqual(record["stage"], "peer_process_timeout")
        self.assertEqual(record["exception_class"], "TimeoutExpired")
        self.assertEqual(record["exit_code"], 124)
        self.assertNotIn("secret-value", output.getvalue())
        self.assertNotIn("raw prompt", output.getvalue())


if __name__ == "__main__":
    unittest.main()
