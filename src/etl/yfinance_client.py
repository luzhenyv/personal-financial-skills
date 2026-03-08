"""Yahoo Finance client — supplement SEC data with market data.

Uses the yfinance library for:
- Real-time / delayed quotes
- Sector and industry classification
- Peer company discovery
- Historical price data (as backup to Alpha Vantage)

Free, no API key required. Rate limits are lenient.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import yfinance as yf

    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False
    logger.warning("yfinance not installed — run: uv add yfinance")


def get_stock_info(ticker: str) -> dict[str, Any]:
    """Get comprehensive stock info from Yahoo Finance.

    Returns sector, industry, market cap, current price, description, etc.
    """
    if not _HAS_YFINANCE:
        return {"error": "yfinance not installed"}

    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info
        return {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "ps_trailing": info.get("priceToSalesTrailing12Months"),
            "pb_ratio": info.get("priceToBook"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "description": info.get("longBusinessSummary", ""),
            "website": info.get("website", ""),
            "employees": info.get("fullTimeEmployees"),
            "country": info.get("country", ""),
            "exchange": info.get("exchange", ""),
        }
    except Exception as e:
        logger.error(f"yfinance error for {ticker}: {e}")
        return {"error": str(e)}


def get_current_price(ticker: str) -> float | None:
    """Get the current/latest price for a ticker."""
    if not _HAS_YFINANCE:
        return None

    try:
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception as e:
        logger.error(f"Price fetch error for {ticker}: {e}")
        return None


def get_peers(ticker: str, n: int = 10) -> list[str]:
    """Discover peer companies in the same sector/industry.

    Uses Yahoo Finance's recommended tickers and sector data.
    """
    if not _HAS_YFINANCE:
        return []

    try:
        stock = yf.Ticker(ticker.upper())
        # yfinance has a recommendations attribute on some tickers
        # but more reliably we can check the sector
        info = stock.info
        sector = info.get("sector", "")
        industry = info.get("industry", "")

        # Get sector peers from known mappings
        peers = _get_sector_peers(ticker.upper(), sector, industry)
        return peers[:n]
    except Exception as e:
        logger.error(f"Peer discovery error for {ticker}: {e}")
        return []


def get_historical_prices(
    ticker: str, period: str = "1y", interval: str = "1d"
) -> list[dict[str, Any]]:
    """Get historical price data from Yahoo Finance.

    Args:
        ticker: Stock symbol
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
    """
    if not _HAS_YFINANCE:
        return []

    try:
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period=period, interval=interval)

        records = []
        for date_idx, row in hist.iterrows():
            records.append({
                "date": str(date_idx.date()),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })
        return records
    except Exception as e:
        logger.error(f"Historical prices error for {ticker}: {e}")
        return []


# ──────────────────────────────────────────────
# Sector Peer Mapping (curated for common sectors)
# ──────────────────────────────────────────────

_SECTOR_PEERS = {
    # Semiconductors
    "Semiconductors": [
        "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN", "ADI", "MRVL", "NXPI", "ON",
        "MU", "LRCX", "KLAC", "ASML", "AMAT", "TSM",
    ],
    # Software
    "Software—Infrastructure": [
        "MSFT", "ORCL", "CRM", "NOW", "SNOW", "PLTR", "MDB", "DDOG", "NET", "PANW",
    ],
    "Software—Application": [
        "ADBE", "INTU", "SHOP", "SQ", "WDAY", "ZM", "DOCU", "HUBS", "VEEV", "TEAM",
    ],
    # Internet
    "Internet Content & Information": [
        "GOOG", "META", "SNAP", "PINS", "RDDT", "SPOT",
    ],
    "Internet Retail": [
        "AMZN", "BABA", "JD", "PDD", "MELI", "SE", "CPNG", "ETSY",
    ],
    # Consumer
    "Consumer Electronics": [
        "AAPL", "SONY", "DELL", "HPQ", "LOGI",
    ],
    # Autos
    "Auto Manufacturers": [
        "TSLA", "TM", "F", "GM", "RIVN", "LCID", "NIO", "LI", "XPEV",
    ],
    # Financials
    "Banks—Diversified": [
        "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "COF",
    ],
    # Healthcare / Pharma
    "Drug Manufacturers—General": [
        "JNJ", "PFE", "MRK", "ABBV", "LLY", "NVO", "AZN", "BMY", "AMGN", "GILD",
    ],
    "Biotechnology": [
        "MRNA", "REGN", "VRTX", "BIIB", "ILMN", "SGEN", "ALNY",
    ],
    # Energy
    "Oil & Gas Integrated": [
        "XOM", "CVX", "COP", "EOG", "SLB", "OXY", "PSX", "VLO", "MPC",
    ],
}


def _get_sector_peers(ticker: str, sector: str, industry: str) -> list[str]:
    """Find peers based on industry, then sector."""
    # Try industry first (more specific)
    for key, tickers in _SECTOR_PEERS.items():
        if key.lower() in industry.lower() or industry.lower() in key.lower():
            return [t for t in tickers if t != ticker]

    # Try sector match
    for key, tickers in _SECTOR_PEERS.items():
        if key.lower() in sector.lower() or sector.lower() in key.lower():
            return [t for t in tickers if t != ticker]

    return []
