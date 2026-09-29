"""flatten category taxonomy and widen merchant_sanitized

Collapses the old two-level category taxonomy (10 main categories with 27
subcategories) into a single flat list of 10 categories, per product
decision: subcategory labels were duplicating the parent name in the
classification dropdown (e.g. "طعام وشراب / مطاعم وكافيهات") and made the
list feel long and repetitive.

Any transaction or rule pointing at an old subcategory is repointed to that
subcategory's parent, except the old "غير مصنّف" subcategory (under "أخرى"),
which already duplicated the app's own built-in "unclassified" placeholder:
transactions referencing it become truly unclassified (category_id = NULL),
and any rule referencing it (rules.category_id is NOT NULL) falls back to
the flat "أخرى" category instead.

Also widens transactions.merchant_sanitized from 120 to 160 characters to
match the sanitizer's raised max_len, so long-but-safe (PII-stripped)
descriptions aren't truncated before being stored.

Revision ID: 2277e06708ad
Revises: 640b01802c05
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2277e06708ad'
down_revision: Union[str, None] = '640b01802c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old main-category name -> new flat-category name. Most keep their name;
# these two are renamed because the group's new single label reads better
# than the old parent's name once its subcategories are gone.
_RENAMES = {
    "طعام وشراب": "مطاعم وكافيهات",
    "سكن ومرافق": "فواتير",
}


def upgrade() -> None:
    # --- widen merchant_sanitized (matches sanitizer.py's raised max_len) ---
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column(
            'merchant_sanitized',
            existing_type=sa.String(length=120),
            type_=sa.String(length=160),
            existing_nullable=True,
        )

    # --- flatten categories ---
    bind = op.get_bind()
    meta = sa.MetaData()
    categories = sa.Table('categories', meta, autoload_with=bind)
    transactions = sa.Table('transactions', meta, autoload_with=bind)
    rules = sa.Table('rules', meta, autoload_with=bind)

    for old_name, new_name in _RENAMES.items():
        bind.execute(
            categories.update()
            .where(categories.c.name_ar == old_name, categories.c.parent_id.is_(None))
            .values(name_ar=new_name)
        )

    fallback_id = bind.execute(
        sa.select(categories.c.id).where(categories.c.name_ar == "أخرى", categories.c.parent_id.is_(None))
    ).scalar()

    children = bind.execute(
        sa.select(categories.c.id, categories.c.parent_id, categories.c.name_ar)
        .where(categories.c.parent_id.isnot(None))
    ).fetchall()

    for child_id, parent_id, child_name in children:
        if child_name == "غير مصنّف":
            bind.execute(
                transactions.update().where(transactions.c.category_id == child_id).values(category_id=None)
            )
            if fallback_id is not None:
                bind.execute(
                    rules.update().where(rules.c.category_id == child_id).values(category_id=fallback_id)
                )
        else:
            bind.execute(
                transactions.update().where(transactions.c.category_id == child_id).values(category_id=parent_id)
            )
            bind.execute(
                rules.update().where(rules.c.category_id == child_id).values(category_id=parent_id)
            )

    bind.execute(categories.delete().where(categories.c.parent_id.isnot(None)))


def downgrade() -> None:
    # Not cleanly reversible: the original subcategories and which specific
    # transactions/rules belonged to each of them are gone by design. Only
    # the schema-level changes are reverted.
    bind = op.get_bind()
    meta = sa.MetaData()
    categories = sa.Table('categories', meta, autoload_with=bind)
    for old_name, new_name in _RENAMES.items():
        bind.execute(
            categories.update()
            .where(categories.c.name_ar == new_name, categories.c.parent_id.is_(None))
            .values(name_ar=old_name)
        )

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column(
            'merchant_sanitized',
            existing_type=sa.String(length=160),
            type_=sa.String(length=120),
            existing_nullable=True,
        )
