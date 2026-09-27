"""Seed default Arabic category taxonomy. Idempotent: safe to run multiple times."""
from __future__ import annotations

from sqlalchemy.orm import Session

from spendwise.db.models import Category

DEFAULT_TAXONOMY = {
    "طعام وشراب": ["مطاعم وكافيهات", "بقالة وسوبرماركت", "توصيل طلبات"],
    "مواصلات": ["وقود", "صيانة سيارة", "مواقف ورسوم طرق", "تطبيقات نقل"],
    "سكن ومرافق": ["إيجار", "كهرباء وماء", "اتصالات وإنترنت", "صيانة منزل"],
    "صحة": ["صيدلية", "عيادات ومستشفيات", "تأمين صحي"],
    "تسوق": ["ملابس", "إلكترونيات", "متاجر عامة"],
    "ترفيه": ["اشتراكات ترفيه", "سينما ومناسبات", "سفر وسياحة"],
    "تعليم": ["رسوم دراسية", "دورات وكتب"],
    "التزامات مالية": ["أقساط", "رسوم بنكية", "تحويلات"],
    "دخل": ["راتب", "دخل إضافي", "استرداد"],
    "أخرى": ["غير مصنّف", "سحب نقدي"],
}


def seed_default_categories(session: Session) -> None:
    existing = {c.name_ar for c in session.query(Category).filter_by(parent_id=None)}
    for order, (main, subs) in enumerate(DEFAULT_TAXONOMY.items()):
        if main in existing:
            continue
        parent = Category(name_ar=main, parent_id=None, is_system=True, sort_order=order)
        session.add(parent)
        session.flush()
        for sub_order, sub in enumerate(subs):
            session.add(
                Category(name_ar=sub, parent_id=parent.id, is_system=True, sort_order=sub_order)
            )
    session.commit()
