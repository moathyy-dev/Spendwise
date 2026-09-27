"""
Flags likely recurring/subscription payments: repeated expenses to the same
merchant with a similar amount roughly every month. Informational only —
never automatically changes categorization or budget.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

_AMOUNT_TOLERANCE_PCT = Decimal("0.05")
_MIN_INTERVAL_DAYS = 20
_MAX_INTERVAL_DAYS = 40


@dataclass
class RecurringGroup:
    merchant_sanitized: str
    occurrences: int
    average_amount: Decimal
    row_indices: list[int] = field(default_factory=list)


def detect_recurring(transactions: list, min_occurrences: int = 2) -> list[RecurringGroup]:
    """`transactions` items must expose .merchant_sanitized, .amount,
    .txn_date, .transaction_type (only committed EXPENSE rows should be
    passed in by the caller)."""
    by_merchant: dict[str, list] = {}
    for t in transactions:
        if not t.merchant_sanitized:
            continue
        by_merchant.setdefault(t.merchant_sanitized, []).append(t)

    groups: list[RecurringGroup] = []
    for merchant, txns in by_merchant.items():
        if len(txns) < min_occurrences:
            continue
        txns_sorted = sorted(txns, key=lambda t: t.txn_date)
        amounts = [t.amount for t in txns_sorted]
        avg = sum(amounts) / len(amounts)
        if avg == 0:
            continue
        within_tolerance = all(abs(a - avg) <= avg * _AMOUNT_TOLERANCE_PCT for a in amounts)
        if not within_tolerance:
            continue

        intervals = [
            (txns_sorted[i].txn_date - txns_sorted[i - 1].txn_date).days for i in range(1, len(txns_sorted))
        ]
        if not intervals:
            continue
        roughly_monthly = all(_MIN_INTERVAL_DAYS <= d <= _MAX_INTERVAL_DAYS for d in intervals)
        if not roughly_monthly:
            continue

        groups.append(
            RecurringGroup(
                merchant_sanitized=merchant,
                occurrences=len(txns_sorted),
                average_amount=avg,
                row_indices=[getattr(t, "id", None) or getattr(t, "row_index", None) for t in txns_sorted],
            )
        )
    return groups
