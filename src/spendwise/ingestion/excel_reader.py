"""
Excel ingestion (.xlsx / .xls).

Security notes:
- Files are opened without executing macros or embedded content
  (openpyxl never executes VBA; we also explicitly refuse .xlsm/.xlsb).
- Formulas are read as their cached values only (data_only=True); we never
  evaluate formulas ourselves.
- No file is copied into permanent storage — callers are expected to read
  from a temporary path and delete it after processing (see sanitize/tempfiles).
"""
from __future__ import annotations

import os

import pandas as pd

from spendwise.ingestion.common import (
    MAX_FILE_SIZE_MB,
    ExtractionResult,
    FileTooLargeError,
    RawTable,
    UnsupportedFileError,
)

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
BLOCKED_MACRO_EXTENSIONS = {".xlsm", ".xlsb"}


def _check_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in BLOCKED_MACRO_EXTENSIONS:
        raise UnsupportedFileError(
            "لا يمكن استيراد ملفات Excel التي تحتوي على وحدات ماكرو (.xlsm/.xlsb) لأسباب أمنية."
        )
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileError(f"صيغة الملف غير مدعومة: {ext}")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileTooLargeError(f"حجم الملف ({size_mb:.1f} MB) يتجاوز الحد الأقصى المسموح ({MAX_FILE_SIZE_MB} MB).")
    return ext


def read_excel(path: str) -> ExtractionResult:
    ext = _check_file(path)
    engine = "openpyxl" if ext == ".xlsx" else "xlrd"

    warnings: list[str] = []
    tables: list[RawTable] = []
    total_rows = 0

    try:
        sheets = pd.read_excel(path, sheet_name=None, engine=engine, dtype=str, header=None)
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedFileError(f"تعذّرت قراءة ملف Excel: {exc}") from exc

    for sheet_name, raw_df in sheets.items():
        if raw_df.empty:
            continue
        header_row_idx = _guess_header_row(raw_df)
        if header_row_idx is None:
            warnings.append(f"لم يتم العثور على صف عناوين واضح في الورقة '{sheet_name}' — تم تجاهلها.")
            continue

        header = [str(c).strip() if str(c).strip() != "nan" else f"عمود_{i+1}" for i, c in enumerate(raw_df.iloc[header_row_idx])]
        body = raw_df.iloc[header_row_idx + 1 :]
        body = body.dropna(how="all")

        rows = []
        for _, row in body.iterrows():
            row_dict = {header[i]: (str(v).strip() if pd.notna(v) else "") for i, v in enumerate(row) if i < len(header)}
            if any(v for v in row_dict.values()):
                rows.append(row_dict)

        if not rows:
            continue

        tables.append(RawTable(columns=header, rows=rows, source_description=f"ورقة: {sheet_name}"))
        total_rows += len(rows)

    if not tables:
        warnings.append("لم يتم استخراج أي بيانات صالحة من ملف Excel.")

    return ExtractionResult(file_kind="excel", tables=tables, warnings=warnings, total_rows_found=total_rows)


def _guess_header_row(df: pd.DataFrame, max_scan_rows: int = 15) -> int | None:
    """Scan the first N rows to find the most likely header row: the row with
    the most non-empty distinct string cells."""
    best_idx, best_score = None, 0
    for i in range(min(max_scan_rows, len(df))):
        row = df.iloc[i]
        non_empty = [str(v).strip() for v in row if pd.notna(v) and str(v).strip() != ""]
        score = len(set(non_empty))
        if score >= 3 and score > best_score:
            best_score = score
            best_idx = i
    return best_idx
