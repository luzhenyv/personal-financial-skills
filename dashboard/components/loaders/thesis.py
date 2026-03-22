"""Aggregate data loader for the Thesis Tracker page.

Fetches all thesis data in a single call so tab renderers receive a plain
:class:`ThesisPageData` object with everything they need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThesisPageData:
    """All data required to render the Thesis Tracker page."""

    ticker: str = ""
    thesis: dict[str, Any] = field(default_factory=dict)
    updates: list[dict] = field(default_factory=list)
    health_checks: list[dict] = field(default_factory=list)
    latest_health: dict | None = None
    catalysts: list[dict] = field(default_factory=list)

    # Convenience
    assumptions: list[dict] = field(default_factory=list)


def load_thesis_page_data(ticker: str) -> ThesisPageData | None:
    """Load all data needed for the Thesis Tracker page.

    Args:
        ticker: Upper-case ticker symbol, e.g. ``"NVDA"``.

    Returns:
        A :class:`ThesisPageData` instance, or ``None`` if not found.
    """
    from pfs.analysis.thesis_tracker import get_thesis_detail

    detail = get_thesis_detail(ticker)
    if detail is None:
        return None

    thesis = detail["thesis"]
    return ThesisPageData(
        ticker=ticker,
        thesis=thesis,
        updates=detail.get("updates", []),
        health_checks=detail.get("health_checks", []),
        latest_health=detail.get("latest_health"),
        catalysts=detail.get("catalysts", []),
        assumptions=thesis.get("assumptions", []),
    )
