"""Alpha Vantage API client for stock price data.

Free tier: 25 API calls per day.
Standard tier: 5 calls/minute, unlimited daily.
"""

import logging
from datetime import date
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def get_daily_prices(
    ticker: str, output_size: str = "compact"
) -> list[dict[str, Any]]:
    """Fetch daily adjusted prices for a ticker.

    Args:
        ticker: Stock symbol (e.g. 'NVDA')
        output_size: 'compact' (last 100 days) or 'full' (20+ years)

    Returns:
        List of price records sorted by date descending.
    """
    if not settings.alpha_vantage_key:
        logger.warning("Alpha Vantage API key not configured — skipping price fetch")
        return []

    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": ticker.upper(),
        "outputsize": output_size,
        "apikey": settings.alpha_vantage_key,
    }

    logger.info(f"Fetching daily prices for {ticker} ({output_size})")
    resp = httpx.get(settings.alpha_vantage_base_url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Check for API errors
    if "Error Message" in data:
        logger.error(f"Alpha Vantage error: {data['Error Message']}")
        return []
    if "Note" in data:
        logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
        return []

    time_series = data.get("Time Series (Daily)", {})
    if not time_series:
        logger.warning(f"No price data returned for {ticker}")
        return []

    records = []
    for date_str, values in time_series.items():
        records.append({
            "ticker": ticker.upper(),
            "date": date_str,
            "open_price": float(values["1. open"]),
            "high_price": float(values["2. high"]),
            "low_price": float(values["3. low"]),
            "close_price": float(values["4. close"]),
            "adjusted_close": float(values["5. adjusted close"]),
            "volume": int(values["6. volume"]),
        })

    # Sort by date descending
    records.sort(key=lambda x: x["date"], reverse=True)
    logger.info(f"Got {len(records)} price records for {ticker}")
    return records


def get_quote(ticker: str) -> dict[str, Any] | None:
    """Fetch the latest quote for a ticker (real-time-ish)."""
    if not settings.alpha_vantage_key:
        logger.warning("Alpha Vantage API key not configured")
        return None

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker.upper(),
        "apikey": settings.alpha_vantage_key,
    }

    resp = httpx.get(settings.alpha_vantage_base_url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    quote = data.get("Global Quote", {})
    if not quote:
        return None

    return {
        "ticker": ticker.upper(),
        "price": float(quote.get("05. price", 0)),
        "change": float(quote.get("09. change", 0)),
        "change_percent": quote.get("10. change percent", "0%"),
        "volume": int(quote.get("06. volume", 0)),
        "latest_trading_day": quote.get("07. latest trading day", ""),
    }
