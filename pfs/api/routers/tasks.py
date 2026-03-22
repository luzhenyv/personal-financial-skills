"""Task API router — CRUD for the agent_ops.tasks table.

**Stub**: The ``agent_ops.tasks`` table is created in Phase 2.
Endpoints return ``501 Not Implemented`` until the schema is deployed.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_NOT_IMPL = JSONResponse(
    status_code=501,
    content={"error": "Task system not yet deployed. See Phase 2 of migration plan."},
)


@router.get("/next")
def next_task():
    """Return highest-priority pending task, or 204."""
    return _NOT_IMPL


@router.post("/{task_id}/claim")
def claim_task(task_id: int):
    """Atomically SET status = 'running'. Returns 409 if already claimed."""
    return _NOT_IMPL


@router.patch("/{task_id}")
def update_task(task_id: int):
    """Update status, result_summary, error_message, artifacts, git_commit_sha."""
    return _NOT_IMPL


@router.post("/")
def create_task():
    """Insert a new task."""
    return _NOT_IMPL


@router.get("/")
def list_tasks():
    """List tasks with optional filters."""
    return _NOT_IMPL
