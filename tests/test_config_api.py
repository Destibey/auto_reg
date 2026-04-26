from api import config as config_api
from api.config import ConfigUpdate


class FakeConfigStore:
    def __init__(self):
        self.values = {}
        self.saved = {}

    def get_all(self):
        return dict(self.values)

    def set_many(self, data):
        self.saved = dict(data)


def test_config_exposes_camoufox_manual_handoff_defaults(monkeypatch):
    store = FakeConfigStore()
    monkeypatch.setattr(config_api, "config_store", store)

    data = config_api.get_config()

    assert data["chatgpt_manual_browser_provider"] == "camoufox"
    assert data["chatgpt_manual_handoff_timeout_seconds"] == "900"
    assert data["chatgpt_manual_email_poll_interval_seconds"] == "10"
    assert "chatgpt_manual_enable_token_callback" in data
    assert "chatgpt_manual_browser_profile_dir" in data
    assert "chatgpt_manual_browser_keep_open" in data
    assert "chatgpt_camoufox_geoip" in data
    assert "chatgpt_camoufox_humanize" in data
    assert data["chatgpt_locale"] == "en-US,en"
    assert data["chatgpt_signup_entry_url"] == "https://chatgpt.com/"
    assert data["chatgpt_camoufox_locale"] == "en-US,en"
    assert "chatgpt_camoufox_os" in data


def test_config_update_allows_camoufox_manual_handoff_keys(monkeypatch):
    store = FakeConfigStore()
    monkeypatch.setattr(config_api, "config_store", store)

    result = config_api.update_config(
        ConfigUpdate(
            data={
                "chatgpt_manual_browser_provider": "camoufox",
                "chatgpt_manual_handoff_timeout_seconds": "600",
                "chatgpt_manual_email_poll_interval_seconds": "5",
                "chatgpt_manual_enable_token_callback": True,
                "chatgpt_manual_browser_profile_dir": "/tmp/autoreg-camoufox",
                "chatgpt_manual_browser_keep_open": True,
                "chatgpt_camoufox_geoip": True,
                "chatgpt_camoufox_humanize": "1.5",
                "chatgpt_locale": "en-GB,en",
                "chatgpt_signup_entry_url": "https://chatgpt.com/auth/login",
                "chatgpt_camoufox_locale": "en-GB,en",
                "chatgpt_camoufox_os": "macos",
                "unknown_key": "ignored",
            }
        )
    )

    assert result["ok"] is True
    assert store.saved == {
        "chatgpt_manual_browser_provider": "camoufox",
        "chatgpt_manual_handoff_timeout_seconds": "600",
        "chatgpt_manual_email_poll_interval_seconds": "5",
        "chatgpt_manual_enable_token_callback": True,
        "chatgpt_manual_browser_profile_dir": "/tmp/autoreg-camoufox",
        "chatgpt_manual_browser_keep_open": True,
        "chatgpt_camoufox_geoip": True,
        "chatgpt_camoufox_humanize": "1.5",
        "chatgpt_locale": "en-GB,en",
        "chatgpt_signup_entry_url": "https://chatgpt.com/auth/login",
        "chatgpt_camoufox_locale": "en-GB,en",
        "chatgpt_camoufox_os": "macos",
    }


def test_config_backfills_common_chatgpt_keys_from_legacy_values(monkeypatch):
    store = FakeConfigStore()
    store.values = {
        "chatgpt_camoufox_locale": "en-GB,en",
        "chatgpt_manual_signup_url": "https://chatgpt.com/auth/login",
    }
    monkeypatch.setattr(config_api, "config_store", store)

    data = config_api.get_config()

    assert data["chatgpt_locale"] == "en-GB,en"
    assert data["chatgpt_camoufox_locale"] == "en-GB,en"
    assert data["chatgpt_signup_entry_url"] == "https://chatgpt.com/auth/login"
