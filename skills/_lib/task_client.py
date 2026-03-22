# skills/_lib/task_client.py — thin HTTP wrapper for Task API
# Used by agents/task_dispatcher.py on Agent Server.
# NO pfs.db.*, NO sqlalchemy, NO psycopg2 — pure HTTP.

from __future__ import annotations

import httpx


class TaskClient:
    """HTTP client for the Task API on the Data Server."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def next_task(self) -> dict | None:
        """Return highest-priority pending task, or None if queue empty."""
        r = httpx.get(f"{self.base}/api/tasks/next", timeout=self.timeout)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def claim_task(self, task_id: int) -> dict:
        """Atomically set status='running'. Raises on 409 (already claimed)."""
        r = httpx.post(f"{self.base}/api/tasks/{task_id}/claim", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def complete_task(self, task_id: int, **kwargs) -> dict:
        """Mark task completed with optional result_summary, artifacts, git_commit_sha."""
        r = httpx.patch(
            f"{self.base}/api/tasks/{task_id}",
            json={"status": "completed", **kwargs},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def fail_task(self, task_id: int, error: str) -> dict:
        """Mark task failed with error message."""
        r = httpx.patch(
            f"{self.base}/api/tasks/{task_id}",
            json={"status": "failed", "error_message": error},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def create_task(self, **kwargs) -> dict:
        """Insert a new task into the registry."""
        r = httpx.post(
            f"{self.base}/api/tasks/",
            json=kwargs,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def list_tasks(self, **filters) -> list[dict]:
        """List tasks with optional filters (status, ticker, executor, limit)."""
        r = httpx.get(
            f"{self.base}/api/tasks/",
            params={k: v for k, v in filters.items() if v is not None},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()
