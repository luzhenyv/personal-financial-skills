"""Aggregate data loader for the Company Profile page.

Fetches DB rows, JSON profile files, live yfinance data, and the saved report
in a single call so tab renderers receive a plain dict with everything they need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .utils import load_json, load_report_md


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


def load_company_page_data(ticker: str) -> CompanyPageData | None:
    """Load all data needed for the Company Profile page.

    Args:
        ticker: Upper-case ticker symbol, e.g. ``"NVDA"``.

    Returns:
        A :class:`CompanyPageData` instance, or ``None`` if the company is not
        found in the database (detected via the ``"error"`` key returned by
        :func:`get_profile_data`).
    """
    from src.analysis.company_profile import get_profile_data

    raw = get_profile_data(ticker)
    if "error" in raw:
        return None

    data = CompanyPageData(
        company=raw["company"],
        incomes=raw["income_statements"],
        balances=raw["balance_sheets"],
        cash_flows=raw["cash_flows"],
        metrics=raw["metrics"],
        price=raw.get("latest_price"),
    )

    # JSON profile files
    data.overview = load_json(ticker, "company_overview.json")
    data.management = load_json(ticker, "management_team.json")
    data.risks = load_json(ticker, "risk_factors.json")
    data.competitive = load_json(ticker, "competitive_landscape.json")
    data.segments = load_json(ticker, "financial_segments.json")
    data.thesis = load_json(ticker, "investment_thesis.json")
    data.comps = load_json(ticker, "comps_table.json")
    data.report_md = load_report_md(ticker)

    data.has_profile = any([
        data.overview, data.management, data.risks,
        data.competitive, data.thesis,
    ])

    # Live yfinance data (best-effort)
    try:
        from src.etl.yfinance_client import get_stock_info, get_current_price

        data.current_price = get_current_price(ticker)
        data.yf_info = get_stock_info(ticker)
    except Exception:
        pass

    if data.current_price is None and data.price:
        data.current_price = data.price.get("adjusted_close")

    return data
