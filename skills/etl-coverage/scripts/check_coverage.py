"""
ETL Coverage Check Script
=========================
Analyzes NULL/missing values across income_statements, balance_sheets,
and cash_flow_statements for all or specific tickers.

For each NULL field it inspects the SEC XBRL raw company-facts JSON
to determine:
  • "no_data"  – the company genuinely does not report this item
  • "unmapped" – there IS data in the XBRL JSON but our parser lacks a tag mapping
  • "ok"       – field is populated

Outputs a JSON report to data/artifacts/_etl/coverage_report.json
and prints a human-readable summary to stdout.

Usage:
    uv run python skills/etl-coverage/scripts/check_coverage.py
    uv run python skills/etl-coverage/scripts/check_coverage.py --ticker AAPL
    uv run python skills/etl-coverage/scripts/check_coverage.py --ticker AAPL --fix
    uv run python skills/etl-coverage/scripts/check_coverage.py --summary
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Project imports ────────────────────────────────────────────────────────────
from src.config import settings
from src.db.models import (
    BalanceSheet,
    CashFlowStatement,
    Company,
    IncomeStatement,
)
from src.db.session import get_session
from src.etl import sec_client
from src.etl.xbrl_parser import (
    BALANCE_SHEET_TAGS,
    CASH_FLOW_TAGS,
    INCOME_STATEMENT_TAGS,
    _extract_fact_values,
)


# ──────────────────────────────────────────────
# Column lists (must stay in sync with models.py)
# ──────────────────────────────────────────────

INCOME_COLS = [
    "revenue", "cost_of_revenue", "gross_profit",
    "research_and_development", "selling_general_admin",
    "depreciation_amortization", "operating_expenses", "operating_income",
    "interest_expense", "interest_income", "other_income",
    "pretax_income", "income_tax", "net_income",
    "eps_basic", "eps_diluted", "shares_basic", "shares_diluted",
]

BALANCE_COLS = [
    "cash_and_equivalents", "short_term_investments", "accounts_receivable",
    "inventory", "total_current_assets", "property_plant_equipment",
    "goodwill", "intangible_assets", "total_assets",
    "accounts_payable", "deferred_revenue", "short_term_debt",
    "total_current_liabilities", "long_term_debt", "total_liabilities",
    "common_stock", "retained_earnings", "total_stockholders_equity",
]

CASHFLOW_COLS = [
    "net_income", "depreciation_amortization", "stock_based_compensation",
    "change_in_working_capital", "cash_from_operations",
    "capital_expenditure", "acquisitions", "purchases_of_investments",
    "sales_of_investments", "cash_from_investing",
    "debt_issuance", "debt_repayment", "share_repurchase", "dividends_paid",
    "cash_from_financing", "net_change_in_cash", "free_cash_flow",
]

# Fields that are legitimately absent for certain company types
SECTOR_OPTIONAL: dict[str, set[str]] = {
    # Tech/SaaS companies rarely have inventory
    "Technology": {"inventory", "cost_of_revenue"},
    # Financial companies don't report standard revenue/COGS
    "Financial Services": {
        "cost_of_revenue", "gross_profit", "inventory",
        "accounts_receivable", "accounts_payable",
        "capital_expenditure", "depreciation_amortization",
    },
    "Financials": {
        "cost_of_revenue", "gross_profit", "inventory",
        "accounts_receivable", "accounts_payable",
        "capital_expenditure", "depreciation_amortization",
    },
    # REITs
    "Real Estate": {"inventory", "research_and_development"},
}

# Fields that are always optional (many companies don't report these)
ALWAYS_OPTIONAL = {
    "acquisitions", "purchases_of_investments", "sales_of_investments",
    "debt_issuance", "debt_repayment", "short_term_investments",
    "deferred_revenue", "intangible_assets", "goodwill",
    "other_income", "interest_income", "depreciation_amortization",
    "short_term_debt", "share_repurchase", "dividends_paid",
    "change_in_working_capital",
}

# Map DB field → which XBRL tag dict to search
FIELD_TO_TAG_MAP = {
    "income": INCOME_STATEMENT_TAGS,
    "balance": BALANCE_SHEET_TAGS,
    "cashflow": CASH_FLOW_TAGS,
}


# ──────────────────────────────────────────────
# Core Analysis
# ──────────────────────────────────────────────

def _find_candidate_xbrl_tags(
    facts: dict[str, Any],
    field: str,
    tag_map: dict[str, list[str]],
    fiscal_year: int,
) -> dict[str, Any]:
    """Check if any XBRL tags for a field have data for the given year.

    Returns a dict with:
      - mapped_tags: tags already in our mapping that DO have data
      - unmapped_tags: tags found in raw XBRL that aren't in our mapping yet
      - has_data_in_xbrl: bool — whether the field can potentially be filled
    """
    # Determine unit
    eps_fields = {"eps_basic", "eps_diluted"}
    share_fields = {"shares_basic", "shares_diluted"}
    if field in eps_fields:
        unit = "USD/shares"
    elif field in share_fields:
        unit = "shares"
    else:
        unit = "USD"

    known_tags = tag_map.get(field, [])
    mapped_with_data = []
    for tag in known_tags:
        vals = _extract_fact_values(facts, tag, unit, fiscal_year - 1)
        annual = [v for v in vals if v["fy"] == fiscal_year and v["fp"] == "FY"]
        if annual:
            mapped_with_data.append(tag)

    return {
        "mapped_tags_with_data": mapped_with_data,
        "known_tags": known_tags,
        "has_mapped_data": len(mapped_with_data) > 0,
    }


def _scan_raw_xbrl_for_field(
    facts: dict[str, Any],
    field: str,
    fiscal_year: int,
) -> list[str]:
    """Scan ALL us-gaap tags in raw XBRL to find potential matches for a field.

    Uses keyword heuristics to find tags that MIGHT correspond to the field
    but are not yet in our mapping.
    """
    # Keyword mapping: field -> search terms in XBRL tag names
    field_keywords: dict[str, list[str]] = {
        "revenue": ["Revenue", "Sales"],
        "cost_of_revenue": ["CostOf", "CostOfGoods", "CostOfRevenue"],
        "gross_profit": ["GrossProfit"],
        "research_and_development": ["ResearchAndDevelopment", "ResearchDevelopment"],
        "selling_general_admin": ["SellingGeneralAndAdministrative", "GeneralAndAdministrative", "SellingAndMarketing"],
        "depreciation_amortization": ["Depreciation", "Amortization"],
        "operating_expenses": ["OperatingExpenses", "CostsAndExpenses"],
        "operating_income": ["OperatingIncome"],
        "interest_expense": ["InterestExpense", "InterestCost"],
        "interest_income": ["InterestIncome", "InvestmentIncome"],
        "other_income": ["OtherNonoperating", "NonoperatingIncome"],
        "pretax_income": ["IncomeLossFromContinuingOperationsBefore"],
        "income_tax": ["IncomeTaxExpense"],
        "net_income": ["NetIncome", "ProfitLoss"],
        "eps_basic": ["EarningsPerShareBasic"],
        "eps_diluted": ["EarningsPerShareDiluted"],
        "shares_basic": ["WeightedAverageNumberOfSharesOutstandingBasic", "SharesOutstanding"],
        "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
        "cash_and_equivalents": ["CashAndCashEquivalents", "CashCashEquivalents"],
        "short_term_investments": ["ShortTermInvestments", "MarketableSecurities"],
        "accounts_receivable": ["AccountsReceivable", "Receivables"],
        "inventory": ["Inventory"],
        "total_current_assets": ["AssetsCurrent"],
        "property_plant_equipment": ["PropertyPlantAndEquipment"],
        "goodwill": ["Goodwill"],
        "intangible_assets": ["IntangibleAssets", "FiniteLivedIntangible"],
        "total_assets": ["Assets"],
        "accounts_payable": ["AccountsPayable"],
        "deferred_revenue": ["DeferredRevenue", "ContractWithCustomerLiability"],
        "short_term_debt": ["ShortTermBorrowings", "DebtCurrent", "CommercialPaper"],
        "total_current_liabilities": ["LiabilitiesCurrent"],
        "long_term_debt": ["LongTermDebt"],
        "total_liabilities": ["Liabilities"],
        "common_stock": ["CommonStock"],
        "retained_earnings": ["RetainedEarnings"],
        "total_stockholders_equity": ["StockholdersEquity"],
        "stock_based_compensation": ["ShareBasedCompensation"],
        "change_in_working_capital": ["IncreaseDecreaseInOperating"],
        "cash_from_operations": ["NetCashProvidedByUsedInOperating"],
        "capital_expenditure": ["PaymentsToAcquirePropertyPlant", "PaymentsToAcquireProductiveAssets"],
        "acquisitions": ["PaymentsToAcquireBusinesses"],
        "purchases_of_investments": ["PaymentsToAcquireInvestments", "PaymentsToAcquireAvailableForSale"],
        "sales_of_investments": ["ProceedsFromSaleAndMaturity", "ProceedsFromSaleOfInvestments"],
        "cash_from_investing": ["NetCashProvidedByUsedInInvesting"],
        "debt_issuance": ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt"],
        "debt_repayment": ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt"],
        "share_repurchase": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
        "dividends_paid": ["PaymentsOfDividends"],
        "cash_from_financing": ["NetCashProvidedByUsedInFinancing"],
        "net_change_in_cash": ["CashCashEquivalentsRestrictedCash", "CashAndCashEquivalentsPeriod"],
        "free_cash_flow": [],  # derived field, no direct XBRL tag
    }

    keywords = field_keywords.get(field, [])
    if not keywords:
        return []

    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    # Also get already-known tags to exclude
    all_known = set()
    for tag_list in INCOME_STATEMENT_TAGS.values():
        all_known.update(tag_list)
    for tag_list in BALANCE_SHEET_TAGS.values():
        all_known.update(tag_list)
    for tag_list in CASH_FLOW_TAGS.values():
        all_known.update(tag_list)

    candidates = []
    for tag_name, tag_data in us_gaap.items():
        if tag_name in all_known:
            continue
        # Check if tag name matches any keyword
        tag_lower = tag_name.lower()
        for kw in keywords:
            if kw.lower() in tag_lower:
                # Check if it has data for the target year
                for unit_key in ["USD", "USD/shares", "shares"]:
                    units = tag_data.get("units", {}).get(unit_key, [])
                    for item in units:
                        if item.get("fy") == fiscal_year and item.get("fp") == "FY":
                            candidates.append(tag_name)
                            break
                    else:
                        continue
                    break
                break

    return candidates


def analyze_company(
    ticker: str,
    db=None,
) -> dict[str, Any]:
    """Analyze ETL coverage for a single company.

    Returns a dict:
    {
      "ticker": "AAPL",
      "sector": "Technology",
      "fiscal_years": [2021, 2022, 2023, 2024, 2025],
      "income_statement": { field: { year: "ok"|"no_data"|"unmapped"|"optional" } },
      "balance_sheet": { ... },
      "cash_flow": { ... },
      "summary": { "total_fields": N, "ok": N, "no_data": N, "unmapped": N, "optional": N },
      "unmapped_details": [ { field, year, candidate_tags } ],
    }
    """
    own_session = db is None
    if own_session:
        db = get_session()

    try:
        company = db.query(Company).filter_by(ticker=ticker).first()
        if not company:
            return {"ticker": ticker, "error": "Company not in database"}

        sector = company.sector or "Unknown"

        # Fetch XBRL facts
        cik = sec_client.ticker_to_cik(ticker)
        if not cik:
            return {"ticker": ticker, "error": "Cannot resolve CIK"}

        facts = sec_client.get_company_facts_cached(ticker, cik)
        if not facts:
            return {"ticker": ticker, "error": "No XBRL facts available"}

        # Get fiscal years from DB
        income_rows = (
            db.query(IncomeStatement)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(IncomeStatement.fiscal_year)
            .all()
        )
        balance_rows = (
            db.query(BalanceSheet)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(BalanceSheet.fiscal_year)
            .all()
        )
        cashflow_rows = (
            db.query(CashFlowStatement)
            .filter_by(ticker=ticker, fiscal_quarter=None)
            .order_by(CashFlowStatement.fiscal_year)
            .all()
        )

        fiscal_years = sorted({r.fiscal_year for r in income_rows})
        if not fiscal_years:
            return {"ticker": ticker, "error": "No fiscal year data in DB"}

        sector_optional = SECTOR_OPTIONAL.get(sector, set())
        report: dict[str, Any] = {
            "ticker": ticker,
            "sector": sector,
            "fiscal_years": fiscal_years,
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "summary": {"total_cells": 0, "ok": 0, "no_data": 0, "unmapped": 0, "optional": 0},
            "unmapped_details": [],
        }

        def _analyze_statement(rows, cols, tag_map, stmt_key):
            stmt_report = {}
            for col in cols:
                col_report = {}
                for row in rows:
                    fy = row.fiscal_year
                    val = getattr(row, col, None)
                    report["summary"]["total_cells"] += 1

                    if val is not None:
                        col_report[fy] = "ok"
                        report["summary"]["ok"] += 1
                        continue

                    # NULL — is it optional?
                    if col in ALWAYS_OPTIONAL or col in sector_optional:
                        # Still check if it's unmapped
                        check = _find_candidate_xbrl_tags(facts, col, tag_map, fy)
                        if check["has_mapped_data"]:
                            col_report[fy] = "unmapped"
                            report["summary"]["unmapped"] += 1
                            report["unmapped_details"].append({
                                "field": col,
                                "statement": stmt_key,
                                "fiscal_year": fy,
                                "mapped_tags_with_data": check["mapped_tags_with_data"],
                            })
                        else:
                            # Check for truly unmapped candidates
                            raw_candidates = _scan_raw_xbrl_for_field(facts, col, fy)
                            if raw_candidates:
                                col_report[fy] = "unmapped"
                                report["summary"]["unmapped"] += 1
                                report["unmapped_details"].append({
                                    "field": col,
                                    "statement": stmt_key,
                                    "fiscal_year": fy,
                                    "candidate_new_tags": raw_candidates,
                                })
                            else:
                                col_report[fy] = "optional"
                                report["summary"]["optional"] += 1
                        continue

                    # Required field is NULL — check XBRL
                    check = _find_candidate_xbrl_tags(facts, col, tag_map, fy)
                    if check["has_mapped_data"]:
                        # We have tags with data but the parser didn't pick them up
                        col_report[fy] = "unmapped"
                        report["summary"]["unmapped"] += 1
                        report["unmapped_details"].append({
                            "field": col,
                            "statement": stmt_key,
                            "fiscal_year": fy,
                            "mapped_tags_with_data": check["mapped_tags_with_data"],
                        })
                    else:
                        # Scan raw XBRL for unknown tags
                        raw_candidates = _scan_raw_xbrl_for_field(facts, col, fy)
                        if raw_candidates:
                            col_report[fy] = "unmapped"
                            report["summary"]["unmapped"] += 1
                            report["unmapped_details"].append({
                                "field": col,
                                "statement": stmt_key,
                                "fiscal_year": fy,
                                "candidate_new_tags": raw_candidates,
                            })
                        else:
                            col_report[fy] = "no_data"
                            report["summary"]["no_data"] += 1

                stmt_report[col] = col_report
            return stmt_report

        report["income_statement"] = _analyze_statement(
            income_rows, INCOME_COLS, INCOME_STATEMENT_TAGS, "income_statement"
        )
        report["balance_sheet"] = _analyze_statement(
            balance_rows, BALANCE_COLS, BALANCE_SHEET_TAGS, "balance_sheet"
        )
        report["cash_flow"] = _analyze_statement(
            cashflow_rows, CASHFLOW_COLS, CASH_FLOW_TAGS, "cash_flow"
        )

        return report

    finally:
        if own_session:
            db.close()


# ──────────────────────────────────────────────
# Output Formatting
# ──────────────────────────────────────────────

def print_company_report(report: dict[str, Any]) -> None:
    """Print a human-readable coverage report for one company."""
    ticker = report["ticker"]
    if "error" in report:
        print(f"\n{'='*60}")
        print(f"  {ticker}: ERROR — {report['error']}")
        print(f"{'='*60}")
        return

    s = report["summary"]
    total = s["total_cells"]
    print(f"\n{'='*60}")
    print(f"  {ticker}  ({report['sector']})")
    print(f"  Fiscal Years: {report['fiscal_years']}")
    print(f"{'='*60}")
    print(f"  Total cells:  {total}")
    print(f"  OK:           {s['ok']:>4}  ({s['ok']/total*100:.1f}%)")
    print(f"  No data:      {s['no_data']:>4}  ({s['no_data']/total*100:.1f}%)")
    print(f"  Optional:     {s['optional']:>4}  ({s['optional']/total*100:.1f}%)")
    print(f"  Unmapped:     {s['unmapped']:>4}  ({s['unmapped']/total*100:.1f}%)")

    if report["unmapped_details"]:
        print(f"\n  ⚠  UNMAPPED FIELDS (parser may need new tag mappings):")
        for item in report["unmapped_details"]:
            tags = item.get("mapped_tags_with_data") or item.get("candidate_new_tags", [])
            tag_str = ", ".join(tags[:3])
            if len(tags) > 3:
                tag_str += f" (+{len(tags)-3} more)"
            print(f"     {item['statement']:>20s}.{item['field']:<30s} FY{item['fiscal_year']}  → {tag_str}")

    # Show no_data fields (grouped)
    no_data_fields: dict[str, list[int]] = defaultdict(list)
    for stmt_key in ("income_statement", "balance_sheet", "cash_flow"):
        for field, years_data in report[stmt_key].items():
            for fy, status in years_data.items():
                if status == "no_data":
                    no_data_fields[f"{stmt_key}.{field}"].append(fy)

    if no_data_fields:
        print(f"\n  ℹ  NO DATA (company does not report these — skip):")
        for field_key, years in sorted(no_data_fields.items()):
            yr_str = ", ".join(str(y) for y in sorted(years))
            print(f"     {field_key:<50s} FY: {yr_str}")


def print_summary_table(reports: list[dict[str, Any]]) -> None:
    """Print a cross-company summary table."""
    print(f"\n{'='*80}")
    print(f"  ETL COVERAGE SUMMARY — {len(reports)} companies")
    print(f"{'='*80}")
    print(f"  {'Ticker':<8s} {'Sector':<22s} {'OK%':>6s} {'NoData%':>8s} {'Opt%':>6s} {'Unmap%':>7s} {'Total':>6s}")
    print(f"  {'-'*8} {'-'*22} {'-'*6} {'-'*8} {'-'*6} {'-'*7} {'-'*6}")

    total_unmapped = 0
    for r in sorted(reports, key=lambda x: x.get("ticker", "")):
        if "error" in r:
            print(f"  {r['ticker']:<8s} ERROR: {r['error']}")
            continue
        s = r["summary"]
        t = s["total_cells"]
        ok_pct = s["ok"] / t * 100
        nd_pct = s["no_data"] / t * 100
        op_pct = s["optional"] / t * 100
        um_pct = s["unmapped"] / t * 100
        total_unmapped += s["unmapped"]
        flag = " ⚠" if s["unmapped"] > 0 else ""
        print(f"  {r['ticker']:<8s} {r['sector']:<22s} {ok_pct:>5.1f}% {nd_pct:>7.1f}% {op_pct:>5.1f}% {um_pct:>6.1f}% {t:>5d}{flag}")

    print(f"\n  Total unmapped cells across all companies: {total_unmapped}")
    if total_unmapped == 0:
        print("  ✅ All parseable XBRL data is mapped. Remaining NULLs are legitimate.")
    else:
        print("  ⚠  Some fields have XBRL data available but unmapped. Consider updating xbrl_parser.py.")


def save_report(reports: list[dict[str, Any]], output_path: Path) -> None:
    """Save the full coverage report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Make JSON-serializable (convert int keys)
    serializable = []
    for r in reports:
        sr = dict(r)
        for stmt_key in ("income_statement", "balance_sheet", "cash_flow"):
            if stmt_key in sr:
                new_stmt = {}
                for field, years_data in sr[stmt_key].items():
                    new_stmt[field] = {str(k): v for k, v in years_data.items()}
                sr[stmt_key] = new_stmt
        serializable.append(sr)

    output_path.write_text(json.dumps(serializable, indent=2))
    logger.info(f"Coverage report saved to {output_path}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check ETL data coverage across financial statements",
    )
    parser.add_argument(
        "--ticker", "-t",
        type=str,
        default=None,
        help="Analyze a specific ticker (default: all companies in DB)",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Show only the summary table, not per-company detail",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Custom output path for JSON report (default: data/artifacts/_etl/coverage_report.json)",
    )
    args = parser.parse_args()

    db = get_session()
    try:
        if args.ticker:
            tickers = [args.ticker.upper().strip()]
        else:
            tickers = [
                t for (t,) in db.query(Company.ticker).order_by(Company.ticker).all()
            ]

        logger.info(f"Analyzing {len(tickers)} companies...")

        reports = []
        for i, ticker in enumerate(tickers, 1):
            logger.info(f"[{i}/{len(tickers)}] {ticker}")
            report = analyze_company(ticker, db=db)
            reports.append(report)

        # Print results
        if args.summary:
            print_summary_table(reports)
        else:
            for r in reports:
                print_company_report(r)
            if len(reports) > 1:
                print_summary_table(reports)

        # Save JSON report
        output_path = Path(args.output) if args.output else (
            settings.artifacts_dir / "_etl" / "coverage_report.json"
        )
        save_report(reports, output_path)

    finally:
        db.close()


if __name__ == "__main__":
    main()
