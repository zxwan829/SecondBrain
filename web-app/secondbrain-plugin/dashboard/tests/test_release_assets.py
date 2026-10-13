import hashlib
import json
import unittest
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1]
FE4_BASE_SIZE = 78_453
FE4_BASE_SHA256 = "6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe"
REVIEW_MARKER = b"/* Additive Review view for the existing FE-4 plugin. Promote stays disabled. */"


class DashboardReleaseAssetTests(unittest.TestCase):
    def test_review_bundle_preserves_accepted_fe4_base_byte_for_byte(self):
        bundle = (DASHBOARD / "index-20261013-fe4-review.js").read_bytes()
        marker_at = bundle.index(REVIEW_MARKER)
        self.assertEqual(bundle[marker_at - 1:marker_at], b"\n")
        fe4_base = bundle[:marker_at - 1]
        self.assertEqual(len(fe4_base), FE4_BASE_SIZE)
        self.assertEqual(hashlib.sha256(fe4_base).hexdigest(), FE4_BASE_SHA256)
        self.assertIn(b"id:`waiting`", fe4_base)
        self.assertIn(b"className:`module-title`", fe4_base)
        self.assertIn(b"className:`nav-item", fe4_base)
        self.assertIn(b"className:`nav-label`", fe4_base)
        self.assertEqual(fe4_base.count(b"register(`secondbrain`,"), 1)

    def test_review_addon_is_single_and_hooks_the_fe4_review_controls(self):
        bundle = (DASHBOARD / "index-20261013-fe4-review.js").read_bytes()
        addon = bundle[bundle.index(REVIEW_MARKER):]
        self.assertEqual(addon.count(b"__SB_CORE_REVIEW_VIEW__"), 2)
        self.assertEqual(addon.count(b"new MutationObserver(attach)"), 1)
        self.assertIn(b"document.getElementById(\"waiting\")", addon)
        self.assertIn(b"querySelectorAll(\".nav-item\")", addon)
        self.assertIn(b"/review/items", addon)
        self.assertNotIn(b"__HERMES_PLUGINS__", addon)
        self.assertNotIn(b"register(`secondbrain`,", addon)

    def test_manifest_references_combined_bundle_and_existing_api_css(self):
        manifest = json.loads((DASHBOARD / "manifest.json").read_text())
        self.assertEqual(manifest["version"], "0.2.3")
        self.assertEqual(manifest["entry"], "index-20261013-fe4-review.js")
        self.assertEqual(manifest["css"], "style-20261010-v3.css")
        self.assertEqual(manifest["api"], "plugin_api.py")
        self.assertTrue((DASHBOARD / manifest["entry"]).is_file())


if __name__ == "__main__":
    unittest.main()
