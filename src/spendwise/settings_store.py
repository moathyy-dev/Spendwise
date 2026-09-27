"""
Local, non-secret settings overrides (confidence thresholds, online AI/FX
toggles, base currency) editable from the in-app settings screen without
touching .env. Stored as a small local JSON file — never contains API keys.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_OVERRIDE_PATH = Path(__file__).resolve().parents[2] / "data" / "app_settings.json"

_ALLOWED_KEYS = {
    "confidence_auto_accept",
    "confidence_ai_fallback",
    "enable_online_ai",
    "enable_online_fx",
    "base_currency",
}

# Keys that are app-level flags, not Settings fields (kept in the same file
# for simplicity, but excluded from Settings overrides).
_APP_FLAG_KEYS = {"ai_consent_given", "intro_seen"}


def get_flag(key: str, default=False):
    if key not in _APP_FLAG_KEYS:
        raise ValueError(f"غير مسموح بقراءة هذا المفتاح: {key}")
    return _load_raw().get(key, default)


def set_flag(key: str, value) -> None:
    if key not in _APP_FLAG_KEYS:
        raise ValueError(f"غير مسموح بكتابة هذا المفتاح: {key}")
    data = _load_raw()
    data[key] = value
    _save_raw(data)


def _load_raw() -> dict:
    if not _OVERRIDE_PATH.exists():
        return {}
    try:
        with open(_OVERRIDE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(data: dict) -> None:
    _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_overrides() -> dict:
    data = _load_raw()
    return {k: v for k, v in data.items() if k in _ALLOWED_KEYS}


def save_overrides(overrides: dict) -> None:
    current = _load_raw()
    current.update({k: v for k, v in overrides.items() if k in _ALLOWED_KEYS})
    _save_raw(current)
