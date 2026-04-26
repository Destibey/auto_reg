"""Browser-first ChatGPT registration with manual user handoff."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests

from core.task_runtime import TaskInterruption

from .constants import OAUTH_REDIRECT_URI
from .oauth import OAuthManager, OAuthStart
from .refresh_token_registration_engine import RegistrationResult
from .utils import generate_random_password

DEFAULT_CHATGPT_MANUAL_SIGNUP_URL = "https://chatgpt.com/"


@dataclass
class ManualBrowserSession:
    provider: str
    page: object
    browser: object = None
    context: object = None
    playwright: object = None
    adspower_base_url: str = ""
    adspower_profile_key: str = ""
    adspower_profile_value: str = ""
    adspower_headers: Optional[dict] = None
    keep_open: bool = False

    def close(self) -> None:
        if self.keep_open:
            return
        try:
            if self.context is not None and self.provider != "adspower":
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception:
            pass
        if self.provider == "adspower" and self.adspower_base_url and self.adspower_profile_value:
            try:
                requests.get(
                    f"{self.adspower_base_url.rstrip('/')}/api/v1/browser/stop",
                    params={self.adspower_profile_key: self.adspower_profile_value},
                    headers=self.adspower_headers or {},
                    timeout=10,
                )
            except Exception:
                pass
        try:
            if self.playwright is not None:
                self.playwright.stop()
        except Exception:
            pass


@dataclass
class ManualPageState:
    url: str
    title: str = ""
    body_text: str = ""


class BrowserManualHandoffRegistrationEngine:
    """Open a real headed browser and wait for the user to finish signup."""

    def __init__(
        self,
        email_service,
        proxy_url: Optional[str] = None,
        browser_mode: str = "headed",
        callback_logger: Optional[Callable[[str], None]] = None,
        task_uuid: Optional[str] = None,
        max_retries: int = 1,
        extra_config: Optional[dict] = None,
        task_control: Optional[object] = None,
        task_attempt_token: Optional[int] = None,
    ):
        self.email_service = email_service
        self.proxy_url = proxy_url
        self.browser_mode = browser_mode or "headed"
        self.callback_logger = callback_logger or (lambda msg: None)
        self.task_uuid = task_uuid
        self.max_retries = max(1, int(max_retries or 1))
        self.extra_config = dict(extra_config or {})
        self.task_control = task_control
        self.task_attempt_token = task_attempt_token
        self.oauth_manager = OAuthManager(proxy_url=proxy_url)

        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.email_info: Optional[dict] = None
        self.logs: list[str] = []
        self._used_verification_codes: set[str] = set()
        self._last_otp_poll = 0.0

    def _log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.logs.append(log_message)
        self.callback_logger(log_message)

    def _int_config(self, key: str, default: int) -> int:
        try:
            value = int(self.extra_config.get(key) or default)
        except (TypeError, ValueError):
            value = default
        return max(1, value)

    def _bool_config(self, key: str, default: bool = False) -> bool:
        value = self.extra_config.get(key)
        if value in (None, ""):
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _camoufox_humanize_config(self):
        value = self.extra_config.get("chatgpt_camoufox_humanize")
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return True if value else None
        text = str(value).strip().lower()
        if text in {"0", "false", "no", "off"}:
            return None
        if text in {"1", "true", "yes", "on"}:
            return True
        try:
            seconds = float(text)
        except (TypeError, ValueError):
            return None
        return seconds if seconds > 0 else None

    @staticmethod
    def _camoufox_geoip_available() -> bool:
        try:
            import geoip2  # noqa: F401
        except Exception:
            return False
        return True

    def _manual_signup_url(self) -> str:
        return str(
            self.extra_config.get("chatgpt_manual_signup_url")
            or DEFAULT_CHATGPT_MANUAL_SIGNUP_URL
        ).strip()

    def _manual_token_callback_enabled(self) -> bool:
        return self._bool_config("chatgpt_manual_enable_token_callback", False)

    def _checkpoint(self) -> None:
        if self.task_control is None:
            return
        self.task_control.checkpoint(attempt_id=self.task_attempt_token)

    @staticmethod
    def _default_manual_profile_dir(name: str) -> str:
        if os.name == "posix" and os.uname().sysname == "Darwin":
            base_dir = Path.home() / "Library" / "Application Support" / "AutoReg" / "manual_profiles"
        else:
            base_dir = Path.home() / ".cache" / "autoreg" / "manual_profiles"
        return str(base_dir / name)

    def _create_email(self) -> str:
        if self.email:
            return self.email
        self.email_info = self.email_service.create_email()
        email = str((self.email_info or {}).get("email") or "").strip()
        if not email:
            raise RuntimeError("创建邮箱失败: 邮箱服务返回空地址")
        self.email = email
        return email

    def _adspower_headers(self) -> dict:
        api_key = (
            self.extra_config.get("chatgpt_adspower_api_key")
            or self.extra_config.get("adspower_api_key")
            or os.getenv("ADSPOWER_API_KEY")
            or ""
        )
        if not str(api_key).strip():
            return {}
        return {"Authorization": f"Bearer {str(api_key).strip()}"}

    def _open_adspower_session(self) -> ManualBrowserSession:
        from playwright.sync_api import sync_playwright

        base_url = str(
            self.extra_config.get("chatgpt_adspower_api_url")
            or self.extra_config.get("adspower_api_url")
            or os.getenv("ADSPOWER_LOCAL_API_URL")
            or "http://local.adspower.net:50325"
        ).rstrip("/")
        profile_id = str(
            self.extra_config.get("chatgpt_adspower_profile_id")
            or self.extra_config.get("chatgpt_adspower_user_id")
            or self.extra_config.get("adspower_profile_id")
            or self.extra_config.get("adspower_user_id")
            or ""
        ).strip()
        serial_number = str(
            self.extra_config.get("chatgpt_adspower_serial_number")
            or self.extra_config.get("adspower_serial_number")
            or ""
        ).strip()
        params = {"open_tabs": "1", "cdp_mask": "1"}
        profile_key = "user_id"
        profile_value = profile_id
        if profile_id:
            params["user_id"] = profile_id
        elif serial_number:
            profile_key = "serial_number"
            profile_value = serial_number
            params["serial_number"] = serial_number
        else:
            raise RuntimeError("AdsPower 模式需要配置 chatgpt_adspower_profile_id 或 serial_number")

        headers = self._adspower_headers()
        self._log("启动 AdsPower SunBrowser profile...")
        resp = requests.get(
            f"{base_url}/api/v1/browser/start",
            params=params,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"AdsPower 启动失败: {payload.get('msg') or payload}")
        ws_url = (((payload.get("data") or {}).get("ws") or {}).get("puppeteer") or "").strip()
        if not ws_url:
            raise RuntimeError("AdsPower 未返回 data.ws.puppeteer，无法用 Playwright 接管")

        playwright = sync_playwright().start()
        browser = playwright.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        return ManualBrowserSession(
            provider="adspower",
            page=page,
            browser=browser,
            context=context,
            playwright=playwright,
            adspower_base_url=base_url,
            adspower_profile_key=profile_key,
            adspower_profile_value=profile_value,
            adspower_headers=headers,
            keep_open=self._bool_config("chatgpt_manual_browser_keep_open", False),
        )

    def _open_playwright_session(self) -> ManualBrowserSession:
        from playwright.sync_api import sync_playwright

        profile_dir = str(
            self.extra_config.get("chatgpt_manual_browser_profile_dir")
            or self._default_manual_profile_dir("chatgpt")
        )
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        playwright = sync_playwright().start()
        launch_kwargs = {
            "headless": False,
            "viewport": {"width": 1440, "height": 1000},
        }
        if self.proxy_url:
            launch_kwargs["proxy"] = {"server": self.proxy_url}
        context = playwright.chromium.launch_persistent_context(profile_dir, **launch_kwargs)
        page = context.new_page()
        return ManualBrowserSession(
            provider="playwright",
            page=page,
            context=context,
            playwright=playwright,
            keep_open=self._bool_config("chatgpt_manual_browser_keep_open", False),
        )

    def _open_camoufox_session(self) -> ManualBrowserSession:
        from camoufox.sync_api import Camoufox

        profile_dir = str(
            self.extra_config.get("chatgpt_manual_browser_profile_dir")
            or self._default_manual_profile_dir("chatgpt_camoufox")
        )
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        launch_kwargs = self._build_camoufox_launch_kwargs(profile_dir)
        self._log("启动本地 Camoufox 隔离浏览器...")
        camoufox = Camoufox(**launch_kwargs)
        context = camoufox.__enter__()
        page = context.new_page()
        return ManualBrowserSession(
            provider="camoufox",
            page=page,
            context=context,
            playwright=camoufox,
            keep_open=self._bool_config("chatgpt_manual_browser_keep_open", False),
        )

    def _build_camoufox_launch_kwargs(self, profile_dir: str) -> dict:
        launch_kwargs = {
            "headless": False,
            "persistent_context": True,
            "user_data_dir": profile_dir,
            "enable_cache": True,
        }
        if self.proxy_url:
            launch_kwargs["proxy"] = {"server": self.proxy_url}

        os_value = str(self.extra_config.get("chatgpt_camoufox_os") or "").strip().lower()
        if os_value in {"windows", "macos", "linux"}:
            launch_kwargs["os"] = os_value

        humanize = self._camoufox_humanize_config()
        if humanize is not None:
            launch_kwargs["humanize"] = humanize

        if self._bool_config("chatgpt_camoufox_geoip", False):
            if self._camoufox_geoip_available():
                launch_kwargs["geoip"] = True
            else:
                self._log("Camoufox GeoIP 未启用：当前环境未安装 camoufox[geoip] 依赖", "warning")

        return launch_kwargs

    def _open_browser_session(self) -> ManualBrowserSession:
        provider = str(
            self.extra_config.get("chatgpt_manual_browser_provider")
            or self.extra_config.get("manual_browser_provider")
            or "camoufox"
        ).strip().lower()
        if provider in {"camoufox", "free", "free_fingerprint"}:
            return self._open_camoufox_session()
        if provider in {"adspower", "ads", "sunbrowser", "sun_browser"}:
            return self._open_adspower_session()
        if provider in {"playwright", "chromium", "local"}:
            return self._open_playwright_session()
        raise RuntimeError(f"未知人工接管浏览器 provider: {provider}")

    def _read_page_state(self, page) -> ManualPageState | None:
        try:
            if getattr(page, "is_closed", lambda: False)():
                return None
        except Exception:
            return None
        try:
            url = str(page.url or "")
        except Exception:
            url = ""
        title = ""
        body_text = ""
        try:
            title = str(page.title() or "")
        except Exception:
            pass
        try:
            body_text = str(page.locator("body").inner_text(timeout=500) or "")
        except Exception:
            pass
        if not url and not title and not body_text:
            return None
        return ManualPageState(url=url, title=title, body_text=body_text)

    def _collect_page_states(self, session: ManualBrowserSession) -> list[ManualPageState]:
        states: list[ManualPageState] = []
        try:
            if session.browser is not None:
                for context in session.browser.contexts:
                    for page in context.pages:
                        state = self._read_page_state(page)
                        if state is not None:
                            states.append(state)
                return states
        except Exception:
            pass
        try:
            if session.context is not None:
                for page in session.context.pages:
                    state = self._read_page_state(page)
                    if state is not None:
                        states.append(state)
        except Exception:
            pass
        try:
            state = self._read_page_state(session.page)
            if state is not None:
                states.append(state)
        except Exception:
            pass
        return states

    def _collect_page_urls(self, session: ManualBrowserSession) -> list[str]:
        return [state.url for state in self._collect_page_states(session) if state.url]

    @staticmethod
    def _find_callback_url(urls: list[str], oauth_start: OAuthStart) -> str:
        redirect_uri = (oauth_start.redirect_uri or OAUTH_REDIRECT_URI).lower()
        expected_state = oauth_start.state
        for url in urls:
            lowered = (url or "").lower()
            if not lowered.startswith(redirect_uri):
                continue
            if "code=" in lowered and f"state={expected_state}".lower() in lowered:
                return url
        return ""

    @staticmethod
    def _requires_phone(states: list[ManualPageState] | list[str]) -> bool:
        needles = (
            "add-phone",
            "phone-verification",
            "verify your phone",
            "phone number",
            "add a phone",
            "手机号",
            "手机验证",
            "绑定手机号",
        )
        for state in states:
            if isinstance(state, str):
                haystack = state
            else:
                haystack = " ".join((state.url, state.title, state.body_text))
            lowered = haystack.lower()
            if any(needle in lowered for needle in needles):
                return True
        return False

    @staticmethod
    def _looks_like_chatgpt_app(states: list[ManualPageState]) -> bool:
        positive_markers = (
            "new chat",
            "message chatgpt",
            "ask anything",
            "what can i help",
            "explore gpts",
            "upgrade plan",
            "新聊天",
            "向 chatgpt 发送消息",
            "有什么可以帮",
        )
        signed_out_markers = (
            "log in",
            "sign up",
            "sign in",
            "create account",
            "登录",
            "注册",
            "创建账号",
        )
        for state in states:
            lowered_url = (state.url or "").lower()
            if "chatgpt.com" not in lowered_url and "chat.openai.com" not in lowered_url:
                continue
            if "/auth" in lowered_url:
                continue
            text = " ".join((state.title, state.body_text)).lower()
            if any(marker in text for marker in signed_out_markers):
                continue
            if any(marker in text for marker in positive_markers):
                return True
        return False

    def _poll_email_code_for_user(self) -> None:
        if not hasattr(self.email_service, "get_verification_code"):
            return
        self._checkpoint()
        poll_interval = self._int_config("chatgpt_manual_email_poll_interval_seconds", 10)
        now = time.time()
        if now - self._last_otp_poll < poll_interval:
            return
        self._last_otp_poll = now
        try:
            code = self.email_service.get_verification_code(
                email=self.email,
                email_id=(self.email_info or {}).get("service_id"),
                timeout=self._int_config("chatgpt_manual_email_poll_timeout_seconds", 3),
                exclude_codes=self._used_verification_codes,
            )
        except Exception:
            return
        if not code:
            return
        code_text = str(code).strip()
        if code_text in self._used_verification_codes:
            return
        self._used_verification_codes.add(code_text)
        self._log(f"人工接管验证码: {code_text}（请在浏览器中手动输入）")

    def _exchange_callback(self, callback_url: str, oauth_start: OAuthStart) -> dict:
        return self.oauth_manager.handle_callback(
            callback_url,
            expected_state=oauth_start.state,
            code_verifier=oauth_start.code_verifier,
        )

    def _wait_for_manual_completion(self, session: ManualBrowserSession) -> tuple[bool, str]:
        timeout = self._int_config("chatgpt_manual_handoff_timeout_seconds", 900)
        self._log(f"等待你在普通 ChatGPT 页面手动完成注册，最多 {timeout}s ...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._checkpoint()
            states = self._collect_page_states(session)
            if not states:
                return False, "人工接管浏览器已关闭或不可访问，注册流程已停止。"
            if self._requires_phone(states):
                return False, "OpenAI 要求绑定手机号；人工接管模式已按策略停止。"
            if self._looks_like_chatgpt_app(states):
                return True, "检测到普通 ChatGPT 注册/登录已进入应用。已按 signup-only 策略停止，不自动进入 OAuth 取 token。"
            self._poll_email_code_for_user()
            time.sleep(1)
        return False, "等待人工完成注册超时"

    def _wait_for_token_callback(
        self, session: ManualBrowserSession, oauth_start: OAuthStart
    ) -> tuple[bool, dict | str]:
        timeout = self._int_config("chatgpt_manual_handoff_timeout_seconds", 900)
        self._log(f"等待你在浏览器中手动完成 OAuth 授权，最多 {timeout}s ...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._checkpoint()
            states = self._collect_page_states(session)
            if not states:
                return False, "人工接管浏览器已关闭或不可访问，注册流程已停止。"
            if self._requires_phone(states):
                return False, "OpenAI 要求绑定手机号；人工接管模式已按策略停止。"
            callback_url = self._find_callback_url([state.url for state in states if state.url], oauth_start)
            if callback_url:
                self._log("检测到 OAuth callback，开始交换 token...")
                self._checkpoint()
                return True, self._exchange_callback(callback_url, oauth_start)
            time.sleep(1)
        return False, "等待 OAuth callback 超时"

    def run(self) -> RegistrationResult:
        result = RegistrationResult(success=False, logs=self.logs, source="browser_manual_handoff")
        session = None
        try:
            self._log("=" * 60)
            self._log("ChatGPT browser_manual_handoff 注册流程启动")
            self._log("=" * 60)
            self._checkpoint()

            email = self._create_email()
            password = self.password or generate_random_password()
            self.password = password
            result.email = email
            result.password = password
            self._log(f"人工接管邮箱: {email}")
            self._log(f"人工接管密码: {password}")

            session = self._open_browser_session()
            self._log(f"已打开隔离浏览器 provider={session.provider}")
            signup_url = self._manual_signup_url()
            self._log(f"打开普通 ChatGPT 注册入口: {signup_url}")
            session.page.goto(signup_url, wait_until="domcontentloaded")

            ok, payload = self._wait_for_manual_completion(session)
            if not ok:
                result.error_message = str(payload)
                self._log(result.error_message, "error")
                return result

            if self._manual_token_callback_enabled():
                self._log("第二段 OAuth/token 动作已启用：开始打开 OAuth 授权入口")
                oauth_start = self.oauth_manager.start_oauth()
                self._checkpoint()
                session.page.goto(oauth_start.auth_url, wait_until="domcontentloaded")
                ok, payload = self._wait_for_token_callback(session, oauth_start)
                if not ok:
                    result.error_message = str(payload)
                    self._log(result.error_message, "error")
                    return result

                token_info = payload if isinstance(payload, dict) else {}
                result.success = True
                result.email = str(token_info.get("email") or email)
                result.password = password
                result.account_id = str(token_info.get("account_id") or "")
                result.access_token = str(token_info.get("access_token") or "")
                result.refresh_token = str(token_info.get("refresh_token") or "")
                result.id_token = str(token_info.get("id_token") or "")
                result.metadata = {
                    "expired": token_info.get("expired", ""),
                    "chatgpt_registration_mode": "browser_manual_handoff",
                    "manual_handoff_stage": "token_callback",
                    "chatgpt_manual_enable_token_callback": True,
                }
                self._log("browser_manual_handoff token 提取完成")
                return result

            result.success = True
            result.email = email
            result.password = password
            result.metadata = {
                "chatgpt_registration_mode": "browser_manual_handoff",
                "manual_handoff_stage": "signup_only",
                "chatgpt_manual_enable_token_callback": False,
            }
            self._log(str(payload))
            self._log("browser_manual_handoff 普通注册完成，仅保存邮箱和密码")
            return result
        except TaskInterruption:
            raise
        except Exception as e:
            result.error_message = str(e)
            self._log(f"browser_manual_handoff 失败: {e}", "error")
            return result
        finally:
            try:
                if session is not None:
                    session.close()
            except Exception:
                pass
