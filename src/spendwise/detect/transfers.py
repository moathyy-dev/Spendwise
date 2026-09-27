"""
Detects likely transfers between the user's own accounts: a debit in one
account matched to a credit of the same amount in a DIFFERENT account
within a short date window. Transfers are excluded from expense/income
totals but preserved for cash-flow tracking.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

TRANSFER_DATE_WINDOW_DAYS = 3


@dataclass
class TransferCandidateTxn:
    row_index: int
    txn_date: dt.date
    amount: Decimal
    direction: str
    account_key: str


@dataclass
class TransferMatch:
    debit_row_index: int
    credit_row_index: int
    date_diff_days: int


def find_transfers(rows: list[TransferCandidateTxn]) -> list[TransferMatch]:
    debits = [r for r in rows if r.direction == "debit"]
    credits = [r for r in rows if r.direction == "credit"]
    used_credit_indices: set[int] = set()
    matches: list[TransferMatch] = []

    for debit in debits:
        best_credit = None
        best_diff = None
        for credit in credits:
            if credit.row_index in used_credit_indices:
                continue
            if credit.account_key == debit.account_key:
                continue  # must be a DIFFERENT account to be a transfer
            if credit.amount != debit.amount:
                continue
            diff = abs((credit.txn_date - debit.txn_date).days)
            if diff > TRANSFER_DATE_WINDOW_DAYS:
                continue
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_credit = credit

        if best_credit is not None:
            used_credit_indices.add(best_credit.row_index)
            matches.append(
                TransferMatch(debit_row_index=debit.row_index, credit_row_index=best_credit.row_index, date_diff_days=best_diff)
            )

    return matches
