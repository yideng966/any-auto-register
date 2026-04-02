import unittest
from unittest import mock

from core.base_platform import Account, RegisterConfig
from platforms.chatgpt.plugin import ChatGPTPlatform


class _FakeMailbox:
    def __init__(self):
        self.mark_registered = mock.Mock()

    def get_email(self):
        return type("MailboxAccount", (), {"email": "demo@example.com", "account_id": "tok_demo"})()

    def wait_for_code(self, *args, **kwargs):
        return "123456"


class _FakeAdapter:
    def __init__(self, *, success=True):
        self._success = success
        self.run = mock.Mock(
            return_value=type(
                "Result",
                (),
                {
                    "success": success,
                    "error_message": "register failed",
                    "email": "demo@example.com",
                    "password": "pw-demo",
                    "account_id": "acct-demo",
                    "access_token": "at-demo",
                    "refresh_token": "rt-demo",
                    "id_token": "id-demo",
                    "session_token": "",
                    "workspace_id": "ws-demo",
                    "source": "register",
                },
            )()
        )
        self.build_account = mock.Mock(
            return_value=Account(
                platform="chatgpt",
                email="demo@example.com",
                password="pw-demo",
                user_id="acct-demo",
                token="at-demo",
                extra={"refresh_token": "rt-demo"},
            )
        )


class ChatGPTPlatformTests(unittest.TestCase):
    def test_register_marks_mailbox_after_success(self):
        mailbox = _FakeMailbox()
        platform = ChatGPTPlatform(
            config=RegisterConfig(extra={"chatgpt_registration_mode": "haige"}),
            mailbox=mailbox,
        )
        adapter = _FakeAdapter(success=True)

        with mock.patch(
            "platforms.chatgpt.plugin.build_chatgpt_registration_mode_adapter",
            return_value=adapter,
        ):
            account = platform.register(email="demo@example.com", password="pw-demo")

        self.assertEqual(account.email, "demo@example.com")
        mailbox.mark_registered.assert_called_once_with(success=True)

    def test_register_does_not_mark_mailbox_when_registration_fails(self):
        mailbox = _FakeMailbox()
        platform = ChatGPTPlatform(
            config=RegisterConfig(extra={"chatgpt_registration_mode": "haige"}),
            mailbox=mailbox,
        )
        adapter = _FakeAdapter(success=False)

        with mock.patch(
            "platforms.chatgpt.plugin.build_chatgpt_registration_mode_adapter",
            return_value=adapter,
        ):
            with self.assertRaisesRegex(RuntimeError, "register failed"):
                platform.register(email="demo@example.com", password="pw-demo")

        mailbox.mark_registered.assert_not_called()


if __name__ == "__main__":
    unittest.main()
