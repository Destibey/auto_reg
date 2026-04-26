import sys
import types
import unittest
from unittest import mock

from core.base_platform import RegisterConfig
from platforms.kiro.plugin import KiroPlatform


class KiroPluginExecutorTests(unittest.TestCase):
    def test_browser_executor_controls_headless_mode(self):
        cases = [
            ("protocol", True),
            ("headless", True),
            ("headed", False),
        ]

        for executor_type, expected_headless in cases:
            with self.subTest(executor_type=executor_type):
                calls = []

                class _FakeKiroRegister:
                    def __init__(self, **kwargs):
                        calls.append(kwargs)
                        self.log = None

                    def register(self, **kwargs):
                        return True, {
                            "email": kwargs["email"],
                            "password": kwargs["pwd"],
                        }

                fake_core = types.SimpleNamespace(KiroRegister=_FakeKiroRegister)
                platform = KiroPlatform(config=RegisterConfig(executor_type=executor_type))

                with mock.patch.dict(sys.modules, {"platforms.kiro.core": fake_core}):
                    platform.register(email="demo@example.com", password="pw")

                self.assertEqual(calls[0]["headless"], expected_headless)


if __name__ == "__main__":
    unittest.main()
