"""Initialize the application database for the active backend."""

from __future__ import annotations

import argparse

from sqlalchemy import text

from pfs.config import settings
from pfs.db.models import Base
from pfs.db.session import engine


def init_db() -> None:
    """Create all application tables for the configured backend."""
    settings.ensure_dirs()
    if settings.is_sqlite:
        settings.sqlite_database_path.parent.mkdir(parents=True, exist_ok=True)

    with engine.begin() as connection:
        if settings.is_postgresql:
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS agent_ops"))
        Base.metadata.create_all(bind=connection)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the PFS database")
    parser.add_argument(
        "--seed-tasks",
        action="store_true",
        help="Seed recurring tasks after creating tables",
    )
    args = parser.parse_args()

    init_db()
    print(f"Initialized database: {settings.database_url}")

    if args.seed_tasks:
        from scripts.seed_tasks import seed

        seed()


if __name__ == "__main__":
    main()