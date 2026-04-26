import unittest
from unittest import mock

from core.base_platform import Account
from services.external_sync import sync_account


class ExternalSyncTests(unittest.TestCase):
    def _grok_account(self) -> Account:
        return Account(
            platform="grok",
            email="grok@example.com",
            password="secret",
            extra={"sso": "sso-token", "sso_rw": "sso-rw-token"},
        )

    def _config_getter(self, values: dict[str, str]):
        def _get(key: str, default: str = "") -> str:
            return values.get(key, default)

        return _get

    def test_grok_sync_does_not_upload_account_to_cpa_when_cpa_configured(self):
        with mock.patch(
            "core.config_store.config_store.get",
            side_effect=self._config_getter(
                {
                    "cliproxyapi_base_url": "http://cpa.example",
                    "cliproxyapi_management_key": "secret",
                }
            ),
        ):
            results = sync_account(self._grok_account())

        self.assertEqual(results, [])

    def test_grok_sync_imports_grok2api_then_registers_cpa_upstream(self):
        with mock.patch(
            "core.config_store.config_store.get",
            side_effect=self._config_getter(
                {
                    "cliproxyapi_base_url": "http://cpa.example",
                    "cliproxyapi_management_key": "secret",
                    "grok2api_url": "http://grok2api.example",
                    "grok2api_app_key": "grok2api-key",
                }
            ),
        ):
            with mock.patch("services.grok2api_runtime.ensure_grok2api_ready", return_value=(True, "ok")):
                with mock.patch(
                    "platforms.grok.grok2api_upload.upload_to_grok2api",
                    return_value=(True, "导入成功"),
                ):
                    with mock.patch(
                        "services.grok2api_cpa_bridge.ensure_grok2api_openai_compat_in_cpa",
                        return_value=(True, "CPA 已接入 grok2api 上游"),
                    ) as bridge:
                        results = sync_account(self._grok_account())

        self.assertEqual(
            results,
            [
                {"name": "grok2api", "ok": True, "msg": "导入成功"},
                {"name": "CPA/CLIProxyAPI(grok2api)", "ok": True, "msg": "CPA 已接入 grok2api 上游"},
            ],
        )
        bridge.assert_called_once()


if __name__ == "__main__":
    unittest.main()
