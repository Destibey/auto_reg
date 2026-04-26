import unittest
from unittest import mock

from api.integrations import BackfillRequest, backfill_integrations
from core.db import AccountModel


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def exec(self, _query):
        return _ExecResult(self._rows)


class IntegrationsBackfillTests(unittest.TestCase):
    def _grok_model(self) -> AccountModel:
        account = AccountModel(
            platform="grok",
            email="grok@example.com",
            password="secret",
            status="registered",
        )
        account.set_extra({"sso": "sso-token", "sso_rw": "sso-rw-token"})
        return account

    def _config_getter(self, values: dict[str, str]):
        def _get(key: str, default: str = "") -> str:
            return values.get(key, default)

        return _get

    def test_grok_backfill_imports_grok2api_then_registers_cpa_upstream(self):
        fake_session = _FakeSession([self._grok_model()])

        with mock.patch("api.integrations.Session", return_value=fake_session):
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
                            result = backfill_integrations(BackfillRequest(platforms=["grok"]))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(
            result["items"][0]["results"],
            [
                {"name": "grok2api", "ok": True, "msg": "导入成功"},
                {"name": "CPA/CLIProxyAPI(grok2api)", "ok": True, "msg": "CPA 已接入 grok2api 上游"},
            ],
        )
        bridge.assert_called_once()


if __name__ == "__main__":
    unittest.main()
