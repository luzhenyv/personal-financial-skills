"""Thin HTTP client for skills to call the Data Server API.

Skill scripts use this instead of importing ``pfs.analysis.*`` directly,
keeping them decoupled from the platform database layer.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

API_BASE = os.environ.get("PFS_API_URL", "http://127.0.0.1:8000")
_TIMEOUT = 60


def get_profile(ticker: str, years: int = 7) -> dict[str, Any]:
    """Fetch full company profile data (DB join of 6 tables)."""
    r = httpx.get(
        f"{API_BASE}/api/analysis/profile/{ticker}",
        params={"years": years},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_valuation(ticker: str, **overrides: Any) -> dict[str, Any]:
    """Run full DCF + scenario + comps valuation."""
    r = httpx.get(
        f"{API_BASE}/api/analysis/valuation/{ticker}",
        params=overrides,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_current_price(ticker: str) -> dict[str, Any]:
    """Get the latest price for *ticker*."""
    r = httpx.get(
        f"{API_BASE}/api/analysis/current-price/{ticker}",
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_coverage(ticker: str) -> dict[str, Any]:
    """Run ETL coverage analysis for *ticker*."""
    r = httpx.get(
        f"{API_BASE}/api/analysis/coverage/{ticker}",
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()
