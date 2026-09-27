"""
Provider-agnostic currency-conversion abstraction. Manual entry is always
available; an optional free online provider can be enabled by the user.
Either way, the app must keep working (falling back to manual rates) if
the online provider is unavailable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class FxRateResult:
    rate: Decimal
    source: str  # "manual" | "online"


class FxProviderError(Exception):
    """Raised when a rate could not be determined. Callers must fall back
    to asking the user for a manual rate rather than failing the import."""


class FxProvider(ABC):
    @abstractmethod
    def get_rate(self, currency: str, base_currency: str, manual_rate: Decimal | None = None) -> FxRateResult:
        ...
