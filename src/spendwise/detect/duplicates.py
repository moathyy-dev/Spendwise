"""
Transparent, explainable duplicate-transaction scoring. Never auto-deletes
anything — only flags candidate pairs with a score and reasons so the user
can decide (keep one / keep both / exclude).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

DUPLICATE_THRESHOLD = 80
DATE_WINDOW_DAYS = 3


@dataclass
class TxnFingerprintInput:
    row_index: int
    txn_date: dt.date
    amount: Decimal
    direction: str
    account_key: str
    merchant_sanitized: str


@dataclass
class DuplicateCandidate:
    row_index_a: int
    row_index_b: int
    score: int
    reasons_ar: list[str] = field(default_factory=list)


def score_pair(a: TxnFingerprintInput, b: TxnFingerprintInput) -> tuple[int, list[str]]:
    reasons: list[str] = []

    if a.amount != b.amount or a.direction != b.direction:
        return 0, reasons

    day_diff = abs((a.txn_date - b.txn_date).days)
    if day_diff > DATE_WINDOW_DAYS:
        return 0, reasons

    score = 40
    reasons.append("نفس المبلغ والاتجاه (مدين/دائن).")

    if day_diff == 0:
        score += 30
        reasons.append("في نفس التاريخ تمامًا.")
    else:
        score += 15
        reasons.append(f"التاريخ متقارب (فرق {day_diff} يوم/أيام).")

    if a.account_key == b.account_key:
        score += 15
        reasons.append("في نفس الحساب.")

    if a.merchant_sanitized and a.merchant_sanitized == b.merchant_sanitized:
        score += 15
        reasons.append("نفس اسم التاجر.")
    elif a.merchant_sanitized and b.merchant_sanitized and (
        a.merchant_sanitized in b.merchant_sanitized or b.merchant_sanitized in a.merchant_sanitized
    ):
        score += 8
        reasons.append("اسم تاجر متشابه جزئيًا.")

    return score, reasons


def find_duplicates(rows: list[TxnFingerprintInput], threshold: int = DUPLICATE_THRESHOLD) -> list[DuplicateCandidate]:
    candidates: list[DuplicateCandidate] = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            score, reasons = score_pair(rows[i], rows[j])
            if score >= threshold:
                candidates.append(
                    DuplicateCandidate(row_index_a=rows[i].row_index, row_index_b=rows[j].row_index, score=score, reasons_ar=reasons)
                )
    return candidates
