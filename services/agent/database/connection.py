"""Database engine and session management."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _psycopg_url(url: str) -> str:
    # Supabase hands out a bare `postgresql://` URL, which SQLAlchemy maps to the
    # psycopg2 driver we don't install. Pin it to psycopg (v3), our real driver.
    prefix = "postgresql://"
    if url.startswith(prefix):
        return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def get_engine() -> Engine:
    # Built lazily so importing the app never requires a configured database —
    # the health check and computer-use routes stay usable without one.
    global _engine
    if _engine is None:
        _engine = create_engine(
            _psycopg_url(settings.database_url),
            pool_pre_ping=True,  # Supabase closes idle connections; revalidate on checkout.
            pool_size=5,
            max_overflow=0,
        )
    return _engine


def new_session() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory()


def dispose() -> None:
    if _engine is not None:
        _engine.dispose()
