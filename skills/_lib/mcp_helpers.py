"""Common MCP call patterns for skill scripts.

Provides pre-built data-fetching helpers that wrap the ``personal-finance``
MCP tools through the Data Server REST API.  Each function returns clean
Python dicts ready for analysis or artifact writing.

These mirror the MCP tool signatures but call through the FastAPI REST
endpoints, keeping skill scripts decoupled from the database layer.

Usage::

    from skills._lib.mcp_helpers import fetch_full_financials, fetch_company_snapshot

    snapshot = fetch_company_snapshot("NVDA")
    financials = fetch_full_financials("NVDA", years=5)
"""

from __future__ import annotations

import os
from typing import Any

import httpx

API_BASE = os.environ.get("PFS_API_URL", "http://127.0.0.1:8000")
_TIMEOUT = 60


# ── Low-level MCP wrappers ───────────────────────────────────────────────────
# These mirror the MCP tool signatures, calling through the REST API.


def list_companies() -> list[dict[str, Any]]:
    """Return all ingested companies (ticker, name, sector)."""
    r = httpx.get(f"{API_BASE}/api/companies/", timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_company(ticker: str) -> dict[str, Any]:
    """Full company details for *ticker*."""
    r = httpx.get(f"{API_BASE}/api/companies/{ticker}", timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_income_statements(
    ticker: str, years: int = 5, quarterly: bool = False
) -> list[dict[str, Any]]:
    """Income statement data, oldest-first."""
    r = httpx.get(
        f"{API_BASE}/api/financials/{ticker}/income-statements",
        params={"years": years, "quarterly": quarterly},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_balance_sheets(
    ticker: str, years: int = 5, quarterly: bool = False
) -> list[dict[str, Any]]:
    """Balance sheet data, oldest-first."""
    r = httpx.get(
        f"{API_BASE}/api/financials/{ticker}/balance-sheets",
        params={"years": years, "quarterly": quarterly},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_cash_flows(
    ticker: str, years: int = 5, quarterly: bool = False
) -> list[dict[str, Any]]:
    """Cash flow statement data, oldest-first."""
    r = httpx.get(
        f"{API_BASE}/api/financials/{ticker}/cash-flows",
        params={"years": years, "quarterly": quarterly},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_financial_metrics(ticker: str) -> list[dict[str, Any]]:
    """Computed margins, growth, returns, valuation ratios."""
    r = httpx.get(
        f"{API_BASE}/api/financials/{ticker}/metrics",
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_prices(ticker: str, period: str = "1y") -> list[dict[str, Any]]:
    """Daily OHLCV price data."""
    r = httpx.get(
        f"{API_BASE}/api/financials/{ticker}/prices",
        params={"period": period},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_revenue_segments(
    ticker: str, fiscal_year: int | None = None
) -> list[dict[str, Any]]:
    """Revenue segment breakdown (product, geography, channel)."""
    params: dict[str, Any] = {}
    if fiscal_year is not None:
        params["fiscal_year"] = fiscal_year
    r = httpx.get(
        f"{API_BASE}/api/financials/{ticker}/segments",
        params=params,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_annual_financials(
    ticker: str, years: int = 5
) -> dict[str, Any]:
    """Combined annual financials with split-adjusted EPS.

    Calls ``/api/analysis/profile/{ticker}`` which joins multiple tables.
    The response includes income, balance, cashflow plus split-adjusted EPS.
    """
    r = httpx.get(
        f"{API_BASE}/api/analysis/profile/{ticker}",
        params={"years": years},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Higher-level patterns ────────────────────────────────────────────────────


def fetch_company_snapshot(ticker: str) -> dict[str, Any]:
    """Fetch company details + latest metrics in one call.

    Returns a dict with keys ``company`` and ``metrics``.
    """
    company = get_company(ticker)
    metrics = get_financial_metrics(ticker)
    return {
        "company": company,
        "metrics": metrics,
    }


def fetch_full_financials(ticker: str, years: int = 5) -> dict[str, Any]:
    """Fetch all financial tables for *ticker*.

    Returns a dict with keys ``income``, ``balance``, ``cashflow``, ``metrics``.
    """
    return {
        "income": get_income_statements(ticker, years=years),
        "balance": get_balance_sheets(ticker, years=years),
        "cashflow": get_cash_flows(ticker, years=years),
        "metrics": get_financial_metrics(ticker),
    }


def check_data_available(ticker: str) -> bool:
    """Return True if *ticker* has income statement data in the DB.

    Useful as a pre-flight check before running a skill.
    """
    try:
        data = get_income_statements(ticker, years=1)
        return len(data) > 0
    except httpx.HTTPStatusError:
        return False


def safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """Nested dict access that returns *default* on any missing key.

    Example::

        safe_get(row, "balance", "total_assets", default=0)
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current
