"""Smoke tests for the ETL pipeline and company profile."""

import pytest
from unittest.mock import patch, MagicMock

from pfs.etl.xbrl_parser import (
    parse_income_statement,
    parse_balance_sheet,
    parse_cash_flow,
    compute_metrics,
    get_available_fiscal_years,
)


# Minimal XBRL facts fixture
SAMPLE_FACTS = {
    "cik": 1045810,
    "entityName": "TEST CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {"val": 50000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                        {"val": 30000000000, "fy": 2022, "fp": "FY", "form": "10-K",
                         "filed": "2023-02-20", "end": "2023-01-29"},
                    ]
                }
            },
            "GrossProfit": {
                "label": "Gross Profit",
                "units": {
                    "USD": [
                        {"val": 35000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                        {"val": 18000000000, "fy": 2022, "fp": "FY", "form": "10-K",
                         "filed": "2023-02-20", "end": "2023-01-29"},
                    ]
                }
            },
            "OperatingIncomeLoss": {
                "label": "Operating Income",
                "units": {
                    "USD": [
                        {"val": 25000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                        {"val": 10000000000, "fy": 2022, "fp": "FY", "form": "10-K",
                         "filed": "2023-02-20", "end": "2023-01-29"},
                    ]
                }
            },
            "NetIncomeLoss": {
                "label": "Net Income",
                "units": {
                    "USD": [
                        {"val": 20000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                        {"val": 8000000000, "fy": 2022, "fp": "FY", "form": "10-K",
                         "filed": "2023-02-20", "end": "2023-01-29"},
                    ]
                }
            },
            "Assets": {
                "label": "Assets",
                "units": {
                    "USD": [
                        {"val": 65000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                    ]
                }
            },
            "StockholdersEquity": {
                "label": "Equity",
                "units": {
                    "USD": [
                        {"val": 42000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                    ]
                }
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "label": "Cash from Operations",
                "units": {
                    "USD": [
                        {"val": 28000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                    ]
                }
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "label": "CapEx",
                "units": {
                    "USD": [
                        {"val": 2000000000, "fy": 2023, "fp": "FY", "form": "10-K",
                         "filed": "2024-02-20", "end": "2024-01-28"},
                    ]
                }
            },
        }
    }
}


def test_get_available_fiscal_years():
    years = get_available_fiscal_years(SAMPLE_FACTS, min_year=2020)
    assert 2023 in years
    assert 2022 in years


def test_parse_income_statement():
    result = parse_income_statement(SAMPLE_FACTS, 2023)
    assert result["fiscal_year"] == 2023
    assert result["revenue"] == 50000000000
    assert result["gross_profit"] == 35000000000
    assert result["operating_income"] == 25000000000
    assert result["net_income"] == 20000000000


def test_parse_balance_sheet():
    result = parse_balance_sheet(SAMPLE_FACTS, 2023)
    assert result["fiscal_year"] == 2023
    assert result["total_assets"] == 65000000000
    assert result["total_stockholders_equity"] == 42000000000


def test_parse_cash_flow():
    result = parse_cash_flow(SAMPLE_FACTS, 2023)
    assert result["fiscal_year"] == 2023
    assert result["cash_from_operations"] == 28000000000
    assert result["capital_expenditure"] == 2000000000
    assert result["free_cash_flow"] == 26000000000  # 28B - 2B


def test_compute_metrics():
    income = {
        "revenue": 50000000000,
        "gross_profit": 35000000000,
        "operating_income": 25000000000,
        "net_income": 20000000000,
        "eps_diluted": 8.0,
        "pretax_income": 25000000000,
        "income_tax": 5000000000,
    }
    balance = {
        "total_assets": 65000000000,
        "total_stockholders_equity": 42000000000,
        "total_current_assets": 40000000000,
        "total_current_liabilities": 10000000000,
        "inventory": 5000000000,
        "long_term_debt": 10000000000,
        "short_term_debt": 1000000000,
        "cash_and_equivalents": 8000000000,
    }
    cash_flow = {
        "free_cash_flow": 26000000000,
    }
    prev_income = {
        "revenue": 30000000000,
        "operating_income": 10000000000,
        "net_income": 8000000000,
        "eps_diluted": 3.2,
    }

    metrics = compute_metrics(income, balance, cash_flow, prev_income)

    # Margins
    assert metrics["gross_margin"] == pytest.approx(0.7, rel=0.01)
    assert metrics["operating_margin"] == pytest.approx(0.5, rel=0.01)
    assert metrics["net_margin"] == pytest.approx(0.4, rel=0.01)
    assert metrics["fcf_margin"] == pytest.approx(0.52, rel=0.01)

    # Growth
    assert metrics["revenue_growth"] == pytest.approx(0.6667, rel=0.01)
    assert metrics["net_income_growth"] == pytest.approx(1.5, rel=0.01)

    # Returns
    assert metrics["roe"] is not None
    assert metrics["roa"] is not None

    # Leverage
    assert metrics["current_ratio"] == pytest.approx(4.0, rel=0.01)


def test_compute_metrics_ebitda():
    """EBITDA = Operating Income + D&A."""
    income = {
        "revenue": 50000000000,
        "gross_profit": 35000000000,
        "operating_income": 25000000000,
        "net_income": 20000000000,
        "cost_of_revenue": 15000000000,
    }
    balance = {
        "total_assets": 65000000000,
        "total_stockholders_equity": 42000000000,
        "accounts_receivable": 7000000000,
        "inventory": 5000000000,
        "accounts_payable": 3000000000,
    }
    cash_flow = {
        "free_cash_flow": 26000000000,
        "depreciation_amortization": 3000000000,
    }

    metrics = compute_metrics(income, balance, cash_flow)

    assert metrics["ebitda"] == 28000000000  # 25B + 3B
    assert metrics["ebitda_margin"] == pytest.approx(0.56, rel=0.01)


def test_compute_metrics_efficiency():
    """DSO, DIO, DPO calculations."""
    income = {
        "revenue": 36500000000,
        "cost_of_revenue": 18250000000,
        "operating_income": 10000000000,
        "net_income": 8000000000,
        "gross_profit": 18250000000,
    }
    balance = {
        "accounts_receivable": 5000000000,
        "inventory": 2500000000,
        "accounts_payable": 1825000000,
        "total_assets": 50000000000,
        "total_stockholders_equity": 30000000000,
    }
    cash_flow = {"free_cash_flow": 7000000000}

    metrics = compute_metrics(income, balance, cash_flow)

    # DSO = (5B / 36.5B) * 365 ≈ 50 days
    assert metrics["dso"] == pytest.approx(50.0, rel=0.02)
    # DIO = (2.5B / 18.25B) * 365 ≈ 50 days
    assert metrics["dio"] == pytest.approx(50.0, rel=0.02)
    # DPO = (1.825B / 18.25B) * 365 ≈ 36.5 days
    assert metrics["dpo"] == pytest.approx(36.5, rel=0.02)


def test_compute_metrics_with_market_data():
    """Valuation metrics (PE, PS, PB, EV/EBITDA, FCF yield)."""
    income = {
        "revenue": 50000000000,
        "gross_profit": 35000000000,
        "operating_income": 25000000000,
        "net_income": 20000000000,
        "eps_diluted": 8.0,
        "cost_of_revenue": 15000000000,
    }
    balance = {
        "total_assets": 65000000000,
        "total_stockholders_equity": 42000000000,
        "long_term_debt": 10000000000,
        "short_term_debt": 1000000000,
        "cash_and_equivalents": 8000000000,
    }
    cash_flow = {
        "free_cash_flow": 26000000000,
        "depreciation_amortization": 3000000000,
    }
    market_data = {
        "price": 800.0,
        "market_cap": 2000000000000,  # $2T
        "shares_outstanding": 2500000000,
    }

    metrics = compute_metrics(income, balance, cash_flow, market_data=market_data)

    # PE = 800 / 8 = 100
    assert metrics["pe_ratio"] == pytest.approx(100.0, rel=0.01)
    # PS = 2T / 50B = 40
    assert metrics["ps_ratio"] == pytest.approx(40.0, rel=0.01)
    # PB = 2T / 42B ≈ 47.62
    assert metrics["pb_ratio"] == pytest.approx(47.62, rel=0.01)
    # EV = 2T + 11B - 8B = 2.003T, EBITDA = 28B, EV/EBITDA ≈ 71.5
    assert metrics["ev_to_ebitda"] == pytest.approx(71.54, rel=0.02)
    # FCF yield = 26B / 2T = 0.013
    assert metrics["fcf_yield"] == pytest.approx(0.013, rel=0.01)


def test_parse_revenue_segments():
    """Revenue segment parsing returns a list (possibly empty for basic facts)."""
    from pfs.etl.xbrl_parser import parse_revenue_segments

    segments = parse_revenue_segments(SAMPLE_FACTS, 2023)
    assert isinstance(segments, list)


def test_parse_missing_year():
    """Parsing a year with no data should return None values."""
    result = parse_income_statement(SAMPLE_FACTS, 2020)
    assert result["fiscal_year"] == 2020
    assert result["revenue"] is None
