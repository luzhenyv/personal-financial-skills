"""Seed the unified task registry with all recurring tasks.

Run once after deploying the agent_ops schema:
    uv run python scripts/seed_tasks.py
"""

from __future__ import annotations

from pfs.db.session import get_session
from pfs.tasks.models import Task

RECURRING_TASKS = [
    # === DATA SERVER (executor=prefect) ===
    {
        "type": "recurring",
        "skill": "price-sync",
        "action": "sync",
        "trigger_cron": "30 21 * * 1-5",
        "executor": "prefect",
        "server": "data_server",
        "requires_intelligence": False,
        "created_by": "system",
        "params": {"description": "Sync daily OHLCV for all tickers (M-F 17:30 ET)"},
    },
    {
        "type": "recurring",
        "skill": "filing-check",
        "action": "check",
        "trigger_cron": "0 10 * * *",
        "executor": "prefect",
        "server": "data_server",
        "requires_intelligence": False,
        "created_by": "system",
        "params": {"description": "Check SEC EDGAR for new filings (daily 06:00 ET)"},
    },
    {
        "type": "recurring",
        "skill": "data-validation",
        "action": "validate",
        "trigger_cron": "0 6 * * 0",
        "executor": "prefect",
        "server": "data_server",
        "requires_intelligence": False,
        "created_by": "system",
        "params": {"description": "Validate DB integrity (weekly Sun 02:00 ET)"},
    },
    # === AGENT SERVER (executor=openclaw) ===
    {
        "type": "recurring",
        "skill": "morning-brief",
        "action": "generate",
        "trigger_cron": "30 11 * * 1-5",
        "executor": "openclaw",
        "server": "agent_server",
        "requires_intelligence": True,
        "created_by": "system",
        "params": {"description": "Morning market brief (M-F 07:30 ET)"},
    },
    {
        "type": "recurring",
        "skill": "thesis-tracker",
        "action": "check --all",
        "trigger_cron": "0 14 * * 6",
        "executor": "openclaw",
        "server": "agent_server",
        "requires_intelligence": True,
        "created_by": "system",
        "params": {"description": "Weekly thesis health check (Sat 10:00 ET)"},
    },
    {
        "type": "recurring",
        "skill": "portfolio-summary",
        "action": "generate",
        "trigger_cron": "0 22 * * 5",
        "executor": "openclaw",
        "server": "agent_server",
        "requires_intelligence": True,
        "created_by": "system",
        "params": {"description": "Weekly portfolio summary (Fri 18:00 ET)"},
    },
]


def seed():
    session = get_session()
    try:
        for t in RECURRING_TASKS:
            existing = (
                session.query(Task)
                .filter(Task.skill == t["skill"], Task.type == "recurring")
                .first()
            )
            if existing:
                print(f"  skip  {t['skill']} (already exists, id={existing.id})")
                continue
            task = Task(**t)
            session.add(task)
            print(f"  add   {t['skill']}  executor={t['executor']}  server={t['server']}")
        session.commit()
        print("\nDone. All recurring tasks registered.")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
