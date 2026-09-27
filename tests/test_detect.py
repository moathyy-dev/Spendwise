import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from spendwise.detect.anomalies import detect_anomalies
from spendwise.detect.duplicates import TxnFingerprintInput, find_duplicates
from spendwise.detect.recurring import detect_recurring
from spendwise.detect.refunds import RefundCandidateTxn, find_refund_links
from spendwise.detect.transfers import TransferCandidateTxn, find_transfers


def test_find_duplicates_flags_same_day_same_amount():
    rows = [
        TxnFingerprintInput(0, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "acc1", "ستاربكس"),
        TxnFingerprintInput(1, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "acc1", "ستاربكس"),
    ]
    candidates = find_duplicates(rows)
    assert len(candidates) == 1
    assert candidates[0].score >= 80


def test_find_duplicates_no_match_different_amount():
    rows = [
        TxnFingerprintInput(0, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "acc1", "ستاربكس"),
        TxnFingerprintInput(1, dt.date(2026, 8, 1), Decimal("50.00"), "debit", "acc1", "ستاربكس"),
    ]
    assert find_duplicates(rows) == []


def test_find_duplicates_out_of_window():
    rows = [
        TxnFingerprintInput(0, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "acc1", "ستاربكس"),
        TxnFingerprintInput(1, dt.date(2026, 8, 10), Decimal("100.00"), "debit", "acc1", "ستاربكس"),
    ]
    assert find_duplicates(rows) == []


def test_find_transfers_matches_debit_credit_different_accounts():
    rows = [
        TransferCandidateTxn(0, dt.date(2026, 8, 1), Decimal("500.00"), "debit", "acc1"),
        TransferCandidateTxn(1, dt.date(2026, 8, 1), Decimal("500.00"), "credit", "acc2"),
    ]
    matches = find_transfers(rows)
    assert len(matches) == 1
    assert matches[0].debit_row_index == 0
    assert matches[0].credit_row_index == 1


def test_find_transfers_ignores_same_account():
    rows = [
        TransferCandidateTxn(0, dt.date(2026, 8, 1), Decimal("500.00"), "debit", "acc1"),
        TransferCandidateTxn(1, dt.date(2026, 8, 1), Decimal("500.00"), "credit", "acc1"),
    ]
    assert find_transfers(rows) == []


def test_find_refund_links_matches_prior_debit():
    rows = [
        RefundCandidateTxn(0, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "acc1", "مطعم"),
        RefundCandidateTxn(1, dt.date(2026, 8, 5), Decimal("100.00"), "credit", "acc1", "مطعم"),
    ]
    matches = find_refund_links(rows)
    assert len(matches) == 1
    assert matches[0].debit_row_index == 0
    assert matches[0].credit_row_index == 1


def test_find_refund_links_requires_same_merchant():
    rows = [
        RefundCandidateTxn(0, dt.date(2026, 8, 1), Decimal("100.00"), "debit", "acc1", "مطعم"),
        RefundCandidateTxn(1, dt.date(2026, 8, 5), Decimal("100.00"), "credit", "acc1", "متجر آخر"),
    ]
    assert find_refund_links(rows) == []


@dataclass
class _FakeTxn:
    merchant_sanitized: str
    amount: Decimal
    txn_date: dt.date
    id: int = 0


def test_detect_recurring_flags_monthly_similar_amounts():
    txns = [
        _FakeTxn("نتفلكس", Decimal("45.00"), dt.date(2026, 6, 1)),
        _FakeTxn("نتفلكس", Decimal("45.00"), dt.date(2026, 7, 2)),
        _FakeTxn("نتفلكس", Decimal("46.00"), dt.date(2026, 8, 1)),
    ]
    groups = detect_recurring(txns)
    assert len(groups) == 1
    assert groups[0].merchant_sanitized == "نتفلكس"


def test_detect_recurring_ignores_irregular_intervals():
    txns = [
        _FakeTxn("متجر", Decimal("45.00"), dt.date(2026, 6, 1)),
        _FakeTxn("متجر", Decimal("45.00"), dt.date(2026, 6, 5)),
    ]
    assert detect_recurring(txns) == []


@dataclass
class _FakeExpenseTxn:
    id: int
    category_id: int
    amount: Decimal


def test_detect_anomalies_flags_large_outlier():
    txns = [_FakeExpenseTxn(i, 1, Decimal("50.00")) for i in range(6)]
    txns.append(_FakeExpenseTxn(99, 1, Decimal("500.00")))
    flags = detect_anomalies(txns, min_history=5)
    assert any(f.row_id == 99 for f in flags)


def test_detect_anomalies_no_flags_for_consistent_spending():
    txns = [_FakeExpenseTxn(i, 1, Decimal("50.00")) for i in range(6)]
    assert detect_anomalies(txns, min_history=5) == []
