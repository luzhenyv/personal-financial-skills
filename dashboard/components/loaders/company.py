"""Aggregate data loader for the Company Profile page.

Fetches data from the REST API, JSON profile files, live yfinance data,
and the saved report in a single call so tab renderers receive a plain
dict with everything they need.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..utils import load_json, load_report_md

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@dataclass
class CompanyPageData:
    """All data required to render the Company Profile page."""

    # ── Core DB data ──
    company: dict[str, Any] = field(default_factory=dict)
    incomes: list[dict] = field(default_factory=list)
    balances: list[dict] = field(default_factory=list)
    cash_flows: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    price: dict | None = None

    # ── AI-generated JSON profile files ──
    overview: dict | None = None
    management: dict | None = None
    risks: dict | None = None
    competitive: dict | None = None
    segments: dict | None = None
    thesis: dict | None = None
    comps: dict | None = None

    # ── Report markdown ──
    report_md: str | None = None

    # ── Live yfinance data ──
    yf_info: dict[str, Any] = field(default_factory=dict)
    current_price: float | None = None

    # ── Derived convenience flags ──
    has_profile: bool = False


def _api_get(path: str, params: dict | None = None) -> dict | list | None:
    """GET from the REST API. Returns parsed JSON or None on error."""
    try:
        resp = httpx.get(f"{API_BASE_URL}{path}", params=params, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def load_company_page_data(ticker: str) -> CompanyPageData | None:
    """Load all data needed for the Company Profile page.

    Args:
        ticker: Upper-case ticker symbol, e.g. ``"NVDA"``.

    Returns:
        A :class:`CompanyPageData` instance, or ``None`` if the company is not
        found in the database.
    """
    company = _api_get(f"/api/companies/{ticker}")
    if company is None:
        return None

    incomes = _api_get(f"/api/financials/{ticker}/income-statements", {"years": 7}) or []
    balances = _api_get(f"/api/financials/{ticker}/balance-sheets", {"years": 7}) or []
    cash_flows = _api_get(f"/api/financials/{ticker}/cash-flows", {"years": 7}) or []
    metrics = _api_get(f"/api/financials/{ticker}/metrics") or []
    prices = _api_get(f"/api/financials/{ticker}/prices", {"period": "1y"}) or []
    latest_price = prices[-1] if prices else None

    data = CompanyPageData(
        company=company,
        incomes=incomes,
        balances=balances,
        cash_flows=cash_flows,
        metrics=metrics,
        price=latest_price,
    )

    # ── Split-adjust per-share metrics to current share basis ──
    from pfs.services.splits import get_split_adjustor
    from pfs.db.session import get_session

    fye = company.get("fiscal_year_end")  # e.g. "0131"
    _db = get_session()
    try:
        adjust = get_split_adjustor(ticker, fiscal_year_end=fye, db=_db)
        for inc in data.incomes:
            fy = inc.get("fiscal_year")
            if fy is not None:
                inc["eps_diluted"] = adjust(fy, inc.get("eps_diluted"))
                inc["eps_basic"] = adjust(fy, inc.get("eps_basic"))
    finally:
        _db.close()

    # JSON profile files
    data.overview = load_json(ticker, "company_overview.json", subdir="profile")
    data.management = load_json(ticker, "management_team.json", subdir="profile")
    data.risks = load_json(ticker, "risk_factors.json", subdir="profile")
    data.competitive = load_json(ticker, "competitive_landscape.json", subdir="profile")
    data.segments = load_json(ticker, "financial_segments.json", subdir="profile")
    data.thesis = load_json(ticker, "investment_thesis.json", subdir="profile")
    data.comps = load_json(ticker, "comps_table.json", subdir="profile")
    data.report_md = load_report_md(ticker)

    data.has_profile = any([
        data.overview, data.management, data.risks,
        data.competitive, data.thesis,
    ])

    # Live yfinance data (best-effort)
    try:
        from pfs.etl.yfinance_client import get_stock_info, get_current_price

        data.current_price = get_current_price(ticker)
        data.yf_info = get_stock_info(ticker)
    except Exception:
        pass

    if data.current_price is None and data.price:
        data.current_price = data.price.get("adjusted_close")

    return data
