"""Filing check flow — checks SEC EDGAR for new filings and queues tasks.

Schedule: Daily 06:00 ET  (cron 0 10 * * * UTC)
Executor: prefect (mechanical, no LLM)

When a new filing is detected, inserts an event_triggered task for OpenClaw
to analyze it.
"""

from __future__ import annotations

import subprocess
import sys

from prefect import flow, task


@task(retries=2, retry_delay_seconds=180)
def check_new_filings() -> list[dict]:
    """Run the filing-check script and return newly found filings."""
    result = subprocess.run(
        [sys.executable, "-m", "pfs.etl.pipeline", "check-filings"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"filing-check failed: {result.stderr[:500]}")
    return result.stdout


@task
def queue_analysis_tasks(filings_output: str):
    """For each new filing, insert an event_triggered task for OpenClaw."""
    from pfs.db.session import get_session
    from pfs.tasks.models import Task

    # Simple heuristic: parse stdout for lines like "NEW: AAPL 10-K 2025-01-31"
    session = get_session()
    try:
        for line in filings_output.strip().splitlines():
            if not line.startswith("NEW:"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            ticker = parts[1]
            form_type = parts[2]
            skill = "company-profile" if form_type == "10-K" else "earnings-analysis"
            task_obj = Task(
                type="event_triggered",
                skill=skill,
                action="analyze",
                ticker=ticker,
                trigger_event=f"new_filing:{form_type}",
                executor="openclaw",
                server="agent_server",
                requires_intelligence=True,
                created_by="prefect",
            )
            session.add(task_obj)
        session.commit()
    finally:
        session.close()


@flow(name="filing-check")
def filing_check():
    """Check SEC EDGAR for new filings, queue analysis tasks."""
    try:
        output = check_new_filings()
        queue_analysis_tasks(output)
    except Exception as e:
        raise


if __name__ == "__main__":
    filing_check()
