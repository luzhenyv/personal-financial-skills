"""Shared helpers for Prefect flows that update the unified task registry."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text as sa_text

from pfs.db.session import get_session


def update_registry(skill: str, status: str, error_message: str | None = None):
    """Update the recurring-task row in agent_ops.tasks for *skill*."""
    session = get_session()
    try:
        now = datetime.now(timezone.utc)
        if status == "running":
            session.execute(
                sa_text("""
                    UPDATE agent_ops.tasks
                    SET status = 'running', started_at = :now
                    WHERE skill = :skill AND executor = 'prefect' AND type = 'recurring'
                """),
                {"skill": skill, "now": now},
            )
        elif status == "completed":
            session.execute(
                sa_text("""
                    UPDATE agent_ops.tasks
                    SET status = 'completed', completed_at = :now, last_run_at = :now,
                        error_message = NULL
                    WHERE skill = :skill AND executor = 'prefect' AND type = 'recurring'
                """),
                {"skill": skill, "now": now},
            )
        elif status == "failed":
            session.execute(
                sa_text("""
                    UPDATE agent_ops.tasks
                    SET status = 'failed', completed_at = :now, error_message = :err
                    WHERE skill = :skill AND executor = 'prefect' AND type = 'recurring'
                """),
                {"skill": skill, "now": now, "err": error_message},
            )
        session.commit()
    finally:
        session.close()
