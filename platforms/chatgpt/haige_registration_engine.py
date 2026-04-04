"""
海哥模式注册引擎

采用策略模式封装注册核心（OAuthPkceRegisterStrategy），
走 auth.openai.com OAuth PKCE 直通注册流程，最终产出 refresh_token。

外部接口与 plugin.py / mode adapter 完全兼容。
"""

import random
import time
import logging
from datetime import datetime
from typing import Optional, Callable

from core.task_runtime import TaskInterruption
from platforms.chatgpt.refresh_token_registration_engine import RegistrationResult

from .oauth_pkce_client import OAuthPkceClient
from .utils import generate_random_name, generate_random_birthday

logger = logging.getLogger(__name__)


_FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "David", "William", "Richard",
    "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda",
    "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen", "Daniel",
    "Matthew", "Anthony", "Mark", "Steven", "Andrew", "Paul", "Emily",
    "Emma", "Olivia", "Sophia", "Ava", "Isabella", "Mia",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Wilson", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White",
]


def _random_name_and_birthday() -> tuple[str, str]:
    name = f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"
    year = random.randint(1985, 2004)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return name, f"{year}-{month:02d}-{day:02d}"


class _EmailServiceAdapter:
    """
    将 email_service（含 create_email / get_verification_code）
    适配为 OAuthPkceRegisterStrategy 期待的接口。
    """

    def __init__(self, email_service, log: Callable[[str], None]):
        self._svc = email_service
        self._log = log
        self._used_codes: set = set()

    def create_email(self, config=None):
        return self._svc.create_email(config)

    def wait_for_verification_code(
        self, email: str, timeout: int = 120, otp_sent_at=None
    ) -> Optional[str]:
        self._log(f"等待邮箱 {email} 的验证码（timeout={timeout}s）...")
        code = self._svc.get_verification_code(
            email=email,
            timeout=timeout,
            otp_sent_at=otp_sent_at,
            exclude_codes=self._used_codes,
        )
        if code:
            self._used_codes.add(code)
            self._log(f"成功获取验证码: {code}")
        return code


class OAuthPkceRegisterStrategy:
    """
    OAuth PKCE 注册策略（策略模式）

    完整注册流程（12 步）：
      1.  检查 IP 地区
      2.  创建邮箱
      3.  访问 OAuth 授权 URL，获取 oai-did Cookie
      4.  获取 Sentinel Token
      5.  提交邮箱 (authorize/continue)
      6.  提交密码 (user/register)
      7.  发送 OTP + 等待验证码
      8.  验证 OTP (email-otp/validate)
      9.  创建账户 (create_account)
      10. 注册后重新 OAuth 登录
      11. 解析 workspace_id + 选择 workspace
      12. 跟踪重定向链，交换 OAuth code -> access_token + refresh_token
    """

    def execute(
        self,
        client: OAuthPkceClient,
        email_service,
        email: str,
        password: str,
        log: Callable[[str], None],
    ) -> RegistrationResult:
        result = RegistrationResult(success=False)

        log("步骤 1/12: 检查 IP 地区...")
        client.check_ip_region()

        log("步骤 2/12: 创建邮箱接码订单...")
        email_data = email_service.create_email()
        email_addr = email or (email_data.get("email") if email_data else None)
        if not email_addr:
            result.error_message = "创建邮箱失败"
            return result
        result.email = email_addr
        result.password = password
        log(f"邮箱: {email_addr}")

        log("步骤 3/12: 访问 OAuth 授权 URL，获取 oai-did...")
        client.init_oauth_session()

        log("步骤 4/12: 获取 Sentinel Token...")
        client.refresh_sentinel()

        log("步骤 5/12: 提交邮箱...")
        client.submit_email(email_addr)

        log("步骤 6/12: 提交密码...")
        continue_url = client.submit_password(email_addr, password)

        log("步骤 7/12: 发送验证码...")
        otp_sent_at = time.time()
        client.send_otp(continue_url)

        log("步骤 7/12: 等待邮箱验证码（最多 120s）...")
        otp_code = email_service.wait_for_verification_code(
            email_addr,
            timeout=120,
            otp_sent_at=otp_sent_at,
        )
        if not otp_code:
            result.error_message = "未收到邮箱验证码"
            return result
        log(f"验证码: {otp_code}")

        log("步骤 8/12: 验证 OTP...")
        client.validate_otp(otp_code)

        log("步骤 9/12: 填写账户信息（姓名/生日）...")
        name, birthdate = _random_name_and_birthday()
        log(f"账户信息: {name} ({birthdate})")
        client.create_account(name, birthdate)

        log("步骤 10/12: 注册后重新 OAuth 登录...")
        login_oauth = client.login_after_register(email_addr, password, otp_code)

        log("步骤 11/12: 解析 workspace_id...")
        workspace_id = client.extract_workspace_id()
        result.workspace_id = workspace_id

        log("步骤 12/12: 选择 workspace...")
        ws_continue_url = client.select_workspace(workspace_id)

        log("步骤 12/12: 跟踪重定向链，交换 OAuth Token...")
        token_data = client.follow_redirects_and_exchange_token(ws_continue_url, login_oauth)

        result.success = True
        result.access_token = token_data.get("access_token", "")
        result.refresh_token = token_data.get("refresh_token", "")
        result.id_token = token_data.get("id_token", "")
        result.account_id = token_data.get("account_id", "") or workspace_id
        result.metadata = {
            "type": token_data.get("type", "codex"),
            "expired": token_data.get("expired", ""),
        }

        log("=" * 50)
        log("注册流程成功完成!")
        log("=" * 50)
        return result


