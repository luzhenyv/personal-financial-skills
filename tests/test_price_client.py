"""Tests for the unified price client."""

from unittest.mock import patch

from pfs.etl.price_client import get_daily_prices, get_quote


@patch("pfs.etl.price_client._fetch_yfinance")
def test_get_daily_prices_yfinance_primary(mock_yf):
    """Default source uses yfinance."""
    mock_yf.return_value = [
        {
            "ticker": "NVDA",
            "date": "2024-01-15",
            "open_price": 500.0,
            "high_price": 510.0,
            "low_price": 495.0,
            "close_price": 505.0,
            "adjusted_close": 505.0,
            "volume": 30000000,
        }
    ]

    result = get_daily_prices("NVDA", period="1y")
    assert len(result) == 1
    assert result[0]["ticker"] == "NVDA"
    assert result[0]["close_price"] == 505.0
    mock_yf.assert_called_once_with("NVDA", "1y")


@patch("pfs.etl.price_client._fetch_yfinance")
@patch("pfs.etl.price_client._fetch_alpha_vantage")
@patch("pfs.etl.price_client.settings")
def test_get_daily_prices_fallback(mock_settings, mock_av, mock_yf):
    """Falls back to Alpha Vantage when yfinance fails and key is available."""
    mock_yf.return_value = []
    mock_settings.alpha_vantage_key = "test_key"
    mock_av.return_value = [
        {
            "ticker": "NVDA",
            "date": "2024-01-15",
            "open_price": 500.0,
            "high_price": 510.0,
            "low_price": 495.0,
            "close_price": 505.0,
            "adjusted_close": 505.0,
            "volume": 30000000,
        }
    ]

    result = get_daily_prices("NVDA", period="5y")
    assert len(result) == 1
    mock_av.assert_called_once_with("NVDA", "full")


@patch("pfs.etl.price_client._fetch_yfinance")
@patch("pfs.etl.price_client.settings")
def test_get_daily_prices_no_fallback(mock_settings, mock_yf):
    """Returns empty when yfinance fails and no AV key."""
    mock_yf.return_value = []
    mock_settings.alpha_vantage_key = ""

    result = get_daily_prices("NVDA")
    assert result == []


@patch("pfs.etl.price_client._quote_yfinance")
def test_get_quote_yfinance(mock_quote):
    """get_quote uses yfinance by default."""
    mock_quote.return_value = {
        "ticker": "NVDA",
        "price": 800.0,
        "previous_close": 795.0,
        "volume": None,
        "latest_trading_day": "",
    }

    result = get_quote("NVDA")
    assert result is not None
    assert result["ticker"] == "NVDA"
    assert result["price"] == 800.0
