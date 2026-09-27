"""
Detects likely refunds: a credit matched back to an earlier debit at the
same account/merchant with an amount at least as large as the refund,
within a lookback window. Confirmed matches are linked so the refund can be
deducted from the appropriate category/period per the documented rule
(see analytics/metrics.py).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

REFUND_LOOKBACK_DAYS = 90


@dataclass
class RefundCandidateTxn:
    row_index: int
    txn_date: dt.date
    amount: Decimal
    direction: str
    account_key: str
    merchant_sanitized: str


@dataclass
class RefundMatch:
    debit_row_index: int
    credit_row_index: int
    date_diff_days: int


def find_refund_links(rows: list[RefundCandidateTxn]) -> list[RefundMatch]:
    debits = [r for r in rows if r.direction == "debit"]
    credits = [r for r in rows if r.direction == "credit"]
    matches: list[RefundMatch] = []

    for credit in credits:
        best_debit = None
        best_diff = None
        for debit in debits:
            if debit.account_key != credit.account_key:
                continue
            if debit.merchant_sanitized != credit.merchant_sanitized or not debit.merchant_sanitized:
                continue
            if debit.amount < credit.amount:
                continue
            if debit.txn_date > credit.txn_date:
                continue
            diff = (credit.txn_date - debit.txn_date).days
            if diff > REFUND_LOOKBACK_DAYS:
                continue
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_debit = debit

        if best_debit is not None:
            matches.append(
                RefundMatch(debit_row_index=best_debit.row_index, credit_row_index=credit.row_index, date_diff_days=best_diff)
            )

    return matches
