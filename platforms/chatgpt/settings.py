"""Shared ChatGPT registration settings."""

from __future__ import annotations

from typing import Optional

DEFAULT_CHATGPT_LOCALE = "en-US,en"
DEFAULT_CHATGPT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"
DEFAULT_CHATGPT_SIGNUP_ENTRY_URL = "https://chatgpt.com/"

_AUTO_LOCALE_VALUES = {"auto", "geoip", "default", "none", "off"}


def _first_non_empty(extra: Optional[dict], *keys: str) -> str:
    extra = extra or {}
    for key in keys:
        value = str(extra.get(key) or "").strip()
        if value:
            return value
    return ""


def resolve_chatgpt_locale(extra: Optional[dict], *, allow_auto: bool = False) -> str:
    """Resolve the shared ChatGPT locale, keeping legacy Camoufox config as fallback."""
    value = _first_non_empty(extra, "chatgpt_locale", "chatgpt_camoufox_locale")
    if not value:
        return DEFAULT_CHATGPT_LOCALE
    if value.lower() in _AUTO_LOCALE_VALUES:
        return "" if allow_auto else DEFAULT_CHATGPT_LOCALE
    return value


def chatgpt_accept_language_from_locale(locale: str) -> str:
    """Convert a locale list such as ``en-US,en`` into an Accept-Language header."""
    value = str(locale or "").strip()
    if not value or value.lower() in _AUTO_LOCALE_VALUES:
        return DEFAULT_CHATGPT_ACCEPT_LANGUAGE
    if "q=" in value:
        return value
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return DEFAULT_CHATGPT_ACCEPT_LANGUAGE
    if len(parts) == 1:
        return parts[0]
    weighted = [parts[0]]
    for index, part in enumerate(parts[1:], start=1):
        quality = max(0.1, 1.0 - (index * 0.1))
        weighted.append(f"{part};q={quality:.1f}")
    return ",".join(weighted)


def resolve_chatgpt_accept_language(extra: Optional[dict]) -> str:
    return chatgpt_accept_language_from_locale(resolve_chatgpt_locale(extra))


def resolve_chatgpt_signup_entry_url(extra: Optional[dict]) -> str:
    """Resolve the shared ChatGPT browser signup entry, with legacy fallback."""
    value = _first_non_empty(extra, "chatgpt_signup_entry_url", "chatgpt_manual_signup_url")
    return value or DEFAULT_CHATGPT_SIGNUP_ENTRY_URL
