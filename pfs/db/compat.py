"""Cross-database compatibility helpers."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from pfs.config import settings

CompatibleJSON = JSON().with_variant(JSONB, "postgresql")


def task_table_schema() -> str | None:
    """Return the task table schema when the active backend supports schemas."""
    return None if settings.is_sqlite else "agent_ops"


def task_table_ref() -> str:
    """Return the SQL table reference for the unified task registry."""
    schema = task_table_schema()
    return "tasks" if schema is None else f"{schema}.tasks"


def task_table_args(*constraints: object) -> tuple[object, ...]:
    """Build task table args with a schema only when required."""
    schema = task_table_schema()
    if schema is None:
        return tuple(constraints)
    return (*constraints, {"schema": schema})
