"""SQLAlchemy model for agent_ops.tasks — the unified task registry."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from pfs.db.models import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "type IN ('immediate','scheduled','recurring','event_triggered')",
            name="ck_tasks_type",
        ),
        CheckConstraint(
            "executor IN ('prefect','openclaw','dispatcher','script')",
            name="ck_tasks_executor",
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_tasks_status",
        ),
        CheckConstraint("priority BETWEEN 1 AND 9", name="ck_tasks_priority"),
        {"schema": "agent_ops"},
    )

    id = Column(Integer, primary_key=True)

    # What to do
    type = Column(String(20), nullable=False)
    skill = Column(String(50), nullable=False)
    action = Column(String(50))
    ticker = Column(String(10))
    params = Column(JSONB, default=dict)

    # Who runs this task
    executor = Column(String(20), nullable=False, default="dispatcher")

    # Scheduling
    trigger_cron = Column(String(100))
    trigger_event = Column(String(100))
    scheduled_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    last_run_at = Column(DateTime(timezone=True))

    # Lifecycle
    status = Column(String(20), default="pending")
    priority = Column(Integer, default=5)
    retries_left = Column(Integer, default=2)

    # Execution context
    server = Column(String(20))
    requires_intelligence = Column(Boolean, default=True)

    # Audit
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Results
    result_summary = Column(Text)
    error_message = Column(Text)
    artifacts = Column(JSONB, default=list)
    git_commit_sha = Column(String(40))

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        d = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            d[col.name] = val
        return d
