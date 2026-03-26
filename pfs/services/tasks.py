"""Task management service — CRUD for the unified task registry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from pfs.tasks.models import Task


def get_schedule(db: Session) -> list[dict]:
    """All recurring tasks — the unified schedule view."""
    rows = (
        db.query(Task)
        .filter(Task.type == "recurring")
        .order_by(Task.server, Task.skill)
        .all()
    )
    return [r.to_dict() for r in rows]


def get_stats(db: Session) -> dict:
    """Summary counts by status and executor."""
    from sqlalchemy import func

    rows = (
        db.query(Task.status, Task.executor, func.count())
        .group_by(Task.status, Task.executor)
        .all()
    )
    stats: dict = {}
    for status, executor, count in rows:
        stats.setdefault(status, {})[executor] = count
    return stats


def next_task(db: Session) -> dict | None:
    """Return highest-priority pending task for dispatcher, or ``None``."""
    task = (
        db.query(Task)
        .filter(
            Task.status == "pending",
            Task.executor.in_(["openclaw", "dispatcher", "script"]),
        )
        .order_by(Task.priority, Task.created_at)
        .first()
    )
    if not task:
        return None
    return task.to_dict()


def claim_task(db: Session, task_id: int) -> tuple[dict | None, str | None]:
    """Atomically claim a task.

    Returns ``(task_dict, None)`` on success, or ``(None, error_msg)``
    if the task is not found or already claimed.
    """
    now = datetime.now(timezone.utc)

    if db.bind is not None and db.bind.dialect.name == "sqlite":
        updated = (
            db.query(Task)
            .filter(Task.id == task_id, Task.status == "pending")
            .update({Task.status: "running", Task.started_at: now}, synchronize_session=False)
        )
        db.commit()
        if updated:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task is None:
                return None, "Task not found"
            return task.to_dict(), None

        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return None, "Task not found"
        return None, f"Task already {task.status}"

    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not task:
        return None, "Task not found"
    if task.status != "pending":
        return None, f"Task already {task.status}"
    task.status = "running"
    task.started_at = now
    db.commit()
    db.refresh(task)
    return task.to_dict(), None


def update_task(db: Session, task_id: int, update_data: dict[str, Any]) -> dict | None:
    """Update task fields. Returns updated task dict or ``None`` if not found."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return None
    if "status" in update_data and update_data["status"] in ("completed", "failed"):
        update_data["completed_at"] = datetime.now(timezone.utc)
    for key, val in update_data.items():
        setattr(task, key, val)
    db.commit()
    db.refresh(task)
    return task.to_dict()


def create_task(db: Session, task_data: dict[str, Any]) -> dict:
    """Insert a new task and return its dict."""
    task = Task(**task_data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task.to_dict()


def list_tasks(
    db: Session,
    *,
    status: str | None = None,
    ticker: str | None = None,
    executor: str | None = None,
    server: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List tasks with optional filters."""
    q = db.query(Task)
    if status:
        q = q.filter(Task.status == status)
    if ticker:
        q = q.filter(Task.ticker == ticker.upper())
    if executor:
        q = q.filter(Task.executor == executor)
    if server:
        q = q.filter(Task.server == server)
    rows = q.order_by(Task.created_at.desc()).limit(limit).all()
    return [r.to_dict() for r in rows]
