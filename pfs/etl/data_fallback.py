"""Multi-source financial data fallback chain.

Priority: SEC XBRL (already parsed) → yfinance → Alpha Vantage

After SEC XBRL parsing produces the initial data dicts, this module checks
for missing fields and fills gaps from secondary sources. Every filled field
is tracked for provenance so downstream consumers know where data originated.

Required fields are enforced — if they remain None after all sources are
exhausted, a WARNING is logged so data-quality issues are visible.
"""

import logging
from typing import Any

import httpx

from pfs.config import settings

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Required / Important field definitions
# ════════════════════════════════════════════════════════════════════════════

# REQUIRED: must be present for meaningful analysis — will warn if still None
REQUIRED_INCOME_FIELDS = frozenset({
    "revenue", "net_income", "operating_income", "gross_profit",
    "eps_diluted", "shares_diluted",
})

REQUIRED_BALANCE_FIELDS = frozenset({
    "total_assets", "total_liabilities", "total_stockholders_equity",
    "cash_and_equivalents",
})

REQUIRED_CASHFLOW_FIELDS = frozenset({
    "cash_from_operations", "capital_expenditure", "free_cash_flow",
})

# IMPORTANT: valuable for deeper analysis, but not fatal if absent
IMPORTANT_INCOME_FIELDS = frozenset({
    "cost_of_revenue", "research_and_development", "selling_general_admin",
    "pretax_income", "income_tax", "interest_expense",
    "eps_basic", "shares_basic",
})

IMPORTANT_BALANCE_FIELDS = frozenset({
    "total_current_assets", "total_current_liabilities",
    "long_term_debt", "retained_earnings",
    "accounts_receivable", "inventory",
})

IMPORTANT_CASHFLOW_FIELDS = frozenset({
    "net_income", "depreciation_amortization", "stock_based_compensation",
    "cash_from_investing", "cash_from_financing",
})

# Cash-flow fields stored as absolute values (outflows)
ABS_VALUE_CASHFLOW_FIELDS = frozenset({
    "capital_expenditure", "debt_repayment", "share_repurchase",
    "dividends_paid", "purchases_of_investments", "acquisitions",
})


# ════════════════════════════════════════════════════════════════════════════
# yfinance label → our field mapping
# ════════════════════════════════════════════════════════════════════════════

YF_INCOME_MAP: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Revenue", "Operating Revenue"],
    "cost_of_revenue": ["Cost Of Revenue", "Cost Of Goods Sold"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Operating Revenue"],
    "operating_expenses": ["Operating Expense", "Total Operating Expenses"],
    "net_income": [
        "Net Income", "Net Income Common Stockholders",
        "Net Income From Continuing Operations",
    ],
    "pretax_income": ["Pretax Income", "Income Before Tax"],
    "income_tax": ["Tax Provision", "Income Tax Expense"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "interest_income": ["Interest Income", "Interest Income Non Operating"],
    "research_and_development": ["Research And Development", "Research Development"],
    "selling_general_admin": ["Selling General And Administration", "SGA"],
    "depreciation_amortization": ["Depreciation And Amortization In Income Statement", "Depreciation And Amortization"],
    "eps_basic": ["Basic EPS"],
    "eps_diluted": ["Diluted EPS"],
    "shares_basic": ["Basic Average Shares"],
    "shares_diluted": ["Diluted Average Shares"],
}

YF_BALANCE_MAP: dict[str, list[str]] = {
    "cash_and_equivalents": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
    ],
    "short_term_investments": ["Other Short Term Investments", "Short Term Investments"],
    "accounts_receivable": ["Accounts Receivable", "Receivables", "Net Receivables"],
    "inventory": ["Inventory", "Raw Materials", "Finished Goods"],
    "total_current_assets": ["Current Assets"],
    "property_plant_equipment": ["Net PPE", "Property Plant Equipment Net"],
    "goodwill": ["Goodwill"],
    "intangible_assets": ["Other Intangible Assets"],
    "total_assets": ["Total Assets"],
    "accounts_payable": [
        "Accounts Payable", "Current Accounts Payable",
        "Payables And Accrued Expenses",
    ],
    "deferred_revenue": ["Current Deferred Revenue", "Deferred Revenue"],
    "short_term_debt": ["Current Debt", "Current Debt And Capital Lease Obligation"],
    "total_current_liabilities": ["Current Liabilities"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "total_liabilities": [
        "Total Liabilities Net Minority Interest", "Total Liabilities",
    ],
    "common_stock": ["Common Stock", "Capital Stock"],
    "retained_earnings": ["Retained Earnings"],
    "total_stockholders_equity": [
        "Stockholders Equity", "Total Equity Gross Minority Interest",
    ],
}

YF_CASHFLOW_MAP: dict[str, list[str]] = {
    "net_income": ["Net Income From Continuing Operations", "Net Income"],
    "depreciation_amortization": [
        "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
    ],
    "stock_based_compensation": ["Stock Based Compensation"],
    "change_in_working_capital": [
        "Change In Working Capital", "Changes In Account Receivables",
    ],
    "cash_from_operations": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
    ],
    "capital_expenditure": ["Capital Expenditure", "Purchase Of PPE"],
    "acquisitions": ["Purchase Of Business", "Acquisitions Net"],
    "purchases_of_investments": [
        "Purchase Of Investment", "Net Investment Purchase And Sale",
    ],
    "sales_of_investments": ["Sale Of Investment"],
    "cash_from_investing": [
        "Investing Cash Flow",
        "Cash Flow From Continuing Investing Activities",
    ],
    "debt_issuance": ["Issuance Of Debt", "Long Term Debt Issuance"],
    "debt_repayment": ["Repayment Of Debt", "Long Term Debt Payments"],
    "share_repurchase": ["Repurchase Of Capital Stock", "Common Stock Payments"],
    "dividends_paid": ["Common Stock Dividend Paid", "Cash Dividends Paid"],
    "cash_from_financing": [
        "Financing Cash Flow",
        "Cash Flow From Continuing Financing Activities",
    ],
    "net_change_in_cash": [
        "Changes In Cash", "Change In Cash Supplemental As Reported",
    ],
    "free_cash_flow": ["Free Cash Flow"],
}


