"""
Orchestrates the full guided import workflow on IN-MEMORY staged data only.
Nothing is persisted to the database until commit_import() is explicitly
called with the user's approved rows. This lets the review/edit/approve UI
work freely without any risk of partial/accidental writes.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select

from spendwise.categorize.service import PendingClassification, classify_batch
from spendwise.db.models import (
    Account,
    FileFingerprint,
    FxRate,
    FxSource,
    ImportBatch,
    ImportBatchStatus,
    ReviewStatus,
    Transaction,
    TransactionDirection,
    TransactionType,
)
from spendwise.detect.duplicates import DuplicateCandidate, TxnFingerprintInput, find_duplicates
from spendwise.detect.refunds import RefundCandidateTxn, find_refund_links
from spendwise.detect.transfers import TransferCandidateTxn, find_transfers
from spendwise.ingestion.common import ExtractionResult
from spendwise.mapping.column_mapper import ColumnMapping, guess_mapping
from spendwise.mapping.normalizer import NormalizedRow, normalize_table
from spendwise.money import convert, to_money
from spendwise.sanitize.fingerprint import fingerprint_row
from spendwise.sanitize.sanitizer import sanitize_merchant


class DuplicateFileError(Exception):
    pass


@dataclass
class StagedRow:
    row_index: int
    txn_date: dt.date
    amount: Decimal
    direction: str  # "debit" | "credit"
    currency: str
    merchant_sanitized: str
    row_fingerprint: str
    warnings: list[str] = field(default_factory=list)

    # Populated by later stages:
    category_id: int | None = None
    confidence: int = 0
    classification_source: str = "unclassified"
    explanation_ar: str = ""
    matched_rule_id: int | None = None
    needs_review: bool = True

    is_probable_duplicate: bool = False
    duplicate_reasons_ar: list[str] = field(default_factory=list)
    duplicate_of_row_index: int | None = None

    is_transfer: bool = False
    transfer_pair_row_index: int | None = None
    transfer_pair_existing_txn_id: int | None = None  # set when matched against an already-committed txn in another account

    txn_type: str = "unknown"
    is_refund: bool = False
    refund_of_row_index: int | None = None

    excluded: bool = False
    manual_category_override: int | None = None


@dataclass
class StagedImport:
    account_id: int
    family_member_id: int
    rows: list[StagedRow] = field(default_factory=list)
    default_currency: str = "SAR"


def check_file_not_duplicate(session, account_id: int, file_fingerprint: str) -> None:
    exists = session.execute(
        select(FileFingerprint).where(
            FileFingerprint.account_id == account_id, FileFingerprint.fingerprint_hash == file_fingerprint
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise DuplicateFileError("هذا الملف تم استيراده مسبقًا لهذا الحساب — لن يتم استيراده مرة أخرى.")


def guess_mappings_for_extraction(extraction: ExtractionResult) -> list[ColumnMapping]:
    return [guess_mapping(table.columns) for table in extraction.tables]


def build_staged_rows(
    extraction: ExtractionResult,
    mappings: list[ColumnMapping],
    default_currency: str,
    account_alias: str,
    start_index: int = 0,
) -> list[StagedRow]:
    staged: list[StagedRow] = []
    idx = start_index
    for table, mapping in zip(extraction.tables, mappings):
        normalized_rows: list[NormalizedRow] = normalize_table(table, mapping, default_currency)
        for nrow in normalized_rows:
            merchant = sanitize_merchant(nrow.raw_description)
            fp = fingerprint_row(
                date_str=nrow.txn_date.isoformat() if nrow.txn_date else "",
                amount_str=str(nrow.amount) if nrow.amount is not None else "",
                direction=nrow.direction or "",
                account_alias=account_alias,
                merchant_sanitized=merchant,
            )
            staged.append(
                StagedRow(
                    row_index=idx,
                    txn_date=nrow.txn_date,
                    amount=nrow.amount if nrow.amount is not None else Decimal("0"),
                    direction=nrow.direction or "debit",
                    currency=nrow.currency,
                    merchant_sanitized=merchant,
                    row_fingerprint=fp,
                    warnings=list(nrow.warnings),
                )
            )
            idx += 1
    return staged


def run_categorization(session, family_member_id: int, rows: list[StagedRow], settings, ai_provider=None) -> None:
    valid_rows = [r for r in rows if r.txn_date is not None]
    results: list[PendingClassification] = classify_batch(session, family_member_id, valid_rows, settings, ai_provider)
    by_index = {r.row_index: r for r in results}
    for row in rows:
        result = by_index.get(row.row_index)
        if result is None:
            row.explanation_ar = "تعذّر تصنيف هذا الصف تلقائيًا بسبب بيانات غير مكتملة."
            row.needs_review = True
            continue
        row.category_id = result.category_id
        row.confidence = result.confidence
        row.classification_source = result.source
        row.explanation_ar = result.explanation_ar
        row.matched_rule_id = result.matched_rule_id
        row.needs_review = result.needs_review


def run_duplicate_detection(rows: list[StagedRow], account_alias: str) -> list[DuplicateCandidate]:
    inputs = [
        TxnFingerprintInput(
            row_index=r.row_index, txn_date=r.txn_date, amount=r.amount, direction=r.direction,
            account_key=account_alias, merchant_sanitized=r.merchant_sanitized,
        )
        for r in rows if r.txn_date is not None
    ]
    candidates = find_duplicates(inputs)
    by_row = {r.row_index: r for r in rows}
    for c in candidates:
        by_row[c.row_index_b].is_probable_duplicate = True
        by_row[c.row_index_b].duplicate_reasons_ar = c.reasons_ar
        by_row[c.row_index_b].duplicate_of_row_index = c.row_index_a
    return candidates


def run_transfer_detection(rows: list[StagedRow], account_alias: str):
    inputs = [
        TransferCandidateTxn(row_index=r.row_index, txn_date=r.txn_date, amount=r.amount, direction=r.direction, account_key=account_alias)
        for r in rows if r.txn_date is not None
    ]
    matches = find_transfers(inputs)
    by_row = {r.row_index: r for r in rows}
    for m in matches:
        by_row[m.debit_row_index].is_transfer = True
        by_row[m.debit_row_index].transfer_pair_row_index = m.credit_row_index
        by_row[m.credit_row_index].is_transfer = True
        by_row[m.credit_row_index].transfer_pair_row_index = m.debit_row_index
    return matches


def run_cross_account_transfer_detection(session, family_member_id: int, rows: list[StagedRow], current_account_id: int):
    """Matches staged rows against already-COMMITTED transactions in the
    family member's OTHER accounts. This is the realistic path for transfer
    detection: since one import session only covers a single account's
    statement, a transfer's other leg is almost always an existing
    transaction from a previous import of the other account, not another
    row in this same batch."""
    valid_rows = [r for r in rows if r.txn_date is not None]
    if not valid_rows:
        return []

    dates = [r.txn_date for r in valid_rows]
    window_start = min(dates) - dt.timedelta(days=3)
    window_end = max(dates) + dt.timedelta(days=3)

    existing_candidates = list(
        session.execute(
            select(Transaction).where(
                Transaction.family_member_id == family_member_id,
                Transaction.account_id != current_account_id,
                Transaction.txn_date >= window_start,
                Transaction.txn_date <= window_end,
                Transaction.review_status.in_([ReviewStatus.APPROVED, ReviewStatus.AUTO_APPROVED]),
            )
        ).scalars()
    )

    staged_inputs = [
        TransferCandidateTxn(row_index=r.row_index, txn_date=r.txn_date, amount=r.amount, direction=r.direction, account_key=current_account_id)
        for r in valid_rows
    ]
    # Existing transactions get negative synthetic row indices so they never
    # collide with staged row_index values.
    existing_by_synthetic_index: dict[int, Transaction] = {}
    existing_inputs = []
    for i, txn in enumerate(existing_candidates):
        synthetic_index = -(i + 1)
        existing_by_synthetic_index[synthetic_index] = txn
        existing_inputs.append(
            TransferCandidateTxn(
                row_index=synthetic_index, txn_date=txn.txn_date, amount=txn.amount,
                direction=txn.direction.value, account_key=txn.account_id,
            )
        )

    matches = find_transfers(staged_inputs + existing_inputs)
    by_row = {r.row_index: r for r in rows}

    for m in matches:
        debit_is_staged = m.debit_row_index in by_row
        credit_is_staged = m.credit_row_index in by_row
        if debit_is_staged and credit_is_staged:
            by_row[m.debit_row_index].is_transfer = True
            by_row[m.debit_row_index].transfer_pair_row_index = m.credit_row_index
            by_row[m.credit_row_index].is_transfer = True
            by_row[m.credit_row_index].transfer_pair_row_index = m.debit_row_index
        elif debit_is_staged:
            by_row[m.debit_row_index].is_transfer = True
            by_row[m.debit_row_index].transfer_pair_existing_txn_id = existing_by_synthetic_index[m.credit_row_index].id
        elif credit_is_staged:
            by_row[m.credit_row_index].is_transfer = True
            by_row[m.credit_row_index].transfer_pair_existing_txn_id = existing_by_synthetic_index[m.debit_row_index].id

    return matches


def run_refund_detection(rows: list[StagedRow], account_alias: str):
    inputs = [
        RefundCandidateTxn(
            row_index=r.row_index, txn_date=r.txn_date, amount=r.amount, direction=r.direction,
            account_key=account_alias, merchant_sanitized=r.merchant_sanitized,
        )
        for r in rows if r.txn_date is not None
    ]
    matches = find_refund_links(inputs)
    by_row = {r.row_index: r for r in rows}
    for m in matches:
        by_row[m.credit_row_index].is_refund = True
        by_row[m.credit_row_index].refund_of_row_index = m.debit_row_index
    return matches


def commit_import(
    session,
    account: Account,
    family_member_id: int,
    file_label: str,
    file_fingerprints: list[str],
    approved_rows: list[StagedRow],
    base_currency: str,
    manual_fx_rates: dict[str, Decimal] | None = None,
) -> ImportBatch:
    manual_fx_rates = manual_fx_rates or {}

    batch = ImportBatch(account_id=account.id, label=file_label, status=ImportBatchStatus.DRAFT)
    session.add(batch)
    session.flush()

    fx_cache: dict[str, FxRate] = {}

    def _get_fx_rate(currency: str) -> FxRate:
        currency = currency.upper()
        if currency == base_currency.upper():
            rate_value = Decimal("1")
            source = FxSource.MANUAL
        else:
            rate_value = manual_fx_rates.get(currency)
            if rate_value is None:
                raise ValueError(f"لا يوجد سعر تحويل محدد للعملة {currency}.")
            source = FxSource.MANUAL
        if currency in fx_cache:
            return fx_cache[currency]
        fx = FxRate(currency=currency, rate_to_base=rate_value, base_currency=base_currency.upper(), effective_date=dt.date.today(), source=source)
        session.add(fx)
        session.flush()
        fx_cache[currency] = fx
        return fx

    row_index_to_txn_id: dict[int, int] = {}
    kept_rows = [r for r in approved_rows if not r.excluded]

    for row in kept_rows:
        fx = _get_fx_rate(row.currency)
        base_amount = convert(row.amount, fx.rate_to_base)

        category_id = row.manual_category_override if row.manual_category_override is not None else row.category_id

        if row.is_transfer:
            txn_type = TransactionType.TRANSFER
        elif row.is_refund:
            txn_type = TransactionType.REFUND
        elif row.direction == "credit":
            txn_type = TransactionType.INCOME
        else:
            txn_type = TransactionType.EXPENSE

        review_status = ReviewStatus.AUTO_APPROVED if not row.needs_review else ReviewStatus.APPROVED

        txn = Transaction(
            import_batch_id=batch.id,
            account_id=account.id,
            family_member_id=family_member_id,
            txn_date=row.txn_date,
            amount=to_money(row.amount),
            direction=TransactionDirection(row.direction),
            original_currency=row.currency.upper(),
            base_amount=base_amount,
            fx_rate_id=fx.id,
            txn_type=txn_type,
            category_id=category_id,
            merchant_sanitized=row.merchant_sanitized,
            classification_source=_map_source(row.classification_source),
            confidence=row.confidence,
            matched_rule_id=row.matched_rule_id,
            review_status=review_status,
            is_transfer=row.is_transfer,
            is_probable_duplicate=row.is_probable_duplicate,
            row_fingerprint=row.row_fingerprint,
        )
        session.add(txn)
        session.flush()
        row_index_to_txn_id[row.row_index] = txn.id

    # Second pass: link transfer/refund pairs now that all txn ids exist.
    for row in kept_rows:
        txn_id = row_index_to_txn_id.get(row.row_index)
        if txn_id is None:
            continue
        linked_row_index = row.transfer_pair_row_index if row.is_transfer else (row.refund_of_row_index if row.is_refund else None)
        linked_txn_id = row_index_to_txn_id.get(linked_row_index) if linked_row_index is not None else None
        if linked_txn_id is None and row.is_transfer and row.transfer_pair_existing_txn_id is not None:
            linked_txn_id = row.transfer_pair_existing_txn_id
            existing_txn = session.get(Transaction, linked_txn_id)
            if existing_txn is not None:
                existing_txn.linked_transaction_id = txn_id
        if linked_txn_id:
            session.get(Transaction, txn_id).linked_transaction_id = linked_txn_id
        if row.duplicate_of_row_index is not None:
            dup_txn_id = row_index_to_txn_id.get(row.duplicate_of_row_index)
            if dup_txn_id:
                session.get(Transaction, txn_id).duplicate_of_id = dup_txn_id

    for fp in file_fingerprints:
        session.add(FileFingerprint(account_id=account.id, fingerprint_hash=fp, import_batch_id=batch.id))

    batch.row_count = len(kept_rows)
    batch.status = ImportBatchStatus.COMMITTED
    batch.committed_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    return batch


def _map_source(source: str):
    from spendwise.db.models import ClassificationSource

    mapping = {
        "rule": ClassificationSource.RULE,
        "ai": ClassificationSource.AI,
        "manual": ClassificationSource.MANUAL,
        "unclassified": ClassificationSource.UNCLASSIFIED,
    }
    return mapping.get(source, ClassificationSource.UNCLASSIFIED)


def undo_last_import(session, account_id: int) -> ImportBatch | None:
    batch = session.execute(
        select(ImportBatch)
        .where(ImportBatch.account_id == account_id, ImportBatch.status == ImportBatchStatus.COMMITTED)
        .order_by(ImportBatch.committed_at.desc())
    ).scalars().first()
    if batch is None:
        return None

    txn_ids = [t.id for t in session.execute(select(Transaction).where(Transaction.import_batch_id == batch.id)).scalars()]
    if txn_ids:
        session.execute(
            Transaction.__table__.update().where(Transaction.linked_transaction_id.in_(txn_ids)).values(linked_transaction_id=None)
        )
        session.execute(
            Transaction.__table__.update().where(Transaction.duplicate_of_id.in_(txn_ids)).values(duplicate_of_id=None)
        )
        session.execute(Transaction.__table__.delete().where(Transaction.import_batch_id == batch.id))

    session.execute(FileFingerprint.__table__.delete().where(FileFingerprint.import_batch_id == batch.id))

    batch.status = ImportBatchStatus.ROLLED_BACK
    batch.rolled_back_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    return batch


def get_last_committed_batch(session, account_id: int) -> ImportBatch | None:
    return session.execute(
        select(ImportBatch)
        .where(ImportBatch.account_id == account_id, ImportBatch.status == ImportBatchStatus.COMMITTED)
        .order_by(ImportBatch.committed_at.desc())
    ).scalars().first()
