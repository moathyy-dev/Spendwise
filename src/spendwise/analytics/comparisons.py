"""
Compares a month against the previous month and against the historical
average — always being explicit in Arabic when data is partial or
insufficient, rather than silently showing a misleading comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from spendwise.analytics.metrics import PeriodMetrics, compute_period_metrics, list_available_months, ZERO


@dataclass
class ComparisonResult:
    current: PeriodMetrics
    previous: PeriodMetrics | None
    previous_delta_amount: Decimal | None
    previous_delta_pct: Decimal | None
    historical_average_expenses: Decimal | None
    historical_delta_amount: Decimal | None
    historical_delta_pct: Decimal | None
    note_ar: str | None


def _prev_month_str(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{mon - 1:02d}"


def _pct_delta(current: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline == 0:
        return None
    return (current - baseline) / baseline * Decimal("100")


def compute_comparison(session, family_member_id: int, month: str, account_id: int | None = None) -> ComparisonResult:
    current = compute_period_metrics(session, family_member_id, month, account_id)

    notes: list[str] = []

    previous = None
    previous_delta_amount = None
    previous_delta_pct = None
    prev_month = _prev_month_str(month)
    prev_metrics = compute_period_metrics(session, family_member_id, prev_month, account_id)
    if prev_metrics.has_sufficient_data:
        previous = prev_metrics
        previous_delta_amount = current.total_expenses - prev_metrics.total_expenses
        previous_delta_pct = _pct_delta(current.total_expenses, prev_metrics.total_expenses)
    else:
        notes.append("لا تتوفر بيانات كافية عن الشهر السابق للمقارنة.")

    available_months = [m for m in list_available_months(session, family_member_id) if m != month]
    historical_average = None
    historical_delta_amount = None
    historical_delta_pct = None
    if len(available_months) >= 2:
        totals = []
        for m in available_months:
            mm = compute_period_metrics(session, family_member_id, m, account_id)
            if mm.has_sufficient_data:
                totals.append(mm.total_expenses)
        if len(totals) >= 2:
            historical_average = sum(totals, ZERO) / len(totals)
            historical_delta_amount = current.total_expenses - historical_average
            historical_delta_pct = _pct_delta(current.total_expenses, historical_average)
        else:
            notes.append("لا تتوفر أشهر سابقة كافية لحساب متوسط تاريخي موثوق.")
    else:
        notes.append("لا تتوفر أشهر سابقة كافية لحساب متوسط تاريخي موثوق.")

    if current.is_partial_month:
        notes.append("الشهر الحالي لم يكتمل بعد، فقد تتغيّر هذه الأرقام حتى نهاية الشهر.")

    return ComparisonResult(
        current=current,
        previous=previous,
        previous_delta_amount=previous_delta_amount,
        previous_delta_pct=previous_delta_pct,
        historical_average_expenses=historical_average,
        historical_delta_amount=historical_delta_amount,
        historical_delta_pct=historical_delta_pct,
        note_ar=" ".join(notes) if notes else None,
    )