# ════════════════════════════════════════════════════════════════════════════
# Alpha Vantage key → our field mapping
# ════════════════════════════════════════════════════════════════════════════

AV_INCOME_MAP: dict[str, str] = {
    "revenue": "totalRevenue",
    "cost_of_revenue": "costOfRevenue",
    "gross_profit": "grossProfit",
    "operating_income": "operatingIncome",
    "operating_expenses": "operatingExpenses",
    "net_income": "netIncome",
    "pretax_income": "incomeBeforeTax",
    "income_tax": "incomeTaxExpense",
    "interest_expense": "interestExpense",
    "interest_income": "interestIncome",
    "research_and_development": "researchAndDevelopment",
    "selling_general_admin": "sellingGeneralAndAdministrative",
    "depreciation_amortization": "depreciationAndAmortization",
    "eps_diluted": "reportedEPS",
}

AV_BALANCE_MAP: dict[str, str] = {
    "cash_and_equivalents": "cashAndCashEquivalentsAtCarryingValue",
    "short_term_investments": "shortTermInvestments",
    "accounts_receivable": "currentNetReceivables",
    "inventory": "inventory",
    "total_current_assets": "totalCurrentAssets",
    "property_plant_equipment": "propertyPlantEquipment",
    "goodwill": "goodwill",
    "intangible_assets": "intangibleAssets",
    "total_assets": "totalAssets",
    "accounts_payable": "currentAccountsPayable",
    "total_current_liabilities": "totalCurrentLiabilities",
    "long_term_debt": "longTermDebt",
    "short_term_debt": "shortTermDebt",
    "total_liabilities": "totalLiabilities",
    "retained_earnings": "retainedEarnings",
    "total_stockholders_equity": "totalShareholderEquity",
}

AV_CASHFLOW_MAP: dict[str, str] = {
    "net_income": "netIncome",
    "depreciation_amortization": "depreciationDepletionAndAmortization",
    "cash_from_operations": "operatingCashflow",
    "capital_expenditure": "capitalExpenditures",
    "cash_from_investing": "cashflowFromInvestment",
    "cash_from_financing": "cashflowFromFinancing",
    "dividends_paid": "dividendPayout",
    "net_change_in_cash": "changeInCashAndCashEquivalents",
}


# ════════════════════════════════════════════════════════════════════════════
# yfinance Fallback Source (lazy, cached)
# ════════════════════════════════════════════════════════════════════════════

