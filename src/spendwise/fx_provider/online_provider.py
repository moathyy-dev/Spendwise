"""
Optional free online FX rates via open.er-api.com (no API key required).
Disabled by default; the user must explicitly enable it in Settings. Any
failure raises FxProviderError so the caller falls back to a manual rate —
this must never block an import.
"""
from __future__ import annotations

from decimal import Decimal

import requests

from spendwise.fx_provider.base import FxProvider, FxProviderError, FxRateResult

_API_URL = "https://open.er-api.com/v6/latest/{base}"


class OnlineFxProvider(FxProvider):
    def __init__(self, timeout_seconds: int = 10):
        self._timeout_seconds = timeout_seconds

    def get_rate(self, currency: str, base_currency: str, manual_rate: Decimal | None = None) -> FxRateResult:
        currency = currency.upper()
        base_currency = base_currency.upper()
        if currency == base_currency:
            return FxRateResult(rate=Decimal("1"), source="online")
        try:
            response = requests.get(_API_URL.format(base=base_currency), timeout=self._timeout_seconds)
            response.raise_for_status()
            data = response.json()
            rates = data.get("rates", {})
            rate = rates.get(currency)
            if rate is None:
                raise FxProviderError(f"لا يوجد سعر صرف متاح لعملة {currency}.")
            return FxRateResult(rate=Decimal(str(rate)), source="online")
        except FxProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FxProviderError(f"تعذّر جلب سعر الصرف من الإنترنت: {exc}") from exc
