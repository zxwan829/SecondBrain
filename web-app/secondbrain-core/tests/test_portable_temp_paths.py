from pathlib import Path
import re
import unittest


class PortableTemporaryPathTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[3]

    def test_core_tests_and_linux_workflow_do_not_hardcode_macos_private_tmp(self):
        forbidden_path = "/private/" + "tmp"
        core_tests = self.repo_root / "web-app" / "secondbrain-core" / "tests"
        workflow = self.repo_root / ".github" / "workflows" / "d077-core-linux-tests.yml"
        scanned_files = sorted(core_tests.rglob("*.py")) + [workflow]

        violations = []
        for path in scanned_files:
            text = path.read_text(encoding="utf-8")
            if forbidden_path in text:
                violations.append(str(path.relative_to(self.repo_root)))

        self.assertEqual(violations, [], "Non-portable temporary path found in: " + ", ".join(violations))

    def test_linux_workflow_does_not_recreate_the_macos_temp_path_shim(self):
        workflow = (self.repo_root / ".github" / "workflows" / "d077-core-linux-tests.yml").read_text(encoding="utf-8")
        shim = re.compile(r"sudo\s+install\s+-d\s+-m\s+1777")
        self.assertIsNone(shim.search(workflow), "Linux workflow must not create the macOS temporary-directory compatibility shim")


if __name__ == "__main__":
    unittest.main()
