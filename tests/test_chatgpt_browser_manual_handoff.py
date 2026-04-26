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


class FakeAssistedPage(FakePage):
    def __init__(self, result):
        super().__init__()
        self.result = result
        self.payloads = []

    def evaluate(self, script, *args):
        self.evaluated_scripts.append(script)
        if args and isinstance(args[0], dict):
            self.payloads.append(args[0])
            return self.result
        return super().evaluate(script, *args)


class FakeBrowserSession:
    provider = "fake"

    def __init__(self, page=None):
        self.page = page or FakePage()
        self.closed = False

    def close(self):
        self.closed = True


class FakeReadableLocator:
    def inner_text(self, **_kwargs):
        return "Create account"


class FakeReadablePage(FakePage):
    url = "https://chatgpt.com/"

    def is_closed(self):
        return False

    def title(self):
        return "ChatGPT signup"

    def locator(self, _selector):
        return FakeReadableLocator()


class FakeBrowserContext:
    def __init__(self, pages):
        self.pages = pages


class FakeDisconnectedBrowser:
    def __init__(self, pages):
        self.contexts = [FakeBrowserContext(pages)]

    def is_connected(self):
        return False


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

    def test_default_signup_url_opens_chatgpt_homepage(self):
        self.assertEqual(
            DEFAULT_CHATGPT_MANUAL_SIGNUP_URL,
            "https://chatgpt.com/",
        )

    def test_token_callback_stage_is_ignored_during_registration(self):
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
                with mock.patch.object(engine, "_wait_for_token_callback") as wait_for_token_callback:
                    result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(session.page.goto_urls, [DEFAULT_CHATGPT_MANUAL_SIGNUP_URL])
        self.assertEqual(result.account_id, "")
        self.assertEqual(result.access_token, "")
        self.assertEqual(result.refresh_token, "")
        self.assertEqual(result.metadata["manual_handoff_stage"], "signup_only")
        self.assertEqual(result.metadata["registration_stage"], "signup_only")
        engine.oauth_manager.start_oauth.assert_not_called()
        wait_for_token_callback.assert_not_called()

    def test_assisted_signup_uses_assisted_wait_and_saves_signup_only_metadata(self):
        session = FakeBrowserSession()
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={
                "chatgpt_assisted_signup": True,
                "chatgpt_manual_handoff_timeout_seconds": 5,
                "chatgpt_manual_clipboard_sequence": False,
            },
        )
        engine.password = "pw-demo"

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(
                engine,
                "_wait_for_assisted_signup_completion",
                return_value=(True, "assisted signup ok"),
            ) as assisted_wait:
                with mock.patch.object(engine, "_wait_for_manual_completion") as manual_wait:
                    result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(session.page.goto_urls, [DEFAULT_CHATGPT_MANUAL_SIGNUP_URL])
        self.assertEqual(result.account_id, "")
        self.assertEqual(result.access_token, "")
        self.assertEqual(result.refresh_token, "")
        self.assertEqual(result.metadata["chatgpt_registration_mode"], "camoufox_assisted_signup")
        self.assertEqual(result.metadata["manual_handoff_stage"], "signup_only")
        self.assertEqual(result.metadata["registration_stage"], "signup_only")
        self.assertFalse(result.metadata["token_acquired"])
        assisted_wait.assert_called_once_with(session)
        manual_wait.assert_not_called()

    def test_assisted_signup_fills_known_fields_and_clicks_required_consent(self):
        page = FakeAssistedPage(
            {
                "actions": [
                    "filled_email",
                    "filled_password",
                    "filled_code",
                    "filled_name",
                    "filled_age",
                    "clicked_required_consent",
                ],
                "checkboxBlocked": False,
            }
        )
        session = FakeBrowserSession(page=page)
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeCodeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={
                "chatgpt_manual_handoff_timeout_seconds": 5,
                "chatgpt_manual_clipboard_sequence": False,
            },
        )
        engine.email = "manual@example.com"
        engine.email_info = {"service_id": "mail-1"}
        engine.password = "pw-demo"

        with mock.patch.object(
            engine,
            "_manual_signup_user_info",
            return_value={"name": "Jane Miller", "age": "28"},
        ):
            changed = engine._assist_signup_pages(session)

        self.assertTrue(changed)
        self.assertEqual(page.payloads[-1]["email"], "manual@example.com")
        self.assertEqual(page.payloads[-1]["password"], "pw-demo")
        self.assertEqual(page.payloads[-1]["code"], "123456")
        self.assertEqual(page.payloads[-1]["name"], "Jane Miller")
        self.assertEqual(page.payloads[-1]["age"], "28")
        self.assertTrue(any("同意确认框" in log for log in engine.logs))
        self.assertFalse(any("人工勾选" in log for log in engine.logs))

    def test_assisted_signup_script_defers_continue_after_fresh_fill(self):
        script = BrowserManualHandoffRegistrationEngine._assisted_signup_script()

        self.assertIn("clicked_required_consent", script)
        self.assertIn("const hasFreshFill", script)
        self.assertIn("&& !hasFreshFill", script)
        self.assertIn("socialProvider", script)
        self.assertIn("formContainsFilledControl", script)
        self.assertIn("submitForm: true", script)

    def test_assisted_signup_can_click_signup_entry_before_form_fields(self):
        page = FakeAssistedPage({"actions": ["clicked_signup_entry"]})
        session = FakeBrowserSession(page=page)
        engine = self._make_engine()
        engine.email = "manual@example.com"
        engine.password = "pw-demo"

        changed = engine._assist_signup_pages(session)

        self.assertTrue(changed)
        self.assertTrue(any("注册入口" in log for log in engine.logs))

    def test_assisted_wait_attempts_browser_automation_before_success(self):
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
            with mock.patch.object(engine, "_assist_signup_pages", return_value=True) as assist:
                ok, payload = engine._wait_for_assisted_signup_completion(session)

        self.assertTrue(ok)
        self.assertIn("signup-only", payload)
        assist.assert_called_once_with(session)

    def test_assisted_wait_fails_on_phone_before_automation(self):
        session = FakeBrowserSession()
        engine = self._make_engine()

        with mock.patch.object(
            engine,
            "_collect_page_states",
            return_value=[ManualPageState(url="https://auth.openai.com/add-phone")],
        ):
            with mock.patch.object(engine, "_assist_signup_pages") as assist:
                ok, payload = engine._wait_for_assisted_signup_completion(session)

        self.assertFalse(ok)
        self.assertIn("手机号", payload)
        assist.assert_not_called()

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
        self.assertEqual(launch_kwargs["locale"], "en-US,en")

    def test_camoufox_launch_allows_custom_locale(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={"chatgpt_locale": "en-GB,en"},
        )

        launch_kwargs = engine._build_camoufox_launch_kwargs("/tmp/autoreg-camoufox")

        self.assertEqual(launch_kwargs["locale"], "en-GB,en")

    def test_camoufox_launch_keeps_legacy_locale_fallback(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={"chatgpt_camoufox_locale": "fr-FR,fr"},
        )

        launch_kwargs = engine._build_camoufox_launch_kwargs("/tmp/autoreg-camoufox")

        self.assertEqual(launch_kwargs["locale"], "fr-FR,fr")

    def test_camoufox_launch_can_leave_locale_automatic(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={"chatgpt_locale": "auto"},
        )

        launch_kwargs = engine._build_camoufox_launch_kwargs("/tmp/autoreg-camoufox")

        self.assertNotIn("locale", launch_kwargs)

    def test_manual_signup_url_prefers_common_entry_url(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={"chatgpt_signup_entry_url": "https://chatgpt.com/auth/login"},
        )

        self.assertEqual(engine._manual_signup_url(), "https://chatgpt.com/auth/login")

    def test_manual_signup_url_keeps_legacy_fallback(self):
        engine = BrowserManualHandoffRegistrationEngine(
            email_service=FakeEmailService(),
            callback_logger=lambda _msg: None,
            extra_config={"chatgpt_manual_signup_url": "https://chatgpt.com/g/g-example"},
        )

        self.assertEqual(engine._manual_signup_url(), "https://chatgpt.com/g/g-example")

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

    def test_disconnected_browser_ignores_stale_page_state(self):
        page = FakeReadablePage()
        session = FakeBrowserSession(page=page)
        session.browser = FakeDisconnectedBrowser([page])
        engine = self._make_engine()

        states = engine._collect_page_states(session)

        self.assertEqual(states, [])

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
