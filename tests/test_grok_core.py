import unittest

from core.base_captcha import ManualCaptcha
from platforms.grok.core import GrokRegister


class FakeTurnstilePage:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.waits = 0

    def wait_for_timeout(self, _ms):
        self.waits += 1

    def evaluate(self, _script):
        if not self.tokens:
            return ""
        return self.tokens.pop(0)


class GrokRegisterTurnstileTests(unittest.TestCase):
    def test_manual_captcha_waits_for_user_completed_turnstile_token(self):
        logs = []
        page = FakeTurnstilePage(["", "", "manual-token-value-that-is-long-enough"])
        reg = GrokRegister(
            captcha_solver=ManualCaptcha(),
            log_fn=logs.append,
            manual_turnstile_timeout_seconds=5,
        )

        token = reg._solve_turnstile_on_page(page)

        self.assertEqual(token, "manual-token-value-that-is-long-enough")
        self.assertGreaterEqual(page.waits, 2)
        self.assertTrue(any("手动完成 Cloudflare" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
