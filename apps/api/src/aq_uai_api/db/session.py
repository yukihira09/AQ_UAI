"""Database connections: one engine per process, sessions per request."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from aq_uai_api.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        hide_parameters=True,
        isolation_level="READ COMMITTED",
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 3},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session


@contextmanager
def write_transaction() -> Iterator[Session]:
    """Own one fresh write session, committing before returning to the caller."""
    with get_session_factory().begin() as session:
        yield session
