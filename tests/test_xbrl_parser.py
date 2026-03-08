"""Smoke tests for the ETL pipeline and company profile."""

import pytest
from unittest.mock import patch, MagicMock

from src.etl.xbrl_parser import (
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


def test_parse_missing_year():
    """Parsing a year with no data should return None values."""
    result = parse_income_statement(SAMPLE_FACTS, 2020)
    assert result["fiscal_year"] == 2020
    assert result["revenue"] is None
