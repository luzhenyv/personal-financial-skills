"""Yahoo Finance client — primary market data source.

Uses the yfinance library for:
- Daily OHLCV price data (primary price source, replaces Alpha Vantage)
- Real-time / delayed quotes
- Sector and industry classification
- Stock split history
- Key financials (for cross-validation against SEC XBRL)
- Peer company discovery

Free, no API key required. Rate limits are lenient.
"""

import logging
from datetime import date
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
            "gross_margins": info.get("grossMargins"),
            "operating_margins": info.get("operatingMargins"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "description": info.get("longBusinessSummary", ""),
            "website": info.get("website", ""),
            "employees": info.get("fullTimeEmployees"),
            "country": info.get("country", ""),
            "exchange": info.get("exchange", ""),
            "shares_outstanding": info.get("sharesOutstanding"),
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


def get_daily_prices(
    ticker: str, period: str = "5y"
) -> list[dict[str, Any]]:
    """Fetch daily adjusted OHLCV prices from Yahoo Finance.

    This is the primary price data source for the ETL pipeline.

    Args:
        ticker: Stock symbol (e.g. 'NVDA')
        period: Data period — '1y', '2y', '5y', '10y', 'max', etc.

    Returns:
        List of price records matching DailyPrice model fields,
        sorted by date descending.
    """
    if not _HAS_YFINANCE:
        logger.warning("yfinance not installed — skipping price fetch")
        return []

    try:
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period=period, interval="1d", auto_adjust=False)

        if hist.empty:
            logger.warning(f"No price data from yfinance for {ticker}")
            return []

        records = []
        for date_idx, row in hist.iterrows():
            records.append({
                "ticker": ticker.upper(),
                "date": str(date_idx.date()),
                "open_price": float(row["Open"]),
                "high_price": float(row["High"]),
                "low_price": float(row["Low"]),
                "close_price": float(row["Close"]),
                "adjusted_close": float(row.get("Adj Close", row["Close"])),
                "volume": int(row["Volume"]),
            })

        # Sort by date descending (most recent first)
        records.sort(key=lambda x: x["date"], reverse=True)
        logger.info(f"Got {len(records)} price records for {ticker} from yfinance")
        return records

    except Exception as e:
        logger.error(f"yfinance daily prices error for {ticker}: {e}")
        return []


def get_stock_splits(ticker: str) -> list[dict[str, Any]]:
    """Fetch stock split history from Yahoo Finance.

    Returns:
        List of {date: "YYYY-MM-DD", ratio: float} dicts, sorted by date ascending.
        The ratio is the split multiplier (e.g. 10.0 for a 10:1 split).
    """
    if not _HAS_YFINANCE:
        return []

    try:
        stock = yf.Ticker(ticker.upper())
        splits = stock.splits

        if splits is None or splits.empty:
            return []

        result = []
        for date_idx, ratio in splits.items():
            result.append({
                "date": str(date_idx.date()),
                "ratio": float(ratio),
            })

        result.sort(key=lambda x: x["date"])
        logger.info(f"Got {len(result)} stock splits for {ticker}")
        return result

    except Exception as e:
        logger.error(f"yfinance splits error for {ticker}: {e}")
        return []


def get_key_financials(ticker: str) -> dict[str, Any]:
    """Fetch key financial data from yfinance for cross-validation against SEC XBRL.

    Returns revenue, net income, EPS, and other key metrics from yfinance's
    financial statements. Used by the validation module to flag discrepancies.
    """
    if not _HAS_YFINANCE:
        return {"error": "yfinance not installed"}

    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        return {
            "ticker": ticker.upper(),
            "revenue": info.get("totalRevenue"),
            "net_income": info.get("netIncomeToCommon"),
            "eps_trailing": info.get("trailingEps"),
            "gross_margins": info.get("grossMargins"),
            "operating_margins": info.get("operatingMargins"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "beta": info.get("beta"),
            "enterprise_value": info.get("enterpriseValue"),
        }

    except Exception as e:
        logger.error(f"yfinance financials error for {ticker}: {e}")
        return {"error": str(e)}


def get_market_data(ticker: str) -> dict[str, Any] | None:
    """Get current market data needed for valuation metric computation.

    Returns a dict with price, market_cap, and shares_outstanding.
    Used as input to xbrl_parser.compute_metrics(market_data=...).
    """
    if not _HAS_YFINANCE:
        return None

    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        mkt_cap = info.get("marketCap")
        shares = info.get("sharesOutstanding")

        if not price:
            return None

        return {
            "price": float(price),
            "market_cap": float(mkt_cap) if mkt_cap else None,
            "shares_outstanding": float(shares) if shares else None,
        }

    except Exception as e:
        logger.error(f"yfinance market data error for {ticker}: {e}")
        return None


def get_historical_capex(ticker: str) -> dict[int, int | None]:
    """Fetch historical annual CapEx from yfinance cashflow statement.

    Used as a fallback when the SEC XBRL company_facts.json is missing the
    capital_expenditure tag for a given fiscal year (e.g. NVDA FY2023 uses
    PaymentsToAcquireProductiveAssets at annual level, which SEC EDGAR omits).

    Returns:
        Dict mapping fiscal_year (int) → capital_expenditure (absolute value, int).
        Years where CapEx is NaN are excluded.
    """
    if not _HAS_YFINANCE:
        return {}

    try:
        stock = yf.Ticker(ticker.upper())
        cf = stock.cashflow  # columns = period end dates, index = line items

        if cf is None or cf.empty:
            return {}

        capex_row = None
        for label in ("Capital Expenditure", "Purchase Of PPE", "Net PPE Purchase And Sale"):
            if label in cf.index:
                capex_row = cf.loc[label]
                break

        if capex_row is None:
            return {}

        result: dict[int, int | None] = {}
        for col, val in capex_row.items():
            try:
                import pandas as pd
                if pd.isna(val):
                    continue
                # yfinance reports CapEx as a negative number; store absolute value
                result[col.year] = abs(int(val))
            except Exception:
                continue

        logger.info(f"yfinance CapEx fallback for {ticker}: {result}")
        return result

    except Exception as e:
        logger.error(f"yfinance historical capex error for {ticker}: {e}")
        return {}


def get_peers(ticker: str, n: int = 10) -> list[str]:
    """Discover peer companies in the same sector/industry."""
    if not _HAS_YFINANCE:
        return []

    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info
        sector = info.get("sector", "")
        industry = info.get("industry", "")

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

_SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": [
        "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AVGO", "ADBE", "CRM",
        "CSCO", "INTC", "AMD", "QCOM", "TXN", "INTU", "NOW", "ORCL",
    ],
    "Communication Services": [
        "GOOGL", "META", "DIS", "CMCSA", "NFLX", "T", "VZ", "TMUS",
    ],
    "Consumer Cyclical": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX",
    ],
    "Healthcare": [
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR",
    ],
    "Financial Services": [
        "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "V", "MA",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "MPC", "VLO",
    ],
    "Consumer Defensive": [
        "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "CL",
    ],
    "Industrials": [
        "UPS", "RTX", "HON", "CAT", "DE", "GE", "MMM", "LMT", "BA",
    ],
}


def _get_sector_peers(ticker: str, sector: str, industry: str) -> list[str]:
    """Get peer tickers from the curated sector map, excluding the input ticker."""
    peers = _SECTOR_PEERS.get(sector, [])
    return [p for p in peers if p != ticker]
