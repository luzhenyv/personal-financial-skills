"""API tests — FastAPI TestClient with mocked DB sessions.

All tests run in-process with no real server or database required.
The SQLAlchemy `get_db` dependency is overridden for each test via
FastAPI's `app.dependency_overrides` mechanism.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pfs.app import app
from pfs.api.deps import get_db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_row(model_cls, data: dict[str, Any]):
    """Return a stub ORM row whose __table__.columns iteration matches *data*.

    The routers convert rows via ``_row_to_dict`` which iterates
    ``obj.__table__.columns`` and calls ``getattr(obj, col.name)``.
    We satisfy that by using the real SQLAlchemy model's ``__table__``
    while overriding attribute values via a simple object.
    """

    class _Row:
        __table__ = model_cls.__table__

    row = _Row()
    # Seed every column with None first so getattr never raises
    for col in model_cls.__table__.columns:
        setattr(row, col.name, None)
    # Apply provided values
    for k, v in data.items():
        setattr(row, k, v)
    return row


def _make_chain_mock(*, first=None, all_rows=None):
    """Return a MagicMock whose query-chain methods return *self*.

    Terminal calls:
      .first()  → *first*
      .all()    → *all_rows* (default: [])
    """
    mock = MagicMock()
    all_rows = all_rows or []

    # Make every chaining method return the same mock so the length of the
    # chain doesn't matter.
    for method in ("filter", "order_by", "offset", "limit"):
        getattr(mock, method).return_value = mock

    mock.first.return_value = first
    mock.all.return_value = all_rows
    return mock


def _make_db(*, first=None, all_rows=None):
    """Return a mock Session whose .query() returns a chain mock."""
    chain = _make_chain_mock(first=first, all_rows=all_rows)
    db = MagicMock()
    db.query.return_value = chain
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Sample data
# ─────────────────────────────────────────────────────────────────────────────

from pfs.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    EtlRun,
    FinancialMetric,
    IncomeStatement,
    RevenueSegment,
    SecFiling,
)

_COMPANY = dict(
    id=1, cik="0001045810", ticker="NVDA", name="NVIDIA Corporation",
    sector="Technology", industry="Semiconductors", sic_code="3674",
    exchange="NASDAQ", fiscal_year_end="01/26", market_cap=3_000_000_000_000,
    employee_count=36000, headquarters="Santa Clara, CA",
    description="GPU maker", website="https://www.nvidia.com",
    created_at=None, updated_at=None,
)

_ETL_RUN = dict(
    id=42, ticker="NVDA", run_type="full_ingest", status="success",
    started_at=None, completed_at=None,
    income_statements=5, balance_sheets=5, cash_flow_statements=5,
    financial_metrics=5, revenue_segments=2, daily_prices=252,
    sec_filings=3, filings_downloaded=3, errors=None, metadata=None,
)

_FILING = dict(
    id=1, ticker="NVDA", cik="0001045810",
    accession_number="0001045810-24-000010", filing_type="10-K",
    filing_date=date(2024, 2, 22), reporting_date=date(2024, 1, 28),
    primary_doc_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581024000010/nvda20240128.htm",
    xbrl_url=None, is_processed=True, processed_at=None, created_at=None,
)

_INCOME = dict(
    id=1, ticker="NVDA", fiscal_year=2024, fiscal_quarter=None,
    filing_type="10-K", filing_date=date(2024, 2, 22),
    revenue=60_922_000_000, cost_of_revenue=16_621_000_000,
    gross_profit=44_301_000_000, research_and_development=8_675_000_000,
    selling_general_admin=2_654_000_000, depreciation_amortization=1_508_000_000,
    operating_expenses=11_329_000_000, operating_income=32_972_000_000,
    interest_expense=257_000_000, interest_income=1_038_000_000,
    other_income=None, pretax_income=33_753_000_000,
    income_tax=4_042_000_000, net_income=29_711_000_000,
    eps_basic=None, eps_diluted=None, shares_basic=None, shares_diluted=None,
    source="sec_xbrl", raw_json=None, created_at=None,
)

_BALANCE = dict(
    id=1, ticker="NVDA", fiscal_year=2024, fiscal_quarter=None,
    filing_type="10-K", filing_date=date(2024, 2, 22),
    cash_and_equivalents=7_281_000_000, short_term_investments=18_704_000_000,
    accounts_receivable=9_999_000_000, inventory=5_282_000_000,
    total_current_assets=45_515_000_000, property_plant_equipment=3_496_000_000,
    goodwill=4_430_000_000, intangible_assets=None,
    total_assets=65_728_000_000, accounts_payable=2_797_000_000,
    deferred_revenue=None, short_term_debt=None,
    total_current_liabilities=10_631_000_000, long_term_debt=8_462_000_000,
    total_liabilities=22_966_000_000, common_stock=None,
    retained_earnings=29_817_000_000,
    total_stockholders_equity=42_978_000_000,
    source="sec_xbrl", raw_json=None, created_at=None,
)

_CASHFLOW = dict(
    id=1, ticker="NVDA", fiscal_year=2024, fiscal_quarter=None,
    filing_type="10-K", filing_date=date(2024, 2, 22),
    net_income=29_711_000_000, depreciation_amortization=1_508_000_000,
    stock_based_compensation=1_257_000_000, change_in_working_capital=None,
    cash_from_operations=28_660_000_000, capital_expenditure=-1_069_000_000,
    acquisitions=None, purchases_of_investments=None, sales_of_investments=None,
    cash_from_investing=-15_856_000_000, debt_issuance=None, debt_repayment=None,
    share_repurchase=-9_533_000_000, dividends_paid=None,
    cash_from_financing=-14_898_000_000, net_change_in_cash=-2_095_000_000,
    free_cash_flow=27_591_000_000, source="sec_xbrl", raw_json=None, created_at=None,
)

_METRIC = dict(
    id=1, ticker="NVDA", fiscal_year=2024, fiscal_quarter=None,
    gross_margin=0.7272, operating_margin=0.5412, ebitda_margin=0.5659,
    net_margin=0.4876, fcf_margin=0.4529, revenue_growth=1.2222,
    operating_income_growth=None, net_income_growth=None, eps_growth=None,
    roe=0.6912, roa=0.4521, roic=None,
    debt_to_equity=0.1969, current_ratio=4.2808, quick_ratio=None,
    dso=59.88, dio=None, dpo=None,
    ebitda=34_480_000_000, pe_ratio=100.0, ps_ratio=40.0,
    pb_ratio=47.62, ev_to_ebitda=71.54, fcf_yield=0.013, calculated_at=None,
)

_PRICE = dict(
    id=1, ticker="NVDA", date=date(2024, 1, 28),
    open_price=612.0, high_price=627.5, low_price=608.0,
    close_price=625.0, adjusted_close=625.0, volume=50_000_000, created_at=None,
)

_SEGMENT = dict(
    id=1, ticker="NVDA", fiscal_year=2024, fiscal_quarter=None,
    segment_type="product", segment_name="Data Center",
    revenue=47_500_000_000, pct_of_total=0.7799,
    source="sec_xbrl", raw_json=None, created_at=None,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def company_row():
    return _make_row(Company, _COMPANY)


@pytest.fixture
def etl_run_row():
    return _make_row(EtlRun, _ETL_RUN)


@pytest.fixture
def filing_row():
    return _make_row(SecFiling, _FILING)


@pytest.fixture
def client_with_db():
    """Yield a (TestClient, setter) pair.

    Call ``setter(first=..., all_rows=...)`` to configure query results
    before each request.
    """
    state: dict = {}

    def override_get_db():
        yield state["db"]

    app.dependency_overrides[get_db] = override_get_db
    tc = TestClient(app, raise_server_exceptions=False)

    def set_db(*, first=None, all_rows=None):
        state["db"] = _make_db(first=first, all_rows=all_rows)
        return state["db"]

    yield tc, set_db
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────


def test_health_check():
    with TestClient(app) as tc:
        resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Companies
# ─────────────────────────────────────────────────────────────────────────────


def test_list_companies(client_with_db, company_row):
    tc, set_db = client_with_db
    set_db(all_rows=[company_row])
    resp = tc.get("/api/companies/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["ticker"] == "NVDA"


def test_list_companies_sector_filter(client_with_db, company_row):
    tc, set_db = client_with_db
    set_db(all_rows=[company_row])
    resp = tc.get("/api/companies/?sector=Technology")
    assert resp.status_code == 200
    assert resp.json()[0]["sector"] == "Technology"


def test_list_companies_pagination(client_with_db, company_row):
    tc, set_db = client_with_db
    set_db(all_rows=[company_row])
    resp = tc.get("/api/companies/?limit=10&offset=0")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_companies_empty(client_with_db):
    tc, set_db = client_with_db
    set_db(all_rows=[])
    resp = tc.get("/api/companies/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_company_found(client_with_db, company_row):
    tc, set_db = client_with_db
    set_db(first=company_row)
    resp = tc.get("/api/companies/NVDA")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "NVDA"
    assert resp.json()["name"] == "NVIDIA Corporation"


def test_get_company_not_found(client_with_db):
    tc, set_db = client_with_db
    set_db(first=None)
    resp = tc.get("/api/companies/UNKNOWN")
    assert resp.status_code == 404
    assert "UNKNOWN" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# ETL
# ─────────────────────────────────────────────────────────────────────────────


def test_ingest_trigger(client_with_db):
    tc, set_db = client_with_db

    def _db_gen():
        db = MagicMock()
        # Make db.refresh set the id on the EtlRun passed to it
        def _refresh(obj):
            obj.id = 42

        db.refresh.side_effect = _refresh
        yield db

    app.dependency_overrides[get_db] = _db_gen

    with patch("pfs.services.etl.threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()
        resp = tc.post("/api/etl/ingest", json={"ticker": "nvda"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "NVDA"
    assert body["etl_run_id"] == 42
    assert "Ingestion started" in body["message"]
    mock_thread.return_value.start.assert_called_once()


def test_sync_prices(client_with_db):
    tc, set_db = client_with_db
    set_db()
    with patch("pfs.etl.pipeline.sync_prices", return_value={"NVDA": "ok"}) as mock_sync:
        resp = tc.post("/api/etl/sync-prices", json={"tickers": ["NVDA"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Price sync completed"
    assert "results" in body


def test_sync_prices_all(client_with_db):
    tc, set_db = client_with_db
    set_db()
    with patch("pfs.etl.pipeline.sync_prices", return_value={}) as mock_sync:
        resp = tc.post("/api/etl/sync-prices", json={})
    assert resp.status_code == 200
    mock_sync.assert_called_once_with(tickers=None)


def test_list_etl_runs(client_with_db, etl_run_row):
    tc, set_db = client_with_db
    set_db(all_rows=[etl_run_row])
    resp = tc.get("/api/etl/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["ticker"] == "NVDA"
    assert data[0]["status"] == "success"


def test_list_etl_runs_with_filters(client_with_db, etl_run_row):
    tc, set_db = client_with_db
    set_db(all_rows=[etl_run_row])
    resp = tc.get("/api/etl/runs?ticker=NVDA&status=success&limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_latest_etl_run_found(client_with_db, etl_run_row):
    tc, set_db = client_with_db
    set_db(first=etl_run_row)
    resp = tc.get("/api/etl/runs/NVDA")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "NVDA"
    assert resp.json()["id"] == 42


def test_get_latest_etl_run_not_found(client_with_db):
    tc, set_db = client_with_db
    set_db(first=None)
    resp = tc.get("/api/etl/runs/UNKNOWN")
    assert resp.status_code == 404
    assert "UNKNOWN" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Filings
# ─────────────────────────────────────────────────────────────────────────────


def _make_filing_db(*, company=None, filing=None, all_filings=None):
    """Build a DB mock that returns different rows for Company vs SecFiling queries."""
    db = MagicMock()
    company_chain = _make_chain_mock(first=company, all_rows=[company] if company else [])
    filing_chain = _make_chain_mock(first=filing, all_rows=all_filings or [])

    from pfs.db.models import Company as CompanyModel, SecFiling as SecFilingModel

    def _query(model):
        if model is CompanyModel:
            return company_chain
        return filing_chain

    db.query.side_effect = _query
    return db


@pytest.fixture
def filings_client(company_row, filing_row):
    """TestClient pre-wired with a Company + one SecFiling in the mock DB."""
    filing_row.reporting_date = date(2024, 1, 28)
    filing_row.filing_type = "10-K"

    db = _make_filing_db(
        company=company_row,
        filing=filing_row,
        all_filings=[filing_row],
    )

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, raise_server_exceptions=False), db
    app.dependency_overrides.clear()


def test_list_filings(filings_client):
    tc, _ = filings_client
    with patch("pathlib.Path.exists", return_value=False):
        resp = tc.get("/api/filings/NVDA")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["ticker"] == "NVDA"
    assert data[0]["filing_type"] == "10-K"
    assert data[0]["local_path"] is None


def test_list_filings_form_type_filter(filings_client):
    tc, _ = filings_client
    with patch("pathlib.Path.exists", return_value=False):
        resp = tc.get("/api/filings/NVDA?form_type=10-K")
    assert resp.status_code == 200


def test_list_filings_unknown_company(client_with_db):
    tc, set_db = client_with_db
    # Must return None for any company lookup
    db = _make_filing_db(company=None)

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = tc.get("/api/filings/UNKNOWN")
    assert resp.status_code == 404


def test_get_filing_found(filings_client):
    tc, _ = filings_client
    with patch("pathlib.Path.exists", return_value=False):
        resp = tc.get("/api/filings/NVDA/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1
    assert resp.json()["filing_type"] == "10-K"


def test_get_filing_not_found(client_with_db, company_row):
    tc, set_db = client_with_db
    db = _make_filing_db(company=company_row, filing=None)

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = tc.get("/api/filings/NVDA/999")
    assert resp.status_code == 404


def test_get_filing_content_local(filings_client):
    tc, _ = filings_client
    html_bytes = b"<html><body>10-K content</body></html>"
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.name = "10-K_2024_01.htm"
    mock_path.read_bytes.return_value = html_bytes

    with patch("pfs.services.filings._local_filing_path", return_value=mock_path):
        resp = tc.get("/api/filings/NVDA/1/content")

    assert resp.status_code == 200
    assert b"10-K content" in resp.content


def test_get_filing_content_not_found(client_with_db):
    tc, set_db = client_with_db
    db = _make_filing_db(company=None, filing=None)

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = tc.get("/api/filings/NVDA/999/content")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Financials
# ─────────────────────────────────────────────────────────────────────────────


def _make_financials_db(*, company=None, rows=None):
    """Return a DB mock that dispatches Company vs financial-model queries."""
    db = MagicMock()
    company_chain = _make_chain_mock(first=company, all_rows=[company] if company else [])
    data_chain = _make_chain_mock(all_rows=rows or [])

    from pfs.db.models import Company as CompanyModel

    def _query(model):
        if model is CompanyModel:
            return company_chain
        return data_chain

    db.query.side_effect = _query
    return db


@pytest.fixture
def nvda_company(company_row):
    return company_row


def test_income_statements(client_with_db, nvda_company):
    income_row = _make_row(IncomeStatement, _INCOME)
    db = _make_financials_db(company=nvda_company, rows=[income_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get("/api/financials/NVDA/income-statements")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ticker"] == "NVDA"
    assert data[0]["fiscal_year"] == 2024
    assert data[0]["revenue"] == 60_922_000_000


def test_income_statements_quarterly(client_with_db, nvda_company):
    income_q = _make_row(IncomeStatement, {**_INCOME, "fiscal_quarter": 4})
    db = _make_financials_db(company=nvda_company, rows=[income_q])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get(
        "/api/financials/NVDA/income-statements?quarterly=true"
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()[0]["fiscal_quarter"] == 4


def test_balance_sheets(client_with_db, nvda_company):
    balance_row = _make_row(BalanceSheet, _BALANCE)
    db = _make_financials_db(company=nvda_company, rows=[balance_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get("/api/financials/NVDA/balance-sheets")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["total_assets"] == 65_728_000_000


def test_cash_flows(client_with_db, nvda_company):
    cf_row = _make_row(CashFlowStatement, _CASHFLOW)
    db = _make_financials_db(company=nvda_company, rows=[cf_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get("/api/financials/NVDA/cash-flows")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()[0]["free_cash_flow"] == 27_591_000_000


def test_financial_metrics(client_with_db, nvda_company):
    metric_row = _make_row(FinancialMetric, _METRIC)
    db = _make_financials_db(company=nvda_company, rows=[metric_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get("/api/financials/NVDA/metrics")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert float(data[0]["gross_margin"]) == pytest.approx(0.7272)


def test_daily_prices(client_with_db, nvda_company):
    price_row = _make_row(DailyPrice, _PRICE)
    db = _make_financials_db(company=nvda_company, rows=[price_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get("/api/financials/NVDA/prices")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()[0]["close_price"] == pytest.approx(625.0)


@pytest.mark.parametrize("period", ["1m", "3m", "6m", "1y", "2y", "5y"])
def test_daily_prices_period(client_with_db, nvda_company, period):
    price_row = _make_row(DailyPrice, _PRICE)
    db = _make_financials_db(company=nvda_company, rows=[price_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get(
        f"/api/financials/NVDA/prices?period={period}"
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200


def test_daily_prices_date_range(client_with_db, nvda_company):
    price_row = _make_row(DailyPrice, _PRICE)
    db = _make_financials_db(company=nvda_company, rows=[price_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get(
        "/api/financials/NVDA/prices?start=2024-01-01&end=2024-12-31"
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200


def test_revenue_segments(client_with_db, nvda_company):
    seg_row = _make_row(RevenueSegment, _SEGMENT)
    db = _make_financials_db(company=nvda_company, rows=[seg_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get("/api/financials/NVDA/segments")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["segment_name"] == "Data Center"


def test_revenue_segments_fiscal_year_filter(client_with_db, nvda_company):
    seg_row = _make_row(RevenueSegment, _SEGMENT)
    db = _make_financials_db(company=nvda_company, rows=[seg_row])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get(
        "/api/financials/NVDA/segments?fiscal_year=2024"
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200


def test_financials_unknown_company(client_with_db):
    db = _make_financials_db(company=None, rows=[])

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    resp = TestClient(app, raise_server_exceptions=False).get(
        "/api/financials/UNKNOWN/income-statements"
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 404
    assert "UNKNOWN" in resp.json()["detail"]
