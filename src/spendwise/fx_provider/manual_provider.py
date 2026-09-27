from __future__ import annotations

from decimal import Decimal

from spendwise.fx_provider.base import FxProvider, FxRateResult


class ManualFxProvider(FxProvider):
    def get_rate(self, currency: str, base_currency: str, manual_rate: Decimal | None = None) -> FxRateResult:
        if currency.upper() == base_currency.upper():
            return FxRateResult(rate=Decimal("1"), source="manual")
        if manual_rate is None:
            raise ValueError("يجب إدخال سعر تحويل يدوي لهذه العملة.")
        return FxRateResult(rate=manual_rate, source="manual")
