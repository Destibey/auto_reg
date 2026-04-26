import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.external_apps import _ensure_grok2api_runtime_config


class ExternalAppsGrok2apiConfigTests(unittest.TestCase):
    def test_runtime_config_writes_admin_and_api_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "config.defaults.toml").write_text(
                '[app]\napp_key = "old-admin"\napi_key = "old-api"\n',
                encoding="utf-8",
            )

            def _get_setting(key: str, default: str = "") -> str:
                values = {
                    "grok2api_app_key": "admin-key",
                    "grok2api_api_key": "api-key",
                }
                return values.get(key, default)

            with mock.patch("services.external_apps._get_setting", side_effect=_get_setting):
                _ensure_grok2api_runtime_config(repo)

            text = (repo / "data" / "config.toml").read_text(encoding="utf-8")
            self.assertIn('app_key = "admin-key"', text)
            self.assertIn('api_key = "api-key"', text)


if __name__ == "__main__":
    unittest.main()
