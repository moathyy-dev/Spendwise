"""
Precise decimal money handling. Never use binary floats for persisted
financial values.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def to_money(value) -> Decimal:
    """Coerce any numeric-ish input into a Decimal rounded to 2 places."""
    if value is None:
        raise ValueError("Cannot convert None to money")
    if isinstance(value, Decimal):
        d = value
    else:
        # Route through str() to avoid binary float artefacts (e.g. 0.1 + 0.2)
        d = Decimal(str(value))
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def convert(amount: Decimal, rate: Decimal) -> Decimal:
    """Convert an amount using an exchange rate, both as Decimal."""
    amount = to_money(amount)
    rate = Decimal(str(rate))
    return (amount * rate).quantize(CENTS, rounding=ROUND_HALF_UP)
