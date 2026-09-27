"""
Computes all dashboard metrics for a given family member + month, strictly
from APPROVED transactions already in the database (no re-upload needed).

Documented rule for refunds: a refund transaction's base_amount is
subtracted from its OWN category's total for the period the refund itself
occurred in — not retroactively re-allocated back to the original expense's
period. This keeps each month's numbers self-consistent and easy to
explain to a non-technical user.

Transfers are excluded from expense/income totals entirely (tracked
separately in `transfers_total`) since they don't represent real
spending or earning.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select

from spendwise.db.models import Category, ReviewStatus, Transaction, TransactionDirection, TransactionType

ZERO = Decimal("0")


@dataclass
class PeriodMetrics:
    month: str
    total_expenses: Decimal = ZERO
    total_income: Decimal = ZERO
    net_savings: Decimal = ZERO
    transfers_total: Decimal = ZERO
    refunds_deducted_total: Decimal = ZERO
    category_totals: dict[int, Decimal] = field(default_factory=dict)
    category_names: dict[int, str] = field(default_factory=dict)
    daily_totals: dict[str, Decimal] = field(default_factory=dict)
    highest_spending_days: list[tuple[str, Decimal]] = field(default_factory=list)
    highest_categories: list[tuple[int, Decimal]] = field(default_factory=list)
    highest_merchants: list[tuple[str, Decimal]] = field(default_factory=list)
    transaction_count: int = 0
    pending_review_count: int = 0
    is_partial_month: bool = False
    has_sufficient_data: bool = True
    insufficient_data_reason_ar: str | None = None


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    year, mon = int(month[:4]), int(month[5:7])
    last_day = calendar.monthrange(year, mon)[1]
    return dt.date(year, mon, 1), dt.date(year, mon, last_day)


_COUNTED_REVIEW_STATUSES = (ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED)


def list_available_months(session, family_member_id: int) -> list[str]:
    rows = session.execute(
        select(Transaction.txn_date).where(
            Transaction.family_member_id == family_member_id,
            Transaction.review_status.in_(_COUNTED_REVIEW_STATUSES),
        )
    ).scalars()
    months = sorted({f"{d.year:04d}-{d.month:02d}" for d in rows}, reverse=True)
    return months


def compute_period_metrics(session, family_member_id: int, month: str, account_id: int | None = None) -> PeriodMetrics:
    start, end = _month_bounds(month)
    metrics = PeriodMetrics(month=month)

    today = dt.date.today()
    metrics.is_partial_month = (today.year == start.year and today.month == start.month) and today <= end

    filters = [
        Transaction.family_member_id == family_member_id,
        Transaction.txn_date >= start,
        Transaction.txn_date <= end,
        Transaction.review_status.in_(_COUNTED_REVIEW_STATUSES),
    ]
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)

    txns = list(session.execute(select(Transaction).where(*filters)).scalars())
    metrics.transaction_count = len(txns)

    pending_filters = [
        Transaction.family_member_id == family_member_id,
        Transaction.txn_date >= start,
        Transaction.txn_date <= end,
        Transaction.review_status == ReviewStatus.PENDING,
    ]
    if account_id is not None:
        pending_filters.append(Transaction.account_id == account_id)
    metrics.pending_review_count = len(list(session.execute(select(Transaction).where(*pending_filters)).scalars()))

    if not txns:
        metrics.has_sufficient_data = False
        metrics.insufficient_data_reason_ar = "لا توجد معاملات معتمدة لهذا الشهر بعد."
        return metrics

    category_totals: dict[int, Decimal] = {}
    category_names: dict[int, str] = {}
    daily_totals: dict[str, Decimal] = {}
    merchant_totals: dict[str, Decimal] = {}

    for t in txns:
        day_key = t.txn_date.isoformat()

        if t.txn_type == TransactionType.TRANSFER:
            metrics.transfers_total += t.base_amount
            continue

        if t.txn_type == TransactionType.REFUND:
            metrics.refunds_deducted_total += t.base_amount
            if t.category_id is not None:
                category_totals[t.category_id] = category_totals.get(t.category_id, ZERO) - t.base_amount
            continue

        if t.direction == TransactionDirection.CREDIT or t.txn_type == TransactionType.INCOME:
            metrics.total_income += t.base_amount
            continue

        # Everything else counted as an expense (expense/fee/cash_withdrawal/unknown debit)
        daily_totals[day_key] = daily_totals.get(day_key, ZERO) + t.base_amount
        if t.category_id is not None:
            category_totals[t.category_id] = category_totals.get(t.category_id, ZERO) + t.base_amount
        if t.merchant_sanitized:
            merchant_totals[t.merchant_sanitized] = merchant_totals.get(t.merchant_sanitized, ZERO) + t.base_amount

    metrics.total_expenses = sum(category_totals.values(), ZERO) if category_totals else sum(daily_totals.values(), ZERO)
    metrics.net_savings = metrics.total_income - metrics.total_expenses
    metrics.category_totals = category_totals
    metrics.daily_totals = daily_totals

    category_ids = list(category_totals.keys())
    if category_ids:
        cats = session.execute(select(Category).where(Category.id.in_(category_ids))).scalars()
        for c in cats:
            category_names[c.id] = c.name_ar if c.parent_id is None else f"{c.parent.name_ar} / {c.name_ar}"
    metrics.category_names = category_names

    metrics.highest_spending_days = sorted(daily_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    metrics.highest_categories = sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    metrics.highest_merchants = sorted(merchant_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return metrics
