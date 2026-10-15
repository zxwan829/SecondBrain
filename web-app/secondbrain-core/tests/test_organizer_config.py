import unittest
from unittest.mock import patch

from secondbrain_core.modules.organizer_config import configured_organizer_model
from secondbrain_core.modules.siliconflow_organizer import MODEL_DEFAULT


class OrganizerConfigurationTests(unittest.TestCase):
    def test_adapter_is_not_loaded_or_secret_read_by_default(self):
        with patch("secondbrain_core.modules.organizer_config.SiliconFlowOrganizerModel.from_secret_file") as load:
            self.assertIsNone(configured_organizer_model({}))
            load.assert_not_called()

    def test_explicit_opt_in_uses_private_file_and_deepseek_default_candidate(self):
        expected = object()
        env = {"SB_ORGANIZER_MODEL_ENABLED": "true", "SB_ORGANIZER_API_KEY_FILE": "/private/organizer-key"}
        with patch("secondbrain_core.modules.organizer_config.SiliconFlowOrganizerModel.from_secret_file",
                   return_value=expected) as load:
            self.assertIs(configured_organizer_model(env), expected)
        load.assert_called_once_with("/private/organizer-key", model=MODEL_DEFAULT)

    def test_invalid_enable_flag_and_missing_secret_fail_closed(self):
        with self.assertRaises(RuntimeError):
            configured_organizer_model({"SB_ORGANIZER_MODEL_ENABLED": "yes"})
        with self.assertRaises(RuntimeError):
            configured_organizer_model({"SB_ORGANIZER_MODEL_ENABLED": "true"})


if __name__ == "__main__":
    unittest.main()
