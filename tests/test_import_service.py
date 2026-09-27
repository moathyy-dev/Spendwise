import datetime as dt
from decimal import Decimal

import pytest

from spendwise.db.models import Account, FamilyMember, ImportBatchStatus, ReviewStatus, Transaction
from spendwise.import_service import (
    DuplicateFileError,
    StagedRow,
    check_file_not_duplicate,
    commit_import,
    run_cross_account_transfer_detection,
    run_duplicate_detection,
    run_refund_detection,
    undo_last_import,
)
from spendwise.sanitize.fingerprint import fingerprint_file_bytes


def _make_member_and_account(session, name="tester", alias="حساب الاختبار"):
    member = FamilyMember(name=name)
    session.add(member)
    session.flush()
    account = Account(family_member_id=member.id, alias=alias)
    session.add(account)
    session.flush()
    return member, account


def test_check_file_not_duplicate_passes_for_new_file(db_session):
    _, account = _make_member_and_account(db_session)
    fp = fingerprint_file_bytes(b"some file content")
    check_file_not_duplicate(db_session, account.id, fp)  # should not raise


def test_check_file_not_duplicate_raises_for_known_fingerprint(db_session):
    from spendwise.db.models import FileFingerprint

    _, account = _make_member_and_account(db_session)
    fp = fingerprint_file_bytes(b"some file content")
    db_session.add(FileFingerprint(account_id=account.id, fingerprint_hash=fp))
    db_session.commit()

    with pytest.raises(DuplicateFileError):
        check_file_not_duplicate(db_session, account.id, fp)


def _basic_row(row_index, amount="100.00", direction="debit", category_id=None):
    return StagedRow(
        row_index=row_index,
        txn_date=dt.date(2026, 8, 1),
        amount=Decimal(amount),
        direction=direction,
        currency="SAR",
        merchant_sanitized="متجر اختبار",
        row_fingerprint=f"fp-{row_index}",
        category_id=category_id,
        needs_review=False,
    )


def test_commit_import_creates_transactions_and_fingerprint(db_session):
    member, account = _make_member_and_account(db_session)
    rows = [_basic_row(0)]

    batch = commit_import(
        session=db_session, account=account, family_member_id=member.id, file_label="test import",
        file_fingerprints=["file-fp-1"], approved_rows=rows, base_currency="SAR",
    )
    db_session.commit()

    assert batch.status == ImportBatchStatus.COMMITTED
    txns = db_session.query(Transaction).filter(Transaction.import_batch_id == batch.id).all()
    assert len(txns) == 1
    assert txns[0].base_amount == Decimal("100.00")


def test_commit_import_excludes_excluded_rows(db_session):
    member, account = _make_member_and_account(db_session)
    row1 = _basic_row(0)
    row2 = _basic_row(1)
    row2.excluded = True

    batch = commit_import(
        session=db_session, account=account, family_member_id=member.id, file_label="test",
        file_fingerprints=["fp-x"], approved_rows=[row1, row2], base_currency="SAR",
    )
    db_session.commit()
    txns = db_session.query(Transaction).filter(Transaction.import_batch_id == batch.id).all()
    assert len(txns) == 1


def test_commit_import_requires_manual_fx_for_foreign_currency(db_session):
    member, account = _make_member_and_account(db_session)
    row = _basic_row(0)
    row.currency = "USD"

    with pytest.raises(ValueError):
        commit_import(
            session=db_session, account=account, family_member_id=member.id, file_label="test",
            file_fingerprints=["fp-usd"], approved_rows=[row], base_currency="SAR",
        )


def test_commit_import_converts_foreign_currency_with_manual_rate(db_session):
    member, account = _make_member_and_account(db_session)
    row = _basic_row(0, amount="100.00")
    row.currency = "USD"

    batch = commit_import(
        session=db_session, account=account, family_member_id=member.id, file_label="test",
        file_fingerprints=["fp-usd2"], approved_rows=[row], base_currency="SAR",
        manual_fx_rates={"USD": Decimal("3.75")},
    )
    db_session.commit()
    txn = db_session.query(Transaction).filter(Transaction.import_batch_id == batch.id).first()
    assert txn.base_amount == Decimal("375.00")


def test_undo_last_import_removes_transactions(db_session):
    member, account = _make_member_and_account(db_session)
    row = _basic_row(0)
    batch = commit_import(
        session=db_session, account=account, family_member_id=member.id, file_label="test",
        file_fingerprints=["fp-undo"], approved_rows=[row], base_currency="SAR",
    )
    db_session.commit()

    undone = undo_last_import(db_session, account.id)
    db_session.commit()
    assert undone.id == batch.id
    assert undone.status == ImportBatchStatus.ROLLED_BACK
    remaining = db_session.query(Transaction).filter(Transaction.import_batch_id == batch.id).all()
    assert remaining == []


def test_undo_last_import_allows_reimport_of_same_file(db_session):
    """After undo, the file fingerprint must be removed so the same file can
    be re-imported (per the spec's safe-undo requirement)."""
    member, account = _make_member_and_account(db_session)
    row = _basic_row(0)
    commit_import(
        session=db_session, account=account, family_member_id=member.id, file_label="test",
        file_fingerprints=["fp-reimport"], approved_rows=[row], base_currency="SAR",
    )
    db_session.commit()
    undo_last_import(db_session, account.id)
    db_session.commit()

    check_file_not_duplicate(db_session, account.id, "fp-reimport")  # should not raise


def test_run_cross_account_transfer_detection_matches_existing_committed_txn(db_session):
    """A transfer's other leg is normally an already-committed transaction
    in a DIFFERENT account of the same family member (from a previous
    import), not another row in the same single-account import batch."""
    member, account_a = _make_member_and_account(db_session, alias="account_a")
    account_b = Account(family_member_id=member.id, alias="account_b")
    db_session.add(account_b)
    db_session.flush()

    existing_row = _basic_row(0, amount="500.00", direction="credit")
    batch = commit_import(
        session=db_session, account=account_b, family_member_id=member.id, file_label="prior import",
        file_fingerprints=["fp-existing"], approved_rows=[existing_row], base_currency="SAR",
    )
    db_session.commit()

    new_debit_row = _basic_row(0, amount="500.00", direction="debit")
    run_cross_account_transfer_detection(db_session, member.id, [new_debit_row], account_a.id)

    assert new_debit_row.is_transfer
    assert new_debit_row.transfer_pair_existing_txn_id is not None


def test_run_duplicate_detection_marks_second_row():
    r1 = StagedRow(0, dt.date(2026, 8, 1), Decimal("50.00"), "debit", "SAR", "متجر", "fp0")
    r2 = StagedRow(1, dt.date(2026, 8, 1), Decimal("50.00"), "debit", "SAR", "متجر", "fp1")
    run_duplicate_detection([r1, r2], "acc1")
    assert r2.is_probable_duplicate
    assert not r1.is_probable_duplicate


def test_run_refund_detection_marks_credit_row():
    debit = StagedRow(0, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "SAR", "مطعم", "fp0")
    credit = StagedRow(1, dt.date(2026, 8, 5), Decimal("100.00"), "credit", "SAR", "مطعم", "fp1")
    run_refund_detection([debit, credit], "acc1")
    assert credit.is_refund
    assert credit.refund_of_row_index == 0
