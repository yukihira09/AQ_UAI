"""Base for future ORM entities, owned by Alembic migrations."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
