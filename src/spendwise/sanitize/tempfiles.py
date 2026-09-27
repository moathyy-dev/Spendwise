"""
Safe temporary file handling for uploaded statements.

Uploaded files are NEVER copied into permanent application storage. They are
written to a dedicated temp directory, processed, and deleted immediately
after — including on error (via try/finally and a context manager).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager

_SAFE_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,6}$")


def safe_temp_filename(original_filename: str) -> str:
    """Generate a random, safe filename that preserves only the extension —
    never the user-provided name (defends against path traversal / unsafe
    filenames)."""
    ext = os.path.splitext(original_filename or "")[1].lower()
    if not _SAFE_EXT_RE.match(ext):
        ext = ""
    return f"{uuid.uuid4().hex}{ext}"


@contextmanager
def temp_upload_dir():
    """Yields a fresh temp directory; guarantees deletion afterwards, even on
    exceptions (cancellation, failure, etc.)."""
    d = tempfile.mkdtemp(prefix="spendwise_upload_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def write_uploaded_file(directory: str, original_filename: str, content: bytes) -> str:
    filename = safe_temp_filename(original_filename)
    path = os.path.join(directory, filename)
    # Defensive: ensure the resolved path stays inside `directory`
    if os.path.commonpath([os.path.abspath(directory), os.path.abspath(path)]) != os.path.abspath(directory):
        raise ValueError("مسار ملف غير آمن.")
    with open(path, "wb") as f:
        f.write(content)
    return path
