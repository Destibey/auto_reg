import unittest
from unittest import mock

from platforms.chatgpt.refresh_token_registration_engine import (
    RefreshTokenRegistrationEngine,
)


class _EmailService:
    service_type = type("ST", (), {"value": "dummy_mail"})()

    def create_email(self):
        return {"email": "user@example.com", "service_id": "svc-1"}


class ChatGPTDiagnosticsTests(unittest.TestCase):
    def test_runtime_diagnostics_describe_protocol_chain_without_secrets(self):
        logs = []
        engine = RefreshTokenRegistrationEngine(
            email_service=_EmailService(),
            proxy_url="http://user:pass@127.0.0.1:7890",
            browser_mode="headed",
            callback_logger=logs.append,
        )

        engine._log_runtime_diagnostics()

        joined = "\n".join(logs)
        self.assertIn("executor_type=headed", joined)
        self.assertIn("协议请求 + Sentinel Browser", joined)
        self.assertIn("代理=已配置", joined)
        self.assertNotIn("user:pass", joined)

    def test_response_diagnostics_logs_selected_headers_only(self):
        logs = []
        engine = RefreshTokenRegistrationEngine(
            email_service=_EmailService(),
            callback_logger=logs.append,
        )
        response = mock.Mock(
            status_code=400,
            headers={
                "cf-ray": "ray-123",
                "x-request-id": "req-456",
                "set-cookie": "secret-cookie",
                "content-type": "application/json",
            },
        )

        engine._log_response_diagnostics("注册密码", response)

        joined = "\n".join(logs)
        self.assertIn("注册密码响应诊断: status=400", joined)
        self.assertIn("cf-ray=ray-123", joined)
        self.assertIn("x-request-id=req-456", joined)
        self.assertIn("content-type=application/json", joined)
        self.assertNotIn("secret-cookie", joined)


if __name__ == "__main__":
    unittest.main()
