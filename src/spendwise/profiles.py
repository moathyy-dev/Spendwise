"""
Simple CRUD helpers for family members and accounts. Every account belongs
to exactly one family member, and all downstream data (transactions,
budgets, rules) is scoped by family_member_id to guarantee data is never
mixed between profiles.
"""
from __future__ import annotations

from sqlalchemy import select

from spendwise.db.models import Account, FamilyMember


def list_family_members(session) -> list[FamilyMember]:
    return list(session.execute(select(FamilyMember).order_by(FamilyMember.name)).scalars())


def get_or_create_family_member(session, name: str) -> FamilyMember:
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم العضو مطلوب.")
    member = session.execute(select(FamilyMember).where(FamilyMember.name == name)).scalar_one_or_none()
    if member is None:
        member = FamilyMember(name=name)
        session.add(member)
        session.flush()
    return member


def list_accounts(session, family_member_id: int, active_only: bool = True) -> list[Account]:
    query = select(Account).where(Account.family_member_id == family_member_id)
    if active_only:
        query = query.where(Account.is_active.is_(True))
    return list(session.execute(query.order_by(Account.alias)).scalars())


def get_or_create_account(session, family_member_id: int, alias: str) -> Account:
    alias = (alias or "").strip()
    if not alias:
        raise ValueError("اسم/رمز الحساب مطلوب.")
    account = session.execute(
        select(Account).where(Account.family_member_id == family_member_id, Account.alias == alias)
    ).scalar_one_or_none()
    if account is None:
        account = Account(family_member_id=family_member_id, alias=alias)
        session.add(account)
        session.flush()
    return account
