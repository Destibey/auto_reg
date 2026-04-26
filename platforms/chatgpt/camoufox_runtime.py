"""Shared Camoufox launch helpers for ChatGPT browser-backed flows."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from core.proxy_utils import build_playwright_proxy_config


def bool_config(extra_config: dict, key: str, default: bool = False) -> bool:
    value = (extra_config or {}).get(key)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def camoufox_humanize_config(extra_config: dict):
    value = (extra_config or {}).get("chatgpt_camoufox_humanize")
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


def camoufox_geoip_available() -> bool:
    try:
        import geoip2  # noqa: F401
    except Exception:
        return False
    return True


def build_camoufox_launch_kwargs(
    *,
    extra_config: Optional[dict] = None,
    proxy_url: Optional[str] = None,
    headless: bool = False,
    persistent_context: bool = False,
    profile_dir: Optional[str] = None,
    enable_cache: bool = True,
    log_fn: Optional[Callable[[str, str], None]] = None,
    geoip_available_fn: Optional[Callable[[], bool]] = None,
) -> dict:
    extra_config = dict(extra_config or {})
    launch_kwargs = {
        "headless": bool(headless),
        "enable_cache": bool(enable_cache),
    }

    if persistent_context:
        if not profile_dir:
            raise ValueError("profile_dir is required when persistent_context=True")
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        launch_kwargs.update(
            {
                "persistent_context": True,
                "user_data_dir": profile_dir,
            }
        )

    proxy_config = build_playwright_proxy_config(proxy_url)
    if proxy_config:
        launch_kwargs["proxy"] = proxy_config

    os_value = str(extra_config.get("chatgpt_camoufox_os") or "").strip().lower()
    if os_value in {"windows", "macos", "linux"}:
        launch_kwargs["os"] = os_value

    humanize = camoufox_humanize_config(extra_config)
    if humanize is not None:
        launch_kwargs["humanize"] = humanize

    if bool_config(extra_config, "chatgpt_camoufox_geoip", False):
        is_geoip_available = geoip_available_fn or camoufox_geoip_available
        if is_geoip_available():
            launch_kwargs["geoip"] = True
        elif log_fn:
            log_fn("Camoufox GeoIP 未启用：当前环境未安装 camoufox[geoip] 依赖", "warning")

    return launch_kwargs
