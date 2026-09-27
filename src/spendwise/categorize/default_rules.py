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

# (keyword, main_category_ar, sub_category_ar)
DEFAULT_KEYWORDS: list[tuple[str, str, str]] = [
    # طعام وشراب
    ("مطعم", "طعام وشراب", "مطاعم"),
    ("restaurant", "طعام وشراب", "مطاعم"),
    ("كافي", "طعام وشراب", "مقاهي"),
    ("cafe", "طعام وشراب", "مقاهي"),
    ("starbucks", "طعام وشراب", "مقاهي"),
    ("ستاربكس", "طعام وشراب", "مقاهي"),
    ("هنقرستيشن", "طعام وشراب", "توصيل طعام"),
    ("hungerstation", "طعام وشراب", "توصيل طعام"),
    ("جاهز", "طعام وشراب", "توصيل طعام"),
    ("مرسول", "طعام وشراب", "توصيل طعام"),
    ("talabat", "طعام وشراب", "توصيل طعام"),
    ("بقالة", "طعام وشراب", "بقالة"),
    ("سوبرماركت", "طعام وشراب", "بقالة"),
    ("supermarket", "طعام وشراب", "بقالة"),
    ("panda", "طعام وشراب", "بقالة"),
    ("بنده", "طعام وشراب", "بقالة"),
    ("carrefour", "طعام وشراب", "بقالة"),
    ("كارفور", "طعام وشراب", "بقالة"),
    # مواصلات
    ("بنزين", "مواصلات", "وقود"),
    ("محطة وقود", "مواصلات", "وقود"),
    ("petrol", "مواصلات", "وقود"),
    ("fuel", "مواصلات", "وقود"),
    ("uber", "مواصلات", "نقل تشاركي"),
    ("اوبر", "مواصلات", "نقل تشاركي"),
    ("كريم", "مواصلات", "نقل تشاركي"),
    ("careem", "مواصلات", "نقل تشاركي"),
    ("taxi", "مواصلات", "نقل تشاركي"),
    ("تاكسي", "مواصلات", "نقل تشاركي"),
    ("parking", "مواصلات", "مواقف"),
    ("موقف", "مواصلات", "مواقف"),
    # سكن ومرافق
    ("كهرباء", "سكن ومرافق", "فواتير"),
    ("electricity", "سكن ومرافق", "فواتير"),
    ("مياه", "سكن ومرافق", "فواتير"),
    ("water bill", "سكن ومرافق", "فواتير"),
    ("إيجار", "سكن ومرافق", "إيجار"),
    ("ايجار", "سكن ومرافق", "إيجار"),
    ("rent", "سكن ومرافق", "إيجار"),
    ("stc", "سكن ومرافق", "اتصالات وإنترنت"),
    ("موبايلي", "سكن ومرافق", "اتصالات وإنترنت"),
    ("mobily", "سكن ومرافق", "اتصالات وإنترنت"),
    ("zain", "سكن ومرافق", "اتصالات وإنترنت"),
    ("زين", "سكن ومرافق", "اتصالات وإنترنت"),
    ("internet", "سكن ومرافق", "اتصالات وإنترنت"),
    # صحة
    ("صيدلية", "صحة", "أدوية"),
    ("nahdi", "صحة", "أدوية"),
    ("النهدي", "صحة", "أدوية"),
    ("pharmacy", "صحة", "أدوية"),
    ("مستشفى", "صحة", "استشارات ومستشفيات"),
    ("hospital", "صحة", "استشارات ومستشفيات"),
    ("عيادة", "صحة", "استشارات ومستشفيات"),
    ("clinic", "صحة", "استشارات ومستشفيات"),
    # تسوق
    ("امازون", "تسوق", "تسوق عبر الإنترنت"),
    ("amazon", "تسوق", "تسوق عبر الإنترنت"),
    ("نون", "تسوق", "تسوق عبر الإنترنت"),
    ("noon", "تسوق", "تسوق عبر الإنترنت"),
    ("shein", "تسوق", "ملابس"),
    ("ملابس", "تسوق", "ملابس"),
    ("mall", "تسوق", "تسوق عام"),
    ("مول", "تسوق", "تسوق عام"),
    # ترفيه
    ("netflix", "ترفيه", "اشتراكات ترفيه"),
    ("نتفلكس", "ترفيه", "اشتراكات ترفيه"),
    ("shahid", "ترفيه", "اشتراكات ترفيه"),
    ("شاهد", "ترفيه", "اشتراكات ترفيه"),
    ("spotify", "ترفيه", "اشتراكات ترفيه"),
    ("سينما", "ترفيه", "سينما وفعاليات"),
    ("cinema", "ترفيه", "سينما وفعاليات"),
    # تعليم
    ("مدرسة", "تعليم", "رسوم تعليمية"),
    ("school", "تعليم", "رسوم تعليمية"),
    ("جامعة", "تعليم", "رسوم تعليمية"),
    ("university", "تعليم", "رسوم تعليمية"),
    ("كورس", "تعليم", "دورات تدريبية"),
    ("course", "تعليم", "دورات تدريبية"),
    # التزامات مالية
    ("تحويل الى", "التزامات مالية", "تحويلات"),
    ("قرض", "التزامات مالية", "قروض وتقسيط"),
    ("loan", "التزامات مالية", "قروض وتقسيط"),
    ("تقسيط", "التزامات مالية", "قروض وتقسيط"),
    ("تأمين", "التزامات مالية", "تأمين"),
    ("insurance", "التزامات مالية", "تأمين"),
    ("رسوم", "التزامات مالية", "رسوم بنكية"),
    ("fee", "التزامات مالية", "رسوم بنكية"),
    # دخل
    ("راتب", "دخل", "راتب"),
    ("salary", "دخل", "راتب"),
    ("سحب نقدي", "التزامات مالية", "سحب نقدي"),
    ("atm", "التزامات مالية", "سحب نقدي"),
    # سفر
    ("سفر", "ترفيه", "سفر"),
    ("travel", "ترفيه", "سفر"),
    ("hotel", "ترفيه", "سفر"),
    ("فندق", "ترفيه", "سفر"),
    ("flynas", "ترفيه", "سفر"),
    ("saudia", "ترفيه", "سفر"),
]


def _find_category(session, main_name: str, sub_name: str):
    parent = session.execute(
        select(Category).where(Category.name_ar == main_name, Category.parent_id.is_(None))
    ).scalar_one_or_none()
    if parent is None:
        return None
    child = session.execute(
        select(Category).where(Category.name_ar == sub_name, Category.parent_id == parent.id)
    ).scalar_one_or_none()
    return child or parent


def seed_default_rules(session) -> None:
    existing_patterns = {
        r.pattern for r in session.execute(
            select(Rule).where(Rule.family_member_id.is_(None), Rule.rule_type == RuleType.KEYWORD)
        ).scalars()
    }
    for keyword, main_name, sub_name in DEFAULT_KEYWORDS:
        if keyword in existing_patterns:
            continue
        category = _find_category(session, main_name, sub_name)
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
