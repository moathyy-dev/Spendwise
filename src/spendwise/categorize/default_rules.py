"""
Seed data for local keyword-based categorization rules. These are global
(not tied to a specific family member), low priority (tried last, since
learned/exact/merchant rules should win first), and only serve as a
reasonable starting point — the user can add/edit/disable rules freely
from the "القواعد" (Rules) page.
"""
from __future__ import annotations

from sqlalchemy import select

from spendwise.db.models import Category, Rule, RuleType

# (keyword, category_ar) — flat taxonomy (Phase 1 simplification, 2026-09-29).
# Categories used to be nested (main + sub), but that made the classification
# dropdown long and repetitive, so the default set is now a single flat list
# (see db/seed.py). Rules just point at the flat category name directly.
DEFAULT_KEYWORDS: list[tuple[str, str]] = [
    # مطاعم وكافيهات
    ("مطعم", "مطاعم وكافيهات"),
    ("restaurant", "مطاعم وكافيهات"),
    ("كافي", "مطاعم وكافيهات"),
    ("cafe", "مطاعم وكافيهات"),
    ("starbucks", "مطاعم وكافيهات"),
    ("ستاربكس", "مطاعم وكافيهات"),
    ("هنقرستيشن", "مطاعم وكافيهات"),
    ("hungerstation", "مطاعم وكافيهات"),
    ("جاهز", "مطاعم وكافيهات"),
    ("مرسول", "مطاعم وكافيهات"),
    ("talabat", "مطاعم وكافيهات"),
    ("بقالة", "مطاعم وكافيهات"),
    ("سوبرماركت", "مطاعم وكافيهات"),
    ("supermarket", "مطاعم وكافيهات"),
    ("panda", "مطاعم وكافيهات"),
    ("بنده", "مطاعم وكافيهات"),
    ("carrefour", "مطاعم وكافيهات"),
    ("كارفور", "مطاعم وكافيهات"),
    # مواصلات
    ("بنزين", "مواصلات"),
    ("محطة وقود", "مواصلات"),
    ("petrol", "مواصلات"),
    ("fuel", "مواصلات"),
    ("uber", "مواصلات"),
    ("اوبر", "مواصلات"),
    ("كريم", "مواصلات"),
    ("careem", "مواصلات"),
    ("taxi", "مواصلات"),
    ("تاكسي", "مواصلات"),
    ("parking", "مواصلات"),
    ("موقف", "مواصلات"),
    # فواتير (كان اسمه "سكن ومرافق")
    ("كهرباء", "فواتير"),
    ("electricity", "فواتير"),
    ("مياه", "فواتير"),
    ("water bill", "فواتير"),
    ("إيجار", "فواتير"),
    ("ايجار", "فواتير"),
    ("rent", "فواتير"),
    ("stc", "فواتير"),
    ("موبايلي", "فواتير"),
    ("mobily", "فواتير"),
    ("zain", "فواتير"),
    ("زين", "فواتير"),
    ("internet", "فواتير"),
    # صحة
    ("صيدلية", "صحة"),
    ("nahdi", "صحة"),
    ("النهدي", "صحة"),
    ("pharmacy", "صحة"),
    ("مستشفى", "صحة"),
    ("hospital", "صحة"),
    ("عيادة", "صحة"),
    ("clinic", "صحة"),
    # تسوق
    ("امازون", "تسوق"),
    ("amazon", "تسوق"),
    ("نون", "تسوق"),
    ("noon", "تسوق"),
    ("shein", "تسوق"),
    ("ملابس", "تسوق"),
    ("mall", "تسوق"),
    ("مول", "تسوق"),
    # ترفيه
    ("netflix", "ترفيه"),
    ("نتفلكس", "ترفيه"),
    ("shahid", "ترفيه"),
    ("شاهد", "ترفيه"),
    ("spotify", "ترفيه"),
    ("سينما", "ترفيه"),
    ("cinema", "ترفيه"),
    ("سفر", "ترفيه"),
    ("travel", "ترفيه"),
    ("hotel", "ترفيه"),
    ("فندق", "ترفيه"),
    ("flynas", "ترفيه"),
    ("saudia", "ترفيه"),
    # تعليم
    ("مدرسة", "تعليم"),
    ("school", "تعليم"),
    ("جامعة", "تعليم"),
    ("university", "تعليم"),
    ("كورس", "تعليم"),
    ("course", "تعليم"),
    # التزامات مالية
    ("تحويل الى", "التزامات مالية"),
    ("قرض", "التزامات مالية"),
    ("loan", "التزامات مالية"),
    ("تقسيط", "التزامات مالية"),
    ("تأمين", "التزامات مالية"),
    ("insurance", "التزامات مالية"),
    ("رسوم", "التزامات مالية"),
    ("fee", "التزامات مالية"),
    # دخل
    ("راتب", "دخل"),
    ("salary", "دخل"),
    # أخرى
    ("سحب نقدي", "أخرى"),
    ("atm", "أخرى"),
]


def _find_category(session, name: str):
    return session.execute(
        select(Category).where(Category.name_ar == name, Category.parent_id.is_(None))
    ).scalar_one_or_none()


def seed_default_rules(session) -> None:
    existing_patterns = {
        r.pattern for r in session.execute(
            select(Rule).where(Rule.family_member_id.is_(None), Rule.rule_type == RuleType.KEYWORD)
        ).scalars()
    }
    for keyword, category_name in DEFAULT_KEYWORDS:
        if keyword in existing_patterns:
            continue
        category = _find_category(session, category_name)
        if category is None:
            continue
        session.add(
            Rule(
                family_member_id=None,
                rule_type=RuleType.KEYWORD,
                pattern=keyword,
                category_id=category.id,
                priority=500,
                is_active=True,
            )
        )
    session.flush()
