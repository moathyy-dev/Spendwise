"""
Single overall monthly budget per person (Phase 1 — no category-level
budgets yet, but the Budget model/month-key design does not block adding
that later).
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from spendwise.analytics.metrics import PeriodMetrics, ZERO
from spendwise.db.models import Budget


@dataclass
class BudgetStatus:
    month: str
    budget_amount: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    consumed_pct: Decimal | None
    projected_month_end: Decimal | None
    projected_overrun: Decimal | None


def get_budget(session, family_member_id: int, month: str) -> Budget | None:
    return session.execute(
        select(Budget).where(Budget.family_member_id == family_member_id, Budget.month == month)
    ).scalar_one_or_none()


def set_budget(session, family_member_id: int, month: str, amount: Decimal) -> Budget:
    existing = get_budget(session, family_member_id, month)
    if existing:
        existing.amount = amount
        session.flush()
        return existing
    budget = Budget(family_member_id=family_member_id, month=month, amount=amount)
    session.add(budget)
    session.flush()
    return budget


def list_budgets(session, family_member_id: int) -> list[Budget]:
    return list(
        session.execute(
            select(Budget).where(Budget.family_member_id == family_member_id).order_by(Budget.month.desc())
        ).scalars()
    )


def compute_budget_status(session, family_member_id: int, month: str, metrics: PeriodMetrics) -> BudgetStatus:
    budget = get_budget(session, family_member_id, month)
    spent = metrics.total_expenses

    if budget is None:
        return BudgetStatus(
            month=month, budget_amount=None, spent=spent, remaining=None,
            consumed_pct=None, projected_month_end=None, projected_overrun=None,
        )

    remaining = budget.amount - spent
    consumed_pct = (spent / budget.amount * Decimal("100")) if budget.amount > 0 else None

    projected = spent
    if metrics.is_partial_month:
        today = dt.date.today()
        year, mon = int(month[:4]), int(month[5:7])
        days_in_month = calendar.monthrange(year, mon)[1]
        days_elapsed = max(today.day, 1)
        if days_elapsed > 0:
            projected = (spent / days_elapsed) * days_in_month

    projected_overrun = projected - budget.amount if projected > budget.amount else ZERO

    return BudgetStatus(
        month=month,
        budget_amount=budget.amount,
        spent=spent,
        remaining=remaining,
        consumed_pct=consumed_pct,
        projected_month_end=projected,
        projected_overrun=projected_overrun,
    )
