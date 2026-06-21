"""Database engine + session management.

If DATABASE_URL is unset, db_enabled() is False and the app runs entirely on its
hardcoded mappings + in-memory cache (so local dev and the test suite need no
Postgres). When set, we create a pooled engine and hand out sessions.

Normalizes the common 'postgres://' scheme to 'postgresql+psycopg://' so URLs
from hosts like Render/Heroku work with the modern psycopg 3 driver.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from ..config import settings
from ..core.logging_setup import get_logger

logger = get_logger("db")

_engine = None
_SessionLocal = None


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def db_enabled() -> bool:
    return bool(settings.database_url)


def init_engine():
    """Create the engine + session factory once. No-op if DB disabled."""
    global _engine, _SessionLocal
    if not db_enabled() or _engine is not None:
        return _engine

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = _normalize_url(settings.database_url)
    _engine = create_engine(
        url,
        pool_pre_ping=True,     # recycle dead connections (managed PG drops idle ones)
        pool_size=5,
        max_overflow=10,
        future=True,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    logger.info("database engine initialized")
    return _engine


def get_engine():
    return init_engine()


@contextmanager
def session_scope() -> Iterator["object"]:
    """Transactional session context. Commits on success, rolls back on error."""
    if _SessionLocal is None:
        init_engine()
    if _SessionLocal is None:
        raise RuntimeError("database is not configured (DATABASE_URL unset)")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
