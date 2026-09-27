"""
Provider-agnostic AI abstraction. Any concrete provider (Gemini, a future
Ollama/local-LLM provider, etc.) implements this same interface so the rest
of the app never depends on a specific vendor.

Only sanitized, non-sensitive fields ever cross this boundary — no raw
description text, no account numbers, no personal identifiers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AITransactionInput:
    row_index: int
    merchant_sanitized: str
    amount: str
    direction: str  # "debit" | "credit"


@dataclass
class AIClassificationOutput:
    row_index: int
    category_id: int | None
    confidence: int
    explanation_ar: str


class AIProviderError(Exception):
    """Raised when the AI provider cannot produce a usable result (timeout,
    network error, malformed response after retries, etc.). Callers must
    treat this as non-fatal and continue with local-rules-only results."""


class AIProvider(ABC):
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything it needs (e.g. an API key)."""

    @abstractmethod
    def classify_batch(
        self, transactions: list[AITransactionInput], categories: list[dict]
    ) -> list[AIClassificationOutput]:
        """`categories` is a list of {"id": int, "name": str} choices.
        Must never raise for individual malformed items — only raises
        AIProviderError if the whole batch could not be processed."""
