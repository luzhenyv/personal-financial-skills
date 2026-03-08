"""ETL Pipeline — orchestrates SEC data fetch, parse, and database storage.

Usage:
    from src.etl.pipeline import ingest_company
    result = ingest_company("NVDA")
"""

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    FinancialMetric,
    IncomeStatement,
    SecFiling,
)
from src.db.session import get_session
from src.etl import sec_client, xbrl_parser
from src.etl.price_client import get_daily_prices
from src.etl.yfinance_client import get_stock_info

logger = logging.getLogger(__name__)


def ingest_company(
    ticker: str,
    years: int = 5,
    include_quarterly: bool = False,
    include_prices: bool = True,
    session: Session | None = None,
) -> dict:
    """Full ETL pipeline for a single company.

    1. Resolve ticker → CIK
    2. Fetch company metadata & create/update company record
    3. Fetch XBRL company facts
    4. Parse 3 statements for each fiscal year
    5. Compute derived metrics
    6. Fetch filing history
    7. Optionally fetch price data

    Args:
        ticker: Stock ticker symbol (e.g. 'NVDA')
        years: Number of historical years to load
        include_quarterly: Also load quarterly (10-Q) data
        include_prices: Fetch daily price data from Alpha Vantage
        session: Optional existing DB session

    Returns:
        Summary dict with counts of rows inserted/updated
    """
    ticker = ticker.upper()
    own_session = session is None
    if own_session:
        session = get_session()

    result = {
        "ticker": ticker,
        "company": False,
        "income_statements": 0,
        "balance_sheets": 0,
        "cash_flow_statements": 0,
        "financial_metrics": 0,
        "sec_filings": 0,
        "daily_prices": 0,
        "errors": [],
    }

    try:
        # ── Step 1: Resolve ticker → CIK ──
        cik = sec_client.ticker_to_cik(ticker)
        if not cik:
            result["errors"].append(f"Could not resolve ticker {ticker} to CIK")
            return result

        logger.info(f"[{ticker}] CIK: {cik}")

        # ── Step 2: Company metadata ──
        try:
            meta = sec_client.get_company_metadata(cik)
            company = _upsert_company(session, ticker, cik, meta)
            result["company"] = True
            logger.info(f"[{ticker}] Company: {company.name}")
        except Exception as e:
            result["errors"].append(f"Company metadata: {e}")
            logger.error(f"[{ticker}] Company metadata error: {e}")

        # ── Step 2b: Enrich with Yahoo Finance (sector, industry, market cap, price) ──
        try:
            yf_info = get_stock_info(ticker)
            if yf_info and "error" not in yf_info:
                company = session.query(Company).filter_by(ticker=ticker).first()
                if company:
                    if yf_info.get("sector"):
                        company.sector = yf_info["sector"]
                    if yf_info.get("industry"):
                        company.industry = yf_info["industry"]
                    if yf_info.get("market_cap"):
                        company.market_cap = yf_info["market_cap"]
                    if yf_info.get("description"):
                        company.description = yf_info["description"]
                    if yf_info.get("website"):
                        company.website = yf_info["website"]
                    session.flush()
                    logger.info(f"[{ticker}] yfinance: sector={company.sector}, mkt_cap=${company.market_cap}")
        except Exception as e:
            logger.warning(f"[{ticker}] yfinance enrichment skipped: {e}")

        # ── Step 3: Fetch XBRL facts ──
        try:
            facts = sec_client.get_company_facts_cached(ticker, cik)
        except Exception as e:
            result["errors"].append(f"XBRL fetch: {e}")
            logger.error(f"[{ticker}] XBRL fetch error: {e}")
            return result

        # ── Step 4: Determine fiscal years with data ──
        current_year = datetime.now().year
        min_year = current_year - years
        available_years = xbrl_parser.get_available_fiscal_years(facts, min_year)
        logger.info(f"[{ticker}] Available fiscal years: {available_years}")

        if not available_years:
            result["errors"].append("No fiscal year data found in XBRL")
            return result

        # ── Step 5: Parse & store statements for each year ──
        parsed_incomes = {}
        for fy in available_years:
            try:
                inc = xbrl_parser.parse_income_statement(facts, fy)
                inc["ticker"] = ticker
                inc["filing_type"] = "10-K"
                _upsert_income_statement(session, inc)
                parsed_incomes[fy] = inc
                result["income_statements"] += 1
            except Exception as e:
                result["errors"].append(f"Income Statement FY{fy}: {e}")
                logger.error(f"[{ticker}] IS FY{fy} error: {e}")

            try:
                bs = xbrl_parser.parse_balance_sheet(facts, fy)
                bs["ticker"] = ticker
                bs["filing_type"] = "10-K"
                _upsert_balance_sheet(session, bs)
                result["balance_sheets"] += 1
            except Exception as e:
                result["errors"].append(f"Balance Sheet FY{fy}: {e}")
                logger.error(f"[{ticker}] BS FY{fy} error: {e}")

            try:
                cf = xbrl_parser.parse_cash_flow(facts, fy)
                cf["ticker"] = ticker
                cf["filing_type"] = "10-K"
                _upsert_cash_flow(session, cf)
                result["cash_flow_statements"] += 1
            except Exception as e:
                result["errors"].append(f"Cash Flow FY{fy}: {e}")
                logger.error(f"[{ticker}] CF FY{fy} error: {e}")

        # ── Step 6: Compute metrics ──
        sorted_years = sorted(available_years)
        for i, fy in enumerate(sorted_years):
            try:
                inc = parsed_incomes.get(fy, {})
                bs_data = xbrl_parser.parse_balance_sheet(facts, fy)
                cf_data = xbrl_parser.parse_cash_flow(facts, fy)

                prev_inc = parsed_incomes.get(sorted_years[i - 1]) if i > 0 else None
                prev_bs = (
                    xbrl_parser.parse_balance_sheet(facts, sorted_years[i - 1])
                    if i > 0 else None
                )

                metrics = xbrl_parser.compute_metrics(inc, bs_data, cf_data, prev_inc, prev_bs)
                metrics["ticker"] = ticker
                metrics["fiscal_year"] = fy
                metrics["fiscal_quarter"] = None
                _upsert_metrics(session, metrics)
                result["financial_metrics"] += 1
            except Exception as e:
                result["errors"].append(f"Metrics FY{fy}: {e}")
                logger.error(f"[{ticker}] Metrics FY{fy} error: {e}")

        # ── Step 7: Filing history ──
        try:
            filings = sec_client.get_recent_filings(cik, ["10-K", "10-Q", "8-K"], limit=30)
            for f in filings:
                _upsert_filing(session, ticker, cik, f)
                result["sec_filings"] += 1
        except Exception as e:
            result["errors"].append(f"Filings: {e}")
            logger.error(f"[{ticker}] Filing fetch error: {e}")

        # ── Step 8: Price data ──
        if include_prices:
            try:
                prices = get_daily_prices(ticker, output_size="compact")
                for p in prices:
                    _upsert_price(session, p)
                result["daily_prices"] = len(prices)
            except Exception as e:
                result["errors"].append(f"Prices: {e}")
                logger.error(f"[{ticker}] Price fetch error: {e}")

        session.commit()
        logger.info(f"[{ticker}] Ingestion complete: {result}")

    except Exception as e:
        session.rollback()
        result["errors"].append(f"Pipeline error: {e}")
        logger.error(f"[{ticker}] Pipeline error: {e}")
    finally:
        if own_session:
            session.close()

    return result


