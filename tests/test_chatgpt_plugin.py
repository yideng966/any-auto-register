import unittest
from unittest import mock

from core.base_mailbox import MailboxAccount
from core.base_platform import Account, RegisterConfig
from platforms.chatgpt.plugin import ChatGPTPlatform


class _BlankMailbox:
    def get_email(self):
        return MailboxAccount(email="", account_id="blank-mailbox")

    def wait_for_code(self, *args, **kwargs):
        return "123456"


class _TrackingMailbox:
    def __init__(self):
        self.account = MailboxAccount(email="demo@example.com", account_id="tracked-mailbox")
        self.wait_call = None
        self.current_ids_calls = []

    def get_email(self):
        return self.account

    def get_current_ids(self, account):
        self.current_ids_calls.append(account)
        return {"mid-1"}

    def wait_for_code(self, *args, **kwargs):
        self.wait_call = (args, kwargs)
        return "123456"


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


class _VerificationAdapter:
    def __init__(self):
        self.run_called = False

    def run(self, context):
        self.run_called = True
        context.email_service.create_email()
        code = context.email_service.get_verification_code(
            timeout=30,
            otp_sent_at=123.0,
            exclude_codes={"654321"},
        )
        self.last_code = code
        return mock.Mock(success=True)

    def build_account(self, result, fallback_password):
        return {"success": True, "password": fallback_password}


class _BlankEmailAdapter:
    def run(self, context):
        context.email_service.create_email()
        raise AssertionError("create_email 应该先报错")


class ChatGPTPluginTests(unittest.TestCase):
    def test_custom_provider_rejects_blank_email(self):
        platform = ChatGPTPlatform(
            config=RegisterConfig(extra={"chatgpt_registration_mode": "refresh_token"}),
            mailbox=_BlankMailbox(),
        )

        with mock.patch(
            "platforms.chatgpt.plugin.build_chatgpt_registration_mode_adapter",
            return_value=_BlankEmailAdapter(),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                platform.register()

        self.assertIn("custom_provider 返回空邮箱地址", str(ctx.exception))

    def test_custom_provider_uses_mailbox_baseline_for_verification_code(self):
        mailbox = _TrackingMailbox()
        platform = ChatGPTPlatform(
            config=RegisterConfig(extra={"chatgpt_registration_mode": "refresh_token"}),
            mailbox=mailbox,
        )
        adapter = _VerificationAdapter()

        with mock.patch(
            "platforms.chatgpt.plugin.build_chatgpt_registration_mode_adapter",
            return_value=adapter,
        ):
            result = platform.register()

        self.assertTrue(adapter.run_called)
        self.assertEqual(adapter.last_code, "123456")
        self.assertEqual(result["success"], True)
        self.assertEqual(mailbox.current_ids_calls, [mailbox.account])
        self.assertIsNotNone(mailbox.wait_call)
        _, kwargs = mailbox.wait_call
        self.assertEqual(kwargs.get("before_ids"), {"mid-1"})
        self.assertEqual(kwargs.get("otp_sent_at"), 123.0)
        self.assertEqual(kwargs.get("exclude_codes"), {"654321"})


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
