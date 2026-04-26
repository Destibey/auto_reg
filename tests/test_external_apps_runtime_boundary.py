import unittest
from unittest import mock

from services.external_apps import install, list_status, start


class ExternalAppsRuntimeBoundaryTests(unittest.TestCase):
    def test_cpa_is_external_and_grok2api_is_docker_managed(self):
        items = {item["name"]: item for item in list_status()}

        self.assertEqual(items["cliproxyapi"]["runtime_boundary"], "external")
        self.assertIn("独立稳定服务", items["cliproxyapi"]["runtime_hint"])
        self.assertEqual(items["grok2api"]["runtime_boundary"], "docker")
        self.assertIn("docker-compose.integrations.yml", items["grok2api"]["runtime_hint"])

    def test_cpa_is_not_installed_or_started_by_autoreg(self):
        for action in (install, start):
            with self.subTest(action=action.__name__):
                with self.assertRaisesRegex(RuntimeError, "独立稳定服务"):
                    action("cliproxyapi")

    def test_grok2api_is_managed_by_autoreg_compose(self):
        with mock.patch("services.external_apps._run_compose") as compose_mock:
            with mock.patch("services.external_apps._status_one", return_value={"name": "grok2api"}):
                self.assertEqual(install("grok2api"), {"name": "grok2api"})
                self.assertEqual(start("grok2api"), {"name": "grok2api"})

        compose_mock.assert_has_calls([
            mock.call(["pull", "grok2api"]),
            mock.call(["up", "-d", "grok2api"]),
        ])


if __name__ == "__main__":
    unittest.main()
