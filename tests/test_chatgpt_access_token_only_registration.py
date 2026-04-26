import unittest
from unittest import mock

from platforms.chatgpt.access_token_only_registration_engine import (
    AccessTokenOnlyRegistrationEngine,
)


class FakeEmailService:
    service_type = type("ST", (), {"value": "fake_mail"})()

    def create_email(self):
        return {"email": "signup@example.com", "service_id": "mail-1"}

    def get_verification_code(self, **_kwargs):
        return "123456"


class AccessTokenOnlyRegistrationEngineTests(unittest.TestCase):
    def test_successful_registration_stops_before_session_token_extraction(self):
        client = mock.Mock()
        client.device_id = "device-fixed"
        client.register_complete_flow.return_value = (True, "ok")
        client.reuse_session_and_get_tokens.side_effect = AssertionError(
            "registration must not extract tokens"
        )

        engine = AccessTokenOnlyRegistrationEngine(
            email_service=FakeEmailService(),
            proxy_url="http://127.0.0.1:7890",
            callback_logger=lambda _msg: None,
            max_retries=1,
        )

        with mock.patch(
            "platforms.chatgpt.access_token_only_registration_engine.ChatGPTClient",
            return_value=client,
        ):
            result = engine.run()

        self.assertTrue(result.success)
        self.assertEqual(result.email, "signup@example.com")
        self.assertEqual(result.access_token, "")
        self.assertEqual(result.refresh_token, "")
        self.assertEqual(result.session_token, "")
        self.assertEqual(result.metadata["registration_stage"], "signup_only")
        self.assertFalse(result.metadata["token_acquired"])
        client.register_complete_flow.assert_called_once()
        client.reuse_session_and_get_tokens.assert_not_called()


if __name__ == "__main__":
    unittest.main()
