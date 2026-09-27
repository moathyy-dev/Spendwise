from __future__ import annotations

import dataclasses

import pytest


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    salt = "test-fixed-salt-not-secret"

    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SPENDWISE_FINGERPRINT_SALT", salt)

    import spendwise.db.session as session_module

    session_module._engine = None
    session_module._SessionLocal = None

    from spendwise.db.models import Base
    from spendwise.db.seed import seed_default_categories

    engine = session_module.get_engine()
    Base.metadata.create_all(engine)

    factory = session_module.get_session_factory()
    session = factory()
    seed_default_categories(session)
    session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def settings_factory():
    from spendwise.config import Settings

    def _make(**overrides):
        base = Settings(
            ai_provider="none",
            enable_online_ai=False,
            confidence_auto_accept=95,
            confidence_ai_fallback=80,
            base_currency="SAR",
        )
        return dataclasses.replace(base, **overrides)

    return _make
