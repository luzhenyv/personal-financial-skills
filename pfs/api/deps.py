"""Shared FastAPI dependencies.

Centralised so every router imports from one place.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from pfs.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
