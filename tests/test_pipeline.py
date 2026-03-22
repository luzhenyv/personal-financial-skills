"""Tests for the ETL pipeline."""

from unittest.mock import MagicMock, patch




@patch("pfs.etl.pipeline.get_session")
@patch("pfs.etl.pipeline.sec_client")
@patch("pfs.etl.pipeline.xbrl_parser")
@patch("pfs.etl.pipeline.get_daily_prices")
@patch("pfs.etl.pipeline.get_market_data")
@patch("pfs.etl.pipeline.get_stock_info")
@patch("pfs.etl.pipeline.get_stock_splits")
@patch("pfs.etl.pipeline.validate_financials")
@patch("pfs.etl.pipeline.validate_price_data")
def test_ingest_company_success(
    mock_val_price, mock_val_fin, mock_splits, mock_stock_info,
    mock_mkt, mock_prices, mock_xbrl, mock_sec, mock_session,
):
    """Full ingest completes with 'success' status when no errors."""
    from pfs.etl.pipeline import ingest_company

    # Setup mock DB session
    db = MagicMock()
    mock_session.return_value = db

    # Mock the EtlRun
    etl_run = MagicMock()
    etl_run.id = 1
    db.query.return_value.filter_by.return_value.first.return_value = None

    # SEC client
    mock_sec.ticker_to_cik.return_value = "0001045810"
    mock_sec.get_company_facts_cached.return_value = {
        "facts": {"us-gaap": {}}
    }
    mock_sec.get_company_metadata.return_value = {"name": "Test Corp"}
    mock_sec.get_recent_filings.return_value = []
    mock_sec.pad_cik.return_value = "0001045810"

    # XBRL parser
    mock_xbrl.get_available_fiscal_years.return_value = [2023]
    mock_xbrl.parse_income_statement.return_value = {
        "fiscal_year": 2023, "fiscal_quarter": None, "revenue": 50000000000
    }
    mock_xbrl.parse_balance_sheet.return_value = {
        "fiscal_year": 2023, "fiscal_quarter": None, "total_assets": 65000000000
    }
    mock_xbrl.parse_cash_flow.return_value = {
        "fiscal_year": 2023, "fiscal_quarter": None, "free_cash_flow": 26000000000
    }
    mock_xbrl.parse_revenue_segments.return_value = []
    mock_xbrl.compute_metrics.return_value = {"gross_margin": 0.7}

    # Price
    mock_prices.return_value = [
        {"date": "2024-01-15", "close_price": 500, "ticker": "NVDA"}
    ]
    mock_val_price.return_value = []

    # Market data for valuation
    mock_mkt.return_value = {"price": 800, "market_cap": 2e12, "shares_outstanding": 2.5e9}

    # yfinance
    mock_stock_info.return_value = {"name": "Test Corp", "sector": "Tech"}
    mock_splits.return_value = []

    # Validation
    mock_val_fin.return_value = []

    result = ingest_company("NVDA", years=3, db=db)

    assert result["status"] in ("success", "partial")
    assert result["ticker"] == "NVDA"
    assert "counts" in result


@patch("pfs.etl.pipeline.get_session")
@patch("pfs.etl.pipeline.sec_client")
def test_ingest_company_bad_cik(mock_sec, mock_session):
    """Ingest fails gracefully when ticker can't be resolved."""
    from pfs.etl.pipeline import ingest_company

    db = MagicMock()
    etl_run = MagicMock()
    etl_run.id = 2

    mock_sec.ticker_to_cik.return_value = None

    result = ingest_company("FAKE", years=1, db=db)

    assert result["status"] == "failed"
    assert any("CIK" in str(e) for e in result["errors"])


def test_build_parser():
    """CLI parser handles all subcommands."""
    from pfs.etl.pipeline import _build_parser

    parser = _build_parser()

    # ingest
    args = parser.parse_args(["ingest", "NVDA", "--years", "3"])
    assert args.command == "ingest"
    assert args.ticker == "NVDA"
    assert args.years == 3

    # ingest-batch
    args = parser.parse_args(["ingest-batch", "NVDA,AAPL"])
    assert args.command == "ingest-batch"
    assert args.tickers == "NVDA,AAPL"

    # sync-prices
    args = parser.parse_args(["sync-prices", "--tickers", "NVDA"])
    assert args.command == "sync-prices"
    assert args.tickers == "NVDA"


def test_validation_module():
    """Basic validation module tests."""
    from pfs.etl.validation import validate_financials, validate_price_data

    # Within tolerance (1% < 2%)
    sec = {"revenue": 100, "net_income": 20}
    yf = {"total_revenue": 101, "net_income": 20}
    result = validate_financials(sec, yf, "TEST", tolerance=0.02)
    assert len(result) == 0

    # Outside tolerance (5% > 2%)
    sec2 = {"revenue": 100, "net_income": 20}
    yf2 = {"total_revenue": 105, "net_income": 20}
    result2 = validate_financials(sec2, yf2, "TEST", tolerance=0.02)
    assert len(result2) == 1

    # Price data validation
    prices = [
        {"date": "2024-01-15", "open_price": 10, "high_price": 12,
         "low_price": 9, "close_price": 11, "volume": 100},
    ]
    issues = validate_price_data(prices, "TEST")
    assert len(issues) == 0

    # Bad price data
    bad_prices = [
        {"date": "2024-01-15", "open_price": -5, "high_price": 10,
         "low_price": 12, "close_price": 11, "volume": 100},
    ]
    issues = validate_price_data(bad_prices, "TEST")
    assert len(issues) >= 1  # negative open_price
