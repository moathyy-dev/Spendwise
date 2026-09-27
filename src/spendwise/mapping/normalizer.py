"""
Normalizes raw extracted rows (using a ColumnMapping) into a canonical
in-memory transaction shape. This is the last stage where the raw
description text still exists — sanitize.sanitizer strips it immediately
afterwards before anything is persisted.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from spendwise.ingestion.common import RawTable
from spendwise.mapping.column_mapper import ColumnMapping
from spendwise.money import to_money

_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
    "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d.%m.%Y", "%Y.%m.%d",
    "%d-%b-%Y", "%d %b %Y", "%d/%m/%y", "%m/%d/%y",
]


@dataclass
class NormalizedRow:
    row_index: int
    txn_date: dt.date | None
    amount: Decimal | None
    direction: str | None  # "debit" | "credit"
    raw_description: str
    currency: str
    balance: Decimal | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.txn_date is not None and self.amount is not None and self.direction is not None


def _clean_number_string(raw: str) -> str:
    s = raw.strip().translate(_ARABIC_INDIC_DIGITS)
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    s = s.replace("SAR", "").replace("ر.س", "").replace("﷼", "").strip()
    s = re.sub(r"[^\d.,\-]", "", s)
    if s.count(",") > 0 and s.count(".") > 0:
        # Assume comma = thousands separator
        s = s.replace(",", "")
    elif s.count(",") > 0 and s.count(".") == 0:
        # Could be thousands sep (1,234) or decimal comma (1,50) — heuristic:
        last_group = s.split(",")[-1]
        if len(last_group) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    if negative and not s.startswith("-"):
        s = "-" + s
    return s


def parse_amount(raw: str) -> Decimal | None:
    if raw is None:
        return None
    s = _clean_number_string(str(raw))
    if not s or s in {"-", "."}:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date(raw: str) -> dt.date | None:
    if raw is None:
        return None
    s = str(raw).strip().translate(_ARABIC_INDIC_DIGITS)
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Try to salvage from a datetime-looking prefix e.g. "2026-08-21 10:22:00"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return dt.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def normalize_table(table: RawTable, mapping: ColumnMapping, default_currency: str) -> list[NormalizedRow]:
    normalized: list[NormalizedRow] = []
    date_col = mapping.mapping.get("date")
    desc_col = mapping.mapping.get("description")
    amount_col = mapping.mapping.get("amount")
    debit_col = mapping.mapping.get("debit")
    credit_col = mapping.mapping.get("credit")
    currency_col = mapping.mapping.get("currency")
    balance_col = mapping.mapping.get("balance")

    for idx, row in enumerate(table.rows):
        warnings: list[str] = []

        txn_date = parse_date(row.get(date_col, "")) if date_col else None
        if txn_date is None:
            warnings.append("تعذّر التعرف على التاريخ في هذا الصف.")

        description = row.get(desc_col, "") if desc_col else ""

        amount = None
        direction = None
        if amount_col:
            amount = parse_amount(row.get(amount_col, ""))
            if amount is not None:
                direction = "debit" if amount < 0 else "credit"
                amount = abs(amount)
        elif debit_col or credit_col:
            debit_val = parse_amount(row.get(debit_col, "")) if debit_col else None
            credit_val = parse_amount(row.get(credit_col, "")) if credit_col else None
            if debit_val:
                amount, direction = abs(debit_val), "debit"
            elif credit_val:
                amount, direction = abs(credit_val), "credit"

        if amount is None or direction is None:
            warnings.append("تعذّر التعرف على المبلغ أو اتجاه العملية (مدين/دائن) في هذا الصف.")

        currency = (row.get(currency_col, "").strip().upper() if currency_col else "") or default_currency

        balance = parse_amount(row.get(balance_col, "")) if balance_col else None

        money_amount = None
        if amount is not None:
            try:
                money_amount = to_money(amount)
            except Exception:  # noqa: BLE001
                warnings.append("قيمة المبلغ غير صالحة.")

        normalized.append(
            NormalizedRow(
                row_index=idx,
                txn_date=txn_date,
                amount=money_amount,
                direction=direction,
                raw_description=description,
                currency=currency,
                balance=balance,
                warnings=warnings,
            )
        )

    return normalized
