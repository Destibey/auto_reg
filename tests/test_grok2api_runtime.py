import unittest
from unittest import mock

from services.grok2api_runtime import verify_grok2api


class _Response:
    def __init__(self, status_code: int = 200, text: str = "ok"):
        self.status_code = status_code
        self.text = text


class Grok2apiRuntimeTests(unittest.TestCase):
    def test_verify_uses_current_admin_api_verify_endpoint(self):
        with mock.patch("services.grok2api_runtime.requests.get", return_value=_Response()) as get_mock:
            ok, msg = verify_grok2api(api_url="http://grok2api.example", app_key="admin-key")

        self.assertTrue(ok)
        self.assertEqual(msg, "grok2api 鉴权正常")
        get_mock.assert_called_once_with(
            "http://grok2api.example/admin/api/verify",
            headers={"Authorization": "Bearer admin-key"},
            timeout=10,
        )

    def test_verify_falls_back_to_legacy_admin_endpoint_on_404(self):
        with mock.patch(
            "services.grok2api_runtime.requests.get",
            side_effect=[_Response(status_code=404, text="not found"), _Response()],
        ) as get_mock:
            ok, msg = verify_grok2api(api_url="http://grok2api.example", app_key="admin-key")

        self.assertTrue(ok)
        self.assertEqual(msg, "grok2api 鉴权正常")
        self.assertEqual(get_mock.call_args_list[1].args[0], "http://grok2api.example/v1/admin/verify")


if __name__ == "__main__":
    unittest.main()
