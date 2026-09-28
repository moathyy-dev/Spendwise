from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from spendwise.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        # check_same_thread=False is an SQLite-specific pysqlite option
        # (needed because Streamlit can touch the connection from more than
        # one thread); it is not a valid connection argument for other
        # backends such as Postgres, so it's only passed for sqlite:// URLs.
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Session:
    """Provide a transactional scope. Commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
