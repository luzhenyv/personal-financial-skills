"""Cross-source financial data validation.

Compares SEC XBRL data against yfinance key financials
to catch parsing errors or data quality issues.
Flags discrepancies exceeding a configurable threshold.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default relative tolerance: 2%
DEFAULT_TOLERANCE = 0.02

# Trust chain: SEC XBRL > yfinance > Alpha Vantage
# SEC filings are audited; yfinance can lag or use different accounting treatments
TRUST_ORDER = ("sec_xbrl", "yfinance", "alpha_vantage")


def validate_financials(
    sec_data: dict[str, Any],
    yf_data: dict[str, Any],
    ticker: str,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[dict[str, Any]]:
    """Compare SEC XBRL parsed financials against yfinance key financials.

    Args:
        sec_data: Dict of metric_name -> value from XBRL parsing
        yf_data: Dict of metric_name -> value from yfinance
        ticker: Stock symbol (for logging)
        tolerance: Relative tolerance (default 2%)

    Returns:
        List of discrepancy records:
            {metric, sec_value, yf_value, pct_diff, resolution, source_used}
    """
    discrepancies: list[dict[str, Any]] = []

    # Fields to cross-check (SEC key -> yfinance key)
    comparison_map = {
        "revenue": "total_revenue",
        "net_income": "net_income",
        "total_assets": "total_assets",
        "total_liabilities": "total_debt",
        "operating_income": "operating_income",
        "gross_profit": "gross_profit",
        "ebitda": "ebitda",
    }

    for sec_key, yf_key in comparison_map.items():
        sec_val = sec_data.get(sec_key)
        yf_val = yf_data.get(yf_key)

        if sec_val is None or yf_val is None:
            continue
        if sec_val == 0 and yf_val == 0:
            continue

        pct_diff = _pct_difference(sec_val, yf_val)

        if abs(pct_diff) > tolerance:
            resolution = resolve_conflict(sec_key, sec_val, yf_val)
            record = {
                "metric": sec_key,
                "sec_value": sec_val,
                "yf_value": yf_val,
                "pct_diff": round(pct_diff, 4),
                "resolution": resolution["action"],
                "source_used": resolution["source"],
            }
            discrepancies.append(record)
            logger.warning(
                f"[{ticker}] {sec_key}: SEC={sec_val:,.0f} vs YF={yf_val:,.0f} "
                f"({pct_diff:+.2%}) → using {resolution['source']}"
            )

    if not discrepancies:
        logger.info(f"[{ticker}] All cross-checked metrics within {tolerance:.0%} tolerance")

    return discrepancies


def resolve_conflict(
    metric: str,
    sec_value: float,
    yf_value: float,
) -> dict[str, str | float]:
    """Apply trust chain to resolve a data conflict.

    SEC XBRL is trusted over yfinance because SEC data comes from
    audited filings. yfinance may use TTM, different fiscal periods,
    or rounded figures.

    Returns:
        {"action": description, "source": trusted source name, "value": chosen value}
    """
    return {
        "action": "use_sec_xbrl",
        "source": "sec_xbrl",
        "value": sec_value,
    }


def validate_price_data(
    prices: list[dict[str, Any]],
    ticker: str,
) -> list[dict[str, str]]:
    """Basic quality checks on price records.

    Checks:
        - No negative prices
        - High >= Low for each day
        - Volume >= 0
        - No duplicate dates

    Returns:
        List of issue descriptions (empty if clean).
    """
    issues: list[dict[str, str]] = []
    seen_dates: set[str] = set()

    for row in prices:
        date = row.get("date", "unknown")

        if date in seen_dates:
            issues.append({"date": date, "issue": "duplicate_date"})
        seen_dates.add(date)

        for field in ("open_price", "high_price", "low_price", "close_price"):
            val = row.get(field)
            if val is not None and val < 0:
                issues.append({"date": date, "issue": f"negative_{field}", "value": val})

        high = row.get("high_price")
        low = row.get("low_price")
        if high is not None and low is not None and high < low:
            issues.append({
                "date": date,
                "issue": "high_lt_low",
                "high": high,
                "low": low,
            })

        vol = row.get("volume")
        if vol is not None and vol < 0:
            issues.append({"date": date, "issue": "negative_volume", "value": vol})

    if issues:
        logger.warning(f"[{ticker}] Price data quality: {len(issues)} issue(s) found")
    else:
        logger.info(f"[{ticker}] Price data quality: OK ({len(prices)} records)")

    return issues


def _pct_difference(a: float, b: float) -> float:
    """Relative percent difference using the first value as base."""
    if a == 0:
        return float("inf") if b != 0 else 0.0
    return (b - a) / abs(a)
