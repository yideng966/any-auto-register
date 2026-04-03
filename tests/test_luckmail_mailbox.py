import unittest
from unittest import mock
from types import SimpleNamespace

from core.base_mailbox import LuckMailMailbox, MailboxAccount, create_mailbox


class LuckMailMailboxTests(unittest.TestCase):
    def _build_mailbox(self):
        mailbox = LuckMailMailbox.__new__(LuckMailMailbox)
        mailbox._client = mock.Mock()
        mailbox._mode = "auto"
        mailbox._project_code = "openai"
        mailbox._email_type = None
        mailbox._domain = None
        mailbox._source_tag = None
        mailbox._registered_tag = "已注册"
        mailbox._order_no = None
        mailbox._token = "tok_demo"
        mailbox._email = "demo@example.com"
        mailbox._purchase_id = None
        mailbox._log_fn = None
        return mailbox

    def test_create_mailbox_passes_source_and_registered_tags_to_luckmail(self):
        with mock.patch("core.base_mailbox.LuckMailMailbox") as mailbox_cls:
            create_mailbox(
                "luckmail",
                {
                    "luckmail_base_url": "https://mail.example.com",
                    "luckmail_api_key": "api-key",
                    "luckmail_mode": "order",
                    "luckmail_project_code": "openai",
                    "luckmail_email_type": "hotmail",
                    "luckmail_domain": "hotmail.com",
                    "luckmail_source_tag": "主池",
                    "luckmail_registered_tag": "已注册-海哥",
                },
            )

        mailbox_cls.assert_called_once_with(
            base_url="https://mail.example.com",
            api_key="api-key",
            mode="order",
            project_code="openai",
            email_type="hotmail",
            domain="hotmail.com",
            source_tag="主池",
            registered_tag="已注册-海哥",
        )

    def test_explicit_purchase_mode_overrides_legacy_logic(self):
        mailbox = self._build_mailbox()
        mailbox._mode = "purchase"
        mailbox._project_code = "cursor"
        mailbox._source_tag = None
        mailbox._token = None

        self.assertTrue(mailbox._use_purchase_mode())

    def test_explicit_order_mode_overrides_openai_purchase_default(self):
        mailbox = self._build_mailbox()
        mailbox._mode = "order"
        mailbox._project_code = "openai"
        mailbox._source_tag = "主池"
        mailbox._token = None

        self.assertFalse(mailbox._use_purchase_mode())

    def test_get_email_resolves_source_tag_name_to_tag_id(self):
        mailbox = self._build_mailbox()
        mailbox._token = None
        mailbox._email = None
        mailbox._source_tag = "主池"
        mailbox._domain = "hotmail.com"
        mailbox._client.user.get_tags.return_value = [
            SimpleNamespace(id=7, name="主池", limit_type=1),
        ]
        mailbox._client.user.get_purchases.return_value = SimpleNamespace(
            list=[
                SimpleNamespace(
                    id=12,
                    email_address="demo@hotmail.com",
                    token="tok_demo",
                    project_name="openai",
                    price="0.5",
                    tag_id=7,
                    tag_name="主池",
                )
            ]
        )

        account = mailbox.get_email()

        self.assertEqual(account.email, "demo@hotmail.com")
        self.assertEqual(account.account_id, "tok_demo")
        self.assertEqual(mailbox._purchase_id, 12)
        mailbox._client.user.get_purchases.assert_called_once_with(
            page=1,
            page_size=1,
            tag_id=7,
            keyword="@hotmail.com",
            user_disabled=0,
        )

    def test_mark_registered_sets_purchase_tag_for_last_purchase(self):
        mailbox = self._build_mailbox()
        mailbox._purchase_id = 12

        mailbox.mark_registered(success=True)

        mailbox._client.user.set_purchase_tag.assert_called_once_with(
            12,
            tag_name="已注册",
        )

    @mock.patch("time.sleep", return_value=None)
    def test_wait_for_code_skips_excluded_purchase_code_and_keeps_polling_for_fresh_mail(self, _sleep):
        mailbox = self._build_mailbox()
        mailbox.get_current_ids = mock.Mock(return_value={"m1"})
        mailbox._client.user.get_token_mails.side_effect = [
            SimpleNamespace(
                email_address="demo@example.com",
                project="openai",
                mails=[
                    SimpleNamespace(message_id="m1", subject="Your OpenAI code is 111111", body="", html_body=""),
                ],
            ),
            SimpleNamespace(
                email_address="demo@example.com",
                project="openai",
                mails=[
                    SimpleNamespace(message_id="m1", subject="Your OpenAI code is 111111", body="", html_body=""),
                    SimpleNamespace(message_id="m2", subject="Your OpenAI code is 222222", body="", html_body=""),
                ],
            ),
        ]

        code = mailbox.wait_for_code(
            MailboxAccount(email="demo@example.com", account_id="tok_demo"),
            timeout=5,
            exclude_codes={"111111"},
        )

        self.assertEqual(code, "222222")
        mailbox.get_current_ids.assert_called_once()
        self.assertEqual(mailbox._client.user.get_token_mails.call_count, 2)


if __name__ == "__main__":
    unittest.main()
