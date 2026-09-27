"""
Text-based PDF ingestion.

Only text-based PDFs are supported in Phase 1 (OCR for scanned PDFs is out of
scope). We attempt table extraction first (works well for most bank
statement layouts); if no tables are detected we fall back to line-based
text parsing, splitting on 2+ whitespace as a column separator heuristic.
"""
from __future__ import annotations

import os
import re

import pdfplumber

from spendwise.ingestion.common import (
    MAX_FILE_SIZE_MB,
    ExtractionResult,
    FileTooLargeError,
    RawTable,
    UnsupportedFileError,
)

_MULTI_SPACE = re.compile(r"\s{2,}")


def _check_file(path: str) -> None:
    if os.path.splitext(path)[1].lower() != ".pdf":
        raise UnsupportedFileError("الملف ليس بصيغة PDF.")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileTooLargeError(f"حجم الملف ({size_mb:.1f} MB) يتجاوز الحد الأقصى المسموح ({MAX_FILE_SIZE_MB} MB).")


def read_pdf(path: str) -> ExtractionResult:
    _check_file(path)
    warnings: list[str] = []
    tables: list[RawTable] = []
    total_rows = 0
    any_text_found = False

    with pdfplumber.open(path) as pdf:
        if pdf.metadata and "/Encrypt" in str(pdf.metadata):
            warnings.append("الملف قد يكون محميًا/مشفّرًا — قد يفشل الاستخراج.")

        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                any_text_found = True

            extracted_tables = page.extract_tables()
            page_had_table = False
            for t_idx, raw_table in enumerate(extracted_tables):
                if not raw_table or len(raw_table) < 2:
                    continue
                header = [str(c).strip() if c else f"عمود_{i+1}" for i, c in enumerate(raw_table[0])]
                rows = []
                for r in raw_table[1:]:
                    row_dict = {header[i]: (str(v).strip() if v else "") for i, v in enumerate(r) if i < len(header)}
                    if any(v for v in row_dict.values()):
                        rows.append(row_dict)
                if rows:
                    tables.append(
                        RawTable(
                            columns=header,
                            rows=rows,
                            source_description=f"صفحة {page_num}، جدول {t_idx + 1}",
                        )
                    )
                    total_rows += len(rows)
                    page_had_table = True

            if not page_had_table and page_text.strip():
                fallback_table = _parse_text_lines(page_text, page_num)
                if fallback_table and fallback_table.rows:
                    tables.append(fallback_table)
                    total_rows += len(fallback_table.rows)

    if not any_text_found:
        warnings.append(
            "لم يتم العثور على نص قابل للاستخراج في هذا الملف. قد يكون PDF ممسوحًا ضوئيًا (صورة) — "
            "التعرف الضوئي على الحروف (OCR) غير مدعوم في هذه المرحلة."
        )
    if not tables:
        warnings.append("لم يتم استخراج أي صفوف بيانات منظمة من ملف PDF.")

    return ExtractionResult(file_kind="pdf", tables=tables, warnings=warnings, total_rows_found=total_rows)


def _parse_text_lines(page_text: str, page_num: int) -> RawTable | None:
    """Heuristic fallback: split lines on runs of 2+ spaces into columns.
    Only keeps lines that look like transaction rows (contain a date-like
    token and a number)."""
    date_pat = re.compile(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}")
    number_pat = re.compile(r"[\d,]+\.\d{1,2}|\d+")

    candidate_rows = []
    max_cols = 0
    for line in page_text.splitlines():
        line = line.strip()
        if not line or not date_pat.search(line) or not number_pat.search(line):
            continue
        parts = [p.strip() for p in _MULTI_SPACE.split(line) if p.strip()]
        if len(parts) < 2:
            continue
        candidate_rows.append(parts)
        max_cols = max(max_cols, len(parts))

    if not candidate_rows:
        return None

    header = [f"عمود_{i+1}" for i in range(max_cols)]
    rows = []
    for parts in candidate_rows:
        row_dict = {header[i]: (parts[i] if i < len(parts) else "") for i in range(max_cols)}
        rows.append(row_dict)

    return RawTable(columns=header, rows=rows, source_description=f"صفحة {page_num} (استخراج نصي)")
