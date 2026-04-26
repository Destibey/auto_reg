import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from api.tasks import (
    RegisterTaskRequest,
    _auto_upload_integrations,
    _create_task_record,
    _run_register,
    _sleep_with_task_control,
    _task_store,
)
from core.base_mailbox import BaseMailbox, MailboxAccount
from core.base_platform import Account, BasePlatform
from core.task_runtime import RegisterTaskControl, StopTaskRequested


class _FakeMailbox(BaseMailbox):
    def get_email(self) -> MailboxAccount:
        return MailboxAccount(email="demo@example.com")

    def get_current_ids(self, account: MailboxAccount) -> set:
        return set()

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        **kwargs,
    ) -> str:
        def poll_once():
            return None

        return self._run_polling_wait(
            timeout=timeout,
            poll_interval=0.01,
            poll_once=poll_once,
        )


class _FakePlatform(BasePlatform):
    name = "fake"
    display_name = "Fake"

    def __init__(self, config=None, mailbox=None):
        super().__init__(config)
        self.mailbox = mailbox

    def register(self, email: str, password: str = None) -> Account:
        account = self.mailbox.get_email()
        self.mailbox.wait_for_code(account, timeout=1)
        return Account(
            platform="fake",
            email=account.email,
            password=password or "pw",
        )

    def check_valid(self, account: Account) -> bool:
        return True


class _FailingPlatform(BasePlatform):
    name = "failing"
    display_name = "Failing"

    def __init__(self, config=None, mailbox=None):
        super().__init__(config)
        self.mailbox = mailbox

    def register(self, email: str, password: str = None) -> Account:
        raise RuntimeError("获取验证码失败")

    def check_valid(self, account: Account) -> bool:
        return False


class RegisterTaskControlFlowTests(unittest.TestCase):
    def _build_request(self):
        return RegisterTaskRequest(
            platform="fake",
            count=1,
            concurrency=1,
            proxy="http://proxy.local:8080",
            extra={"mail_provider": "fake"},
        )

    def _run_with_control(self, task_id: str, *, stop: bool = False, skip: bool = False):
        req = self._build_request()
        _create_task_record(task_id, req, "manual", None)
        if stop:
            _task_store.request_stop(task_id)
        if skip:
            _task_store.request_skip_current(task_id)

        with (
            patch("core.registry.get", return_value=_FakePlatform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("core.db.save_account", side_effect=lambda account: account),
            patch("api.tasks._save_task_log"),
        ):
            _run_register(task_id, req)

        return _task_store.snapshot(task_id)

    def test_skip_current_marks_attempt_as_skipped(self):
        snapshot = self._run_with_control("task-control-skip", skip=True)

        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["success"], 0)
        self.assertEqual(snapshot["skipped"], 1)
        self.assertEqual(snapshot["errors"], [])

    def test_stop_marks_task_as_stopped(self):
        snapshot = self._run_with_control("task-control-stop", stop=True)

        self.assertEqual(snapshot["status"], "stopped")
        self.assertEqual(snapshot["success"], 0)
        self.assertEqual(snapshot["skipped"], 0)
        self.assertEqual(snapshot["errors"], [])

    def test_all_failed_attempts_mark_task_as_failed(self):
        req = self._build_request()
        task_id = "task-control-failed"
        _create_task_record(task_id, req, "manual", None)

        with (
            patch("core.registry.get", return_value=_FailingPlatform),
            patch("core.base_mailbox.create_mailbox", return_value=_FakeMailbox()),
            patch("api.tasks._save_task_log"),
        ):
            _run_register(task_id, req)

        snapshot = _task_store.snapshot(task_id)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["success"], 0)
        self.assertEqual(snapshot["skipped"], 0)
        self.assertEqual(snapshot["errors"], ["获取验证码失败"])

    def test_signup_only_chatgpt_account_skips_auto_upload(self):
        account = Account(
            platform="chatgpt",
            email="manual@example.com",
            password="pw",
            extra={"registration_stage": "signup_only"},
        )

        with (
            patch("services.external_sync.sync_account") as sync_account,
            patch("api.tasks._log") as log,
        ):
            _auto_upload_integrations("task-manual-handoff", account)

        sync_account.assert_not_called()
        log.assert_called_once()
        self.assertIn("signup-only", log.call_args.args[1])
        self.assertIn("账号管理页", log.call_args.args[1])

    def test_stop_task_api_requests_cooperative_stop(self):
        task_id = "task-control-api-stop"
        _create_task_record(task_id, self._build_request(), "manual", None)
        client = TestClient(main.app)

        with patch("core.config_store.config_store.get", return_value=""):
            response = client.post(f"/api/tasks/{task_id}/stop")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["control"]["stop_requested"])
        snapshot = _task_store.snapshot(task_id)
        self.assertTrue(snapshot["control"]["stop_requested"])
        self.assertTrue(any("停止任务请求" in line for line in snapshot["logs"]))

    def test_register_delay_sleep_stops_cooperatively(self):
        control = RegisterTaskControl()
        attempt_id = control.start_attempt()
        sleep_calls = []

        def request_stop_during_sleep(_seconds):
            sleep_calls.append(_seconds)
            control.request_stop()

        with patch("api.tasks.time.sleep", side_effect=request_stop_during_sleep):
            with self.assertRaises(StopTaskRequested):
                _sleep_with_task_control(control, attempt_id, 30)

        self.assertEqual(sleep_calls, [0.5])

    def test_skip_current_api_targets_active_attempt(self):
        task_id = "task-control-api-skip"
        _create_task_record(task_id, self._build_request(), "manual", None)
        control = _task_store.control_for(task_id)
        attempt_id = control.start_attempt()
        client = TestClient(main.app)

        try:
            with patch("core.config_store.config_store.get", return_value=""):
                response = client.post(f"/api/tasks/{task_id}/skip-current")
        finally:
            control.finish_attempt(attempt_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["control"]["targeted_skip_attempts"], 1)
        snapshot = _task_store.snapshot(task_id)
        self.assertTrue(any("跳过当前账号请求" in line for line in snapshot["logs"]))


if __name__ == "__main__":
    unittest.main()
