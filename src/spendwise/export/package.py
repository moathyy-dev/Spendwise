"""
Portable "SpendWise data package": categories, rules, budgets, and APPROVED
transactions (sanitized, non-sensitive fields only) for ONE family member —
for migration/recovery purposes only. Never includes original files or any
raw/sensitive data.

Important isolation rule: duplicate-detection when importing a package is
always scoped to the TARGET family member. row_fingerprint is derived from
(date, amount, direction, account_alias, merchant) — it does not encode
family-member identity by itself, so a global (cross-member) duplicate
check could incorrectly treat a new family member's data as "already
imported" if an account alias happens to be reused. Scoping by
family_member_id avoids that.
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from sqlalchemy import select

from spendwise.db.models import (
    Account,
    Budget,
    Category,
    FamilyMember,
    ImportBatch,
    ImportBatchStatus,
    Rule,
    Transaction,
    ReviewStatus,
)

PACKAGE_FORMAT_VERSION = 1


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    return value


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return dt.datetime.fromisoformat(value).date()


def export_package(session, family_member_id: int) -> dict:
    member = session.get(FamilyMember, family_member_id)
    if member is None:
        raise ValueError("العضو المطلوب غير موجود.")

    categories = session.execute(select(Category)).scalars().all()
    rules = session.execute(
        select(Rule).where((Rule.family_member_id.is_(None)) | (Rule.family_member_id == family_member_id))
    ).scalars().all()
    budgets = session.execute(select(Budget).where(Budget.family_member_id == family_member_id)).scalars().all()
    accounts = session.execute(select(Account).where(Account.family_member_id == family_member_id)).scalars().all()
    account_alias_by_id = {a.id: a.alias for a in accounts}

    txns = session.execute(
        select(Transaction).where(
            Transaction.family_member_id == family_member_id,
            Transaction.review_status.in_([ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]),
        )
    ).scalars().all()

    return {
        "format_version": PACKAGE_FORMAT_VERSION,
        "family_member_name": member.name,
        "categories": [
            {"name_ar": c.name_ar, "parent_name_ar": c.parent.name_ar if c.parent else None, "is_active": c.is_active}
            for c in categories
        ],
        "rules": [
            {
                "rule_type": r.rule_type.value,
                "pattern": r.pattern,
                "category_name_ar": r.category.name_ar,
                "priority": r.priority,
                "is_active": r.is_active,
                "scoped_to_member": r.family_member_id is not None,
            }
            for r in rules
        ],
        "budgets": [{"month": b.month, "amount": str(b.amount)} for b in budgets],
        "accounts": [{"alias": a.alias} for a in accounts],
        "transactions": [
            {
                "account_alias": account_alias_by_id.get(t.account_id, ""),
                "txn_date": _as_date(t.txn_date).isoformat(),
                "amount": str(t.amount),
                "direction": t.direction.value,
                "original_currency": t.original_currency,
                "base_amount": str(t.base_amount),
                "txn_type": t.txn_type.value,
                "category_name_ar": t.category.name_ar if t.category else None,
                "merchant_sanitized": t.merchant_sanitized,
                "row_fingerprint": t.row_fingerprint,
            }
            for t in txns
        ],
    }


def preview_package(session, package: dict, target_family_member_id: int | None = None) -> dict:
    if package.get("format_version") != PACKAGE_FORMAT_VERSION:
        raise ValueError("إصدار ملف الحزمة غير متوافق مع هذا الإصدار من البرنامج.")

    existing_fingerprints: set[str] = set()
    scope_id = target_family_member_id if target_family_member_id is not None else -1
    rows = session.execute(select(Transaction.row_fingerprint).where(Transaction.family_member_id == scope_id)).scalars()
    existing_fingerprints.update(rows)

    txns = package.get("transactions", [])
    already_imported = sum(1 for t in txns if t.get("row_fingerprint") in existing_fingerprints)

    return {
        "family_member_name": package.get("family_member_name"),
        "total_transactions": len(txns),
        "already_imported_count": already_imported,
        "new_count": len(txns) - already_imported,
        "categories_count": len(package.get("categories", [])),
        "rules_count": len(package.get("rules", [])),
        "budgets_count": len(package.get("budgets", [])),
    }


def _get_or_create_category(session, name_ar: str, parent_name_ar: str | None) -> Category:
    parent = None
    if parent_name_ar:
        parent = session.execute(
            select(Category).where(Category.name_ar == parent_name_ar, Category.parent_id.is_(None))
        ).scalar_one_or_none()
        if parent is None:
            parent = Category(name_ar=parent_name_ar, parent_id=None)
            session.add(parent)
            session.flush()

    query = select(Category).where(Category.name_ar == name_ar)
    query = query.where(Category.parent_id == (parent.id if parent else None))
    category = session.execute(query).scalar_one_or_none()
    if category is None:
        category = Category(name_ar=name_ar, parent_id=parent.id if parent else None)
        session.add(category)
        session.flush()
    return category


def import_package(session, package: dict, target_family_member_name: str) -> dict:
    if package.get("format_version") != PACKAGE_FORMAT_VERSION:
        raise ValueError("إصدار ملف الحزمة غير متوافق مع هذا الإصدار من البرنامج.")

    member = session.execute(select(FamilyMember).where(FamilyMember.name == target_family_member_name)).scalar_one_or_none()
    if member is None:
        member = FamilyMember(name=target_family_member_name)
        session.add(member)
        session.flush()

    for cat in package.get("categories", []):
        _get_or_create_category(session, cat["name_ar"], cat.get("parent_name_ar"))
    session.flush()

    for rule in package.get("rules", []):
        category = _get_or_create_category(session, rule["category_name_ar"].split(" / ")[-1], None)
        exists = session.execute(
            select(Rule).where(
                Rule.pattern == rule["pattern"],
                Rule.family_member_id == (member.id if rule.get("scoped_to_member") else None),
            )
        ).scalar_one_or_none()
        if exists:
            continue
        from spendwise.db.models import RuleType

        session.add(
            Rule(
                rule_type=RuleType(rule["rule_type"]),
                pattern=rule["pattern"],
                category_id=category.id,
                priority=rule.get("priority", 100),
                is_active=rule.get("is_active", True),
                family_member_id=member.id if rule.get("scoped_to_member") else None,
            )
        )

    for budget in package.get("budgets", []):
        exists = session.execute(
            select(Budget).where(Budget.family_member_id == member.id, Budget.month == budget["month"])
        ).scalar_one_or_none()
        if exists:
            continue
        session.add(Budget(family_member_id=member.id, month=budget["month"], amount=Decimal(budget["amount"])))

    account_cache: dict[str, Account] = {}

    def _get_or_create_account(alias: str) -> Account:
        if alias in account_cache:
            return account_cache[alias]
        acc = session.execute(
            select(Account).where(Account.family_member_id == member.id, Account.alias == alias)
        ).scalar_one_or_none()
        if acc is None:
            acc = Account(family_member_id=member.id, alias=alias)
            session.add(acc)
            session.flush()
        account_cache[alias] = acc
        return acc

    existing_fingerprints = set(
        session.execute(select(Transaction.row_fingerprint).where(Transaction.family_member_id == member.id)).scalars()
    )

    txns = package.get("transactions", [])
    skipped = 0
    imported = 0
    import_batch: ImportBatch | None = None

    from spendwise.db.models import TransactionDirection, TransactionType

    for t in txns:
        if t["row_fingerprint"] in existing_fingerprints:
            skipped += 1
            continue

        account = _get_or_create_account(t["account_alias"] or "حساب مستورد")
        if import_batch is None:
            import_batch = ImportBatch(account_id=account.id, label="استيراد حزمة بيانات", status=ImportBatchStatus.COMMITTED)
            session.add(import_batch)
            session.flush()

        category = None
        if t.get("category_name_ar"):
            category = _get_or_create_category(session, t["category_name_ar"].split(" / ")[-1], None)

        session.add(
            Transaction(
                import_batch_id=import_batch.id,
                account_id=account.id,
                family_member_id=member.id,
                txn_date=_parse_date(t["txn_date"]),
                amount=Decimal(t["amount"]),
                direction=TransactionDirection(t["direction"]),
                original_currency=t["original_currency"],
                base_amount=Decimal(t["base_amount"]),
                txn_type=TransactionType(t["txn_type"]),
                category_id=category.id if category else None,
                merchant_sanitized=t.get("merchant_sanitized"),
                review_status=ReviewStatus.APPROVED,
                row_fingerprint=t["row_fingerprint"],
            )
        )
        existing_fingerprints.add(t["row_fingerprint"])
        imported += 1

    if import_batch is not None:
        import_batch.row_count = imported

    session.flush()
    return {"family_member_id": member.id, "imported_count": imported, "skipped_count": skipped}
