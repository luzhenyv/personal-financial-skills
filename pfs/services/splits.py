"""Stock-split adjustment utilities.

Reads split history from the ``stock_splits`` table in PostgreSQL and computes
cumulative split factors so that per-share metrics from different filing eras
can be restated to the **current** share basis.

Usage::

    from pfs.services.splits import get_split_adjustor
    from pfs.db.session import get_session

    db = get_session()
    adjust = get_split_adjustor("NVDA", fiscal_year_end="0131", db=db)
    adjusted_eps = adjust(fiscal_year=2024, value=11.93)  # → 1.193
    db.close()
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def load_splits_from_db(ticker: str, db: "Session") -> list[dict]:
    """Load the split history for *ticker* from the database.

    Returns a list of ``{"date": "YYYY-MM-DD", "ratio": <float>}`` dicts,
    sorted ascending by date.  Returns ``[]`` if no splits are recorded.
    """
    from pfs.db.models import StockSplit

    rows = (
        db.query(StockSplit)
        .filter(StockSplit.ticker == ticker)
        .order_by(StockSplit.split_date)
        .all()
    )
    return [{"date": str(row.split_date), "ratio": float(row.ratio)} for row in rows]


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
    db: "Session",
) -> Callable[[int, float | None], float | None]:
    """Return a function ``adjust(fiscal_year, value) -> adjusted_value``.

    The returned callable divides *value* by the cumulative split factor for
    that fiscal year.  If the company has no recorded splits the value is
    returned unchanged.

    Args:
        ticker: Upper-case ticker symbol.
        fiscal_year_end: ``"MMDD"`` string (e.g. ``"0131"`` for January 31).
        db: Open SQLAlchemy session used to query ``stock_splits``.
    """
    splits = load_splits_from_db(ticker, db)
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
