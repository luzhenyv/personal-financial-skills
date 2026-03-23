"""Copy application data from PostgreSQL into a SQLite database."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from sqlalchemy import MetaData, Table, create_engine, delete, select, text

TABLE_MAPPINGS: Sequence[tuple[str | None, str, str]] = (
    (None, "companies", "companies"),
    (None, "income_statements", "income_statements"),
    (None, "balance_sheets", "balance_sheets"),
    (None, "cash_flow_statements", "cash_flow_statements"),
    (None, "financial_metrics", "financial_metrics"),
    (None, "revenue_segments", "revenue_segments"),
    (None, "daily_prices", "daily_prices"),
    (None, "analysis_reports", "analysis_reports"),
    (None, "sec_filings", "sec_filings"),
    (None, "stock_splits", "stock_splits"),
    (None, "watchlist", "watchlist"),
    (None, "etl_runs", "etl_runs"),
    ("agent_ops", "tasks", "tasks"),
)


def _load_table(engine, name: str, schema: str | None = None) -> Table:
    metadata = MetaData()
    return Table(name, metadata, schema=schema, autoload_with=engine)


def _copy_table(source_engine, target_engine, source_schema: str | None, source_name: str, target_name: str) -> int:
    source_table = _load_table(source_engine, source_name, schema=source_schema)
    target_table = _load_table(target_engine, target_name)

    with source_engine.connect() as source_conn:
        rows = [dict(row) for row in source_conn.execute(select(source_table)).mappings()]

    with target_engine.begin() as target_conn:
        if rows:
            target_conn.execute(target_table.insert(), rows)
    return len(rows)


def _clear_target_tables(target_engine) -> None:
    with target_engine.begin() as target_conn:
        target_conn.execute(text("PRAGMA foreign_keys=OFF"))
        for _, _, target_name in reversed(TABLE_MAPPINGS):
            target_table = _load_table(target_engine, target_name)
            target_conn.execute(delete(target_table))
        target_conn.execute(text("PRAGMA foreign_keys=ON"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate PostgreSQL data into SQLite")
    parser.add_argument("--source-url", required=True, help="PostgreSQL source database URL")
    parser.add_argument("--target-url", required=True, help="SQLite target database URL")
    parser.add_argument(
        "--init-target",
        action="store_true",
        help="Initialize the target database before copying data",
    )
    args = parser.parse_args()

    if not args.source_url.startswith("postgresql"):
        raise SystemExit("--source-url must point to PostgreSQL")
    if not args.target_url.startswith("sqlite"):
        raise SystemExit("--target-url must point to SQLite")

    if args.init_target:
        env = os.environ.copy()
        env["DATABASE_URL"] = args.target_url
        import subprocess
        import sys

        subprocess.run([sys.executable, "scripts/init_db.py"], check=True, env=env)

    source_engine = create_engine(args.source_url)
    target_engine = create_engine(args.target_url, connect_args={"check_same_thread": False})

    with target_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("PRAGMA busy_timeout=5000"))

    _clear_target_tables(target_engine)

    print("Migrating tables:")
    for source_schema, source_name, target_name in TABLE_MAPPINGS:
        count = _copy_table(source_engine, target_engine, source_schema, source_name, target_name)
        source_ref = source_name if source_schema is None else f"{source_schema}.{source_name}"
        print(f"  {source_ref} -> {target_name}: {count} rows")


if __name__ == "__main__":
    main()