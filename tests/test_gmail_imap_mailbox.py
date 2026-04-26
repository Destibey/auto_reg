import email
import unittest
from unittest import mock

from core.base_mailbox import MailboxAccount, create_mailbox


class _FakeIMAP:
    instances = []
    messages = {}
    searched = False

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.login_args = None
        self.selected_mailbox = None
        _FakeIMAP.instances.append(self)

    def login(self, username, password):
        self.login_args = (username, password)
        return "OK", [b"ok"]

    def select(self, mailbox):
        self.selected_mailbox = mailbox
        return "OK", [b"1"]

    def uid(self, command, *args):
        command = command.upper()
        if command == "SEARCH":
            _FakeIMAP.searched = True
            ids = b" ".join(_FakeIMAP.messages.keys())
            return "OK", [ids]
        if command == "FETCH":
            uid = args[0]
            return "OK", [(b"BODY[]", _FakeIMAP.messages[uid])]
        raise AssertionError(f"unexpected IMAP command: {command}")

    def logout(self):
        return "BYE", [b"bye"]


class GmailIMAPMailboxTests(unittest.TestCase):
    def setUp(self):
        _FakeIMAP.instances = []
        _FakeIMAP.messages = {}
        _FakeIMAP.searched = False

    def _mail_bytes(self, *, to_addr, body, extra_headers=None):
        msg = email.message.EmailMessage()
        msg["From"] = "noreply@example.test"
        msg["To"] = to_addr
        msg["Subject"] = "Your verification code"
        for name, value in (extra_headers or {}).items():
            msg[name] = value
        msg.set_content(body)
        return msg.as_bytes()

    def test_factory_generates_catch_all_address_for_gmail_imap(self):
        mailbox = create_mailbox(
            "gmail_imap",
            extra={
                "gmail_imap_email": "owner@gmail.com",
                "gmail_imap_app_password": "app-pass",
                "gmail_imap_target_domain": "example.com",
            },
        )

        with mock.patch.object(type(mailbox), "_generate_local_part", return_value="alias123"):
            account = mailbox.get_email()

        self.assertEqual(account.email, "alias123@example.com")
        self.assertEqual(account.account_id, "alias123@example.com")

    @mock.patch("imaplib.IMAP4_SSL", _FakeIMAP)
    def test_get_current_ids_uses_configured_gmail_imap_mailbox(self):
        _FakeIMAP.messages = {
            b"101": self._mail_bytes(to_addr="alias@example.com", body="old code 111111")
        }
        mailbox = create_mailbox(
            "gmail_imap",
            extra={
                "gmail_imap_email": "owner@gmail.com",
                "gmail_imap_app_password": "app-pass",
                "gmail_imap_host": "imap.gmail.com",
                "gmail_imap_port": "993",
                "gmail_imap_mailbox": "INBOX",
                "gmail_imap_target_email": "alias@example.com",
            },
        )

        ids = mailbox.get_current_ids(MailboxAccount(email="alias@example.com"))

        self.assertEqual(ids, {"101"})
        self.assertEqual(_FakeIMAP.instances[0].host, "imap.gmail.com")
        self.assertEqual(_FakeIMAP.instances[0].port, 993)
        self.assertEqual(_FakeIMAP.instances[0].login_args, ("owner@gmail.com", "app-pass"))
        self.assertEqual(_FakeIMAP.instances[0].selected_mailbox, "INBOX")

    @mock.patch("imaplib.IMAP4_SSL", _FakeIMAP)
    def test_wait_for_code_reads_new_message_addressed_to_generated_alias(self):
        _FakeIMAP.messages = {
            b"100": self._mail_bytes(to_addr="alias@example.com", body="old code 111111"),
            b"101": self._mail_bytes(to_addr="alias@example.com", body="verification code: 654321"),
            b"102": self._mail_bytes(to_addr="other@example.com", body="verification code: 999999"),
        }
        mailbox = create_mailbox(
            "gmail_imap",
            extra={
                "gmail_imap_email": "owner@gmail.com",
                "gmail_imap_app_password": "app-pass",
                "gmail_imap_target_email": "alias@example.com",
            },
        )

        code = mailbox.wait_for_code(
            MailboxAccount(email="alias@example.com"),
            timeout=1,
            before_ids={"100"},
        )

        self.assertEqual(code, "654321")

    @mock.patch("imaplib.IMAP4_SSL", _FakeIMAP)
    def test_wait_for_code_keeps_forwarded_alias_when_body_has_blank_line(self):
        _FakeIMAP.messages = {
            b"101": self._mail_bytes(
                to_addr="owner@gmail.com",
                extra_headers={"X-Original-To": "alias@example.com"},
                body="Hello,\n\nverification code: 654321",
            ),
        }
        mailbox = create_mailbox(
            "gmail_imap",
            extra={
                "gmail_imap_email": "owner@gmail.com",
                "gmail_imap_app_password": "app-pass",
                "gmail_imap_target_email": "alias@example.com",
            },
        )

        code = mailbox.wait_for_code(
            MailboxAccount(email="alias@example.com"),
            timeout=1,
        )

        self.assertEqual(code, "654321")


if __name__ == "__main__":
    unittest.main()
