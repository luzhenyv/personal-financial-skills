"""FastAPI dependency injection."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from src.db.session import get_db as _get_db


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session for FastAPI Depends()."""
    yield from _get_db()
