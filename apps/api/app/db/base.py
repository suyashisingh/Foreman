"""SQLAlchemy declarative base shared by all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common base for every ORM model.

    All models inherit from this class so Alembic can discover them via
    ``Base.metadata`` when generating migrations.
    """
