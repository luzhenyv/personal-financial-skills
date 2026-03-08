"""Stock-split adjustment utilities.

Reads ``data/processed/{TICKER}/stock_splits.json`` and computes cumulative
split factors so that per-share metrics from different filing eras can be
restated to the **current** share basis.

Usage::

    from src.splits import get_split_adjustor

    adjust = get_split_adjustor("NVDA", fiscal_year_end="0131")
    adjusted_eps = adjust(fiscal_year=2024, value=11.93)  # → 1.193
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Callable


def load_splits(ticker: str, base: str = "data/processed") -> list[dict]:
    """Load the split history for *ticker* from the processed JSON file.

    Returns a list of ``{"date": "YYYY-MM-DD", "ratio": <int|float>}`` dicts,
    sorted ascending by date.  Returns ``[]`` if the file does not exist.
    """
    path = Path(base) / ticker / "stock_splits.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return sorted(data.get("splits", []), key=lambda s: s["date"])
    except Exception:
        return []


def cumulative_split_factor(
    splits: list[dict],
    fy_end_date: date,
) -> float:
    """Return the product of all split ratios that occurred **after** *fy_end_date*.

    If no splits happened after the fiscal-year end, returns ``1.0`` (no adjustment).
    """
    factor = 1.0
    for s in splits:
        split_date = date.fromisoformat(s["date"])
        if split_date > fy_end_date:
            factor *= float(s["ratio"])
    return factor


def _parse_fiscal_year_end(fye: str | None) -> tuple[int, int]:
    """Parse a ``"MMDD"`` fiscal-year-end string into ``(month, day)``.

    Falls back to ``(12, 31)`` (calendar-year end) when the value is missing
    or malformed.
    """
    if fye and len(fye) == 4 and fye.isdigit():
        return int(fye[:2]), int(fye[2:])
    return 12, 31


def get_split_adjustor(
    ticker: str,
    fiscal_year_end: str | None = None,
    *,
    base: str = "data/processed",
) -> Callable[[int, float | None], float | None]:
    """Return a function ``adjust(fiscal_year, value) -> adjusted_value``.

    The returned callable divides *value* by the cumulative split factor for
    that fiscal year.  If the company has no recorded splits the value is
    returned unchanged.

    Args:
        ticker: Upper-case ticker symbol.
        fiscal_year_end: ``"MMDD"`` string (e.g. ``"0131"`` for January 31).
        base: Root directory for processed data files.
    """
    splits = load_splits(ticker, base=base)
    month, day = _parse_fiscal_year_end(fiscal_year_end)

    # Pre-compute factors per fiscal year we might encounter (cache)
    _cache: dict[int, float] = {}

    def adjust(fiscal_year: int, value: float | None) -> float | None:
        if value is None or not splits:
            return value
        if fiscal_year not in _cache:
            fy_end = date(fiscal_year, month, day)
            _cache[fiscal_year] = cumulative_split_factor(splits, fy_end)
        factor = _cache[fiscal_year]
        if factor == 1.0:
            return value
        return round(float(value) / factor, 4)

    return adjust
