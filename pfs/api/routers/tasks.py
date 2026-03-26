"""Task API router — CRUD for the agent_ops.tasks table.

Provides the unified view of ALL scheduled work: Prefect mechanical,
OpenClaw intelligent, event-driven, and user-requested tasks.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from pfs.api.deps import get_db
from pfs.api.schemas.tasks import TaskCreate, TaskUpdate
from pfs.services import tasks as task_svc

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    """All recurring tasks — the unified schedule view."""
    return task_svc.get_schedule(db)


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Summary counts by status and executor."""
    return task_svc.get_stats(db)


@router.get("/next")
def next_task(db: Session = Depends(get_db)):
    """Return highest-priority pending task for dispatcher, or 204."""
    result = task_svc.next_task(db)
    if result is None:
        return Response(status_code=204)
    return result


@router.post("/{task_id}/claim")
def claim_task(task_id: int, db: Session = Depends(get_db)):
    """Atomically SET status = 'running'. Returns 409 if already claimed."""
    result, error = task_svc.claim_task(db, task_id)
    if error:
        status = 404 if "not found" in error.lower() else 409
        raise HTTPException(status_code=status, detail=error)
    return result


@router.patch("/{task_id}")
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    """Update task fields (status, results, retry info)."""
    result = task_svc.update_task(db, task_id, body.model_dump(exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/")
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    """Insert a new task. Used by: Prefect flows, dispatcher, user."""
    return task_svc.create_task(db, body.model_dump())


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
    return task_svc.list_tasks(
        db, status=status, ticker=ticker, executor=executor, server=server, limit=limit
    )
