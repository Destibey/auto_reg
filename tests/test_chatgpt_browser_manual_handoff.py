import unittest
from unittest import mock

from core.task_runtime import SkipCurrentAttemptRequested, StopTaskRequested
from platforms.chatgpt.browser_manual_handoff_registration_engine import (
    BrowserManualHandoffRegistrationEngine,
    DEFAULT_CHATGPT_MANUAL_SIGNUP_URL,
    ManualPageState,
)


class FakeEmailService:
    def create_email(self, config=None):
        return {"email": "manual@example.com", "service_id": "mail-1"}

    def get_verification_code(self, **_kwargs):
        return ""


class FakePage:
    def __init__(self):
        self.goto_url = ""

    def goto(self, url, **_kwargs):
        self.goto_url = url


class FakeBrowserSession:
    provider = "fake"

    def __init__(self):
        self.page = FakePage()
        self.closed = False

    def close(self):
        self.closed = True


class FakeTaskControl:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0
        self.attempt_ids = []

    def checkpoint(self, *, attempt_id=None, consume_skip=True):
        self.calls += 1
        self.attempt_ids.append(attempt_id)
        raise self.exc


class BrowserManualHandoffEngineTests(unittest.TestCase):
    def _make_engine(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={"chatgpt_manual_handoff_timeout_seconds": 5},
        )
        engine.password = "pw-demo"
        return engine

    def test_signup_only_saves_email_and_password_without_token_exchange(self):
        session = FakeBrowserSession()
        engine = self._make_engine()

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(
                engine,
                "_collect_page_states",
                return_value=[ManualPageState(url="https://chatgpt.com/", body_text="New chat Message ChatGPT")],
            ):
                result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(result.email, "manual@example.com")
        self.assertEqual(result.password, "pw-demo")
        self.assertEqual(result.account_id, "")
        self.assertEqual(result.access_token, "")
        self.assertEqual(result.refresh_token, "")
        self.assertEqual(result.metadata["manual_handoff_stage"], "signup_only")
        self.assertEqual(session.page.goto_url, DEFAULT_CHATGPT_MANUAL_SIGNUP_URL)
        session.close()
        self.assertTrue(session.closed)

    def test_add_phone_fails_without_token_exchange(self):
        session = FakeBrowserSession()
        engine = self._make_engine()

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(
                engine,
                "_collect_page_states",
                return_value=[ManualPageState(url="https://auth.openai.com/add-phone")],
            ):
                result = engine.run()

        self.assertFalse(result.success)
        self.assertIn("手机号", result.error_message)

    def test_default_manual_browser_provider_is_camoufox(self):
        engine = self._make_engine()

        with mock.patch.object(engine, "_open_camoufox_session", return_value=FakeBrowserSession()) as mocked:
            session = engine._open_browser_session()

        self.assertEqual(session.provider, "fake")
        mocked.assert_called_once()

    def test_camoufox_launch_uses_generated_window_by_default(self):
        engine = self._make_engine()

        launch_kwargs = engine._build_camoufox_launch_kwargs("/tmp/autoreg-camoufox")

        self.assertEqual(launch_kwargs["user_data_dir"], "/tmp/autoreg-camoufox")
        self.assertNotIn("window", launch_kwargs)
        self.assertNotIn("geoip", launch_kwargs)
        self.assertNotIn("humanize", launch_kwargs)
        self.assertNotIn("os", launch_kwargs)

    def test_camoufox_launch_accepts_normal_runtime_options(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            proxy_url="http://127.0.0.1:7890",
            extra_config={
                "chatgpt_camoufox_os": "macos",
                "chatgpt_camoufox_humanize": "1.5",
                "chatgpt_camoufox_geoip": True,
            },
        )

        with mock.patch.object(engine, "_camoufox_geoip_available", return_value=True):
            launch_kwargs = engine._build_camoufox_launch_kwargs("/tmp/autoreg-camoufox")

        self.assertEqual(launch_kwargs["proxy"], {"server": "http://127.0.0.1:7890"})
        self.assertEqual(launch_kwargs["os"], "macos")
        self.assertEqual(launch_kwargs["humanize"], 1.5)
        self.assertTrue(launch_kwargs["geoip"])

    def test_camoufox_geoip_without_extra_logs_and_falls_back(self):
        messages = []
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=messages.append,
            extra_config={"chatgpt_camoufox_geoip": True},
        )

        with mock.patch.object(engine, "_camoufox_geoip_available", return_value=False):
            launch_kwargs = engine._build_camoufox_launch_kwargs("/tmp/autoreg-camoufox")

        self.assertNotIn("geoip", launch_kwargs)
        self.assertTrue(any("camoufox[geoip]" in msg.lower() for msg in messages))

    def test_add_phone_detection_reads_page_text(self):
        engine = self._make_engine()

        self.assertTrue(
            engine._requires_phone(
                [ManualPageState(url="https://auth.openai.com/u/signup", body_text="Verify your phone number")]
            )
        )

    def test_detects_normal_chatgpt_app_then_completes_signup_only(self):
        session = FakeBrowserSession()
        engine = self._make_engine()

        with mock.patch.object(
            engine,
            "_collect_page_states",
            return_value=[ManualPageState(url="https://chatgpt.com/", body_text="New chat Message ChatGPT")],
        ):
            ok, payload = engine._wait_for_manual_completion(session)

        self.assertTrue(ok)
        self.assertIn("signup-only", payload)
        self.assertEqual(session.page.goto_url, "")

    def test_logged_out_chatgpt_home_does_not_open_oauth(self):
        engine = self._make_engine()

        self.assertFalse(
            engine._looks_like_chatgpt_app(
                [ManualPageState(url="https://chatgpt.com/", body_text="Log in Sign up")]
            )
        )

    def test_closed_browser_fails_manual_wait(self):
        session = FakeBrowserSession()
        engine = self._make_engine()

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(engine, "_collect_page_states", return_value=[]):
                result = engine.run()

        self.assertFalse(result.success)
        self.assertIn("浏览器已关闭", result.error_message)

    def test_stop_request_interrupts_manual_wait_loop(self):
        control = FakeTaskControl(StopTaskRequested())
        engine = self._make_engine()
        engine.task_control = control
        engine.task_attempt_token = 7

        with self.assertRaises(StopTaskRequested):
            engine._wait_for_manual_completion(FakeBrowserSession())

        self.assertEqual(control.attempt_ids, [7])

    def test_skip_request_interrupts_manual_wait_loop(self):
        control = FakeTaskControl(SkipCurrentAttemptRequested())
        engine = self._make_engine()
        engine.task_control = control
        engine.task_attempt_token = 8

        with self.assertRaises(SkipCurrentAttemptRequested):
            engine._wait_for_manual_completion(FakeBrowserSession())

        self.assertEqual(control.attempt_ids, [8])


if __name__ == "__main__":
    unittest.main()
