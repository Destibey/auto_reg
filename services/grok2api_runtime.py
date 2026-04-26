from __future__ import annotations

from typing import Tuple

import requests

ADMIN_VERIFY_PATHS = ("/admin/api/verify", "/v1/admin/verify")


def _get_config(key: str, default: str = "") -> str:
    try:
        from core.config_store import config_store

        value = str(config_store.get(key, "") or "").strip()
        return value or default
    except Exception:
        return default


def verify_grok2api(api_url: str | None = None, app_key: str | None = None) -> Tuple[bool, str]:
    api_url = str(api_url or _get_config("grok2api_url", "")).strip()
    app_key = str(app_key or _get_config("grok2api_app_key", "")).strip()

    if not api_url:
        return False, "grok2api URL 未配置"
    if not app_key:
        return False, "grok2api App Key 未配置"

    try:
        last_resp = None
        for path in ADMIN_VERIFY_PATHS:
            resp = requests.get(
                f"{api_url.rstrip('/')}{path}",
                headers={"Authorization": f"Bearer {app_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return True, "grok2api 鉴权正常"
            last_resp = resp
            if resp.status_code != 404:
                break
        if last_resp is None:
            return False, "grok2api 鉴权失败: 未收到响应"
        return False, f"grok2api 鉴权失败: HTTP {last_resp.status_code} - {last_resp.text[:200]}"
    except Exception as e:
        return False, f"grok2api 连接失败: {e}"


def ensure_grok2api_ready() -> Tuple[bool, str]:
    api_url = _get_config("grok2api_url", "http://127.0.0.1:8011")
    app_key = _get_config("grok2api_app_key", "grok2api")

    ok, msg = verify_grok2api(api_url=api_url, app_key=app_key)
    if ok:
        return True, msg

    return (
        False,
        (
            f"{msg}; grok2api 推荐通过 Docker 运行。"
            "请在 AutoReg 仓库根目录执行 "
            "`docker compose -f docker-compose.integrations.yml up -d grok2api`，"
            f"并确认 grok2api_url 指向 {api_url}。"
        ),
    )
