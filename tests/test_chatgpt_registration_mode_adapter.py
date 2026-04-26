import unittest
from unittest import mock

from platforms.chatgpt.chatgpt_registration_mode_adapter import (
    CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
    CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF,
    CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP,
    CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
    ChatGPTRegistrationContext,
    build_chatgpt_registration_mode_adapter,
    resolve_chatgpt_registration_mode,
)


class ChatGPTRegistrationModeAdapterTests(unittest.TestCase):
    def test_resolve_defaults_to_refresh_token_mode(self):
        self.assertEqual(
            resolve_chatgpt_registration_mode({}),
            CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
        )

    def test_resolve_supports_boolean_no_rt_flag(self):
        self.assertEqual(
            resolve_chatgpt_registration_mode(
                {"chatgpt_has_refresh_token_solution": False}
            ),
            CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
        )

    def test_resolve_supports_browser_manual_handoff_mode(self):
        self.assertEqual(
            resolve_chatgpt_registration_mode(
                {"chatgpt_registration_mode": "browser_manual_handoff"}
            ),
            CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF,
        )

    def test_resolve_supports_camoufox_assisted_signup_mode(self):
        self.assertEqual(
            resolve_chatgpt_registration_mode(
                {"chatgpt_registration_mode": "camoufox_assisted_signup"}
            ),
            CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP,
        )

    def test_build_account_marks_selected_mode(self):
        adapter = build_chatgpt_registration_mode_adapter(
            {"chatgpt_registration_mode": "access_token_only"}
        )
        result = type(
            "Result",
            (),
            {
                "email": "demo@example.com",
                "password": "pw",
                "account_id": "acct-demo",
                "access_token": "at-demo",
                "refresh_token": "",
                "id_token": "id-demo",
                "session_token": "session-demo",
                "workspace_id": "ws-demo",
                "source": "register",
            },
        )()

        account = adapter.build_account(result, fallback_password="fallback")

        self.assertEqual(account.email, "demo@example.com")
        self.assertEqual(account.password, "pw")
        self.assertEqual(
            account.extra["chatgpt_registration_mode"],
            CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
        )
        self.assertFalse(account.extra["chatgpt_has_refresh_token_solution"])

    def test_build_account_marks_refresh_token_mode_signup_only_without_rt_solution(self):
        adapter = build_chatgpt_registration_mode_adapter(
            {"chatgpt_registration_mode": "refresh_token"}
        )
        result = type(
            "Result",
            (),
            {
                "email": "demo@example.com",
                "password": "pw",
                "account_id": "",
                "access_token": "",
                "refresh_token": "",
                "id_token": "",
                "session_token": "",
                "workspace_id": "",
                "source": "register",
                "metadata": {"registration_stage": "signup_only"},
            },
        )()

        account = adapter.build_account(result, fallback_password="fallback")

        self.assertEqual(
            account.extra["chatgpt_registration_mode"],
            CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
        )
        self.assertEqual(account.extra["registration_stage"], "signup_only")
        self.assertFalse(account.extra["chatgpt_has_refresh_token_solution"])

    def test_build_account_preserves_engine_metadata(self):
        adapter = build_chatgpt_registration_mode_adapter(
            {"chatgpt_registration_mode": "browser_manual_handoff"}
        )
        result = type(
            "Result",
            (),
            {
                "email": "manual@example.com",
                "password": "pw",
                "account_id": "",
                "access_token": "",
                "refresh_token": "",
                "id_token": "",
                "session_token": "",
                "workspace_id": "",
                "source": "browser_manual_handoff",
                "metadata": {
                    "manual_handoff_stage": "signup_only",
                    "chatgpt_manual_enable_token_callback": False,
                },
            },
        )()

        account = adapter.build_account(result, fallback_password="fallback")

        self.assertEqual(account.extra["manual_handoff_stage"], "signup_only")
        self.assertFalse(account.extra["chatgpt_manual_enable_token_callback"])
        self.assertFalse(account.extra["chatgpt_has_refresh_token_solution"])

    def test_access_token_only_adapter_passes_runtime_context_to_engine(self):
        created = {}

        class FakeEngine:
            def __init__(self, **kwargs):
                created["kwargs"] = kwargs
                self.email = None
                self.password = None

            def run(self):
                created["email"] = self.email
                created["password"] = self.password
                return type("Result", (), {"success": True})()

        adapter = build_chatgpt_registration_mode_adapter(
            {"chatgpt_registration_mode": "access_token_only"}
        )
        context = ChatGPTRegistrationContext(
            email_service=object(),
            proxy_url="http://127.0.0.1:7890",
            callback_logger=lambda _msg: None,
            email="demo@example.com",
            password="pw-demo",
            browser_mode="headed",
            max_retries=5,
            extra_config={"register_max_retries": 5},
        )

        with mock.patch(
            "platforms.chatgpt.access_token_only_registration_engine.AccessTokenOnlyRegistrationEngine",
            FakeEngine,
        ):
            adapter.run(context)

        self.assertEqual(created["email"], "demo@example.com")
        self.assertEqual(created["password"], "pw-demo")
        self.assertEqual(created["kwargs"]["browser_mode"], "headed")
        self.assertEqual(created["kwargs"]["max_retries"], 5)

    def test_browser_manual_handoff_adapter_passes_runtime_context_to_engine(self):
        created = {}

        class FakeEngine:
            def __init__(self, **kwargs):
                created["kwargs"] = kwargs
                self.email = None
                self.password = None

            def run(self):
                created["email"] = self.email
                created["password"] = self.password
                return type("Result", (), {"success": True})()

        adapter = build_chatgpt_registration_mode_adapter(
            {"chatgpt_registration_mode": "browser_manual_handoff"}
        )
        context = ChatGPTRegistrationContext(
            email_service=object(),
            proxy_url="http://127.0.0.1:7890",
            callback_logger=lambda _msg: None,
            email="demo@example.com",
            password="pw-demo",
            browser_mode="headed",
            max_retries=5,
            extra_config={"chatgpt_manual_handoff_timeout_seconds": 300},
            task_control="task-control-demo",
            task_attempt_token=12,
        )

        with mock.patch(
            "platforms.chatgpt.browser_manual_handoff_registration_engine.BrowserManualHandoffRegistrationEngine",
            FakeEngine,
        ):
            adapter.run(context)

        self.assertEqual(created["email"], "demo@example.com")
        self.assertEqual(created["password"], "pw-demo")
        self.assertEqual(created["kwargs"]["proxy_url"], "http://127.0.0.1:7890")
        self.assertEqual(created["kwargs"]["extra_config"]["chatgpt_manual_handoff_timeout_seconds"], 300)
        self.assertEqual(created["kwargs"]["task_control"], "task-control-demo")
        self.assertEqual(created["kwargs"]["task_attempt_token"], 12)

    def test_camoufox_assisted_signup_adapter_enables_assisted_engine_mode(self):
        created = {}

        class FakeEngine:
            def __init__(self, **kwargs):
                created["kwargs"] = kwargs
                self.email = None
                self.password = None

            def run(self):
                created["email"] = self.email
                created["password"] = self.password
                return type("Result", (), {"success": True})()

        adapter = build_chatgpt_registration_mode_adapter(
            {"chatgpt_registration_mode": "camoufox_assisted_signup"}
        )
        context = ChatGPTRegistrationContext(
            email_service=object(),
            proxy_url="http://127.0.0.1:7890",
            callback_logger=lambda _msg: None,
            email="demo@example.com",
            password="pw-demo",
            browser_mode="headed",
            max_retries=5,
            extra_config={"chatgpt_manual_handoff_timeout_seconds": 300},
            task_control="task-control-demo",
            task_attempt_token=12,
        )

        with mock.patch(
            "platforms.chatgpt.browser_manual_handoff_registration_engine.BrowserManualHandoffRegistrationEngine",
            FakeEngine,
        ):
            adapter.run(context)

        self.assertEqual(created["email"], "demo@example.com")
        self.assertEqual(created["password"], "pw-demo")
        self.assertEqual(created["kwargs"]["proxy_url"], "http://127.0.0.1:7890")
        self.assertEqual(created["kwargs"]["extra_config"]["chatgpt_manual_handoff_timeout_seconds"], 300)
        self.assertTrue(created["kwargs"]["extra_config"]["chatgpt_assisted_signup"])
        self.assertEqual(created["kwargs"]["task_control"], "task-control-demo")
        self.assertEqual(created["kwargs"]["task_attempt_token"], 12)


if __name__ == "__main__":
    unittest.main()
