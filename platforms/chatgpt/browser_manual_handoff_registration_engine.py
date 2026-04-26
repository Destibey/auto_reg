"""Browser-first ChatGPT registration with manual user handoff."""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests

from core.task_runtime import TaskInterruption

from .constants import MAX_REGISTRATION_AGE, MIN_REGISTRATION_AGE, OAUTH_REDIRECT_URI
from .oauth import OAuthManager, OAuthStart
from .refresh_token_registration_engine import RegistrationResult
from .settings import (
    DEFAULT_CHATGPT_LOCALE,
    DEFAULT_CHATGPT_SIGNUP_ENTRY_URL,
    resolve_chatgpt_locale,
    resolve_chatgpt_signup_entry_url,
)
from .utils import generate_random_name, generate_random_password

DEFAULT_CHATGPT_MANUAL_SIGNUP_URL = DEFAULT_CHATGPT_SIGNUP_ENTRY_URL
DEFAULT_CHATGPT_CAMOUFOX_LOCALE = DEFAULT_CHATGPT_LOCALE


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
    profile_dir: str = ""
    cleanup_profile_on_close: bool = False

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
        if self.cleanup_profile_on_close and self.profile_dir:
            try:
                shutil.rmtree(self.profile_dir, ignore_errors=True)
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
        self._clipboard_lock = threading.Lock()
        self._clipboard_sequence: list[tuple[str, str]] = []
        self._clipboard_index = 0
        self._last_clipboard_value = ""
        self._saw_manual_credential_paste = False
        self._manual_user_info: dict[str, str] = {}
        self._assisted_verification_code = ""
        self._assisted_logged_events: set[str] = set()

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

    def _camoufox_locale_config(self) -> str:
        return resolve_chatgpt_locale(self.extra_config, allow_auto=True)

    @staticmethod
    def _camoufox_geoip_available() -> bool:
        try:
            import geoip2  # noqa: F401
        except Exception:
            return False
        return True

    def _manual_signup_url(self) -> str:
        return resolve_chatgpt_signup_entry_url(self.extra_config)

    def _manual_token_callback_enabled(self) -> bool:
        return self._bool_config("chatgpt_manual_enable_token_callback", False)

    def _assisted_signup_enabled(self) -> bool:
        return self._bool_config("chatgpt_assisted_signup", False)

    def _registration_mode_name(self) -> str:
        if self._assisted_signup_enabled():
            return "camoufox_assisted_signup"
        return "browser_manual_handoff"

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

    def _manual_profile_dir(self, name: str) -> tuple[str, bool]:
        configured = str(self.extra_config.get("chatgpt_manual_browser_profile_dir") or "").strip()
        if configured:
            return configured, False
        root = Path(self._default_manual_profile_dir(name))
        profile_dir = root / f"run-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        return str(profile_dir), True

    def _manual_clipboard_enabled(self) -> bool:
        return self._bool_config("chatgpt_manual_clipboard_sequence", True)

    def _set_system_clipboard(self, value: str) -> bool:
        if not value:
            return False
        try:
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=value, text=True, check=True, timeout=3)
                return True
            if os.name == "nt":
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                    input=value,
                    text=True,
                    check=True,
                    timeout=3,
                )
                return True
            wl_copy = shutil.which("wl-copy")
            if wl_copy:
                subprocess.run([wl_copy], input=value, text=True, check=True, timeout=3)
                return True
            xclip = shutil.which("xclip")
            if xclip:
                subprocess.run(
                    [xclip, "-selection", "clipboard"],
                    input=value,
                    text=True,
                    check=True,
                    timeout=3,
                )
                return True
            xsel = shutil.which("xsel")
            if xsel:
                subprocess.run(
                    [xsel, "--clipboard", "--input"],
                    input=value,
                    text=True,
                    check=True,
                    timeout=3,
                )
                return True
        except Exception:
            return False
        return False

    def _prepare_manual_clipboard(self, email: str, password: str) -> None:
        if not self._manual_clipboard_enabled():
            return
        with self._clipboard_lock:
            self._clipboard_sequence = [("邮箱", email), ("密码", password)]
            self._clipboard_index = 0
            self._last_clipboard_value = ""
            self._saw_manual_credential_paste = False
        self._copy_next_clipboard_item()

    def _append_manual_clipboard_items(self, items: list[tuple[str, str]]) -> None:
        if not self._manual_clipboard_enabled():
            return
        clean_items = [(label, str(value or "").strip()) for label, value in items if str(value or "").strip()]
        if not clean_items:
            return
        should_copy_now = False
        with self._clipboard_lock:
            existing_values = {value for _, value in self._clipboard_sequence}
            for label, value in clean_items:
                if value not in existing_values:
                    self._clipboard_sequence.append((label, value))
                    existing_values.add(value)
            should_copy_now = self._clipboard_index >= len(self._clipboard_sequence) - len(clean_items)
        if should_copy_now:
            self._copy_next_clipboard_item()

    def _manual_signup_user_info(self) -> dict[str, str]:
        if self._manual_user_info:
            return dict(self._manual_user_info)
        first_name, last_name = generate_random_name()
        full_name = f"{first_name} {last_name}".strip()
        age = random.randint(MIN_REGISTRATION_AGE, MAX_REGISTRATION_AGE)
        self._manual_user_info = {
            "name": full_name,
            "age": str(age),
        }
        return dict(self._manual_user_info)

    def _copy_next_clipboard_item(self) -> None:
        with self._clipboard_lock:
            if self._clipboard_index >= len(self._clipboard_sequence):
                return
            label, value = self._clipboard_sequence[self._clipboard_index]
            next_index = self._clipboard_index + 1
        if not self._set_system_clipboard(value):
            self._log(f"{label} 未能自动写入系统剪贴板，请从任务日志手动复制。", "warning")
            return
        with self._clipboard_lock:
            self._clipboard_index = next_index
            self._last_clipboard_value = value
        if label == "邮箱":
            self._log("邮箱已复制到系统剪贴板；在浏览器中粘贴邮箱后，将自动把密码放入剪贴板。")
        elif label == "密码":
            self._log("密码已复制到系统剪贴板；请继续在浏览器中粘贴密码。")
        elif label == "验证码":
            self._log("验证码已复制到系统剪贴板；粘贴验证码后，将自动把姓名放入剪贴板。")
        elif label == "姓名":
            self._log("随机姓名已复制到系统剪贴板；粘贴姓名后，将自动把年龄放入剪贴板。")
        elif label == "年龄":
            self._log("随机合法年龄已复制到系统剪贴板。")
        else:
            self._log(f"{label} 已复制到系统剪贴板。")

    def _handle_page_paste(self, pasted_text: str = "") -> None:
        pasted = str(pasted_text or "").strip()
        with self._clipboard_lock:
            expected = self._last_clipboard_value.strip()
            has_next = self._clipboard_index < len(self._clipboard_sequence)
        if expected and pasted and pasted != expected:
            return
        if expected:
            self._saw_manual_credential_paste = True
        if has_next:
            self._copy_next_clipboard_item()

    @staticmethod
    def _page_has_input_value(page, value: str) -> bool:
        target = str(value or "").strip()
        if not target:
            return False
        script = """
(target) => {
  const collect = (root, acc = []) => {
    if (!root) return acc;
    const nodes = root.querySelectorAll ? root.querySelectorAll('input, textarea, [contenteditable="true"]') : [];
    nodes.forEach(node => {
      acc.push(node);
      if (node.shadowRoot) collect(node.shadowRoot, acc);
    });
    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
    all.forEach(node => {
      if (node.shadowRoot) collect(node.shadowRoot, acc);
    });
    return acc;
  };
  const values = collect(document).map(node => {
    const value = 'value' in node ? node.value : '';
    const text = node.textContent || '';
    return String(value || text || '').trim();
  }).filter(Boolean);
  if (values.some(value => value.includes(target))) return true;
  const targetParts = target.split(/\\s+/).filter(Boolean);
  if (targetParts.length <= 1) return false;
  const joined = values.join(' ');
  return targetParts.every(part => joined.includes(part));
}
"""
        try:
            return bool(page.evaluate(script, target))
        except Exception:
            return False

    @staticmethod
    def _browser_session_disconnected(session: ManualBrowserSession) -> bool:
        browser = getattr(session, "browser", None)
        if browser is None:
            return False
        is_connected = getattr(browser, "is_connected", None)
        if not callable(is_connected):
            return False
        try:
            return not bool(is_connected())
        except Exception:
            return True

    def _iter_session_pages(self, session: ManualBrowserSession) -> list[object]:
        if self._browser_session_disconnected(session):
            return []
        pages = []
        seen = set()

        def add_page(page):
            if page is None:
                return
            ident = id(page)
            if ident in seen:
                return
            seen.add(ident)
            pages.append(page)

        try:
            if session.browser is not None:
                for context in session.browser.contexts:
                    for page in context.pages:
                        add_page(page)
        except Exception:
            pass
        try:
            if session.context is not None:
                for page in session.context.pages:
                    add_page(page)
        except Exception:
            pass
        add_page(getattr(session, "page", None))
        return pages

    def _session_has_input_value(self, session: ManualBrowserSession, value: str) -> bool:
        try:
            if session.browser is not None:
                for context in session.browser.contexts:
                    for page in context.pages:
                        if self._page_has_input_value(page, value):
                            return True
                return False
        except Exception:
            pass
        try:
            if session.context is not None:
                for page in session.context.pages:
                    if self._page_has_input_value(page, value):
                        return True
        except Exception:
            pass
        try:
            return self._page_has_input_value(session.page, value)
        except Exception:
            return False

    def _advance_clipboard_from_visible_inputs(self, session: ManualBrowserSession) -> None:
        if not self._manual_clipboard_enabled():
            return
        with self._clipboard_lock:
            expected = self._last_clipboard_value.strip()
            has_next = self._clipboard_index < len(self._clipboard_sequence)
        if not expected or not has_next:
            return
        if self._session_has_input_value(session, expected):
            self._handle_page_paste(expected)

    def _install_clipboard_paste_watcher(self, session: ManualBrowserSession) -> None:
        if not self._manual_clipboard_enabled():
            return

        def on_paste(text=""):
            self._handle_page_paste(str(text or ""))

        script = """
(() => {
  const readElementValue = element => {
    if (!element) return '';
    const value = 'value' in element ? element.value : '';
    const text = element.textContent || '';
    return String(value || text || '').trim();
  };
  const report = text => {
    if (!text) return;
    if (window.__autoregClipboardPasted) {
      Promise.resolve(window.__autoregClipboardPasted(text)).catch(() => {});
    }
  };
  const reportActiveElement = () => {
    const active = document.activeElement;
    report(readElementValue(active));
  };
  const install = () => {
    if (window.__autoregClipboardWatcherInstalled) return;
    window.__autoregClipboardWatcherInstalled = true;
    document.addEventListener('paste', event => {
      const text = event.clipboardData ? event.clipboardData.getData('text') : '';
      report(text);
      window.setTimeout(reportActiveElement, 0);
      window.setTimeout(reportActiveElement, 80);
    }, true);
    ['input', 'change', 'keyup'].forEach(type => {
      document.addEventListener(type, event => {
        report(readElementValue(event.target));
      }, true);
    });
  };
  install();
})();
"""
        try:
            if session.context is not None:
                session.context.expose_function("__autoregClipboardPasted", on_paste)
        except Exception:
            pass
        try:
            if session.context is not None:
                session.context.add_init_script(script)
        except Exception:
            pass
        for page in self._iter_session_pages(session):
            try:
                page.expose_function("__autoregClipboardPasted", on_paste)
            except Exception:
                pass
            try:
                page.add_init_script(script)
            except Exception:
                pass
            try:
                page.evaluate(script)
            except Exception:
                pass

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

        profile_dir, cleanup_profile = self._manual_profile_dir("chatgpt")
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
            profile_dir=profile_dir,
            cleanup_profile_on_close=cleanup_profile,
        )

    def _open_camoufox_session(self) -> ManualBrowserSession:
        from camoufox.sync_api import Camoufox

        profile_dir, cleanup_profile = self._manual_profile_dir("chatgpt_camoufox")
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        launch_kwargs = self._build_camoufox_launch_kwargs(profile_dir)
        self._log("启动本地 Camoufox 隔离浏览器（本次任务使用全新 profile）...")
        camoufox = Camoufox(**launch_kwargs)
        context = camoufox.__enter__()
        page = context.new_page()
        return ManualBrowserSession(
            provider="camoufox",
            page=page,
            context=context,
            playwright=camoufox,
            keep_open=self._bool_config("chatgpt_manual_browser_keep_open", False),
            profile_dir=profile_dir,
            cleanup_profile_on_close=cleanup_profile,
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

        locale = self._camoufox_locale_config()
        if locale:
            launch_kwargs["locale"] = locale

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
        if self._browser_session_disconnected(session):
            return []
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

    @staticmethod
    def _looks_like_signup_flow(states: list[ManualPageState]) -> bool:
        url_markers = (
            "/auth",
            "auth.openai.com",
            "auth0.openai.com",
            "login.openai.com",
        )
        text_markers = (
            "log in",
            "sign up",
            "sign in",
            "create account",
            "continue with email",
            "verify your email",
            "enter code",
            "verification code",
            "password",
            "登录",
            "注册",
            "创建账号",
            "验证码",
            "密码",
        )
        for state in states:
            lowered_url = (state.url or "").lower()
            if any(marker in lowered_url for marker in url_markers):
                return True
            text = " ".join((state.title, state.body_text)).lower()
            if any(marker in text for marker in text_markers):
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
        user_info = self._manual_signup_user_info()
        self._log(
            f"人工接管资料: 姓名={user_info['name']}, 年龄={user_info['age']}"
        )
        self._append_manual_clipboard_items(
            [
                ("验证码", code_text),
                ("姓名", user_info["name"]),
                ("年龄", user_info["age"]),
            ]
        )

    def _poll_email_code_for_assisted_signup(self) -> str:
        if self._assisted_verification_code:
            return self._assisted_verification_code
        if not hasattr(self.email_service, "get_verification_code"):
            return ""
        self._checkpoint()
        poll_interval = self._int_config("chatgpt_manual_email_poll_interval_seconds", 10)
        now = time.time()
        if now - self._last_otp_poll < poll_interval:
            return ""
        self._last_otp_poll = now
        try:
            code = self.email_service.get_verification_code(
                email=self.email,
                email_id=(self.email_info or {}).get("service_id"),
                timeout=self._int_config("chatgpt_manual_email_poll_timeout_seconds", 3),
                exclude_codes=self._used_verification_codes,
            )
        except Exception:
            return ""
        if not code:
            return ""
        code_text = str(code).strip()
        if not code_text or code_text in self._used_verification_codes:
            return ""
        self._used_verification_codes.add(code_text)
        self._assisted_verification_code = code_text
        self._log(f"自动辅助验证码: {code_text}（将尝试自动填入；也已保留人工接管兜底）")
        user_info = self._manual_signup_user_info()
        self._log(
            f"自动辅助资料: 姓名={user_info['name']}, 年龄={user_info['age']}"
        )
        self._append_manual_clipboard_items(
            [
                ("验证码", code_text),
                ("姓名", user_info["name"]),
                ("年龄", user_info["age"]),
            ]
        )
        return code_text

    def _log_assisted_event_once(self, key: str, message: str, level: str = "info") -> None:
        if key in self._assisted_logged_events:
            return
        self._assisted_logged_events.add(key)
        self._log(message, level)

    def _log_assisted_actions(self, result: dict) -> None:
        actions = set(result.get("actions") or [])
        action_messages = {
            "filled_email": "自动辅助已填写邮箱。",
            "filled_password": "自动辅助已填写密码。",
            "filled_code": "自动辅助已填写邮箱验证码。",
            "filled_name": "自动辅助已填写姓名。",
            "filled_age": "自动辅助已填写年龄。",
            "clicked_signup_entry": "自动辅助已点击普通 ChatGPT 页面的注册入口。",
            "clicked_continue": "自动辅助已点击继续/下一步。",
        }
        for action, message in action_messages.items():
            if action in actions:
                self._log_assisted_event_once(action, message)
        if result.get("checkboxBlocked"):
            self._log_assisted_event_once(
                "checkbox_blocked",
                "检测到注册资料页需要人工勾选确认；已停止自动点击下一步，请你手动勾选并继续。",
                "warning",
            )
        if result.get("challengeDetected"):
            self._log_assisted_event_once(
                "challenge_detected",
                "检测到 CAPTCHA 或人工验证挑战；自动辅助不会处理该步骤，请你在浏览器中手动完成。",
                "warning",
            )

    def _assist_signup_pages(self, session: ManualBrowserSession) -> bool:
        user_info = self._manual_signup_user_info()
        payload = {
            "email": self.email or "",
            "password": self.password or "",
            "code": self._poll_email_code_for_assisted_signup(),
            "name": user_info.get("name") or "",
            "age": user_info.get("age") or "",
        }
        changed = False
        for page in self._iter_session_pages(session):
            try:
                result = self._assist_signup_page(page, payload)
            except Exception:
                continue
            if not isinstance(result, dict):
                continue
            self._log_assisted_actions(result)
            if result.get("actions"):
                changed = True
        return changed

    def _assist_signup_page(self, page, payload: dict) -> dict:
        script = """
(payload) => {
  const result = { actions: [], checkboxBlocked: false, challengeDetected: false };
  const lower = value => String(value || '').toLowerCase();
  const roots = [];
  const visitRoot = root => {
    if (!root || roots.includes(root)) return;
    roots.push(root);
    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
    all.forEach(node => {
      if (node.shadowRoot) visitRoot(node.shadowRoot);
    });
  };
  visitRoot(document);
  const collect = selector => {
    const nodes = [];
    roots.forEach(root => {
      try {
        root.querySelectorAll(selector).forEach(node => nodes.push(node));
      } catch (_err) {}
    });
    return nodes;
  };
  const visible = element => {
    if (!element || element.disabled || element.getAttribute('aria-disabled') === 'true') return false;
    const style = window.getComputedStyle(element);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const attrText = element => {
    if (!element) return '';
    const parts = [
      element.getAttribute('aria-label'),
      element.getAttribute('placeholder'),
      element.getAttribute('name'),
      element.getAttribute('id'),
      element.getAttribute('autocomplete'),
      element.getAttribute('inputmode'),
      element.getAttribute('type'),
    ];
    const id = element.getAttribute('id');
    if (id) {
      collect(`label[for="${CSS.escape(id)}"]`).forEach(label => parts.push(label.innerText));
    }
    const label = element.closest ? element.closest('label') : null;
    if (label) parts.push(label.innerText);
    const parent = element.parentElement;
    if (parent) parts.push(String(parent.innerText || '').slice(0, 160));
    return lower(parts.filter(Boolean).join(' '));
  };
  const controls = collect('input, textarea, [contenteditable="true"]').filter(visible);
  const setValue = (element, value) => {
    if (!element || !value) return false;
    const current = 'value' in element ? String(element.value || '') : String(element.textContent || '');
    if (current.trim() === String(value).trim()) return false;
    element.focus();
    if ('value' in element) {
      const proto = Object.getPrototypeOf(element);
      const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
      if (descriptor && descriptor.set) {
        descriptor.set.call(element, value);
      } else {
        element.value = value;
      }
    } else {
      element.textContent = value;
    }
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const emptyEnough = element => {
    const value = 'value' in element ? element.value : element.textContent;
    return !String(value || '').trim();
  };
  const currentValue = element => {
    return String(('value' in element ? element.value : element.textContent) || '').trim();
  };
  const fillFirst = (action, value, predicate) => {
    if (!value) return false;
    const target = controls.find(element => emptyEnough(element) && predicate(element, attrText(element)));
    if (!target) return false;
    if (setValue(target, value)) {
      result.actions.push(action);
      return true;
    }
    return false;
  };
  const hasFilled = (value, predicate) => {
    if (!value) return false;
    return controls.some(element => {
      if (!predicate(element, attrText(element))) return false;
      return currentValue(element).includes(String(value).trim());
    });
  };
  const bodyText = lower(document.body ? document.body.innerText : '');
  if (/(captcha|hcaptcha|recaptcha|turnstile|are you human|verify you are human)/.test(bodyText)) {
    result.challengeDetected = true;
  }
  const hasCredentialField = controls.some(element => {
    const text = attrText(element);
    const type = lower(element.getAttribute('type'));
    return type === 'email' || type === 'password' || /(email|identifier|username|password|code|otp)/.test(text);
  });
  if (!hasCredentialField && !result.challengeDetected) {
    const entry = collect('a, button, [role="button"], input[type="button"], input[type="submit"]').find(element => {
      if (!visible(element)) return false;
      const text = lower([
        element.innerText,
        element.textContent,
        element.getAttribute('value'),
        element.getAttribute('aria-label'),
        element.getAttribute('title'),
        element.getAttribute('href'),
      ].filter(Boolean).join(' '));
      if (/(log in|login|sign in|se connecter|ouvrir une session|登录|登入)/.test(text)) return false;
      return /(sign up|signup|create account|get started|register|s'inscrire|s’inscrire|inscription|créer un compte|creer un compte|注册|创建账号)/.test(text);
    });
    if (entry) {
      entry.click();
      result.actions.push('clicked_signup_entry');
      return result;
    }
  }
  fillFirst('filled_email', payload.email, (element, text) => {
    const type = lower(element.getAttribute('type'));
    return type === 'email' || (/(email|identifier|username)/.test(text) && !/(password|code|otp)/.test(text));
  });
  fillFirst('filled_password', payload.password, element => lower(element.getAttribute('type')) === 'password');
  if (payload.code) {
    const codeChars = String(payload.code).split('');
    const oneCharFields = controls.filter(element => {
      const text = attrText(element);
      const maxLength = Number(element.getAttribute('maxlength') || element.maxLength || 0);
      const inputMode = lower(element.getAttribute('inputmode'));
      return emptyEnough(element)
        && (maxLength === 1 || inputMode === 'numeric')
        && !/(age|name|password|email)/.test(text);
    });
    if (oneCharFields.length >= codeChars.length) {
      oneCharFields.slice(0, codeChars.length).forEach((element, index) => setValue(element, codeChars[index]));
      result.actions.push('filled_code');
    } else {
      fillFirst('filled_code', payload.code, (element, text) => {
        const maxLength = Number(element.getAttribute('maxlength') || element.maxLength || 0);
        return /(code|otp|verification|one-time|one time)/.test(text) || maxLength >= 6;
      });
    }
  }
  const nameParts = String(payload.name || '').split(/\\s+/).filter(Boolean);
  const firstName = nameParts[0] || payload.name;
  const lastName = nameParts.slice(1).join(' ');
  const filledFirst = fillFirst('filled_name', firstName, (_element, text) => /(first name|given name)/.test(text));
  const filledLast = fillFirst('filled_name', lastName, (_element, text) => /(last name|family name|surname)/.test(text));
  if (!filledFirst && !filledLast) {
    fillFirst('filled_name', payload.name, (_element, text) => {
      return /(full name|your name|display name|name)/.test(text) && !/(username|email|password|domain)/.test(text);
    });
  }
  fillFirst('filled_age', payload.age, (element, text) => {
    const type = lower(element.getAttribute('type'));
    return (type === 'number' || /(age|your age)/.test(text)) && !/(birth|birthday|date|day|month|year|code|otp)/.test(text);
  });
  const codeAlreadyFilled = payload.code && controls.map(currentValue).join('').includes(String(payload.code));
  const nameAlreadyFilled = payload.name && String(payload.name).split(/\\s+/).filter(Boolean).every(part => {
    return controls.map(currentValue).join(' ').includes(part);
  });
  const ageAlreadyFilled = hasFilled(payload.age, (element, text) => {
    const type = lower(element.getAttribute('type'));
    return (type === 'number' || /(age|your age)/.test(text)) && !/(birth|birthday|date|day|month|year|code|otp)/.test(text);
  });
  const checkboxes = collect('input[type="checkbox"], [role="checkbox"]').filter(visible);
  const unchecked = checkboxes.some(element => {
    if (element.matches && element.matches('input[type="checkbox"]')) return !element.checked;
    return lower(element.getAttribute('aria-checked')) !== 'true';
  });
  if (unchecked && (
    result.actions.includes('filled_name') ||
    result.actions.includes('filled_age') ||
    nameAlreadyFilled ||
    ageAlreadyFilled
  )) {
    result.checkboxBlocked = true;
  }
  const readyToContinue =
    result.actions.length > 0 ||
    hasFilled(payload.email, (element, text) => {
      const type = lower(element.getAttribute('type'));
      return type === 'email' || (/(email|identifier|username)/.test(text) && !/(password|code|otp)/.test(text));
    }) ||
    hasFilled(payload.password, element => lower(element.getAttribute('type')) === 'password') ||
    codeAlreadyFilled ||
    nameAlreadyFilled ||
    ageAlreadyFilled;
  const canClick = readyToContinue && !result.checkboxBlocked && !result.challengeDetected;
  if (canClick) {
    const button = collect('button, [role="button"], input[type="submit"], input[type="button"]').find(element => {
      if (!visible(element)) return false;
      const text = lower([
        element.innerText,
        element.getAttribute('value'),
        element.getAttribute('aria-label'),
        element.getAttribute('name'),
      ].filter(Boolean).join(' '));
      return /(continue|next|submit|verify|sign up|create account|继续|下一步|提交|验证|注册)/.test(text);
    });
    if (button) {
      button.click();
      result.actions.push('clicked_continue');
    }
  }
  return result;
}
"""
        result = page.evaluate(script, payload)
        return result if isinstance(result, dict) else {}

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
        seen_signup_flow = False
        warned_existing_session = False
        while time.time() < deadline:
            self._checkpoint()
            states = self._collect_page_states(session)
            if not states:
                return False, "人工接管浏览器已关闭或不可访问，注册流程已停止。"
            if self._requires_phone(states):
                return False, "OpenAI 要求绑定手机号；人工接管模式已按策略停止。"
            if self._looks_like_signup_flow(states) or self._saw_manual_credential_paste:
                seen_signup_flow = True
            if self._looks_like_chatgpt_app(states):
                if seen_signup_flow:
                    return True, "检测到普通 ChatGPT 注册/登录已进入应用。已按 signup-only 策略停止，不自动进入 OAuth 取 token。"
                if not warned_existing_session:
                    self._log("检测到已有 ChatGPT 登录态，暂不判定为本次注册成功；请先退出旧账号后继续注册。", "warning")
                    warned_existing_session = True
            self._install_clipboard_paste_watcher(session)
            self._advance_clipboard_from_visible_inputs(session)
            self._poll_email_code_for_user()
            time.sleep(1)
        return False, "等待人工完成注册超时"

    def _wait_for_assisted_signup_completion(self, session: ManualBrowserSession) -> tuple[bool, str]:
        timeout = self._int_config("chatgpt_manual_handoff_timeout_seconds", 900)
        self._log(
            f"Camoufox 自动辅助注册启动，最多 {timeout}s；会自动填写邮箱、密码、验证码、姓名和年龄，遇到手机号会直接失败。"
        )
        deadline = time.time() + timeout
        seen_signup_flow = False
        warned_existing_session = False
        while time.time() < deadline:
            self._checkpoint()
            states = self._collect_page_states(session)
            if not states:
                return False, "自动辅助浏览器已关闭或不可访问，注册流程已停止。"
            if self._requires_phone(states):
                return False, "OpenAI 要求绑定手机号；自动辅助注册已按策略停止。"
            if self._looks_like_signup_flow(states) or self._saw_manual_credential_paste:
                seen_signup_flow = True
            if self._looks_like_chatgpt_app(states):
                if seen_signup_flow:
                    return True, "检测到普通 ChatGPT 注册/登录已进入应用。已按 signup-only 策略停止，不自动进入 OAuth 取 token。"
                if not warned_existing_session:
                    self._log("检测到已有 ChatGPT 登录态，暂不判定为本次注册成功；请先退出旧账号后继续注册。", "warning")
                    warned_existing_session = True
            self._install_clipboard_paste_watcher(session)
            self._advance_clipboard_from_visible_inputs(session)
            if self._assist_signup_pages(session):
                seen_signup_flow = True
            time.sleep(1)
        return False, "等待自动辅助注册完成超时"

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
            self._install_clipboard_paste_watcher(session)
            self._advance_clipboard_from_visible_inputs(session)
            time.sleep(1)
        return False, "等待 OAuth callback 超时"

    def acquire_token_for_existing_account(self, email: str, password: str) -> RegistrationResult:
        result = RegistrationResult(success=False, logs=self.logs, source="browser_manual_handoff_token")
        session = None
        try:
            self.email = str(email or "").strip()
            self.password = str(password or "")
            if not self.email:
                raise RuntimeError("账号邮箱为空，无法执行 OAuth 取 token")
            if not self.password:
                raise RuntimeError("账号密码为空，无法执行 OAuth 取 token")

            result.email = self.email
            result.password = self.password
            self._log("=" * 60)
            self._log("ChatGPT 已有账号 browser_manual_handoff OAuth 取 token 启动")
            self._log("=" * 60)
            self._log(f"OAuth 账号邮箱: {self.email}")
            self._prepare_manual_clipboard(self.email, self.password)

            session = self._open_browser_session()
            self._log(f"已打开隔离浏览器 provider={session.provider}")
            self._install_clipboard_paste_watcher(session)
            oauth_start = self.oauth_manager.start_oauth()
            self._log("打开 OAuth 授权入口，等待你手动登录并完成授权...")
            session.page.goto(oauth_start.auth_url, wait_until="domcontentloaded")

            ok, payload = self._wait_for_token_callback(session, oauth_start)
            if not ok:
                result.error_message = str(payload)
                self._log(result.error_message, "error")
                return result

            token_info = payload if isinstance(payload, dict) else {}
            result.success = True
            result.email = str(token_info.get("email") or self.email)
            result.password = self.password
            result.account_id = str(token_info.get("account_id") or "")
            result.access_token = str(token_info.get("access_token") or "")
            result.refresh_token = str(token_info.get("refresh_token") or "")
            result.id_token = str(token_info.get("id_token") or "")
            result.metadata = {
                "chatgpt_registration_mode": "browser_manual_handoff",
                "manual_handoff_stage": "token_callback",
                "chatgpt_manual_enable_token_callback": True,
            }
            self._log("已有账号 OAuth token 提取完成")
            return result
        except TaskInterruption:
            raise
        except Exception as e:
            result.error_message = str(e)
            self._log(f"已有账号 OAuth 取 token 失败: {e}", "error")
            return result
        finally:
            try:
                if session is not None:
                    session.close()
            except Exception:
                pass

    def run(self) -> RegistrationResult:
        mode_name = self._registration_mode_name()
        result = RegistrationResult(success=False, logs=self.logs, source=mode_name)
        session = None
        try:
            self._log("=" * 60)
            self._log(f"ChatGPT {mode_name} 注册流程启动")
            self._log("=" * 60)
            self._checkpoint()

            email = self._create_email()
            password = self.password or generate_random_password()
            self.password = password
            result.email = email
            result.password = password
            self._log(f"人工接管邮箱: {email}")
            self._log(f"人工接管密码: {password}")
            self._prepare_manual_clipboard(email, password)

            session = self._open_browser_session()
            self._log(f"已打开隔离浏览器 provider={session.provider}")
            self._install_clipboard_paste_watcher(session)
            signup_url = self._manual_signup_url()
            self._log(f"打开普通 ChatGPT 入口: {signup_url}")
            session.page.goto(signup_url, wait_until="domcontentloaded")

            if self._assisted_signup_enabled():
                ok, payload = self._wait_for_assisted_signup_completion(session)
            else:
                ok, payload = self._wait_for_manual_completion(session)
            if not ok:
                result.error_message = str(payload)
                self._log(result.error_message, "error")
                return result

            if self._manual_token_callback_enabled():
                self._log(
                    "注册任务已忽略第二段 OAuth/token 配置；请在账号管理页对已加入 Team 的账号执行“手动取Token”。"
                )

            result.success = True
            result.email = email
            result.password = password
            result.metadata = {
                "chatgpt_registration_mode": mode_name,
                "manual_handoff_stage": "signup_only",
                "chatgpt_manual_enable_token_callback": False,
                "registration_stage": "signup_only",
                "token_acquired": False,
            }
            self._log(str(payload))
            self._log(f"{mode_name} 普通注册完成，仅保存邮箱和密码")
            return result
        except TaskInterruption:
            raise
        except Exception as e:
            result.error_message = str(e)
            self._log(f"{mode_name} 失败: {e}", "error")
            return result
        finally:
            try:
                if session is not None:
                    session.close()
            except Exception:
                pass
