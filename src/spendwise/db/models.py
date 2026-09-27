"""
SQLAlchemy ORM models for SpendWise.

Design notes (privacy-by-design):
- No raw transaction descriptions are stored — only a sanitized merchant name.
- No account/card numbers, IBANs, or personal identifiers are stored.
- File fingerprints are one-way hashes (see sanitize.fingerprint) — they
  cannot be used to reconstruct the original file.
- All monetary columns use Numeric (Decimal), never floating point.
- Date columns use Date (not DateTime) so range/equality comparisons work
  correctly against plain python date objects under SQLite.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TransactionType(str, enum.Enum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    REFUND = "refund"
    FEE = "fee"
    CASH_WITHDRAWAL = "cash_withdrawal"
    UNKNOWN = "unknown"


class TransactionDirection(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class ClassificationSource(str, enum.Enum):
    RULE = "rule"
    AI = "ai"
    MANUAL = "manual"
    UNCLASSIFIED = "unclassified"


class ReviewStatus(str, enum.Enum):
    AUTO_APPROVED = "auto_approved"
    PENDING = "pending"
    APPROVED = "approved"
    EXCLUDED = "excluded"


class ImportBatchStatus(str, enum.Enum):
    DRAFT = "draft"          # extracted, awaiting review
    COMMITTED = "committed"  # approved and saved
    ROLLED_BACK = "rolled_back"


class RuleType(str, enum.Enum):
    EXACT = "exact"
    MERCHANT_NORMALIZED = "merchant_normalized"
    KEYWORD = "keyword"
    LEARNED = "learned"


class FxSource(str, enum.Enum):
    MANUAL = "manual"
    ONLINE = "online"


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    accounts: Mapped[list["Account"]] = relationship(back_populates="family_member", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="family_member", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("family_member_id", "alias", name="uq_account_alias_per_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_member_id: Mapped[int] = mapped_column(ForeignKey("family_members.id"))
    alias: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    family_member: Mapped[FamilyMember] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    import_batches: Mapped[list["ImportBatch"]] = relationship(back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # seeded default category

    parent: Mapped["Category | None"] = relationship(remote_side=[id])


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_type: Mapped[RuleType] = mapped_column(Enum(RuleType))
    pattern: Mapped[str] = mapped_column(String(255))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    family_member_id: Mapped[int | None] = mapped_column(ForeignKey("family_members.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    source_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    category: Mapped[Category] = relationship()


class FileFingerprint(Base):
    """One-way hash of an imported file, used only to prevent re-importing
    the same file. Cannot be used to reconstruct file contents."""

    __tablename__ = "file_fingerprints"
    __table_args__ = (UniqueConstraint("account_id", "fingerprint_hash", name="uq_fingerprint_per_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    label: Mapped[str] = mapped_column(String(120))  # non-sensitive user-facing label, e.g. "استيراد 2026-08-21"
    status: Mapped[ImportBatchStatus] = mapped_column(Enum(ImportBatchStatus), default=ImportBatchStatus.DRAFT)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    committed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[Account] = relationship(back_populates="import_batches")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="import_batch")


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency: Mapped[str] = mapped_column(String(8))
    rate_to_base: Mapped[Numeric] = mapped_column(Numeric(18, 6))
    base_currency: Mapped[str] = mapped_column(String(8))
    effective_date: Mapped[dt.date] = mapped_column(Date())
    source: Mapped[FxSource] = mapped_column(Enum(FxSource))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    family_member_id: Mapped[int] = mapped_column(ForeignKey("family_members.id"))

    txn_date: Mapped[dt.date] = mapped_column(Date())
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2))  # always positive magnitude
    direction: Mapped[TransactionDirection] = mapped_column(Enum(TransactionDirection))
    original_currency: Mapped[str] = mapped_column(String(8))
    base_amount: Mapped[Numeric] = mapped_column(Numeric(14, 2))
    fx_rate_id: Mapped[int | None] = mapped_column(ForeignKey("fx_rates.id"), nullable=True)

    txn_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), default=TransactionType.UNKNOWN)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    merchant_sanitized: Mapped[str | None] = mapped_column(String(120), nullable=True)

    classification_source: Mapped[ClassificationSource] = mapped_column(
        Enum(ClassificationSource), default=ClassificationSource.UNCLASSIFIED
    )
    confidence: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    matched_rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"), nullable=True)

    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING)

    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    is_probable_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)

    row_fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # for in-batch/duplicate scoring only

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    account: Mapped[Account] = relationship(back_populates="transactions")
    import_batch: Mapped[ImportBatch] = relationship(back_populates="transactions")
    category: Mapped[Category | None] = relationship()


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("family_member_id", "month", name="uq_budget_per_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_member_id: Mapped[int] = mapped_column(ForeignKey("family_members.id"))
    month: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    family_member: Mapped[FamilyMember] = relationship(back_populates="budgets")
