import unittest
from unittest import mock

from core.base_platform import Account
from platforms.grok.grok2api_upload import upload_to_grok2api


class _Response:
    def __init__(self, data=None, status_code: int = 200, text: str = ""):
        self._data = data or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._data


class Grok2apiUploadTests(unittest.TestCase):
    def _account(self) -> Account:
        return Account(
            platform="grok",
            email="demo@example.com",
            password="secret",
            extra={"sso": "sso-new-token"},
        )

    def test_upload_uses_current_admin_tokens_endpoint_and_flat_token_response(self):
        existing = {
            "tokens": [
                {"token": "old-basic-token", "pool": "basic", "tags": ["keep"]},
                {"token": "old-super-token", "pool": "super", "tags": []},
            ]
        }

        with mock.patch(
            "platforms.grok.grok2api_upload.cffi_requests.get",
            return_value=_Response(existing),
        ) as get_mock:
            with mock.patch(
                "platforms.grok.grok2api_upload.cffi_requests.post",
                return_value=_Response({"status": "success"}),
            ) as post_mock:
                ok, msg = upload_to_grok2api(
                    self._account(),
                    api_url="http://grok2api.example",
                    app_key="admin-key",
                    pool_name="ssoBasic",
                )

        self.assertTrue(ok)
        self.assertEqual(msg, "导入成功")
        self.assertEqual(get_mock.call_args.args[0], "http://grok2api.example/admin/api/tokens")
        self.assertEqual(post_mock.call_args.args[0], "http://grok2api.example/admin/api/tokens")
        self.assertEqual(
            post_mock.call_args.kwargs["json"],
            {
                "basic": [
                    {"token": "old-basic-token", "tags": ["keep"]},
                    {"token": "sso-new-token", "tags": []},
                ],
                "super": [{"token": "old-super-token", "tags": []}],
            },
        )

    def test_upload_falls_back_to_legacy_v1_admin_tokens_endpoint_on_404(self):
        with mock.patch(
            "platforms.grok.grok2api_upload.cffi_requests.get",
            side_effect=[
                _Response(status_code=404, text="not found"),
                _Response({"tokens": {"basic": []}}),
            ],
        ) as get_mock:
            with mock.patch(
                "platforms.grok.grok2api_upload.cffi_requests.post",
                return_value=_Response({"ok": True}),
            ) as post_mock:
                ok, msg = upload_to_grok2api(
                    self._account(),
                    api_url="http://grok2api.example",
                    app_key="admin-key",
                    pool_name="basic",
                )

        self.assertTrue(ok)
        self.assertEqual(msg, "导入成功")
        self.assertEqual(get_mock.call_args_list[1].args[0], "http://grok2api.example/v1/admin/tokens")
        self.assertEqual(post_mock.call_args.args[0], "http://grok2api.example/v1/admin/tokens")


if __name__ == "__main__":
    unittest.main()
