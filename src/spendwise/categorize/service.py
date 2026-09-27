"""
Orchestrates the layered categorization workflow for a batch of staged
(in-memory) transaction rows: local rules first, then AI fallback only for
rows that remain unclassified or below the AI-fallback confidence
threshold — and only if AI is enabled/available. AI failures never break
the import; the batch simply proceeds with local-rules-only results and a
pending-review flag.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from spendwise.ai_provider.base import AIProviderError, AITransactionInput
from spendwise.categorize.rules_engine import classify_with_rules
from spendwise.db.models import Rule


@dataclass
class PendingClassification:
    row_index: int
    category_id: int | None
    confidence: int
    source: str  # "rule" | "ai" | "manual" | "unclassified"
    explanation_ar: str
    needs_review: bool
    matched_rule_id: int | None = None


def load_active_rules(session, family_member_id: int) -> list[Rule]:
    """Global rules (family_member_id is NULL) + this member's own rules."""
    return list(
        session.execute(
            select(Rule).where(
                Rule.is_active.is_(True),
                (Rule.family_member_id.is_(None)) | (Rule.family_member_id == family_member_id),
            )
        ).scalars()
    )


def classify_batch(session, family_member_id: int, rows: list, settings, ai_provider=None) -> list[PendingClassification]:
    """`rows` is a list of staged rows exposing `.row_index`, `.merchant_sanitized`,
    `.amount`, `.direction`. Returns one PendingClassification per row, in the
    same order."""
    rules = load_active_rules(session, family_member_id)
    results: dict[int, PendingClassification] = {}
    ai_candidates: list = []

    for row in rows:
        rule_result = classify_with_rules(row.merchant_sanitized, rules)
        auto_approved = (
            rule_result.category_id is not None
            and rule_result.confidence >= settings.confidence_auto_accept
        )
        pc = PendingClassification(
            row_index=row.row_index,
            category_id=rule_result.category_id,
            confidence=rule_result.confidence,
            source=rule_result.source,
            explanation_ar=rule_result.explanation_ar,
            needs_review=not auto_approved,
            matched_rule_id=rule_result.matched_rule_id,
        )
        results[row.row_index] = pc

        needs_ai = rule_result.category_id is None or rule_result.confidence < settings.confidence_ai_fallback
        if needs_ai:
            ai_candidates.append(row)

    if ai_candidates and ai_provider is not None and settings.enable_online_ai:
        try:
            _apply_ai_fallback(session, ai_candidates, results, ai_provider)
        except AIProviderError as exc:
            # Never break the import — local-rules results already stored,
            # rows simply stay flagged for manual review.
            print(f"[spendwise] AI classification unavailable, continuing without it: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[spendwise] Unexpected AI classification error, continuing without it: {exc}")

    return [results[row.row_index] for row in rows]


def _apply_ai_fallback(session, candidate_rows: list, results: dict, ai_provider) -> None:
    categories = _load_category_choices(session)
    ai_inputs = [
        AITransactionInput(
            row_index=row.row_index,
            merchant_sanitized=row.merchant_sanitized,
            amount=str(row.amount),
            direction=row.direction,
        )
        for row in candidate_rows
    ]
    ai_outputs = ai_provider.classify_batch(ai_inputs, categories)
    for out in ai_outputs:
        results[out.row_index] = PendingClassification(
            row_index=out.row_index,
            category_id=out.category_id,
            confidence=out.confidence,
            source="ai",
            explanation_ar=out.explanation_ar or "تم التصنيف بواسطة الذكاء الاصطناعي.",
            needs_review=True,  # AI results always require user confirmation
        )


def _load_category_choices(session) -> list[dict]:
    from spendwise.db.models import Category

    rows = session.execute(select(Category).where(Category.is_active.is_(True))).scalars()
    out = []
    for c in rows:
        label = c.name_ar if c.parent_id is None else f"{c.parent.name_ar} / {c.name_ar}"
        out.append({"id": c.id, "name": label})
    return out


def create_learned_rule(session, family_member_id: int, merchant_sanitized: str, category_id: int, scope: str) -> Rule | None:
    """Only creates a persistent rule if the user explicitly chose
    'future_rule' scope — corrections are NEVER auto-promoted to rules."""
    if scope != "future_rule":
        return None
    if not merchant_sanitized or category_id is None:
        return None
    from spendwise.db.models import RuleType

    rule = Rule(
        family_member_id=family_member_id,
        rule_type=RuleType.LEARNED,
        pattern=merchant_sanitized,
        category_id=category_id,
        priority=200,
        is_active=True,
    )
    session.add(rule)
    session.flush()
    return rule
