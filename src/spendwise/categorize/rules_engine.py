"""
Local, explainable rule-based categorization engine.

Rules are tried in priority order (lower `priority` number = tried first),
with rule TYPE as a tie-breaker when priority values are equal. Every match
carries a plain-Arabic explanation and a confidence score so the user can
always see *why* a transaction was categorized a certain way.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Base confidence per rule type (used when a rule doesn't override anything).
_TYPE_BASE_CONFIDENCE = {
    "exact": 100,
    "merchant_normalized": 95,
    "learned": 85,
    "keyword": 75,
}

# Tie-break order when two rules share the same explicit priority number.
_TYPE_ORDER = {"exact": 0, "merchant_normalized": 1, "learned": 2, "keyword": 3}


@dataclass
class ClassificationResult:
    category_id: int | None
    confidence: int
    source: str  # "rule" | "unclassified"
    explanation_ar: str
    matched_rule_id: int | None = None


def normalize_merchant_for_matching(text: str) -> str:
    """Diacritic-insensitive, case-insensitive, whitespace-collapsed form
    used only for matching (never persisted)."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    return " ".join(normalized.split())


def sort_rules(rules: list) -> list:
    """Sort active rules by (priority, rule-type tie-break) — explicit
    priority always wins first, rule type only decides ties."""
    return sorted(
        rules,
        key=lambda r: (r.priority, _TYPE_ORDER.get(r.rule_type.value if hasattr(r.rule_type, "value") else r.rule_type, 99)),
    )


def _rule_type_str(rule) -> str:
    return rule.rule_type.value if hasattr(rule.rule_type, "value") else rule.rule_type


def classify_with_rules(merchant_sanitized: str, rules: list) -> ClassificationResult:
    """Try each active rule (already sorted) against the sanitized merchant
    label. Returns the first match, or an 'unclassified' result."""
    target = normalize_merchant_for_matching(merchant_sanitized)
    if not target:
        return ClassificationResult(
            category_id=None, confidence=0, source="unclassified",
            explanation_ar="لا يوجد نص كافٍ لتصنيف هذه المعاملة تلقائيًا.",
        )

    for rule in sort_rules([r for r in rules if getattr(r, "is_active", True)]):
        rtype = _rule_type_str(rule)
        pattern = normalize_merchant_for_matching(rule.pattern)
        if not pattern:
            continue

        matched = False
        if rtype == "exact":
            matched = target == pattern
        elif rtype in ("merchant_normalized", "learned", "keyword"):
            matched = pattern in target

        if matched:
            confidence = _TYPE_BASE_CONFIDENCE.get(rtype, 70)
            type_ar = {
                "exact": "قاعدة مطابقة تامة",
                "merchant_normalized": "قاعدة مطابقة اسم تاجر",
                "learned": "قاعدة مُتعلَّمة من تصحيح سابق",
                "keyword": "قاعدة كلمة مفتاحية",
            }.get(rtype, "قاعدة")
            return ClassificationResult(
                category_id=rule.category_id,
                confidence=confidence,
                source="rule",
                explanation_ar=f"تم التصنيف عبر {type_ar} مطابقة لـ «{rule.pattern}».",
                matched_rule_id=rule.id,
            )

    return ClassificationResult(
        category_id=None, confidence=0, source="unclassified",
        explanation_ar="لم يتم العثور على قاعدة محلية مطابقة لهذه المعاملة.",
    )
