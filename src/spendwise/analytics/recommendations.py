"""
Generates concise, evidence-based Arabic observations. Every observation is
tagged with a `kind` so the UI can clearly distinguish facts from
estimates/projections/suggestions — never generic advice, never judgmental
wording.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from spendwise.analytics.budget import BudgetStatus
from spendwise.analytics.comparisons import ComparisonResult
from spendwise.analytics.metrics import ZERO
from spendwise.db.models import ReviewStatus, Transaction, TransactionType
from spendwise.detect.anomalies import detect_anomalies
from spendwise.detect.recurring import detect_recurring

SIGNIFICANT_GROWTH_PCT = Decimal("0.20")
SIGNIFICANT_GROWTH_MIN_AMOUNT = Decimal("100")


@dataclass
class Observation:
    kind: str  # "fact" | "estimate" | "projection" | "suggestion"
    text_ar: str


def _category_growth(comparison: ComparisonResult) -> list[Observation]:
    observations: list[Observation] = []
    if comparison.previous is None:
        return observations

    current_cats = comparison.current.category_totals
    prev_cats = comparison.previous.category_totals
    names = comparison.current.category_names

    for cat_id, current_amount in current_cats.items():
        prev_amount = prev_cats.get(cat_id, ZERO)
        if prev_amount <= 0:
            continue
        growth = current_amount - prev_amount
        growth_pct = growth / prev_amount
        if growth > SIGNIFICANT_GROWTH_MIN_AMOUNT and growth_pct >= SIGNIFICANT_GROWTH_PCT:
            name = names.get(cat_id, "غير مصنّف")
            observations.append(
                Observation(
                    kind="fact",
                    text_ar=(
                        f"ارتفع إنفاقك على «{name}» بمقدار {growth:.2f} "
                        f"({growth_pct * 100:.0f}%) مقارنة بالشهر السابق."
                    ),
                )
            )
    return observations


def _budget_projection(budget_status: BudgetStatus | None) -> list[Observation]:
    if budget_status is None or budget_status.budget_amount is None:
        return []
    if budget_status.projected_overrun and budget_status.projected_overrun > 0:
        return [
            Observation(
                kind="projection",
                text_ar=(
                    f"بناءً على معدل إنفاقك الحالي، من المتوقع أن يتجاوز إجمالي إنفاق هذا الشهر "
                    f"الميزانية بمقدار تقريبي {budget_status.projected_overrun:.2f}."
                ),
            )
        ]
    return []


def _top_category_share(comparison: ComparisonResult) -> list[Observation]:
    metrics = comparison.current
    if not metrics.highest_categories or metrics.total_expenses <= 0:
        return []
    top_id, top_amount = metrics.highest_categories[0]
    share = top_amount / metrics.total_expenses * Decimal("100")
    name = metrics.category_names.get(top_id, "غير مصنّف")
    return [Observation(kind="fact", text_ar=f"يمثّل تصنيف «{name}» أكبر نسبة من إنفاقك هذا الشهر ({share:.0f}%).")]


def _recurring_suggestion(session, family_member_id: int) -> list[Observation]:
    rows = session.execute(
        select(Transaction).where(
            Transaction.family_member_id == family_member_id,
            Transaction.txn_type == TransactionType.EXPENSE,
            Transaction.review_status.in_([ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]),
        )
    ).scalars()
    groups = detect_recurring(list(rows))
    observations = []
    for g in groups[:3]:
        observations.append(
            Observation(
                kind="suggestion",
                text_ar=(
                    f"يبدو أن هناك دفعة متكررة شهريًا تقريبًا لدى «{g.merchant_sanitized}» "
                    f"بمتوسط {g.average_amount:.2f} — قد يكون هذا اشتراكًا يستحق مراجعته."
                ),
            )
        )
    return observations


def _anomaly_facts(session, family_member_id: int) -> list[Observation]:
    rows = session.execute(
        select(Transaction).where(
            Transaction.family_member_id == family_member_id,
            Transaction.txn_type == TransactionType.EXPENSE,
            Transaction.review_status.in_([ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]),
        )
    ).scalars()
    flags = detect_anomalies(list(rows))
    return [Observation(kind="fact", text_ar=f"معاملة بقيمة {f.amount:.2f} أعلى بشكل ملحوظ من إنفاقك المعتاد في هذا التصنيف.") for f in flags[:3]]


def _savings_rate(comparison: ComparisonResult) -> list[Observation]:
    metrics = comparison.current
    if metrics.total_income <= 0:
        return []
    rate = metrics.net_savings / metrics.total_income * Decimal("100")
    return [Observation(kind="fact", text_ar=f"نسبة ما تم توفيره من الدخل هذا الشهر تبلغ تقريبًا {rate:.0f}%.")]


def generate_observations(session, family_member_id: int, comparison: ComparisonResult, budget_status: BudgetStatus | None) -> list[Observation]:
    observations: list[Observation] = []
    observations.extend(_category_growth(comparison))
    observations.extend(_budget_projection(budget_status))
    observations.extend(_top_category_share(comparison))
    observations.extend(_recurring_suggestion(session, family_member_id))
    observations.extend(_anomaly_facts(session, family_member_id))
    observations.extend(_savings_rate(comparison))

    if not observations:
        observations.append(Observation(kind="fact", text_ar="لم يتم رصد أي أنماط لافتة في بيانات هذا الشهر حتى الآن."))

    return observations
