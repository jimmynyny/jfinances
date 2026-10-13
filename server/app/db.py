"""SQLAlchemy engine and session helpers.

One engine per process, created lazily so importing the app never touches the
network (tests import it with no database).
"""
from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


def _normalise(url: str) -> str:
    # Railway hands out postgresql://; SQLAlchemy needs the psycopg3 driver name.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@functools.lru_cache(maxsize=1)
def engine() -> Engine:
    return create_engine(
        _normalise(settings().database_url),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        future=True,
    )


@functools.lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=engine(), expire_on_commit=False, class_=Session)


@contextlib.contextmanager
def session() -> Iterator[Session]:
    """Commit on success, roll back on error."""
    sess = _session_factory()()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session() as s:
        yield s


def ping() -> bool:
    with engine().connect() as conn:
        return conn.execute(text("SELECT 1")).scalar() == 1


def reset_engine_cache() -> None:
    engine.cache_clear()
    _session_factory.cache_clear()