# ──────────────────────────────────────────────
# Upsert Helpers
# ──────────────────────────────────────────────

def _upsert_company(session: Session, ticker: str, cik: str, meta: dict) -> Company:
    """Create or update company record."""
    company = session.query(Company).filter_by(ticker=ticker).first()
    if company:
        company.name = meta.get("name", company.name)
        company.sic_code = meta.get("sic", company.sic_code)
        company.fiscal_year_end = meta.get("fiscal_year_end", company.fiscal_year_end)
        company.website = meta.get("website", company.website)
        company.description = meta.get("description", company.description)
        company.updated_at = datetime.utcnow()
    else:
        company = Company(
            cik=cik,
            ticker=ticker,
            name=meta.get("name", ticker),
            sic_code=meta.get("sic", ""),
            fiscal_year_end=meta.get("fiscal_year_end", ""),
            website=meta.get("website", ""),
            description=meta.get("description", ""),
            exchange=meta.get("exchanges", [""])[0] if meta.get("exchanges") else "",
        )
        session.add(company)

    session.flush()
    return company


def _upsert_income_statement(session: Session, data: dict) -> None:
    """Upsert an income statement row."""
    existing = (
        session.query(IncomeStatement)
        .filter_by(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
        )
        .first()
    )

    fields = [
        "revenue", "cost_of_revenue", "gross_profit",
        "research_and_development", "selling_general_admin",
        "operating_expenses", "operating_income",
        "interest_expense", "interest_income", "other_income",
        "pretax_income", "income_tax", "net_income",
        "eps_basic", "eps_diluted", "shares_basic", "shares_diluted",
        "filing_type", "raw_json",
    ]

    if existing:
        for f in fields:
            if f in data and data[f] is not None:
                setattr(existing, f, data[f])
    else:
        row = IncomeStatement(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
            **{f: data.get(f) for f in fields},
        )
        session.add(row)
    session.flush()


