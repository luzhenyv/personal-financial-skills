"""Task API router — CRUD for the agent_ops.tasks table.

Provides the unified view of ALL scheduled work: Prefect mechanical,
OpenClaw intelligent, event-driven, and user-requested tasks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pfs.db.session import get_db
from pfs.tasks.models import Task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── Pydantic schemas ────────────────────────────


class TaskCreate(BaseModel):
    type: str = Field(..., pattern="^(immediate|scheduled|recurring|event_triggered)$")
    skill: str
    action: str | None = None
    ticker: str | None = None
    params: dict = Field(default_factory=dict)
    executor: str = Field("dispatcher", pattern="^(prefect|openclaw|dispatcher|script)$")
    trigger_cron: str | None = None
    trigger_event: str | None = None
    scheduled_at: datetime | None = None
    next_run_at: datetime | None = None
    priority: int = Field(5, ge=1, le=9)
    server: str | None = None
    requires_intelligence: bool = True
    created_by: str


class TaskUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(pending|running|completed|failed|cancelled)$")
    result_summary: str | None = None
    error_message: str | None = None
    artifacts: list | None = None
    git_commit_sha: str | None = None
    retries_left: int | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


# ── Endpoints ────────────────────────────────────


@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    """All recurring tasks — the unified schedule view."""
    rows = (
        db.query(Task)
        .filter(Task.type == "recurring")
        .order_by(Task.server, Task.skill)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
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


@router.get("/next")
def next_task(db: Session = Depends(get_db)):
    """Return highest-priority pending task for dispatcher, or 204."""
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
        return Response(status_code=204)
    return task.to_dict()


@router.post("/{task_id}/claim")
def claim_task(task_id: int, db: Session = Depends(get_db)):
    """Atomically SET status = 'running'. Returns 409 if already claimed."""
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "pending":
        raise HTTPException(status_code=409, detail=f"Task already {task.status}")
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.patch("/{task_id}")
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    """Update task fields (status, results, retry info)."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] in ("completed", "failed"):
        update_data["completed_at"] = datetime.now(timezone.utc)
    for key, val in update_data.items():
        setattr(task, key, val)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.post("/")
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    """Insert a new task. Used by: Prefect flows, dispatcher, user."""
    task = Task(**body.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.get("/")
def list_tasks(
    status: Optional[str] = Query(None),
    ticker: Optional[str] = Query(None),
    executor: Optional[str] = Query(None),
    server: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
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
