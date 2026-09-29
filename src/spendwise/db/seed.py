"""Seed default Arabic category taxonomy. Idempotent: safe to run multiple times."""
from __future__ import annotations

from sqlalchemy.orm import Session

from spendwise.db.models import Category

# Flat taxonomy (Phase 1 simplification, 2026-09-29): each entry used to be a
# parent category with several subcategories, which duplicated the parent
# name into every child's label (e.g. "طعام وشراب / مطاعم وكافيهات") and made
# the classification dropdown long and repetitive. Now there is exactly one
# selectable category per row — no parent/child nesting for the default set.
# Existing installations are migrated by an Alembic data migration
# (see migrations/versions) rather than by this seeder, which only inserts
# categories that don't already exist.
DEFAULT_TAXONOMY = [
    "مطاعم وكافيهات",
    "مواصلات",
    "فواتير",
    "صحة",
    "تسوق",
    "ترفيه",
    "تعليم",
    "التزامات مالية",
    "دخل",
    "أخرى",
]


def seed_default_categories(session: Session) -> None:
    existing = {c.name_ar for c in session.query(Category).filter_by(parent_id=None)}
    for order, name in enumerate(DEFAULT_TAXONOMY):
        if name in existing:
            continue
        session.add(Category(name_ar=name, parent_id=None, is_system=True, sort_order=order))
    session.commit()