class HaigeRegistrationEngine:
    """
    海哥模式注册引擎（外部接口层）

    plugin.py / mode adapter 通过此类发起注册，不感知内部策略变化。
    """

    def __init__(
        self,
        email_service,
        proxy_url: Optional[str] = None,
        callback_logger: Optional[Callable[[str], None]] = None,
        task_uuid: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.email_service = email_service
        self.proxy_url = proxy_url
        self.callback_logger = callback_logger
        self.task_uuid = task_uuid
        self.max_retries = max(1, int(max_retries or 1))

        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.logs: list[str] = []

    def _log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.logs.append(log_message)
        if self.callback_logger:
            self.callback_logger(log_message)
        if level == "error":
            logger.error(log_message)
        else:
            logger.info(log_message)

    def run(self) -> RegistrationResult:
        result = RegistrationResult(success=False, logs=self.logs)
        last_error = ""

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    self._log(f"整流程重试 {attempt + 1}/{self.max_retries}...")
                    time.sleep(2)

                adapter = _EmailServiceAdapter(self.email_service, self._log)
                client = OAuthPkceClient(proxy=self.proxy_url, log_fn=self._log)
                strategy = OAuthPkceRegisterStrategy()

                result = strategy.execute(
                    client=client,
                    email_service=adapter,
                    email=self.email or "",
                    password=self.password or "AAb1234567890!",
                    log=self._log,
                )
                result.logs = self.logs

                if result.success:
                    return result

                last_error = result.error_message or "注册失败"
                self._log(f"注册失败: {last_error}", "error")

                if attempt < self.max_retries - 1 and self._should_retry(last_error):
                    self._log("准备重试...")
                    continue

                return result

            except TaskInterruption:
                raise
            except Exception as e:
                last_error = str(e)
                self._log(f"注册异常: {last_error}", "error")
                if attempt < self.max_retries - 1 and self._should_retry(last_error):
                    continue
                result.error_message = last_error
                result.logs = self.logs
                return result

        result.error_message = last_error or "注册失败"
        result.logs = self.logs
        return result

    @staticmethod
    def _should_retry(message: str) -> bool:
        text = str(message or "").lower()
        retriable_markers = [
            "tls", "ssl", "curl: (35)",
            "ip 地区检查失败", "sentinel",
            "timeout", "timed out", "connection",
            "验证码", "otp",
        ]
        return any(m in text for m in retriable_markers)
