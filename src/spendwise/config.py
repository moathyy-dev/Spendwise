"""
Central configuration for SpendWise.

All configuration is read from environment variables (see .env.example).
No secrets are hardcoded here. Nothing in this module ever logs or persists
API keys.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (local development). In production/packaged use,
# real environment variables should be set by the OS/shell.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


# Standard locations Streamlit looks for secrets.toml. We check these
# ourselves BEFORE touching st.secrets, because Streamlit renders a visible
# error banner on the page itself (not just a raisable Python exception)
# the moment st.secrets is accessed with no secrets.toml present anywhere —
# which is the normal case for local desktop use, so it must stay silent.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SECRETS_PATHS = (
    _PROJECT_ROOT / ".streamlit" / "secrets.toml",
    Path.home() / ".streamlit" / "secrets.toml",
)


def _get_raw(name: str, default: str | None = None) -> str | None:
    """Reads a config value from (in order): a real OS environment variable
    / .env, then Streamlit Cloud's secrets store (st.secrets) when running
    under Streamlit AND a secrets.toml file actually exists — so the same
    config code works both for local development (.env file, no
    secrets.toml) and for a Streamlit Community Cloud deployment (secrets
    configured in the app dashboard), without any other module needing to
    know which one it's running under."""
    val = os.getenv(name)
    if val is not None:
        return val
    if not any(p.exists() for p in _SECRETS_PATHS):
        return default
    try:
        import streamlit as st  # noqa: PLC0415

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - streamlit not installed/available/secrets unreadable
        pass
    return default


def _get_bool(name: str, default: bool) -> bool:
    val = _get_raw(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    val = _get_raw(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # AI provider
    ai_provider: str = field(default_factory=lambda: _get_raw("SPENDWISE_AI_PROVIDER", "none"))
    gemini_api_key: str = field(default_factory=lambda: _get_raw("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: _get_raw("GEMINI_MODEL", "gemini-1.5-flash"))
    ai_timeout_seconds: int = field(default_factory=lambda: _get_int("AI_TIMEOUT_SECONDS", 20))
    ai_max_retries: int = field(default_factory=lambda: _get_int("AI_MAX_RETRIES", 2))
    enable_online_ai: bool = field(default_factory=lambda: _get_bool("ENABLE_ONLINE_AI", False))

    # Confidence thresholds (0-100)
    confidence_auto_accept: int = field(
        default_factory=lambda: _get_int("CONFIDENCE_THRESHOLD_AUTO_ACCEPT", 95)
    )
    confidence_ai_fallback: int = field(
        default_factory=lambda: _get_int("CONFIDENCE_THRESHOLD_AI_FALLBACK", 80)
    )

    # Currency
    base_currency: str = field(default_factory=lambda: _get_raw("BASE_CURRENCY", "SAR"))
    enable_online_fx: bool = field(default_factory=lambda: _get_bool("ENABLE_ONLINE_FX", False))

    # Database — local SQLite by default (DATABASE_PATH). When DATABASE_URL
    # is set (e.g. a Postgres connection string from a cloud host such as
    # Neon), it takes priority — this is what a Streamlit Community Cloud
    # deployment uses, since that platform has no durable local disk.
    database_path: str = field(default_factory=lambda: _get_raw("DATABASE_PATH", "./data/spendwise.db"))
    database_url_override: str = field(default_factory=lambda: _get_raw("DATABASE_URL", ""))

    # Simple app-level password gate, used only when SpendWise is deployed
    # somewhere reachable over a public URL (e.g. Streamlit Community
    # Cloud). Empty means no password gate (normal local desktop use).
    app_password: str = field(default_factory=lambda: _get_raw("SPENDWISE_APP_PASSWORD", ""))

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.resolve()}"


def get_settings() -> Settings:
    """Return a fresh Settings instance reflecting current environment
    variables, layered with any local non-secret overrides saved from the
    in-app settings screen (see settings_store.py)."""
    base = Settings()
    try:
        from spendwise.settings_store import load_overrides

        overrides = load_overrides()
    except ImportError:
        overrides = {}
    if not overrides:
        return base
    return replace(base, **overrides)
