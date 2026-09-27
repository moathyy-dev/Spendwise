"""
Statistical outlier detection per category, using median + MAD (Median
Absolute Deviation) rather than mean/stddev — more robust to the skewed,
spiky nature of personal spending data. Only flags transactions that are
BOTH a strong statistical outlier AND meaningfully larger than the
category's typical spend, to avoid noisy false positives.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_MAD_CONSISTENCY_CONSTANT = Decimal("1.4826")
_DEVIATION_THRESHOLD = Decimal("3.5")
_MIN_MULTIPLE_OF_MEDIAN = Decimal("2")


@dataclass
class AnomalyFlag:
    row_id: int
    category_id: int
    amount: Decimal
    median_amount: Decimal
    reason_ar: str


def _median(values: list[Decimal]) -> Decimal:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]


def detect_anomalies(transactions: list, min_history: int = 5) -> list[AnomalyFlag]:
    """`transactions` items must expose .id, .category_id, .amount (only
    committed EXPENSE rows should be passed by the caller)."""
    by_category: dict[int, list] = {}
    for t in transactions:
        if t.category_id is None:
            continue
        by_category.setdefault(t.category_id, []).append(t)

    flags: list[AnomalyFlag] = []
    for category_id, txns in by_category.items():
        if len(txns) < min_history:
            continue
        amounts = [t.amount for t in txns]
        med = _median(amounts)
        deviations = [abs(a - med) for a in amounts]
        mad = _median(deviations)

        # When most amounts in a category are identical (or nearly so), MAD
        # collapses to 0 and a robust z-score can't be computed — this is a
        # known edge case of MAD-based detection, not a reason to skip the
        # category entirely. Fall back to flagging amounts that are a large
        # multiple of the median instead.
        for t, dev in zip(txns, deviations):
            if mad > 0:
                robust_z = (dev / mad) * _MAD_CONSISTENCY_CONSTANT
                is_outlier = robust_z > _DEVIATION_THRESHOLD
            else:
                is_outlier = med > 0 and t.amount > med * (_DEVIATION_THRESHOLD)

            if is_outlier and med > 0 and t.amount > med * _MIN_MULTIPLE_OF_MEDIAN:
                flags.append(
                    AnomalyFlag(
                        row_id=t.id,
                        category_id=category_id,
                        amount=t.amount,
                        median_amount=med,
                        reason_ar=f"المبلغ {t.amount} أعلى بكثير من المعتاد لهذا التصنيف (المتوسط المعتاد: {med}).",
                    )
                )
    return flags
