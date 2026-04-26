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

    from services.external_apps import list_status, start, stop

    try:
        status = next((item for item in list_status() if item["name"] == "grok2api"), None)
        if status and not status.get("repo_exists"):
            return False, "grok2api 未安装，请先到“设置 → 插件”里手动安装"
        running = bool(status and status.get("running"))

        if running:
            stop("grok2api")
        start("grok2api")
    except Exception as e:
        return False, f"{msg}; 自动重启 grok2api 失败: {e}"

    return verify_grok2api(api_url=api_url, app_key=app_key)
