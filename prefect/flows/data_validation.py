"""Data validation flow — integrity checks across DB tables.

Schedule: Weekly Sun 02:00 ET  (cron 0 6 * * 0 UTC)
Executor: prefect (mechanical, no LLM)

Flags anomalies and inserts tasks for agent review if needed.
"""

from __future__ import annotations

from datetime import date, timedelta

from prefect import flow, task

from prefect.flows._registry import update_registry


@task
def check_price_gaps() -> list[str]:
    """Find tickers with gaps in recent daily price data."""
    from sqlalchemy import text as sa_text

    from pfs.db.session import get_session

    session = get_session()
    try:
        cutoff = date.today() - timedelta(days=7)
        rows = session.execute(
            sa_text("""
                SELECT c.ticker
                FROM companies c
                LEFT JOIN daily_prices dp
                    ON c.ticker = dp.ticker AND dp.date >= :cutoff
                GROUP BY c.ticker
                HAVING COUNT(dp.id) < 3
            """),
            {"cutoff": cutoff},
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        session.close()


@task
def check_revenue_consistency() -> list[str]:
    """Flag tickers where income_statement revenue differs wildly from metrics."""
    from sqlalchemy import text as sa_text

    from pfs.db.session import get_session

    session = get_session()
    try:
        rows = session.execute(
            sa_text("""
                SELECT i.ticker, i.fiscal_year
                FROM income_statements i
                JOIN financial_metrics m
                    ON i.ticker = m.ticker AND i.fiscal_year = m.fiscal_year
                    AND m.fiscal_quarter IS NULL
                WHERE i.fiscal_quarter IS NULL
                  AND i.revenue IS NOT NULL
                  AND m.gross_margin IS NOT NULL
                  AND ABS(m.gross_margin) > 1.0
            """)
        ).fetchall()
        return [f"{r[0]} FY{r[1]}" for r in rows]
    finally:
        session.close()


@task
def queue_anomaly_tasks(anomalies: list[str]):
    """Insert review tasks for detected anomalies."""
    if not anomalies:
        return

    from pfs.db.session import get_session
    from pfs.tasks.models import Task

    session = get_session()
    try:
        for desc in anomalies:
            ticker = desc.split()[0] if " " in desc else desc
            task_obj = Task(
                type="event_triggered",
                skill="data-validation",
                action="review",
                ticker=ticker,
                params={"anomaly": desc},
                executor="openclaw",
                server="agent_server",
                priority=7,
                requires_intelligence=True,
                created_by="prefect",
            )
            session.add(task_obj)
        session.commit()
    finally:
        session.close()


@flow(name="data-validation")
def data_validation():
    """Run DB integrity checks and flag anomalies."""
    update_registry("data-validation", "running")
    try:
        price_gaps = check_price_gaps()
        rev_issues = check_revenue_consistency()
        all_anomalies = [f"{t} price-gap" for t in price_gaps] + rev_issues
        queue_anomaly_tasks(all_anomalies)
        update_registry("data-validation", "completed")
        return {"price_gaps": price_gaps, "revenue_issues": rev_issues}
    except Exception as e:
        update_registry("data-validation", "failed", error_message=str(e))
        raise


if __name__ == "__main__":
    data_validation()
