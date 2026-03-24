"""Price sync flow — syncs daily OHLCV for all tracked tickers.

Schedule: M-F 17:30 ET  (cron 30 21 * * 1-5 UTC)
Executor: prefect (mechanical, no LLM)
"""

from __future__ import annotations

import subprocess
import sys

from prefect import flow, task


@task(retries=3, retry_delay_seconds=300)
def run_etl_sync():
    """Call the existing ETL price-sync pipeline."""
    result = subprocess.run(
        [sys.executable, "-m", "pfs.etl.pipeline", "sync-prices"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"price-sync failed: {result.stderr[:500]}")
    return result.stdout


@flow(name="price-sync")
def price_sync():
    """Sync daily prices for all tracked tickers."""
    try:
        output = run_etl_sync()
        return output
    except Exception as e:
        raise


if __name__ == "__main__":
    price_sync()
