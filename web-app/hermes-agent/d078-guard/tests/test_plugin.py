import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
spec = importlib.util.spec_from_file_location("secondbrain_d078_guard", PLUGIN_PATH)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class D078PluginTests(unittest.TestCase):
    def test_manifest_declares_registered_pre_tool_call_hook(self):
        manifest = (PLUGIN_PATH.parent / "plugin.yaml").read_text(encoding="utf-8")
        self.assertRegex(manifest, r"(?m)^provides_hooks:\s*\n\s+-\s+pre_tool_call\s*$")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "hermes"
        self.home.mkdir()
        for name in ("sessions", "pending/skills", "logs", "memories", "skills/demo"):
            (self.home / name).mkdir(parents=True, exist_ok=True)
        self.business = self.root / "business"
        self.business.mkdir()
        (self.business / "capture.md").write_text("synthetic", encoding="utf-8")
        self.backend_patch = patch.object(plugin, "_terminal_backend_type", return_value="local")
        self.backend_patch.start()
        self.hooks_patch = patch.object(plugin, "_conflicting_pre_tool_call_hooks", return_value=False)
        self.hooks_patch.start()

    def tearDown(self):
        self.backend_patch.stop()
        self.hooks_patch.stop()
        self.temp.cleanup()

    def test_session_state_config_and_search_ancestors_are_denied(self):
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": str(self.home / "sessions" / "synthetic.jsonl")}, hermes_home=self.home))
        self.assertIn("hermes_private_path", plugin.path_guard("search_files", {
            "path": str(self.home)}, hermes_home=self.home))
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": str(self.home / "config.yaml")}, hermes_home=self.home))
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": str(self.home / "pending/skills/proposal.json")}, hermes_home=self.home))
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": str(self.home / "MEMORY.md")}, hermes_home=self.home))
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": str(self.home / "Sessions/synthetic.jsonl")}, hermes_home=self.home))

    def test_symlink_and_relative_traversal_cannot_reach_sessions(self):
        link = self.home / "skills" / "session-link"
        link.symlink_to(self.home / "sessions", target_is_directory=True)
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": str(link / "x.jsonl")}, hermes_home=self.home))
        cwd = self.home / "skills" / "demo"
        self.assertIn("hermes_private_path", plugin.path_guard("read_file", {
            "path": "../../sessions/x.jsonl"}, hermes_home=self.home, cwd=cwd))

    def test_common_credential_paths_and_secret_files_are_denied(self):
        for path in (self.root / ".ssh/id_ed25519", self.root / "workspace/.env",
                     self.root / "workspace/service.pem"):
            self.assertIsNotNone(plugin.path_guard("read_file", {"path": str(path)}, hermes_home=self.home))
        self.assertIn("hermes_private_path", plugin.path_guard("search_files", {
            "path": str(Path.home())}, hermes_home=self.home))

    def test_business_reads_and_capture_safe_write_targets_remain_available(self):
        self.assertIsNone(plugin.path_guard("read_file", {"path": str(self.business / "capture.md")},
                                            hermes_home=self.home))
        self.assertIsNone(plugin.path_guard("write_file", {"path": str(self.business / "capture.md")},
                                            hermes_home=self.home))

    def test_generic_file_write_waits_for_run_approval_and_binds_resolved_target(self):
        alias = self.root / "capture-alias.md"
        alias.symlink_to(self.business / "capture.md")
        args = {"path": str(alias), "content": "synthetic replacement"}
        with patch.object(plugin, "_conflicting_pre_tool_call_hooks", return_value=False):
            first = plugin.pre_tool_call("write_file", args)
            second = plugin.pre_tool_call("write_file", {"path": str(alias), "content": "synthetic replacement"})
        self.assertEqual(first["action"], "approve")
        self.assertTrue(first["message"].startswith(plugin.FILE_WRITE_APPROVAL_PREFIX))
        self.assertEqual(args["path"], str((self.business / "capture.md").resolve()))
        self.assertNotEqual(first["rule_key"], second["rule_key"])
        request = json.loads(first["message"][len(plugin.FILE_WRITE_APPROVAL_PREFIX):])
        self.assertEqual(request, {"schema": 1, "tool": "write_file", "arguments": args})

    def test_sensitive_skill_and_unverifiable_writes_block_before_approval(self):
        with patch.object(plugin, "_conflicting_pre_tool_call_hooks", return_value=False), \
             patch.object(plugin, "_hermes_homes", return_value=[self.home]):
            sensitive = plugin.pre_tool_call("write_file", {
                "path": str(self.home / "config.yaml"), "content": "synthetic"})
            skill = plugin.pre_tool_call("patch", {
                "path": str(self.home / "skills/demo/SKILL.md"), "old_string": "a", "new_string": "b"})
            missing = plugin.pre_tool_call("patch", {"mode": "patch", "patch": "*** Begin Patch"})
        for result in (sensitive, skill, missing):
            self.assertEqual(result["action"], "block")
        self.assertIn("hermes_private_path", sensitive["message"])
        self.assertIn("skills_write_gate", skill["message"])
        self.assertIn("path_guard_missing", missing["message"])
        with patch.object(plugin, "_conflicting_pre_tool_call_hooks", return_value=False):
            multi_file = plugin.pre_tool_call("patch", {
                "mode": "patch", "path": str(self.business / "capture.md"), "patch": "*** Update File: other.md"})
            altered = plugin.pre_tool_call("write_file", {
                "path": str(self.business / "capture.md"), "content": "x", "cross_profile": True})
        self.assertEqual(multi_file["action"], "block")
        self.assertIn("file_write_target_ambiguous", multi_file["message"])
        self.assertEqual(altered["action"], "block")
        self.assertIn("file_write_arguments_invalid", altered["message"])

    def test_file_write_blocks_if_another_pre_tool_hook_could_rewrite_target(self):
        with patch.object(plugin, "_conflicting_pre_tool_call_hooks", return_value=True):
            result = plugin.pre_tool_call("write_file", {
                "path": str(self.business / "capture.md"), "content": "synthetic"})
        self.assertEqual(result["action"], "block")
        self.assertIn("file_write_binding_ambiguous", result["message"])

    def test_generic_file_write_cannot_bypass_skill_write_approval(self):
        self.assertIn("skills_write_gate", plugin.path_guard("write_file", {
            "path": str(self.home / "skills/demo/SKILL.md")}, hermes_home=self.home))
        self.assertIn("skills_write_gate", plugin.path_guard("patch", {
            "path": str(self.home / "skills/demo/SKILL.md")}, hermes_home=self.home))
        self.assertIn("path_guard_missing", plugin.path_guard("read_file", {}, hermes_home=self.home))

    def test_each_execution_call_requires_unique_one_call_approval(self):
        with patch.object(plugin, "_approval_mode_bypass", return_value=False):
            args = {"command": "pwd", "workdir": str(self.business)}
            first = plugin.pre_tool_call("terminal", args)
            second = plugin.pre_tool_call("terminal", args)
            process = plugin.pre_tool_call("process_manage", {"action": "list"})
            code = plugin.pre_tool_call("execute_code", {"code": "print('synthetic')", "reset": False})
        self.assertEqual(first["action"], "approve")
        self.assertNotEqual(first["rule_key"], second["rule_key"])
        self.assertEqual(process["action"], "approve")
        self.assertEqual(code["action"], "approve")
        payload = json.loads(first["message"][len(plugin.APPROVAL_PREFIX):])
        self.assertEqual(payload, {"schema": 1, "tool": "terminal", "arguments": args})
        self.assertEqual(json.loads(process["message"][len(plugin.APPROVAL_PREFIX):])["arguments"], {"action": "list"})
        self.assertEqual(json.loads(code["message"][len(plugin.APPROVAL_PREFIX):])["arguments"],
                         {"code": "print('synthetic')", "reset": False})

    def test_terminal_requires_explicit_absolute_workdir_and_pinned_arguments(self):
        with patch.object(plugin, "_approval_mode_bypass", return_value=False):
            missing = plugin.pre_tool_call("terminal", {"command": "pwd"})
            relative = plugin.pre_tool_call("terminal", {"command": "pwd", "workdir": "business"})
            unknown = plugin.pre_tool_call("terminal", {
                "command": "pwd", "workdir": str(self.business), "unknown": "value"})
        for result in (missing, relative, unknown):
            self.assertEqual(result["action"], "block")
            self.assertIn("terminal_review_ambiguous", result["message"])

    def test_terminal_refuses_backend_cwd_remapping(self):
        with patch.object(plugin, "_approval_mode_bypass", return_value=False), \
             patch.object(plugin, "_terminal_backend_type", return_value="docker"):
            result = plugin.pre_tool_call("terminal", {
                "command": "pwd", "workdir": str(self.business)})
        self.assertEqual(result["action"], "block")
        self.assertIn("terminal_review_ambiguous", result["message"])

    def test_execution_fails_closed_when_another_hook_can_rewrite_approved_args(self):
        with patch.object(plugin, "_approval_mode_bypass", return_value=False), \
             patch.object(plugin, "_conflicting_pre_tool_call_hooks", return_value=True):
            result = plugin.pre_tool_call("execute_code", {"code": "print('synthetic')"})
        self.assertEqual(result["action"], "block")
        self.assertIn("execution_binding_ambiguous", result["message"])

    def test_process_and_code_approval_require_reviewable_pinned_arguments(self):
        with patch.object(plugin, "_approval_mode_bypass", return_value=False):
            bad_process = plugin.pre_tool_call("process_manage", {"action": "kill"})
            extra_code = plugin.pre_tool_call("execute_code", {"code": "print(1)", "cwd": "/tmp"})
        self.assertEqual(bad_process["action"], "block")
        self.assertEqual(extra_code["action"], "block")

    def test_pinned_v0222_file_registry_names_and_path_arguments_are_guarded(self):
        # Verified against Hermes v0.22.2 fixed source: tools/file_tools.py registers
        # read_file/write_file/patch/search_files, all with the path parameter.
        registry_contract = {
            "read_file": {"path": str(self.home / "sessions" / "synthetic.jsonl")},
            "write_file": {"path": str(self.home / "config.yaml"), "content": "synthetic"},
            "patch": {"path": str(self.home / "sessions" / "synthetic.jsonl"),
                      "old_string": "a", "new_string": "b"},
            "search_files": {"pattern": "synthetic", "path": str(self.home)},
        }
        for tool_name, args in registry_contract.items():
            self.assertIn(tool_name, plugin._READ_TOOLS | plugin._WRITE_TOOLS)
            self.assertIn("hermes_private_path", plugin.path_guard(
                tool_name, args, hermes_home=self.home))
        # Patch's alternate content-only mode has no top-level path; it must fail closed.
        self.assertIn("path_guard_missing", plugin.path_guard(
            "patch", {"mode": "patch", "patch": "*** Update File: ~/.hermes/sessions/x"},
            hermes_home=self.home))

    def test_ambiguous_commands_and_disabled_approval_policy_fail_closed(self):
        with patch.object(plugin, "_approval_mode_bypass", return_value=False):
            for command in ("echo a && echo b", "python3 task.py", "echo $HOME", "sh -c 'id'"):
                result = plugin.pre_tool_call("terminal", {"command": command})
                self.assertEqual(result["action"], "block", command)
                self.assertIn("terminal_review_ambiguous", result["message"])
        with patch.object(plugin, "_approval_mode_bypass", return_value=True):
            self.assertEqual(plugin.pre_tool_call("terminal", {"command": "pwd"})["action"], "block")

    def test_unexpected_guard_errors_fail_closed_for_execution_and_file_tools(self):
        with patch.object(plugin, "_approval_mode_bypass", side_effect=RuntimeError("synthetic")):
            terminal = plugin.pre_tool_call("terminal", {"command": "pwd"})
        with patch.object(plugin, "path_guard", side_effect=RuntimeError("synthetic")):
            read = plugin.pre_tool_call("read_file", {"path": str(self.business / "capture.md")})
        self.assertEqual(terminal["action"], "block")
        self.assertIn("approval_policy_unavailable", terminal["message"])
        self.assertEqual(read["action"], "block")
        self.assertIn("path_guard_unavailable", read["message"])

    def test_plugin_registers_real_pre_tool_hook(self):
        class Context:
            def __init__(self): self.hooks = {}
            def register_hook(self, name, callback): self.hooks[name] = callback
        context = Context()
        plugin.register(context)
        self.assertIs(context.hooks["pre_tool_call"], plugin.pre_tool_call)


if __name__ == "__main__":
    unittest.main()
