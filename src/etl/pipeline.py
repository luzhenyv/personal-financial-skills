"""ETL Pipeline — Mini Bloomberg data ingestion.

Usage:
    python -m src.etl.pipeline ingest NVDA --years 5
    python -m src.etl.pipeline ingest NVDA --years 5 --quarterly
    python -m src.etl.pipeline ingest-batch NVDA,AAPL,MSFT --years 5
    python -m src.etl.pipeline ingest-sp500
    python -m src.etl.pipeline sync-prices
    python -m src.etl.pipeline sync-prices --tickers NVDA,AAPL
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    DailyPrice,
    EtlRun,
    FinancialMetric,
    IncomeStatement,
    RevenueSegment,
    SecFiling,
    StockSplit,
)
from src.db.session import get_session
from src.etl import sec_client, xbrl_parser
from src.etl.price_client import get_daily_prices
from src.etl.validation import validate_financials, validate_price_data
from src.etl.yfinance_client import get_market_data, get_stock_info, get_stock_splits

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Main Ingestion
# ──────────────────────────────────────────────


def ingest_company(
    ticker: str,
    years: int = 5,
    quarterly: bool = False,
    db: Session | None = None,
) -> dict[str, Any]:
    """Full company data ingestion pipeline.

    Steps:
        1.  Create EtlRun audit record
        2.  Resolve ticker → CIK
        3.  Upsert company metadata
        4.  Fetch XBRL facts
        5.  Parse & store 3 statements (income, balance, cash flow)
        6.  Parse & store revenue segments
        7.  Compute & store price-independent metrics
        8.  Fetch & store daily prices
        9.  Compute & store valuation metrics (needs price data)
        10. Fetch & store SEC filing history
        11. Download 10-K/10-Q filing HTML
        12. Save stock split history
        13. Run cross-source validation
        14. Finalize audit record

    Returns:
        Summary dict with counts and status.
    """
    own_session = db is None
    if own_session:
        db = get_session()

    settings.ensure_dirs()

    ticker = ticker.upper().strip()
    summary: dict[str, Any] = {"ticker": ticker, "errors": []}
    counts = {
        "income_statements": 0,
        "balance_sheets": 0,
        "cash_flow_statements": 0,
        "financial_metrics": 0,
        "revenue_segments": 0,
        "daily_prices": 0,
        "sec_filings": 0,
        "filings_downloaded": 0,
        "stock_splits": 0,
    }

    # Step 1: Audit record
    etl_run = EtlRun(ticker=ticker, run_type="full_ingest", status="running")
    db.add(etl_run)
    db.commit()
    db.refresh(etl_run)
    logger.info(f"[{ticker}] ── ETL run #{etl_run.id} started ──")

    try:
        # Step 2: Resolve ticker → CIK
        logger.info(f"[{ticker}] Step 2: Resolving CIK")
        cik = sec_client.ticker_to_cik(ticker)
        if not cik:
            raise ValueError(f"Could not resolve CIK for {ticker}")
        logger.info(f"[{ticker}] CIK = {cik}")

        # Step 3: Upsert company metadata
        logger.info(f"[{ticker}] Step 3: Upserting company metadata")
        try:
            _upsert_company(db, ticker, cik)
        except Exception as e:
            summary["errors"].append(f"company_metadata: {e}")
            logger.error(f"[{ticker}] Company metadata failed: {e}")
            # Company row is required for FK constraints — cannot continue
            raise

        # Step 4: Fetch XBRL facts
        logger.info(f"[{ticker}] Step 4: Fetching XBRL facts")
        facts = sec_client.get_company_facts_cached(ticker, cik)
        if not facts:
            raise ValueError(f"No XBRL facts returned for {ticker}")

        available_years = xbrl_parser.get_available_fiscal_years(
            facts, min_year=datetime.now().year - years
        )
        logger.info(f"[{ticker}] Available fiscal years: {available_years}")

        if not available_years:
            raise ValueError(f"No fiscal year data found for {ticker}")

        # Step 5: Parse & store 3 statements
        logger.info(f"[{ticker}] Step 5: Parsing financial statements")
        parsed_data: dict[int, dict[str, dict]] = {}

        for fy in available_years:
            periods = [(fy, None)]  # Annual
            if quarterly:
                periods.extend([(fy, q) for q in range(1, 5)])

            for year, qtr in periods:
                try:
                    inc = xbrl_parser.parse_income_statement(facts, year, qtr)
                    bal = xbrl_parser.parse_balance_sheet(facts, year, qtr)
                    cf = xbrl_parser.parse_cash_flow(facts, year, qtr)

                    # Skip if no meaningful data
                    if inc.get("revenue") is None and inc.get("net_income") is None:
                        continue

                    n_inc = _upsert_income_statement(db, ticker, inc)
                    n_bal = _upsert_balance_sheet(db, ticker, bal)
                    n_cf = _upsert_cash_flow(db, ticker, cf)

                    counts["income_statements"] += n_inc
                    counts["balance_sheets"] += n_bal
                    counts["cash_flow_statements"] += n_cf

                    # Cache for metrics computation
                    key = (year, qtr)
                    parsed_data[key] = {"income": inc, "balance": bal, "cash_flow": cf}

                except Exception as e:
                    summary["errors"].append(f"statements_{year}_Q{qtr}: {e}")
                    logger.error(f"[{ticker}] Statements FY{year} Q{qtr}: {e}")

        db.commit()
        logger.info(
            f"[{ticker}] Stored: {counts['income_statements']} IS, "
            f"{counts['balance_sheets']} BS, {counts['cash_flow_statements']} CF"
        )

        # Step 6: Revenue segments
        logger.info(f"[{ticker}] Step 6: Parsing revenue segments")
        for fy in available_years:
            try:
                segments = xbrl_parser.parse_revenue_segments(facts, fy)
                for seg in segments:
                    n = _upsert_revenue_segment(db, ticker, fy, seg)
                    counts["revenue_segments"] += n
            except Exception as e:
                summary["errors"].append(f"segments_{fy}: {e}")
                logger.error(f"[{ticker}] Revenue segments FY{fy}: {e}")

        db.commit()
        logger.info(f"[{ticker}] Revenue segments stored: {counts['revenue_segments']}")

        # Step 7: Price-independent metrics
        logger.info(f"[{ticker}] Step 7: Computing price-independent metrics")
        sorted_keys = sorted(parsed_data.keys())
        for i, key in enumerate(sorted_keys):
            try:
                year, qtr = key
                data = parsed_data[key]
                prev_key = sorted_keys[i - 1] if i > 0 else None
                prev_income = parsed_data[prev_key]["income"] if prev_key else None
                prev_balance = parsed_data[prev_key]["balance"] if prev_key else None

                metrics = xbrl_parser.compute_metrics(
                    income=data["income"],
                    balance=data["balance"],
                    cash_flow=data["cash_flow"],
                    prev_income=prev_income,
                    prev_balance=prev_balance,
                    market_data=None,  # Step 9 will update with valuation
                )
                metrics["fiscal_year"] = year
                metrics["fiscal_quarter"] = qtr
                n = _upsert_financial_metric(db, ticker, metrics)
                counts["financial_metrics"] += n
            except Exception as e:
                summary["errors"].append(f"metrics_{key}: {e}")
                logger.error(f"[{ticker}] Metrics {key}: {e}")

        db.commit()
        logger.info(f"[{ticker}] Metrics stored: {counts['financial_metrics']}")

        # Step 8: Daily prices (yfinance primary)
        logger.info(f"[{ticker}] Step 8: Fetching daily prices")
        try:
            period_map = {1: "1y", 2: "2y", 3: "5y", 5: "5y", 10: "10y"}
            yf_period = period_map.get(years, "5y")
            prices = get_daily_prices(ticker, period=yf_period)

            price_issues = validate_price_data(prices, ticker)
            if price_issues:
                summary["errors"].append(
                    f"price_quality: {len(price_issues)} issues"
                )

            n_prices = _upsert_daily_prices(db, ticker, prices)
            counts["daily_prices"] = n_prices
            db.commit()
            logger.info(f"[{ticker}] Prices stored: {n_prices}")
        except Exception as e:
            summary["errors"].append(f"daily_prices: {e}")
            logger.error(f"[{ticker}] Daily prices failed: {e}")

        # Step 9: Valuation metrics (needs price data)
        logger.info(f"[{ticker}] Step 9: Computing valuation metrics")
        try:
            mkt = get_market_data(ticker)
            if mkt and mkt.get("price"):
                # Recompute the latest annual metrics with market data
                latest_annual = None
                for key in reversed(sorted_keys):
                    if key[1] is None:  # annual
                        latest_annual = key
                        break

                if latest_annual and latest_annual in parsed_data:
                    data = parsed_data[latest_annual]
                    year, qtr = latest_annual
                    prev_key_idx = sorted_keys.index(latest_annual) - 1
                    prev_income = (
                        parsed_data[sorted_keys[prev_key_idx]]["income"]
                        if prev_key_idx >= 0 else None
                    )

                    val_metrics = xbrl_parser.compute_metrics(
                        income=data["income"],
                        balance=data["balance"],
                        cash_flow=data["cash_flow"],
                        prev_income=prev_income,
                        market_data=mkt,
                    )
                    val_metrics["fiscal_year"] = year
                    val_metrics["fiscal_quarter"] = qtr
                    _upsert_financial_metric(db, ticker, val_metrics)
                    db.commit()
                    logger.info(f"[{ticker}] Valuation metrics updated for FY{year}")
        except Exception as e:
            summary["errors"].append(f"valuation_metrics: {e}")
            logger.error(f"[{ticker}] Valuation metrics failed: {e}")

        # Step 10: SEC filing history
        logger.info(f"[{ticker}] Step 10: Fetching SEC filing history")
        try:
            filings = sec_client.get_recent_filings(
                cik, filing_types=["10-K", "10-Q", "8-K"]
            )
            for f in filings:
                n = _upsert_sec_filing(db, ticker, cik, f)
                counts["sec_filings"] += n
            db.commit()
            logger.info(f"[{ticker}] SEC filings stored: {counts['sec_filings']}")
        except Exception as e:
            summary["errors"].append(f"sec_filings: {e}")
            logger.error(f"[{ticker}] SEC filings failed: {e}")

        # Step 11: Download 10-K/10-Q HTML
        logger.info(f"[{ticker}] Step 11: Downloading filing HTML")
        try:
            filings_to_dl = sec_client.get_recent_filings(
                cik, filing_types=["10-K", "10-Q"], limit=years * 5
            )
            dest_dir = settings.raw_dir / ticker
            dest_dir.mkdir(parents=True, exist_ok=True)

            for f in filings_to_dl:
                accession = f.get("accession_number", "")
                doc_url = f.get("primary_document", "")
                if not doc_url:
                    continue
                result = sec_client.download_filing_html(cik, f, dest_dir)
                if result:
                    counts["filings_downloaded"] += 1

            logger.info(f"[{ticker}] Filings downloaded: {counts['filings_downloaded']}")
        except Exception as e:
            summary["errors"].append(f"filing_download: {e}")
            logger.error(f"[{ticker}] Filing download failed: {e}")

        # Step 12: Stock split history
        logger.info(f"[{ticker}] Step 12: Saving stock split history")
        try:
            splits = get_stock_splits(ticker)
            n_splits = 0
            for s in splits:
                existing = db.query(StockSplit).filter_by(
                    ticker=ticker, split_date=s["date"]
                ).first()
                if existing is None:
                    db.add(StockSplit(
                        ticker=ticker,
                        split_date=s["date"],
                        ratio=s["ratio"],
                        source="yfinance",
                    ))
                    n_splits += 1
                else:
                    existing.ratio = s["ratio"]
            db.commit()
            counts["stock_splits"] = n_splits
            logger.info(f"[{ticker}] Stock splits saved: {len(splits)} total, {n_splits} new")
        except Exception as e:
            summary["errors"].append(f"stock_splits: {e}")
            logger.error(f"[{ticker}] Stock splits failed: {e}")

        # Step 13: Cross-source validation
        logger.info(f"[{ticker}] Step 13: Cross-source validation")
        try:
            from src.etl.yfinance_client import get_key_financials

            yf_financials = get_key_financials(ticker)

            # Build SEC data from latest annual
            sec_summary: dict[str, Any] = {}
            for key in reversed(sorted_keys):
                if key[1] is None:  # annual
                    data = parsed_data[key]
                    sec_summary = {
                        "revenue": data["income"].get("revenue"),
                        "net_income": data["income"].get("net_income"),
                        "total_assets": data["balance"].get("total_assets"),
                        "total_liabilities": data["balance"].get("total_liabilities"),
                        "operating_income": data["income"].get("operating_income"),
                        "gross_profit": data["income"].get("gross_profit"),
                        "ebitda": (data["income"].get("operating_income") or 0)
                        + abs(data["cash_flow"].get("depreciation_amortization") or 0)
                        if data["income"].get("operating_income") is not None
                        else None,
                    }
                    break

            discrepancies = validate_financials(sec_summary, yf_financials, ticker)
            if discrepancies:
                summary["validation_discrepancies"] = discrepancies
        except Exception as e:
            summary["errors"].append(f"validation: {e}")
            logger.error(f"[{ticker}] Validation failed: {e}")

        # Step 14: Finalize audit
        status = "success" if not summary["errors"] else "partial"

    except Exception as e:
        status = "failed"
        summary["errors"].append(f"fatal: {e}")
        logger.exception(f"[{ticker}] Fatal error: {e}")

    finally:
        etl_run.status = status
        etl_run.completed_at = datetime.utcnow()
        etl_run.income_statements = counts["income_statements"]
        etl_run.balance_sheets = counts["balance_sheets"]
        etl_run.cash_flow_statements = counts["cash_flow_statements"]
        etl_run.financial_metrics = counts["financial_metrics"]
        etl_run.revenue_segments = counts["revenue_segments"]
        etl_run.daily_prices = counts["daily_prices"]
        etl_run.sec_filings = counts["sec_filings"]
        etl_run.filings_downloaded = counts["filings_downloaded"]
        etl_run.stock_splits = counts["stock_splits"]
        etl_run.errors = summary["errors"] if summary["errors"] else []
        etl_run.run_metadata = {
            "years": years,
            "quarterly": quarterly,
            "available_years": available_years if "available_years" in dir() else [],
        }
        db.commit()

        logger.info(
            f"[{ticker}] ── ETL run #{etl_run.id} completed: {status} "
            f"(IS={counts['income_statements']}, BS={counts['balance_sheets']}, "
            f"CF={counts['cash_flow_statements']}, Prices={counts['daily_prices']}) ──"
        )

        if own_session:
            db.close()

    summary["counts"] = counts
    summary["status"] = status
    summary["etl_run_id"] = etl_run.id
    return summary


# ──────────────────────────────────────────────
# Batch / Price Sync
# ──────────────────────────────────────────────


def ingest_batch(
    tickers: list[str],
    years: int = 5,
    quarterly: bool = False,
) -> list[dict[str, Any]]:
    """Ingest multiple tickers sequentially with error isolation."""
    results = []
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[Batch] {i}/{len(tickers)}: {ticker}")
        try:
            result = ingest_company(ticker, years=years, quarterly=quarterly)
            results.append(result)
        except Exception as e:
            logger.error(f"[Batch] {ticker} failed: {e}")
            results.append({"ticker": ticker, "status": "failed", "errors": [str(e)]})
    return results


def sync_prices(
    tickers: list[str] | None = None,
    period: str = "3mo",
) -> dict[str, int]:
    """Update daily prices only (no XBRL re-parse).

    If tickers is None, syncs all tickers in the companies table.
    """
    db = get_session()
    try:
        if tickers is None:
            rows = db.execute(text("SELECT ticker FROM companies")).fetchall()
            tickers = [r[0] for r in rows]

        result: dict[str, int] = {}
        for ticker in tickers:
            ticker = ticker.upper().strip()
            logger.info(f"[Sync] Prices for {ticker}")

            etl_run = EtlRun(ticker=ticker, run_type="price_sync", status="running")
            db.add(etl_run)
            db.commit()

            try:
                prices = get_daily_prices(ticker, period=period)
                n = _upsert_daily_prices(db, ticker, prices)
                db.commit()

                etl_run.status = "success"
                etl_run.daily_prices = n
                etl_run.completed_at = datetime.utcnow()
                db.commit()

                result[ticker] = n
                logger.info(f"[Sync] {ticker}: {n} price records upserted")

            except Exception as e:
                etl_run.status = "failed"
                etl_run.errors = [str(e)]
                etl_run.completed_at = datetime.utcnow()
                db.commit()
                result[ticker] = 0
                logger.error(f"[Sync] {ticker} failed: {e}")

        return result
    finally:
        db.close()


# ──────────────────────────────────────────────
# Upsert Helpers
# ──────────────────────────────────────────────


def _upsert_company(db: Session, ticker: str, cik: str) -> None:
    """Insert or update company metadata from SEC + yfinance."""
    # Get SEC metadata
    sec_meta = sec_client.get_company_metadata(cik)

    # Get yfinance enrichment
    yf_info = get_stock_info(ticker)

    existing = db.query(Company).filter_by(ticker=ticker).first()
    if existing:
        company = existing
    else:
        company = Company(ticker=ticker, cik=sec_client.pad_cik(cik))
        db.add(company)

    # SEC data (trusted)
    company.name = sec_meta.get("name") or yf_info.get("name") or ticker
    company.cik = sec_client.pad_cik(cik)
    company.sic_code = sec_meta.get("sic")
    company.fiscal_year_end = sec_meta.get("fiscal_year_end")
    company.exchange = sec_meta.get("exchange") or yf_info.get("exchange")

    # yfinance enrichment
    company.sector = yf_info.get("sector") or sec_meta.get("sector")
    company.industry = yf_info.get("industry")
    company.market_cap = yf_info.get("market_cap")
    company.employee_count = yf_info.get("employee_count")
    company.headquarters = yf_info.get("headquarters")
    company.description = yf_info.get("description")
    company.website = yf_info.get("website")

    db.commit()
    logger.info(f"[{ticker}] Company: {company.name}")


def _upsert_income_statement(
    db: Session, ticker: str, data: dict[str, Any]
) -> int:
    """Upsert one income statement row. Returns 1 if upserted, 0 otherwise."""
    fy = data.get("fiscal_year")
    fq = data.get("fiscal_quarter")

    existing = (
        db.query(IncomeStatement)
        .filter_by(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        .first()
    )
    if existing:
        row = existing
    else:
        row = IncomeStatement(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        db.add(row)

    for col in (
        "filing_type", "filing_date", "revenue", "cost_of_revenue", "gross_profit",
        "research_and_development", "selling_general_admin", "depreciation_amortization",
        "operating_expenses", "operating_income", "interest_expense", "interest_income",
        "other_income", "pretax_income", "income_tax", "net_income",
        "eps_basic", "eps_diluted", "shares_basic", "shares_diluted",
        "source", "raw_json",
    ):
        if col in data and data[col] is not None:
            setattr(row, col, data[col])

    if row.source is None:
        row.source = "sec_xbrl"
    return 1


def _upsert_balance_sheet(
    db: Session, ticker: str, data: dict[str, Any]
) -> int:
    """Upsert one balance sheet row."""
    fy = data.get("fiscal_year")
    fq = data.get("fiscal_quarter")

    existing = (
        db.query(BalanceSheet)
        .filter_by(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        .first()
    )
    if existing:
        row = existing
    else:
        row = BalanceSheet(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        db.add(row)

    for col in (
        "filing_type", "filing_date", "cash_and_equivalents", "short_term_investments",
        "accounts_receivable", "inventory", "total_current_assets",
        "property_plant_equipment", "goodwill", "intangible_assets", "total_assets",
        "accounts_payable", "deferred_revenue", "short_term_debt",
        "total_current_liabilities", "long_term_debt", "total_liabilities",
        "common_stock", "retained_earnings", "total_stockholders_equity",
        "source", "raw_json",
    ):
        if col in data and data[col] is not None:
            setattr(row, col, data[col])

    if row.source is None:
        row.source = "sec_xbrl"
    return 1


def _upsert_cash_flow(
    db: Session, ticker: str, data: dict[str, Any]
) -> int:
    """Upsert one cash flow statement row."""
    fy = data.get("fiscal_year")
    fq = data.get("fiscal_quarter")

    existing = (
        db.query(CashFlowStatement)
        .filter_by(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        .first()
    )
    if existing:
        row = existing
    else:
        row = CashFlowStatement(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        db.add(row)

    for col in (
        "filing_type", "filing_date", "net_income", "depreciation_amortization",
        "stock_based_compensation", "change_in_working_capital",
        "cash_from_operations", "capital_expenditure", "acquisitions",
        "purchases_of_investments", "sales_of_investments", "cash_from_investing",
        "debt_issuance", "debt_repayment", "share_repurchase", "dividends_paid",
        "cash_from_financing", "net_change_in_cash", "free_cash_flow",
        "source", "raw_json",
    ):
        if col in data and data[col] is not None:
            setattr(row, col, data[col])

    if row.source is None:
        row.source = "sec_xbrl"
    return 1


def _upsert_revenue_segment(
    db: Session, ticker: str, fiscal_year: int, seg: dict[str, Any]
) -> int:
    """Upsert one revenue segment row."""
    seg_type = seg.get("segment_type", "unknown")
    seg_name = seg.get("segment_name", "unknown")

    existing = (
        db.query(RevenueSegment)
        .filter_by(
            ticker=ticker,
            fiscal_year=fiscal_year,
            fiscal_quarter=None,
            segment_type=seg_type,
            segment_name=seg_name,
        )
        .first()
    )
    if existing:
        row = existing
    else:
        row = RevenueSegment(
            ticker=ticker,
            fiscal_year=fiscal_year,
            fiscal_quarter=None,
            segment_type=seg_type,
            segment_name=seg_name,
        )
        db.add(row)

    row.revenue = seg.get("revenue")
    row.pct_of_total = seg.get("pct_of_total")
    row.source = seg.get("source", "sec_xbrl")
    row.raw_json = seg.get("raw_json")
    return 1


def _upsert_financial_metric(
    db: Session, ticker: str, data: dict[str, Any]
) -> int:
    """Upsert one financial metric row."""
    fy = data.get("fiscal_year")
    fq = data.get("fiscal_quarter")

    existing = (
        db.query(FinancialMetric)
        .filter_by(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        .first()
    )
    if existing:
        row = existing
    else:
        row = FinancialMetric(ticker=ticker, fiscal_year=fy, fiscal_quarter=fq)
        db.add(row)

    for col in (
        "gross_margin", "operating_margin", "ebitda_margin", "net_margin", "fcf_margin",
        "revenue_growth", "operating_income_growth", "net_income_growth", "eps_growth",
        "roe", "roa", "roic", "debt_to_equity", "current_ratio", "quick_ratio",
        "dso", "dio", "dpo", "ebitda",
        "pe_ratio", "ps_ratio", "pb_ratio", "ev_to_ebitda", "fcf_yield",
    ):
        if col in data and data[col] is not None:
            setattr(row, col, data[col])

    row.calculated_at = datetime.utcnow()
    return 1


def _upsert_daily_prices(
    db: Session, ticker: str, prices: list[dict[str, Any]]
) -> int:
    """Bulk upsert daily price records. Returns count of upserted rows."""
    if not prices:
        return 0

    count = 0
    for p in prices:
        date_val = p.get("date")
        if not date_val:
            continue

        existing = (
            db.query(DailyPrice)
            .filter_by(ticker=ticker, date=date_val)
            .first()
        )
        if existing:
            row = existing
        else:
            row = DailyPrice(ticker=ticker, date=date_val)
            db.add(row)
            count += 1

        row.open_price = p.get("open_price")
        row.high_price = p.get("high_price")
        row.low_price = p.get("low_price")
        row.close_price = p.get("close_price")
        row.adjusted_close = p.get("adjusted_close")
        row.volume = p.get("volume")

    # Commit in batches to avoid memory issues
    db.flush()
    return count


def _upsert_sec_filing(
    db: Session, ticker: str, cik: str, filing: dict[str, Any]
) -> int:
    """Upsert one SEC filing row."""
    accession = filing.get("accession_number", "")
    if not accession:
        return 0

    existing = db.query(SecFiling).filter_by(accession_number=accession).first()
    if existing:
        return 0

    row = SecFiling(
        ticker=ticker,
        cik=sec_client.pad_cik(cik),
        accession_number=accession,
        filing_type=filing.get("filing_type"),
        filing_date=filing.get("filing_date"),
        reporting_date=filing.get("reporting_date"),
        primary_doc_url=filing.get("primary_doc_url"),
        xbrl_url=filing.get("xbrl_url"),
    )
    db.add(row)
    return 1


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.etl.pipeline",
        description="Mini Bloomberg ETL Pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest a single company")
    p_ingest.add_argument("ticker", type=str, help="Stock ticker (e.g. NVDA)")
    p_ingest.add_argument("--years", type=int, default=5, help="Years of data (default: 5)")
    p_ingest.add_argument(
        "--quarterly", action="store_true", help="Include quarterly data"
    )

    # ingest-batch
    p_batch = sub.add_parser("ingest-batch", help="Ingest multiple companies")
    p_batch.add_argument(
        "tickers", type=str, help="Comma-separated tickers (e.g. NVDA,AAPL,MSFT)"
    )
    p_batch.add_argument("--years", type=int, default=5)
    p_batch.add_argument("--quarterly", action="store_true")

    # ingest-sp500
    sub.add_parser("ingest-sp500", help="Ingest all S&P 500 companies")

    # sync-prices
    p_sync = sub.add_parser("sync-prices", help="Update daily prices only")
    p_sync.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated tickers (default: all in DB)",
    )
    p_sync.add_argument("--period", type=str, default="3mo", help="yfinance period")

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        result = ingest_company(args.ticker, years=args.years, quarterly=args.quarterly)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "ingest-batch":
        tickers = [t.strip() for t in args.tickers.split(",")]
        results = ingest_batch(tickers, years=args.years, quarterly=args.quarterly)
        print(json.dumps(results, indent=2, default=str))

    elif args.command == "ingest-sp500":
        tickers = sec_client.get_sp500_tickers()
        logger.info(f"Ingesting {len(tickers)} S&P 500 tickers")
        results = ingest_batch(tickers, years=5)
        success = sum(1 for r in results if r.get("status") == "success")
        print(f"Completed: {success}/{len(tickers)} successful")

    elif args.command == "sync-prices":
        tickers = None
        if args.tickers:
            tickers = [t.strip() for t in args.tickers.split(",")]
        result = sync_prices(tickers=tickers, period=args.period)
        for t, n in result.items():
            print(f"  {t}: {n} prices")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
