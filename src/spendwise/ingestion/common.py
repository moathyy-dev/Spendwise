"""Common data structures shared by all file ingestion adapters."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawTable:
    """A raw, un-normalized table extracted from a source file.

    columns: the original column headers as found in the file (Arabic/English)
    rows: list of dict rows, keyed by the original column headers
    source_description: human-readable note about where this table came from
                         (e.g. "sheet 1" or "page 2, table 1") — never contains
                         file content itself beyond what's in rows/columns.
    """

    columns: list[str]
    rows: list[dict]
    source_description: str


@dataclass
class ExtractionResult:
    file_kind: str  # "excel" | "pdf"
    tables: list[RawTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_rows_found: int = 0

    @property
    def is_empty(self) -> bool:
        return self.total_rows_found == 0


class UnsupportedFileError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


MAX_FILE_SIZE_MB = 25
