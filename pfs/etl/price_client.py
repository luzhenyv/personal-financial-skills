"""Unified price data client.

Primary source: yfinance (free, no API key)
Fallback source: Alpha Vantage (optional, requires API key)

The returned records always match the DailyPrice model schema:
    {ticker, date, open_price, high_price, low_price, close_price, adjusted_close, volume}
"""

import logging
from typing import Any

import httpx

from pfs.config import settings

logger = logging.getLogger(__name__)


def get_daily_prices(
    ticker: str,
    period: str = "5y",
    source: str = "yfinance",
) -> list[dict[str, Any]]:
    """Fetch daily adjusted prices for a ticker.

    Args:
        ticker: Stock symbol (e.g. 'NVDA')
        period: For yfinance: '1y', '2y', '5y', '10y', 'max'.
                For Alpha Vantage: 'compact' (100 days) or 'full' (20+ years).
        source: 'yfinance' (default) or 'alpha_vantage'

    Returns:
        List of price records sorted by date descending.
    """
    if source == "yfinance":
        records = _fetch_yfinance(ticker, period)
        if records:
            return records
        # Fallback to Alpha Vantage if yfinance fails and key available
        if settings.alpha_vantage_key:
            logger.info(f"yfinance failed for {ticker}, falling back to Alpha Vantage")
            av_period = "full" if period in ("5y", "10y", "max") else "compact"
            return _fetch_alpha_vantage(ticker, av_period)
        return []

    elif source == "alpha_vantage":
        if not settings.alpha_vantage_key:
            logger.warning("Alpha Vantage API key not configured, falling back to yfinance")
            return _fetch_yfinance(ticker, period)
        return _fetch_alpha_vantage(ticker, period)

    else:
        logger.error(f"Unknown price source: {source}")
        return []


def get_quote(ticker: str) -> dict[str, Any] | None:
    """Fetch the latest quote for a ticker.

    Tries yfinance first, falls back to Alpha Vantage.
    """
    quote = _quote_yfinance(ticker)
    if quote:
        return quote

    if settings.alpha_vantage_key:
        return _quote_alpha_vantage(ticker)

    return None


# ──────────────────────────────────────────────
# yfinance Implementation
# ──────────────────────────────────────────────

def _fetch_yfinance(ticker: str, period: str) -> list[dict[str, Any]]:
    """Fetch daily prices from yfinance."""
    from pfs.etl.yfinance_client import get_daily_prices as yf_get_daily_prices

    return yf_get_daily_prices(ticker, period=period)


def _quote_yfinance(ticker: str) -> dict[str, Any] | None:
    """Fetch latest quote from yfinance."""
    from pfs.etl.yfinance_client import get_stock_info

    info = get_stock_info(ticker)
    if "error" in info:
        return None

    price = info.get("current_price")
    if not price:
        return None

    return {
        "ticker": ticker.upper(),
        "price": float(price),
        "previous_close": info.get("previous_close"),
        "volume": None,  # Not available from info endpoint
        "latest_trading_day": "",
    }


# ──────────────────────────────────────────────
# Alpha Vantage Implementation (optional fallback)
# ──────────────────────────────────────────────

def _fetch_alpha_vantage(
    ticker: str, output_size: str = "compact"
) -> list[dict[str, Any]]:
    """Fetch daily adjusted prices from Alpha Vantage API.

    Free tier: 25 API calls per day.
    Standard tier: 5 calls/minute, unlimited daily.
    """
    if not settings.alpha_vantage_key:
        logger.warning("Alpha Vantage API key not configured — skipping")
        return []

    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": ticker.upper(),
        "outputsize": output_size,
        "apikey": settings.alpha_vantage_key,
    }

    logger.info(f"Fetching daily prices for {ticker} from Alpha Vantage ({output_size})")
    try:
        resp = httpx.get(settings.alpha_vantage_base_url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Alpha Vantage request failed: {e}")
        return []

    data = resp.json()

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

    records.sort(key=lambda x: x["date"], reverse=True)
    logger.info(f"Got {len(records)} price records for {ticker} from Alpha Vantage")
    return records


def _quote_alpha_vantage(ticker: str) -> dict[str, Any] | None:
    """Fetch latest quote from Alpha Vantage."""
    if not settings.alpha_vantage_key:
        return None

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker.upper(),
        "apikey": settings.alpha_vantage_key,
    }

    try:
        resp = httpx.get(settings.alpha_vantage_base_url, params=params, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Alpha Vantage quote request failed: {e}")
        return None

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
