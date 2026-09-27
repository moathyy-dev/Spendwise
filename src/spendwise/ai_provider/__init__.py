"""
Factory for building the configured AI provider. Always returns a working
provider object — NullAIProvider whenever AI is disabled, unconfigured, or
the requested provider isn't recognized — so the rest of the app never has
to special-case "no AI available".
"""
from __future__ import annotations

from spendwise.ai_provider.base import AIProvider
from spendwise.ai_provider.null_provider import NullAIProvider


def build_ai_provider(settings) -> AIProvider:
    if not settings.enable_online_ai:
        return NullAIProvider()

    if settings.ai_provider == "gemini":
        from spendwise.ai_provider.gemini_provider import GeminiProvider

        provider = GeminiProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
        )
        if provider.is_configured():
            return provider
        print("[spendwise] Gemini provider not configured (missing API key) — falling back to local rules only.")
        return NullAIProvider()

    return NullAIProvider()
