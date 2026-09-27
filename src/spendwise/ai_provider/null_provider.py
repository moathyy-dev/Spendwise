"""
No-op AI provider used when online AI is disabled or unconfigured. Ensures
the import pipeline never fails just because AI is off — rows simply stay
with local-rules results and are flagged for manual review as needed.
"""
from __future__ import annotations

from spendwise.ai_provider.base import AIClassificationOutput, AIProvider, AITransactionInput


class NullAIProvider(AIProvider):
    def is_configured(self) -> bool:
        return True

    def classify_batch(
        self, transactions: list[AITransactionInput], categories: list[dict]
    ) -> list[AIClassificationOutput]:
        return []