def _upsert_balance_sheet(session: Session, data: dict) -> None:
    """Upsert a balance sheet row."""
    existing = (
        session.query(BalanceSheet)
        .filter_by(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
        )
        .first()
    )

    fields = [
        "cash_and_equivalents", "short_term_investments",
        "accounts_receivable", "inventory", "total_current_assets",
        "property_plant_equipment", "goodwill", "intangible_assets", "total_assets",
        "accounts_payable", "short_term_debt", "total_current_liabilities",
        "long_term_debt", "total_liabilities",
        "common_stock", "retained_earnings", "total_stockholders_equity",
        "filing_type", "raw_json",
    ]

    if existing:
        for f in fields:
            if f in data and data[f] is not None:
                setattr(existing, f, data[f])
    else:
        row = BalanceSheet(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
            **{f: data.get(f) for f in fields},
        )
        session.add(row)
    session.flush()


def _upsert_cash_flow(session: Session, data: dict) -> None:
    """Upsert a cash flow statement row."""
    existing = (
        session.query(CashFlowStatement)
        .filter_by(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
        )
        .first()
    )

    fields = [
        "net_income", "depreciation_amortization", "stock_based_compensation",
        "change_in_working_capital", "cash_from_operations",
        "capital_expenditure", "acquisitions",
        "purchases_of_investments", "sales_of_investments", "cash_from_investing",
        "debt_issuance", "debt_repayment", "share_repurchase",
        "dividends_paid", "cash_from_financing",
        "net_change_in_cash", "free_cash_flow",
        "filing_type", "raw_json",
    ]

    if existing:
        for f in fields:
            if f in data and data[f] is not None:
                setattr(existing, f, data[f])
    else:
        row = CashFlowStatement(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
            **{f: data.get(f) for f in fields},
        )
        session.add(row)
    session.flush()


def _upsert_metrics(session: Session, data: dict) -> None:
    """Upsert a financial metrics row."""
    existing = (
        session.query(FinancialMetric)
        .filter_by(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
        )
        .first()
    )

    fields = [
        "gross_margin", "operating_margin", "net_margin", "fcf_margin",
        "revenue_growth", "operating_income_growth", "net_income_growth", "eps_growth",
        "roe", "roa", "roic",
        "debt_to_equity", "current_ratio", "quick_ratio",
        "pe_ratio", "ps_ratio", "pb_ratio", "ev_to_ebitda", "fcf_yield",
    ]

    if existing:
        for f in fields:
            if f in data and data[f] is not None:
                setattr(existing, f, data[f])
        existing.calculated_at = datetime.utcnow()
    else:
        row = FinancialMetric(
            ticker=data["ticker"],
            fiscal_year=data["fiscal_year"],
            fiscal_quarter=data.get("fiscal_quarter"),
            **{f: data.get(f) for f in fields},
        )
        session.add(row)
    session.flush()


def _upsert_filing(session: Session, ticker: str, cik: str, filing: dict) -> None:
    """Upsert a SEC filing record."""
    accession = filing.get("accession_number", "")
    if not accession:
        return

    existing = session.query(SecFiling).filter_by(accession_number=accession).first()
    if existing:
        return  # Filing already tracked

    row = SecFiling(
        ticker=ticker,
        cik=cik,
        accession_number=accession,
        filing_type=filing.get("form", ""),
        filing_date=filing.get("filing_date") or None,
        reporting_date=filing.get("report_date") or None,
    )
    session.add(row)
    session.flush()


def _upsert_price(session: Session, data: dict) -> None:
    """Upsert a daily price record."""
    existing = (
        session.query(DailyPrice)
        .filter_by(ticker=data["ticker"], date=data["date"])
        .first()
    )

    if existing:
        existing.open_price = data["open_price"]
        existing.high_price = data["high_price"]
        existing.low_price = data["low_price"]
        existing.close_price = data["close_price"]
        existing.adjusted_close = data["adjusted_close"]
        existing.volume = data["volume"]
    else:
        row = DailyPrice(**data)
        session.add(row)
    session.flush()
