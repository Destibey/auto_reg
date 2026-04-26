import unittest
from unittest import mock

from core.base_platform import Account, RegisterConfig
from platforms.grok.plugin import GrokPlatform


class GrokPluginActionsTests(unittest.TestCase):
    def _account(self) -> Account:
        return Account(
            platform="grok",
            email="demo@example.com",
            password="secret",
            extra={
                "sso": "sso-token",
                "sso_rw": "sso-rw-token",
            },
        )

    def test_actions_include_only_grok2api_target(self):
        platform = GrokPlatform(config=RegisterConfig())

        action_ids = [item["id"] for item in platform.get_platform_actions()]

        self.assertNotIn("upload_cpa", action_ids)
        self.assertIn("upload_grok2api", action_ids)

    def test_upload_grok2api_action_uses_grok2api_upload(self):
        platform = GrokPlatform(config=RegisterConfig())

        with mock.patch(
            "platforms.grok.grok2api_upload.upload_to_grok2api",
            return_value=(True, "导入成功"),
        ) as upload_mock:
            result = platform.execute_action("upload_grok2api", self._account(), {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["message"], "导入成功")
        upload_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