class YFinanceFallback:
    """Lazy-loading cache for yfinance annual financial statements."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._income: dict[int, dict] | None = None
        self._balance: dict[int, dict] | None = None
        self._cashflow: dict[int, dict] | None = None
        self._fetched = False

    def _fetch(self) -> None:
        if self._fetched:
            return
        self._fetched = True

        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed — fallback unavailable")
            self._income, self._balance, self._cashflow = {}, {}, {}
            return

        try:
            stock = yf.Ticker(self.ticker)
            self._income = _parse_yf_df(stock.financials, YF_INCOME_MAP)
            self._balance = _parse_yf_df(stock.balance_sheet, YF_BALANCE_MAP)
            self._cashflow = _parse_yf_df(
                stock.cashflow, YF_CASHFLOW_MAP, abs_fields=ABS_VALUE_CASHFLOW_FIELDS,
            )
            logger.info(
                f"[{self.ticker}] yfinance fallback loaded — "
                f"IS years={sorted(self._income)}, "
                f"BS years={sorted(self._balance)}, "
                f"CF years={sorted(self._cashflow)}"
            )
        except Exception as e:
            logger.warning(f"[{self.ticker}] yfinance fallback fetch failed: {e}")
            self._income, self._balance, self._cashflow = {}, {}, {}

    def get_income(self, fiscal_year: int) -> dict[str, Any]:
        self._fetch()
        return (self._income or {}).get(fiscal_year, {})

    def get_balance(self, fiscal_year: int) -> dict[str, Any]:
        self._fetch()
        return (self._balance or {}).get(fiscal_year, {})

    def get_cashflow(self, fiscal_year: int) -> dict[str, Any]:
        self._fetch()
        return (self._cashflow or {}).get(fiscal_year, {})


def _parse_yf_df(
    df: Any,
    mapping: dict[str, list[str]],
    abs_fields: frozenset[str] | None = None,
) -> dict[int, dict[str, Any]]:
    """Convert a yfinance DataFrame → ``{year: {field: value}}``."""
    if df is None:
        return {}
    try:
        import pandas as pd
        if df.empty:
            return {}
    except Exception:
        return {}

    result: dict[int, dict[str, Any]] = {}
    for col in df.columns:
        year = col.year
        yearly: dict[str, Any] = {}

        for our_field, yf_labels in mapping.items():
            for label in yf_labels:
                if label in df.index:
                    val = df.loc[label, col]
                    try:
                        import pandas as pd
                        if pd.isna(val):
                            continue
                    except Exception:
                        if val is None:
                            continue
                    fval = float(val)
                    # Normalize outflow fields to positive
                    if abs_fields and our_field in abs_fields:
                        fval = abs(fval)
                    # Store large numbers as int, small (EPS, ratios) as float
                    yearly[our_field] = int(fval) if abs(fval) >= 1.0 else fval
                    break

        if yearly:
            result[year] = yearly

    return result


# ════════════════════════════════════════════════════════════════════════════
# Alpha Vantage Fallback Source (lazy, cached, endpoint-level)
# ════════════════════════════════════════════════════════════════════════════

class AlphaVantageFallback:
    """Lazy-loading cache for Alpha Vantage financial statements.

    Each endpoint is fetched at most once; subsequent calls return cached data.
    Free-tier is 25 requests/day so we are deliberately conservative.
    """

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self._income: dict[int, dict] | None = None
        self._balance: dict[int, dict] | None = None
        self._cashflow: dict[int, dict] | None = None

    # ── public getters (lazy) ──────────────────────────────────────────

    def get_income(self, fiscal_year: int) -> dict[str, Any]:
        if self._income is None:
            data = self._fetch_endpoint("INCOME_STATEMENT")
            self._income = _parse_av_reports(
                data.get("annualReports", []), AV_INCOME_MAP,
            )
        return self._income.get(fiscal_year, {})

    def get_balance(self, fiscal_year: int) -> dict[str, Any]:
        if self._balance is None:
            data = self._fetch_endpoint("BALANCE_SHEET")
            self._balance = _parse_av_reports(
                data.get("annualReports", []), AV_BALANCE_MAP,
            )
        return self._balance.get(fiscal_year, {})

    def get_cashflow(self, fiscal_year: int) -> dict[str, Any]:
        if self._cashflow is None:
            data = self._fetch_endpoint("CASH_FLOW")
            self._cashflow = _parse_av_reports(
                data.get("annualReports", []), AV_CASHFLOW_MAP,
                abs_fields=ABS_VALUE_CASHFLOW_FIELDS,
            )
        return self._cashflow.get(fiscal_year, {})

    # ── HTTP helper ────────────────────────────────────────────────────

    def _fetch_endpoint(self, function: str) -> dict:
        if not settings.alpha_vantage_key:
            return {}

        params = {
            "function": function,
            "symbol": self.ticker,
            "apikey": settings.alpha_vantage_key,
        }

        try:
            resp = httpx.get(
                settings.alpha_vantage_base_url,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if "Error Message" in data:
                logger.warning(
                    f"[{self.ticker}] AV {function}: {data['Error Message']}"
                )
                return {}
            if "Note" in data:
                logger.warning(
                    f"[{self.ticker}] AV rate-limited on {function}: {data['Note']}"
                )
                return {}

            logger.info(f"[{self.ticker}] AV {function} fetched OK")
            return data

        except Exception as e:
            logger.warning(f"[{self.ticker}] AV {function} failed: {e}")
            return {}


def _parse_av_reports(
    reports: list[dict],
    mapping: dict[str, str],
    abs_fields: frozenset[str] | None = None,
) -> dict[int, dict[str, Any]]:
    """Convert AV ``annualReports`` list → ``{year: {field: value}}``."""
    result: dict[int, dict[str, Any]] = {}

    for report in reports:
        date_str = report.get("fiscalDateEnding", "")
        if not date_str:
            continue

        year = int(date_str[:4])
        yearly: dict[str, Any] = {}

        for our_field, av_key in mapping.items():
            val_str = report.get(av_key)
            if not val_str or val_str == "None":
                continue
            try:
                fval = float(val_str)
                if abs_fields and our_field in abs_fields:
                    fval = abs(fval)
                yearly[our_field] = int(fval) if abs(fval) >= 1.0 else fval
            except ValueError:
                pass

        if yearly:
            result[year] = yearly

    return result


# ════════════════════════════════════════════════════════════════════════════
# Core: fill_statement_gaps
# ════════════════════════════════════════════════════════════════════════════

def fill_statement_gaps(
    ticker: str,
    fiscal_year: int,
    quarter: int | None,
    income: dict[str, Any],
    balance: dict[str, Any],
    cash_flow: dict[str, Any],
    *,
    yf_fallback: YFinanceFallback | None = None,
    av_fallback: AlphaVantageFallback | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, list[str]]]:
    """Fill missing fields in SEC-parsed financial statements.

    For each statement the function:
      1. Identifies missing required + important fields
      2. Tries yfinance to fill gaps
      3. Tries Alpha Vantage for any remaining gaps
      4. Recomputes derived fields (gross profit, FCF, …)
      5. Logs provenance and warns about still-missing required fields

    Args:
        ticker: Company ticker.
        fiscal_year: Fiscal year being processed.
        quarter: Quarter number (1-4) or None for annual.
        income / balance / cash_flow: Dicts from ``xbrl_parser.parse_*`` — **mutated in place**.
        yf_fallback: Pre-created ``YFinanceFallback`` (shared across years).
        av_fallback: Pre-created ``AlphaVantageFallback`` (shared across years).

    Returns:
        ``(income, balance, cash_flow, sources_used)``
        where ``sources_used`` maps ``"yfinance"`` / ``"alpha_vantage"`` → list of
        ``"<stmt>.<field>"`` strings.
    """
    # Only run fallback for annual data — quarterly from secondary sources
    # is less reliable and seldom needed for core analysis.
    if quarter is not None:
        return income, balance, cash_flow, {}

    sources_used: dict[str, list[str]] = {"yfinance": [], "alpha_vantage": []}

    # Build work list: (statement dict, type label, fields to check)
    work = [
        (income, "income",
         REQUIRED_INCOME_FIELDS | IMPORTANT_INCOME_FIELDS),
        (balance, "balance",
         REQUIRED_BALANCE_FIELDS | IMPORTANT_BALANCE_FIELDS),
        (cash_flow, "cashflow",
         REQUIRED_CASHFLOW_FIELDS | IMPORTANT_CASHFLOW_FIELDS),
    ]

    for stmt, stmt_type, target_fields in work:
        missing = [f for f in target_fields if stmt.get(f) is None]
        if not missing:
            continue

        logger.info(
            f"[{ticker}] FY{fiscal_year} {stmt_type}: "
            f"{len(missing)} fields missing from SEC XBRL — starting fallback"
        )

        # ── yfinance ──────────────────────────────────────────────────
        if yf_fallback and missing:
            yf_data = _pick_source(yf_fallback, stmt_type, fiscal_year)
            filled = _apply_fallback(stmt, missing, yf_data)
            if filled:
                sources_used["yfinance"].extend(
                    f"{stmt_type}.{f}" for f in filled
                )
                logger.info(
                    f"[{ticker}] FY{fiscal_year} {stmt_type}: "
                    f"yfinance filled {len(filled)} fields: {filled}"
                )

        # ── Alpha Vantage ─────────────────────────────────────────────
        if av_fallback and missing:
            av_data = _pick_source(av_fallback, stmt_type, fiscal_year)
            filled = _apply_fallback(stmt, missing, av_data)
            if filled:
                sources_used["alpha_vantage"].extend(
                    f"{stmt_type}.{f}" for f in filled
                )
                logger.info(
                    f"[{ticker}] FY{fiscal_year} {stmt_type}: "
                    f"Alpha Vantage filled {len(filled)} fields: {filled}"
                )

    # ── Recompute derived fields after filling ────────────────────────
    _recompute_derived(income, balance, cash_flow)

    # ── Update source provenance string on each statement ─────────────
    _update_source_tags(income, balance, cash_flow, sources_used)

    # ── Validate required fields — loud warning if still missing ──────
    _validate_required(ticker, fiscal_year, income, balance, cash_flow)

    return income, balance, cash_flow, sources_used


# ════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════════

def _pick_source(
    fb: YFinanceFallback | AlphaVantageFallback,
    stmt_type: str,
    fiscal_year: int,
) -> dict[str, Any]:
    """Route to the correct getter on a fallback object."""
    if stmt_type == "income":
        return fb.get_income(fiscal_year)
    if stmt_type == "balance":
        return fb.get_balance(fiscal_year)
    return fb.get_cashflow(fiscal_year)


def _apply_fallback(
    stmt: dict[str, Any],
    missing: list[str],
    source_data: dict[str, Any],
) -> list[str]:
    """Fill *missing* fields from *source_data*. Returns list of filled field names.

    ``missing`` is **mutated** (filled fields are removed).
    """
    filled: list[str] = []
    for field in list(missing):
        val = source_data.get(field)
        if val is not None:
            stmt[field] = val
            filled.append(field)
            missing.remove(field)
    return filled


def _recompute_derived(
    income: dict[str, Any],
    balance: dict[str, Any],
    cash_flow: dict[str, Any],
) -> None:
    """Recompute derived fields that depend on freshly-filled values."""
    # Gross Profit = Revenue − |Cost of Revenue|
    if income.get("gross_profit") is None:
        rev = income.get("revenue")
        cogs = income.get("cost_of_revenue")
        if rev is not None and cogs is not None:
            income["gross_profit"] = rev - abs(cogs)

    # Operating Expenses = Gross Profit − Operating Income
    if income.get("operating_expenses") is None:
        gp = income.get("gross_profit")
        oi = income.get("operating_income")
        if gp is not None and oi is not None:
            income["operating_expenses"] = gp - oi

    # Total Liabilities = Total Assets − Stockholders' Equity
    if balance.get("total_liabilities") is None:
        ta = balance.get("total_assets")
        eq = balance.get("total_stockholders_equity")
        if ta is not None and eq is not None:
            balance["total_liabilities"] = ta - eq

    # Free Cash Flow = CFO − |CapEx|
    if cash_flow.get("free_cash_flow") is None:
        cfo = cash_flow.get("cash_from_operations")
        capex = cash_flow.get("capital_expenditure")
        if cfo is not None and capex is not None:
            cash_flow["free_cash_flow"] = cfo - abs(capex)


def _update_source_tags(
    income: dict[str, Any],
    balance: dict[str, Any],
    cash_flow: dict[str, Any],
    sources_used: dict[str, list[str]],
) -> None:
    """Append secondary-source suffixes to each statement's ``source`` field."""
    has_yf = bool(sources_used.get("yfinance"))
    has_av = bool(sources_used.get("alpha_vantage"))
    if not has_yf and not has_av:
        return

    suffix = ""
    if has_yf:
        suffix += "+yfinance"
    if has_av:
        suffix += "+alpha_vantage"

    for stmt in (income, balance, cash_flow):
        base = stmt.get("source") or "sec_xbrl"
        if suffix not in base:
            stmt["source"] = base + suffix


def _validate_required(
    ticker: str,
    fiscal_year: int,
    income: dict[str, Any],
    balance: dict[str, Any],
    cash_flow: dict[str, Any],
) -> None:
    """Log warnings for required fields that remain None after all fallbacks."""
    checks = [
        (income, REQUIRED_INCOME_FIELDS, "Income Statement"),
        (balance, REQUIRED_BALANCE_FIELDS, "Balance Sheet"),
        (cash_flow, REQUIRED_CASHFLOW_FIELDS, "Cash Flow"),
    ]
    for stmt, required, label in checks:
        still_missing = [f for f in required if stmt.get(f) is None]
        if still_missing:
            logger.warning(
                f"[{ticker}] FY{fiscal_year} {label}: REQUIRED fields still missing "
                f"after SEC + yfinance + Alpha Vantage: {still_missing}"
            )
