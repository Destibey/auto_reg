import unittest
from unittest import mock

from core.task_runtime import SkipCurrentAttemptRequested, StopTaskRequested
from platforms.chatgpt.browser_manual_handoff_registration_engine import (
    BrowserManualHandoffRegistrationEngine,
    DEFAULT_CHATGPT_MANUAL_SIGNUP_URL,
    ManualPageState,
)
from platforms.chatgpt.oauth import OAuthStart


class FakeEmailService:
    def create_email(self, config=None):
        return {"email": "manual@example.com", "service_id": "mail-1"}

    def get_verification_code(self, **_kwargs):
        return ""


class FakeCodeEmailService(FakeEmailService):
    def get_verification_code(self, **_kwargs):
        return "123456"


class FakePage:
    def __init__(self):
        self.goto_url = ""
        self.goto_urls = []
        self.exposed = {}
        self.init_scripts = []
        self.evaluated_scripts = []
        self.input_values = []

    def goto(self, url, **_kwargs):
        self.goto_url = url
        self.goto_urls.append(url)

    def expose_function(self, name, callback):
        self.exposed[name] = callback

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def evaluate(self, script, *args):
        self.evaluated_scripts.append(script)
        if args:
            target = str(args[0])
            if any(target in value for value in self.input_values):
                return True
            parts = [part for part in target.split() if part]
            joined = " ".join(self.input_values)
            return len(parts) > 1 and all(part in joined for part in parts)
        return None


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
            extra_config={
                "chatgpt_manual_handoff_timeout_seconds": 5,
                "chatgpt_manual_clipboard_sequence": False,
            },
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
                side_effect=[
                    [ManualPageState(url="https://chatgpt.com/", body_text="Log in Sign up")],
                    [ManualPageState(url="https://chatgpt.com/", body_text="New chat Message ChatGPT")],
                ],
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

    def test_default_signup_url_opens_direct_create_account_page(self):
        self.assertEqual(
            DEFAULT_CHATGPT_MANUAL_SIGNUP_URL,
            "https://auth.openai.com/create-account",
        )

    def test_token_callback_stage_runs_only_when_enabled(self):
        session = FakeBrowserSession()
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={
                "chatgpt_manual_handoff_timeout_seconds": 5,
                "chatgpt_manual_enable_token_callback": True,
                "chatgpt_manual_clipboard_sequence": False,
            },
        )
        engine.password = "pw-demo"
        engine.oauth_manager = mock.Mock(
            start_oauth=mock.Mock(
                return_value=OAuthStart(
                    auth_url="https://auth.example/authorize",
                    state="state-demo",
                    code_verifier="verifier-demo",
                    redirect_uri="http://localhost/callback",
                )
            )
        )

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(engine, "_wait_for_manual_completion", return_value=(True, "signup ok")):
                with mock.patch.object(
                    engine,
                    "_wait_for_token_callback",
                    return_value=(
                        True,
                        {
                            "email": "manual@example.com",
                            "account_id": "acct-demo",
                            "access_token": "at-demo",
                            "refresh_token": "rt-demo",
                            "id_token": "id-demo",
                        },
                    ),
                ):
                    result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(session.page.goto_urls, [DEFAULT_CHATGPT_MANUAL_SIGNUP_URL, "https://auth.example/authorize"])
        self.assertEqual(result.account_id, "acct-demo")
        self.assertEqual(result.access_token, "at-demo")
        self.assertEqual(result.refresh_token, "rt-demo")
        self.assertEqual(result.metadata["manual_handoff_stage"], "token_callback")

    def test_existing_account_token_acquisition_opens_oauth_directly(self):
        session = FakeBrowserSession()
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={
                "chatgpt_manual_handoff_timeout_seconds": 5,
                "chatgpt_manual_clipboard_sequence": False,
            },
        )
        engine.oauth_manager = mock.Mock(
            start_oauth=mock.Mock(
                return_value=OAuthStart(
                    auth_url="https://auth.example/authorize",
                    state="state-demo",
                    code_verifier="verifier-demo",
                    redirect_uri="http://localhost/callback",
                )
            )
        )

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(
                engine,
                "_wait_for_token_callback",
                return_value=(
                    True,
                    {
                        "email": "manual@example.com",
                        "account_id": "acct-demo",
                        "access_token": "at-demo",
                        "refresh_token": "rt-demo",
                        "id_token": "id-demo",
                    },
                ),
            ):
                result = engine.acquire_token_for_existing_account("manual@example.com", "pw-demo")

        self.assertTrue(result.success)
        self.assertEqual(session.page.goto_urls, ["https://auth.example/authorize"])
        self.assertEqual(result.access_token, "at-demo")
        self.assertEqual(result.refresh_token, "rt-demo")
        self.assertEqual(result.metadata["manual_handoff_stage"], "token_callback")

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

    def test_default_manual_profile_dir_is_unique_and_marked_for_cleanup(self):
        engine = self._make_engine()

        first_dir, first_cleanup = engine._manual_profile_dir("chatgpt_camoufox")
        second_dir, second_cleanup = engine._manual_profile_dir("chatgpt_camoufox")

        self.assertNotEqual(first_dir, second_dir)
        self.assertTrue(first_cleanup)
        self.assertTrue(second_cleanup)
        self.assertIn("run-", first_dir)

    def test_configured_manual_profile_dir_is_reused_without_cleanup(self):
        engine = self._make_engine()
        engine.extra_config["chatgpt_manual_browser_profile_dir"] = "/tmp/fixed-autoreg-profile"

        profile_dir, cleanup = engine._manual_profile_dir("chatgpt_camoufox")

        self.assertEqual(profile_dir, "/tmp/fixed-autoreg-profile")
        self.assertFalse(cleanup)

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
            side_effect=[
                [ManualPageState(url="https://chatgpt.com/", body_text="Log in Sign up")],
                [ManualPageState(url="https://chatgpt.com/", body_text="New chat Message ChatGPT")],
            ],
        ):
            ok, payload = engine._wait_for_manual_completion(session)

        self.assertTrue(ok)
        self.assertIn("signup-only", payload)
        self.assertEqual(session.page.goto_url, "")

    def test_existing_logged_in_chatgpt_app_does_not_complete_immediately(self):
        session = FakeBrowserSession()
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={
                "chatgpt_manual_handoff_timeout_seconds": 1,
                "chatgpt_manual_clipboard_sequence": False,
            },
        )

        with mock.patch.object(
            engine,
            "_collect_page_states",
            return_value=[ManualPageState(url="https://chatgpt.com/", body_text="New chat Message ChatGPT")],
        ):
            ok, payload = engine._wait_for_manual_completion(session)

        self.assertFalse(ok)
        self.assertIn("超时", payload)

    def test_manual_clipboard_advances_from_email_to_password_after_paste(self):
        engine = self._make_engine()
        engine.extra_config["chatgpt_manual_clipboard_sequence"] = True
        copied = []

        with mock.patch.object(engine, "_set_system_clipboard", side_effect=lambda value: copied.append(value) or True):
            engine._prepare_manual_clipboard("manual@example.com", "pw-demo")
            engine._handle_page_paste("manual@example.com")

        self.assertEqual(copied, ["manual@example.com", "pw-demo"])

    def test_manual_clipboard_appends_code_name_and_age(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeCodeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={
                "chatgpt_manual_handoff_timeout_seconds": 5,
                "chatgpt_manual_clipboard_sequence": True,
            },
        )
        engine.email = "manual@example.com"
        engine.email_info = {"service_id": "mail-1"}
        copied = []

        with mock.patch.object(engine, "_set_system_clipboard", side_effect=lambda value: copied.append(value) or True):
            with mock.patch.object(
                engine,
                "_manual_signup_user_info",
                return_value={"name": "Jane Miller", "age": "28"},
            ):
                engine._prepare_manual_clipboard("manual@example.com", "pw-demo")
                engine._handle_page_paste("manual@example.com")
                engine._handle_page_paste("pw-demo")
                engine._poll_email_code_for_user()
                engine._handle_page_paste("123456")
                engine._handle_page_paste("Jane Miller")

        self.assertEqual(
            copied,
            [
                "manual@example.com",
                "pw-demo",
                "123456",
                "Jane Miller",
                "28",
            ],
        )
        self.assertFalse(any("生日" in log or "birth" in log.lower() for log in engine.logs))

    def test_manual_clipboard_advances_when_name_is_split_across_inputs(self):
        session = FakeBrowserSession()
        engine = self._make_engine()
        engine.extra_config["chatgpt_manual_clipboard_sequence"] = True
        copied = []

        with mock.patch.object(engine, "_set_system_clipboard", side_effect=lambda value: copied.append(value) or True):
            engine._prepare_manual_clipboard("manual@example.com", "pw-demo")
            engine._handle_page_paste("manual@example.com")
            engine._handle_page_paste("pw-demo")
            engine._append_manual_clipboard_items(
                [("验证码", "123456"), ("姓名", "Jane Miller"), ("年龄", "28")]
            )
            engine._handle_page_paste("123456")
            session.page.input_values = ["Jane", "Miller"]
            engine._advance_clipboard_from_visible_inputs(session)

        self.assertEqual(
            copied,
            ["manual@example.com", "pw-demo", "123456", "Jane Miller", "28"],
        )

    def test_manual_clipboard_advances_from_input_event_value(self):
        session = FakeBrowserSession()
        engine = self._make_engine()
        engine.extra_config["chatgpt_manual_clipboard_sequence"] = True
        copied = []

        with mock.patch.object(engine, "_set_system_clipboard", side_effect=lambda value: copied.append(value) or True):
            engine._prepare_manual_clipboard("manual@example.com", "pw-demo")
            engine._handle_page_paste("manual@example.com")
            engine._handle_page_paste("pw-demo")
            engine._append_manual_clipboard_items(
                [("验证码", "123456"), ("姓名", "Jane Miller"), ("年龄", "28")]
            )
            engine._handle_page_paste("123456")
            engine._install_clipboard_paste_watcher(session)
            session.page.exposed["__autoregClipboardPasted"]("Jane Miller")

        self.assertEqual(
            copied,
            ["manual@example.com", "pw-demo", "123456", "Jane Miller", "28"],
        )

    def test_manual_clipboard_advances_when_email_appears_in_input(self):
        session = FakeBrowserSession()
        session.page.input_values = ["manual@example.com"]
        engine = self._make_engine()
        engine.extra_config["chatgpt_manual_clipboard_sequence"] = True
        copied = []

        with mock.patch.object(engine, "_set_system_clipboard", side_effect=lambda value: copied.append(value) or True):
            engine._prepare_manual_clipboard("manual@example.com", "pw-demo")
            engine._advance_clipboard_from_visible_inputs(session)

        self.assertEqual(copied, ["manual@example.com", "pw-demo"])

    def test_installs_clipboard_paste_watcher_on_manual_page(self):
        session = FakeBrowserSession()
        engine = self._make_engine()
        engine.extra_config["chatgpt_manual_clipboard_sequence"] = True

        engine._install_clipboard_paste_watcher(session)

        self.assertIn("__autoregClipboardPasted", session.page.exposed)
        self.assertTrue(session.page.init_scripts)
        self.assertTrue(session.page.evaluated_scripts)

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
