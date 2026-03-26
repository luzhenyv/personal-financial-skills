"""Task schemas — request/response models for the task registry."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
