"""
Heuristic column mapping: guesses which raw column corresponds to which
canonical transaction field, for both Arabic and English bank statement
headers. The user can always override the guess manually in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CANONICAL_FIELDS = ["date", "description", "amount", "debit", "credit", "currency", "balance"]

_KEYWORDS: dict[str, list[str]] = {
    "date": ["date", "تاريخ", "التاريخ", "value date", "posting date", "تاريخ العملية", "تاريخ القيمة"],
    "description": [
        "description", "details", "narration", "memo", "بيان", "الوصف", "تفاصيل",
        "وصف العملية", "البيان", "particulars", "transaction details",
    ],
    "debit": ["debit", "withdrawal", "مدين", "سحب", "خصم", "debit amount"],
    "credit": ["credit", "deposit", "دائن", "إيداع", "إضافة", "credit amount"],
    "amount": ["amount", "value", "المبلغ", "قيمة", "مبلغ العملية", "amount (sar)"],
    "currency": ["currency", "العملة", "ccy"],
    "balance": ["balance", "الرصيد", "رصيد بعد العملية", "running balance"],
}


@dataclass
class ColumnMapping:
    mapping: dict[str, str | None] = field(default_factory=dict)  # canonical -> raw column name
    unmapped_raw_columns: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)

    def is_minimally_viable(self) -> bool:
        has_date = bool(self.mapping.get("date"))
        has_amount = bool(self.mapping.get("amount") or (self.mapping.get("debit") or self.mapping.get("credit")))
        return has_date and has_amount


def guess_mapping(columns: list[str]) -> ColumnMapping:
    result = ColumnMapping()
    used_raw: set[str] = set()

    for canonical in CANONICAL_FIELDS:
        keywords = _KEYWORDS[canonical]
        best_col = None
        for col in columns:
            if col in used_raw:
                continue
            norm = col.strip().lower()
            if any(kw in norm for kw in keywords):
                best_col = col
                break
        result.mapping[canonical] = best_col
        if best_col:
            used_raw.add(best_col)
        else:
            result.confidence_notes.append(f"لم يتم العثور تلقائيًا على عمود لحقل '{canonical}'.")

    result.unmapped_raw_columns = [c for c in columns if c not in used_raw]
    return result


def apply_manual_overrides(mapping: ColumnMapping, overrides: dict[str, str | None]) -> ColumnMapping:
    """overrides: canonical_field -> raw_column_name (or None to clear)."""
    new_mapping = dict(mapping.mapping)
    new_mapping.update(overrides)
    used = {v for v in new_mapping.values() if v}
    return ColumnMapping(
        mapping=new_mapping,
        unmapped_raw_columns=[c for c in mapping.unmapped_raw_columns if c not in used],
        confidence_notes=[],
    )
