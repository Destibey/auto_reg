"""将 grok2api 注册为 CLIProxyAPI 的 OpenAI-compatible 上游。"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

PROVIDER_NAME = "grok2api"
DEFAULT_MODELS = [
    "grok-4.20-fast",
    "grok-4.20-auto",
    "grok-4.20-expert",
    "grok-4.20-heavy",
    "grok-4.3-beta",
]


def _get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store

        return str(config_store.get(key, "") or "").strip()
    except Exception:
        return ""


def _resolve_cpa_target(api_url: str | None = None, api_key: str | None = None) -> tuple[str, str]:
    resolved_url = (
        str(api_url or "").strip()
        or _get_config_value("cliproxyapi_base_url")
        or _get_config_value("cpa_api_url")
    )
    resolved_key = (
        str(api_key or "").strip()
        or _get_config_value("cliproxyapi_management_key")
        or _get_config_value("cpa_api_key")
    )
    return resolved_url.rstrip("/"), resolved_key


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def normalize_openai_base_url(api_url: str) -> str:
    """CPA 的 openai-compatibility base-url 需要指向 /v1。"""
    trimmed = str(api_url or "").strip().rstrip("/")
    if not trimmed:
        return ""

    parsed = urlsplit(trimmed)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1") or path == "/v1":
        return trimmed

    new_path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))


def _model_items(model_ids: list[str]) -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for model_id in model_ids:
        normalized = str(model_id or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({"name": normalized, "alias": normalized})
    return items


def _extract_models(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    raw_models = data.get("data")
    if not isinstance(raw_models, list):
        return []
    model_ids: list[str] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            model_ids.append(model_id)
    return model_ids


def list_grok2api_models(api_url: str, api_key: str | None = None) -> list[str]:
    base_url = normalize_openai_base_url(api_url)
    if not base_url:
        return []

    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.get(
        f"{base_url}/models",
        headers=headers,
        timeout=10,
        verify=False,
    )
    response.raise_for_status()
    return _extract_models(response.json())


def build_grok2api_openai_compat_entry(
    *,
    grok2api_url: str,
    grok2api_api_key: str = "",
    models: list[str] | None = None,
) -> dict[str, Any]:
    model_ids = models or DEFAULT_MODELS
    entry: dict[str, Any] = {
        "name": PROVIDER_NAME,
        "base-url": normalize_openai_base_url(grok2api_url),
        "models": _model_items(model_ids),
    }
    if grok2api_api_key:
        entry["api-key-entries"] = [{"api-key": grok2api_api_key}]
    else:
        entry["api-key-entries"] = []
    return entry


def _same_entry(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        str(left.get("name") or "").strip() == str(right.get("name") or "").strip()
        and str(left.get("base-url") or "").strip().rstrip("/") == str(right.get("base-url") or "").strip().rstrip("/")
        and left.get("api-key-entries", []) == right.get("api-key-entries", [])
        and left.get("models", []) == right.get("models", [])
    )


def ensure_grok2api_openai_compat_in_cpa(
    *,
    cpa_url: str | None = None,
    cpa_api_key: str | None = None,
    grok2api_url: str | None = None,
    grok2api_api_key: str | None = None,
    models: list[str] | None = None,
) -> tuple[bool, str]:
    resolved_cpa_url, resolved_cpa_key = _resolve_cpa_target(cpa_url, cpa_api_key)
    resolved_grok2api_url = str(
        grok2api_url
        or _get_config_value("grok2api_cpa_url")
        or _get_config_value("grok2api_url")
        or ""
    ).strip()
    resolved_grok2api_key = str(grok2api_api_key or _get_config_value("grok2api_api_key") or "").strip()

    if not resolved_cpa_url:
        return False, "CLIProxyAPI URL 未配置"
    if not resolved_cpa_key:
        return False, "CLIProxyAPI 管理口令未配置"
    if not resolved_grok2api_url:
        return False, "grok2api URL 未配置"

    model_ids = models
    if model_ids is None:
        try:
            model_ids = list_grok2api_models(resolved_grok2api_url, resolved_grok2api_key)
        except Exception as exc:
            logger.warning("读取 grok2api 模型列表失败，使用默认模型: %s", exc)
            model_ids = DEFAULT_MODELS

    desired = build_grok2api_openai_compat_entry(
        grok2api_url=resolved_grok2api_url,
        grok2api_api_key=resolved_grok2api_key,
        models=model_ids or DEFAULT_MODELS,
    )

    try:
        response = requests.get(
            f"{resolved_cpa_url}/v0/management/openai-compatibility",
            headers=_headers(resolved_cpa_key),
            timeout=15,
            verify=False,
        )
        response.raise_for_status()
        data = response.json()
        entries = data.get("openai-compatibility", []) if isinstance(data, dict) else []
        if not isinstance(entries, list):
            entries = []

        updated_entries: list[dict[str, Any]] = []
        replaced = False
        changed = False
        for item in entries:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "").strip() == PROVIDER_NAME:
                replaced = True
                if _same_entry(item, desired):
                    updated_entries.append(item)
                else:
                    updated_entries.append(desired)
                    changed = True
            else:
                updated_entries.append(item)

        if not replaced:
            updated_entries.append(desired)
            changed = True

        if not changed:
            return True, "CPA grok2api 上游已存在"

        put_response = requests.put(
            f"{resolved_cpa_url}/v0/management/openai-compatibility",
            headers=_headers(resolved_cpa_key),
            json=updated_entries,
            timeout=15,
            verify=False,
        )
        put_response.raise_for_status()
        return True, "CPA 已接入 grok2api 上游"
    except Exception as exc:
        logger.error("CPA 接入 grok2api 上游失败: %s", exc)
        return False, f"CPA 接入 grok2api 上游失败: {exc}"
