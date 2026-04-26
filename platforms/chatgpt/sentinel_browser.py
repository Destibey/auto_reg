"""Sentinel SDK token 获取辅助。"""

from __future__ import annotations

import json
from typing import Callable, Optional

from core.proxy_utils import build_playwright_proxy_config

from .camoufox_runtime import build_camoufox_launch_kwargs


def _flow_page_url(flow: str) -> str:
    flow_name = str(flow or "").strip().lower()
    mapping = {
        "authorize_continue": "https://auth.openai.com/create-account",
        "username_password_create": "https://auth.openai.com/create-account/password",
        "password_verify": "https://auth.openai.com/log-in/password",
        "email_otp_validate": "https://auth.openai.com/email-verification",
        "oauth_create_account": "https://auth.openai.com/about-you",
    }
    return mapping.get(flow_name, "https://auth.openai.com/about-you")


def get_sentinel_token_via_browser(
    *,
    flow: str,
    proxy: Optional[str] = None,
    timeout_ms: int = 45000,
    page_url: Optional[str] = None,
    headless: bool = True,
    device_id: Optional[str] = None,
    browser_provider: str = "playwright",
    browser_config: Optional[dict] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """通过浏览器直接调用 SentinelSDK.token(flow) 获取完整 token。"""
    logger = log_fn or (lambda _msg: None)
    target_url = str(page_url or _flow_page_url(flow)).strip() or _flow_page_url(flow)
    provider = str(browser_provider or "playwright").strip().lower()

    if provider in {"camoufox", "free", "free_fingerprint"}:
        return _get_sentinel_token_via_camoufox(
            flow=flow,
            proxy=proxy,
            timeout_ms=timeout_ms,
            target_url=target_url,
            headless=headless,
            device_id=device_id,
            browser_config=browser_config or {},
            logger=logger,
        )

    return _get_sentinel_token_via_playwright(
        flow=flow,
        proxy=proxy,
        timeout_ms=timeout_ms,
        target_url=target_url,
        headless=headless,
        device_id=device_id,
        logger=logger,
    )


def _add_device_cookie(context, device_id: Optional[str]) -> None:
    if not device_id:
        return
    try:
        context.add_cookies(
            [
                {
                    "name": "oai-did",
                    "value": str(device_id),
                    "url": "https://auth.openai.com/",
                    "path": "/",
                    "secure": True,
                    "sameSite": "Lax",
                }
            ]
        )
    except Exception:
        pass


def _get_token_from_page(page, *, flow: str, target_url: str, timeout_ms: int, logger) -> Optional[str]:
    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_function(
        "() => typeof window.SentinelSDK !== 'undefined' && typeof window.SentinelSDK.token === 'function'",
        timeout=min(timeout_ms, 15000),
    )

    result = page.evaluate(
        """
        async ({ flow }) => {
            try {
                const token = await window.SentinelSDK.token(flow);
                return { success: true, token };
            } catch (e) {
                return {
                    success: false,
                    error: (e && (e.message || String(e))) || "unknown",
                };
            }
        }
        """,
        {"flow": flow},
    )

    if not result or not result.get("success") or not result.get("token"):
        logger(
            "Sentinel Browser 获取失败: "
            + str((result or {}).get("error") or "no result")
        )
        return None

    token = str(result["token"] or "").strip()
    if not token:
        logger("Sentinel Browser 返回空 token")
        return None

    try:
        parsed = json.loads(token)
        logger(
            "Sentinel Browser 成功: "
            f"p={'✓' if parsed.get('p') else '✗'} "
            f"t={'✓' if parsed.get('t') else '✗'} "
            f"c={'✓' if parsed.get('c') else '✗'}"
        )
    except Exception:
        logger(f"Sentinel Browser 成功: len={len(token)}")

    return token


def _get_sentinel_token_via_camoufox(
    *,
    flow: str,
    proxy: Optional[str],
    timeout_ms: int,
    target_url: str,
    headless: bool,
    device_id: Optional[str],
    browser_config: dict,
    logger,
) -> Optional[str]:
    try:
        from camoufox.sync_api import Camoufox
    except Exception as e:
        logger(f"Sentinel Browser Camoufox 不可用: {e}")
        return None

    launch_args = build_camoufox_launch_kwargs(
        extra_config=browser_config,
        proxy_url=proxy,
        headless=bool(headless),
        persistent_context=False,
        enable_cache=True,
        log_fn=lambda msg, level="info": logger(msg),
    )
    logger(f"Sentinel Browser 启动: provider=camoufox, flow={flow}, url={target_url}, headless={headless}")
    logger(f"Sentinel Browser 启动参数: {launch_args}")

    try:
        with Camoufox(**launch_args) as browser:
            context = browser.new_context(ignore_https_errors=True)
            try:
                _add_device_cookie(context, device_id)
                page = context.new_page()
                return _get_token_from_page(
                    page,
                    flow=flow,
                    target_url=target_url,
                    timeout_ms=timeout_ms,
                    logger=logger,
                )
            finally:
                context.close()
    except Exception as e:
        logger(f"Sentinel Browser Camoufox 异常: {e}")
        return None


def _get_sentinel_token_via_playwright(
    *,
    flow: str,
    proxy: Optional[str],
    timeout_ms: int,
    target_url: str,
    headless: bool,
    device_id: Optional[str],
    logger,
) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger(f"Sentinel Browser Playwright 不可用: {e}")
        return None

    launch_args = {
        "headless": bool(headless),
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    proxy_config = build_playwright_proxy_config(proxy)
    if proxy_config:
        launch_args["proxy"] = proxy_config

    logger(f"Sentinel Browser 启动: provider=playwright, flow={flow}, url={target_url}, headless={headless}")
    logger(f"Sentinel Browser 启动参数: {launch_args}")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_args)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.7103.92 Safari/537.36"
                ),
                ignore_https_errors=True,
            )
            _add_device_cookie(context, device_id)

            page = context.new_page()
            return _get_token_from_page(
                page,
                flow=flow,
                target_url=target_url,
                timeout_ms=timeout_ms,
                logger=logger,
            )
        except Exception as e:
            logger(f"Sentinel Browser Playwright 异常: {e}")
            return None
        finally:
            browser.close()
