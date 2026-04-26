import unittest
from unittest import mock

from core.task_runtime import SkipCurrentAttemptRequested, StopTaskRequested
from platforms.chatgpt.oauth import OAuthStart
from platforms.chatgpt.browser_manual_handoff_registration_engine import (
    BrowserManualHandoffRegistrationEngine,
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
        engine.oauth_manager = mock.Mock()
        engine.oauth_manager.start_oauth.return_value = OAuthStart(
            auth_url="https://auth.openai.com/oauth/authorize?state=state-demo",
            state="state-demo",
            code_verifier="verifier-demo",
            redirect_uri="http://localhost:1455/auth/callback",
        )
        return engine

    def test_exchanges_callback_url_for_tokens(self):
        session = FakeBrowserSession()
        engine = self._make_engine()
        callback_url = "http://localhost:1455/auth/callback?code=code-demo&state=state-demo"
        engine.oauth_manager.handle_callback.return_value = {
            "email": "manual@example.com",
            "account_id": "acct-demo",
            "access_token": "at-demo",
            "refresh_token": "rt-demo",
            "id_token": "id-demo",
        }

        with mock.patch.object(engine, "_open_browser_session", return_value=session):
            with mock.patch.object(
                engine,
                "_collect_page_states",
                return_value=[ManualPageState(url=callback_url)],
            ):
                result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(result.email, "manual@example.com")
        self.assertEqual(result.password, "pw-demo")
        self.assertEqual(result.account_id, "acct-demo")
        self.assertEqual(result.access_token, "at-demo")
        self.assertEqual(result.refresh_token, "rt-demo")
        self.assertEqual(session.page.goto_url, engine.oauth_manager.start_oauth.return_value.auth_url)
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
        engine.oauth_manager.handle_callback.assert_not_called()

    def test_default_manual_browser_provider_is_camoufox(self):
        engine = self._make_engine()

        with mock.patch.object(engine, "_open_camoufox_session", return_value=FakeBrowserSession()) as mocked:
            session = engine._open_browser_session()

        self.assertEqual(session.provider, "fake")
        mocked.assert_called_once()

    def test_add_phone_detection_reads_page_text(self):
        engine = self._make_engine()

        self.assertTrue(
            engine._requires_phone(
                [ManualPageState(url="https://auth.openai.com/u/signup", body_text="Verify your phone number")]
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
            engine._wait_for_manual_completion(
                FakeBrowserSession(),
                engine.oauth_manager.start_oauth.return_value,
            )

        self.assertEqual(control.attempt_ids, [7])

    def test_skip_request_interrupts_manual_wait_loop(self):
        control = FakeTaskControl(SkipCurrentAttemptRequested())
        engine = self._make_engine()
        engine.task_control = control
        engine.task_attempt_token = 8

        with self.assertRaises(SkipCurrentAttemptRequested):
            engine._wait_for_manual_completion(
                FakeBrowserSession(),
                engine.oauth_manager.start_oauth.return_value,
            )

        self.assertEqual(control.attempt_ids, [8])


if __name__ == "__main__":
    unittest.main()
