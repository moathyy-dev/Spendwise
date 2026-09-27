"""
Initialize the local SQLite database.

For Phase 1 we use Alembic migrations as the source of truth for schema
changes. This helper is used by the app on first run to ensure the schema is
up to date (runs `alembic upgrade head` programmatically) and seeds default
categories.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from spendwise.categorize.default_rules import seed_default_rules
from spendwise.db.seed import seed_default_categories
from spendwise.db.session import get_session_factory

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def run_migrations() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"فشل تطبيق ترحيلات قاعدة البيانات:\n{result.stdout}\n{result.stderr}")


def ensure_ready() -> None:
    run_migrations()
    session: Session = get_session_factory()()
    try:
        seed_default_categories(session)
        session.commit()
        seed_default_rules(session)
        session.commit()
    finally:
        session.close()
