import unittest
from unittest import mock

from services.grok2api_cpa_bridge import (
    build_grok2api_openai_compat_entry,
    ensure_grok2api_openai_compat_in_cpa,
    normalize_openai_base_url,
)


class _Response:
    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class Grok2apiCpaBridgeTests(unittest.TestCase):
    def test_normalize_openai_base_url_appends_v1_once(self):
        self.assertEqual(
            normalize_openai_base_url("http://grok2api.example"),
            "http://grok2api.example/v1",
        )
        self.assertEqual(
            normalize_openai_base_url("http://grok2api.example/v1/"),
            "http://grok2api.example/v1",
        )

    def test_build_entry_uses_model_aliases_and_optional_api_key(self):
        entry = build_grok2api_openai_compat_entry(
            grok2api_url="http://grok2api.example",
            grok2api_api_key="grok-api-key",
            models=["grok-4.20-auto", "grok-4.20-auto", "grok-4.20-fast"],
        )

        self.assertEqual(entry["name"], "grok2api")
        self.assertEqual(entry["base-url"], "http://grok2api.example/v1")
        self.assertEqual(entry["api-key-entries"], [{"api-key": "grok-api-key"}])
        self.assertEqual(
            entry["models"],
            [
                {"name": "grok-4.20-auto", "alias": "grok-4.20-auto"},
                {"name": "grok-4.20-fast", "alias": "grok-4.20-fast"},
            ],
        )

    def test_ensure_upserts_grok2api_provider_without_touching_other_entries(self):
        existing = {
            "openai-compatibility": [
                {
                    "name": "openrouter",
                    "base-url": "https://openrouter.ai/api/v1",
                    "api-key-entries": [{"api-key": "sk-or"}],
                    "models": [{"name": "x", "alias": "x"}],
                }
            ]
        }

        with mock.patch("services.grok2api_cpa_bridge.requests.get", return_value=_Response(existing)) as get_mock:
            with mock.patch("services.grok2api_cpa_bridge.requests.put", return_value=_Response({"ok": True})) as put_mock:
                ok, msg = ensure_grok2api_openai_compat_in_cpa(
                    cpa_url="http://cpa.example",
                    cpa_api_key="secret",
                    grok2api_url="http://grok2api.example",
                    grok2api_api_key="grok-api-key",
                    models=["grok-4.20-auto"],
                )

        self.assertTrue(ok)
        self.assertEqual(msg, "CPA 已接入 grok2api 上游")
        get_mock.assert_called_once()
        put_mock.assert_called_once()
        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(payload[0]["name"], "openrouter")
        self.assertEqual(payload[1]["name"], "grok2api")
        self.assertEqual(payload[1]["base-url"], "http://grok2api.example/v1")
        self.assertEqual(payload[1]["api-key-entries"], [{"api-key": "grok-api-key"}])

    def test_ensure_skips_put_when_entry_already_matches(self):
        existing = {
            "openai-compatibility": [
                build_grok2api_openai_compat_entry(
                    grok2api_url="http://grok2api.example",
                    models=["grok-4.20-auto"],
                )
            ]
        }

        with mock.patch("services.grok2api_cpa_bridge.requests.get", return_value=_Response(existing)):
            with mock.patch("services.grok2api_cpa_bridge.requests.put") as put_mock:
                ok, msg = ensure_grok2api_openai_compat_in_cpa(
                    cpa_url="http://cpa.example",
                    cpa_api_key="secret",
                    grok2api_url="http://grok2api.example",
                    models=["grok-4.20-auto"],
                )

        self.assertTrue(ok)
        self.assertEqual(msg, "CPA grok2api 上游已存在")
        put_mock.assert_not_called()

    def test_ensure_prefers_cpa_visible_grok2api_url_from_config(self):
        values = {
            "cliproxyapi_base_url": "http://cpa.example",
            "cliproxyapi_management_key": "secret",
            "grok2api_url": "http://127.0.0.1:8011",
            "grok2api_cpa_url": "http://host.docker.internal:8011",
        }

        def _get(key: str, default: str = "") -> str:
            return values.get(key, default)

        with mock.patch("core.config_store.config_store.get", side_effect=_get):
            with mock.patch("services.grok2api_cpa_bridge.requests.get", return_value=_Response({"openai-compatibility": []})):
                with mock.patch("services.grok2api_cpa_bridge.requests.put", return_value=_Response({"ok": True})) as put_mock:
                    ok, msg = ensure_grok2api_openai_compat_in_cpa(models=["grok-4.20-auto"])

        self.assertTrue(ok)
        self.assertEqual(msg, "CPA 已接入 grok2api 上游")
        payload = put_mock.call_args.kwargs["json"]
        self.assertEqual(payload[0]["base-url"], "http://host.docker.internal:8011/v1")


if __name__ == "__main__":
    unittest.main()
