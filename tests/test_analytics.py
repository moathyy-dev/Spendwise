import datetime as dt
from decimal import Decimal

from spendwise.analytics.budget import compute_budget_status, set_budget
from spendwise.analytics.comparisons import compute_comparison
from spendwise.analytics.metrics import compute_period_metrics
from spendwise.db.models import (
    Account,
    Category,
    FamilyMember,
    ImportBatch,
    ImportBatchStatus,
    ReviewStatus,
    Transaction,
    TransactionDirection,
    TransactionType,
)


def _setup_member(session):
    member = FamilyMember(name="tester")
    session.add(member)
    session.flush()
    account = Account(family_member_id=member.id, alias="acc")
    session.add(account)
    session.flush()
    batch = ImportBatch(account_id=account.id, label="test", status=ImportBatchStatus.COMMITTED)
    session.add(batch)
    session.flush()
    category = session.query(Category).filter(Category.parent_id.isnot(None)).first()
    return member, account, batch, category


def _txn(account, batch, member, category, **kwargs):
    defaults = dict(
        import_batch_id=batch.id, account_id=account.id, family_member_id=member.id,
        txn_date=dt.date(2026, 8, 5), amount=Decimal("100.00"), direction=TransactionDirection.DEBIT,
        original_currency="SAR", base_amount=Decimal("100.00"), txn_type=TransactionType.EXPENSE,
        category_id=category.id, merchant_sanitized="متجر", review_status=ReviewStatus.APPROVED,
        row_fingerprint="fp",
    )
    defaults.update(kwargs)
    return Transaction(**defaults)


def test_compute_period_metrics_excludes_transfers(db_session):
    member, account, batch, category = _setup_member(db_session)
    db_session.add(_txn(account, batch, member, category, row_fingerprint="fp1"))
    db_session.add(_txn(account, batch, member, category, txn_type=TransactionType.TRANSFER, row_fingerprint="fp2"))
    db_session.commit()

    metrics = compute_period_metrics(db_session, member.id, "2026-08")
    assert metrics.total_expenses == Decimal("100.00")
    assert metrics.transfers_total == Decimal("100.00")


def test_compute_period_metrics_includes_auto_approved_transactions(db_session):
    """Regression test: commit_import marks high-confidence rows as
    AUTO_APPROVED (not APPROVED) — metrics must count both statuses, or
    correctly-classified transactions would silently vanish from the
    dashboard while still being in the database."""
    member, account, batch, category = _setup_member(db_session)
    db_session.add(_txn(account, batch, member, category, review_status=ReviewStatus.AUTO_APPROVED, row_fingerprint="fp1"))
    db_session.commit()

    metrics = compute_period_metrics(db_session, member.id, "2026-08")
    assert metrics.has_sufficient_data
    assert metrics.total_expenses == Decimal("100.00")


def test_compute_period_metrics_deducts_refund_from_category(db_session):
    member, account, batch, category = _setup_member(db_session)
    db_session.add(_txn(account, batch, member, category, amount=Decimal("100.00"), base_amount=Decimal("100.00"), row_fingerprint="fp1"))
    db_session.add(
        _txn(
            account, batch, member, category, txn_type=TransactionType.REFUND, direction=TransactionDirection.CREDIT,
            amount=Decimal("30.00"), base_amount=Decimal("30.00"), row_fingerprint="fp2",
        )
    )
    db_session.commit()

    metrics = compute_period_metrics(db_session, member.id, "2026-08")
    assert metrics.category_totals[category.id] == Decimal("70.00")
    assert metrics.refunds_deducted_total == Decimal("30.00")


def test_compute_period_metrics_insufficient_data_message(db_session):
    member = FamilyMember(name="empty_tester")
    db_session.add(member)
    db_session.commit()
    metrics = compute_period_metrics(db_session, member.id, "2026-08")
    assert not metrics.has_sufficient_data
    assert metrics.insufficient_data_reason_ar


def test_compute_comparison_notes_missing_previous_month(db_session):
    member, account, batch, category = _setup_member(db_session)
    db_session.add(_txn(account, batch, member, category, row_fingerprint="fp1"))
    db_session.commit()

    comparison = compute_comparison(db_session, member.id, "2026-08")
    assert comparison.previous is None
    assert comparison.note_ar is not None


def test_budget_status_computes_remaining_and_pct(db_session):
    member, account, batch, category = _setup_member(db_session)
    db_session.add(_txn(account, batch, member, category, row_fingerprint="fp1"))
    db_session.commit()
    set_budget(db_session, member.id, "2026-08", Decimal("500.00"))
    db_session.commit()

    metrics = compute_period_metrics(db_session, member.id, "2026-08")
    status = compute_budget_status(db_session, member.id, "2026-08", metrics)
    assert status.remaining == Decimal("400.00")
    assert status.consumed_pct == Decimal("20.00")


def test_budget_status_none_when_no_budget_set(db_session):
    member, account, batch, category = _setup_member(db_session)
    db_session.add(_txn(account, batch, member, category, row_fingerprint="fp1"))
    db_session.commit()
    metrics = compute_period_metrics(db_session, member.id, "2026-08")
    status = compute_budget_status(db_session, member.id, "2026-08", metrics)
    assert status.budget_amount is None
    assert status.remaining is None
