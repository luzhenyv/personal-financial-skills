"""XBRL Company Facts parser.

Parses the SEC XBRL companyfacts JSON into structured financial statement rows.
Maps XBRL US-GAAP taxonomy tags to our database schema fields.
"""

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# XBRL Tag → Schema Field Mapping
# ──────────────────────────────────────────────

# Income Statement mappings (ordered by preference — first match wins)
INCOME_STATEMENT_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ],
    "gross_profit": ["GrossProfit"],
    "research_and_development": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    "selling_general_admin": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ],
    "operating_expenses": [
        "OperatingExpenses",
        "CostsAndExpenses",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
    ],
    "interest_income": [
        "InterestIncome",
        "InvestmentIncomeInterest",
    ],
    "other_income": [
        "OtherNonoperatingIncomeExpense",
        "NonoperatingIncomeExpense",
    ],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "income_tax": [
        "IncomeTaxExpenseBenefit",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "eps_basic": [
        "EarningsPerShareBasic",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
    ],
    "shares_basic": [
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "CommonStockSharesOutstanding",
    ],
    "shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
}

# Balance Sheet mappings
BALANCE_SHEET_TAGS: dict[str, list[str]] = {
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "short_term_investments": [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ],
    "accounts_receivable": [
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
    ],
    "inventory": [
        "InventoryNet",
        "InventoryFinishedGoodsAndWorkInProcess",
    ],
    "total_current_assets": [
        "AssetsCurrent",
    ],
    "property_plant_equipment": [
        "PropertyPlantAndEquipmentNet",
    ],
    "goodwill": [
        "Goodwill",
    ],
    "intangible_assets": [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ],
    "total_assets": [
        "Assets",
    ],
    "accounts_payable": [
        "AccountsPayableCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
    ],
    "short_term_debt": [
        "ShortTermBorrowings",
        "DebtCurrent",
        "LongTermDebtCurrent",
    ],
    "total_current_liabilities": [
        "LiabilitiesCurrent",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    "total_liabilities": [
        "Liabilities",
    ],
    "common_stock": [
        "CommonStockValue",
        "CommonStocksIncludingAdditionalPaidInCapital",
    ],
    "retained_earnings": [
        "RetainedEarningsAccumulatedDeficit",
    ],
    "total_stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
}

# Cash Flow Statement mappings
CASH_FLOW_TAGS: dict[str, list[str]] = {
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "stock_based_compensation": [
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
    ],
    "change_in_working_capital": [
        "IncreaseDecreaseInOperatingCapital",
        "IncreaseDecreaseInOperatingLiabilities",
    ],
    "cash_from_operations": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],
    "capital_expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
    ],
    "acquisitions": [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesGross",
    ],
    "purchases_of_investments": [
        "PaymentsToAcquireInvestments",
        "PaymentsToAcquireAvailableForSaleSecuritiesDebt",
    ],
    "sales_of_investments": [
        "ProceedsFromSaleAndMaturityOfMarketableSecurities",
        "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities",
    ],
    "cash_from_investing": [
        "NetCashProvidedByUsedInInvestingActivities",
    ],
    "debt_issuance": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
    ],
    "debt_repayment": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
    ],
    "share_repurchase": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ],
    "dividends_paid": [
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfDividends",
    ],
    "cash_from_financing": [
        "NetCashProvidedByUsedInFinancingActivities",
    ],
    "net_change_in_cash": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
    ],
}

# EPS tags use different units (USD/shares instead of USD)
EPS_FIELDS = {"eps_basic", "eps_diluted"}
PER_SHARE_FIELDS = EPS_FIELDS


def _extract_fact_values(
    facts: dict[str, Any],
    tag: str,
    unit_key: str = "USD",
    min_year: int = 2020,
) -> list[dict]:
    """Extract values for a single XBRL tag, filtered to recent fiscal years.

    Returns list of dicts with keys: fy, fp, val, end, filed, form
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    tag_data = us_gaap.get(tag, {})
    if not tag_data:
        return []

    units = tag_data.get("units", {})
    values = units.get(unit_key, [])
    if not values:
        # Try alternate unit keys
        for alt_key in ["USD/shares", "shares", "pure"]:
            if alt_key in units:
                values = units[alt_key]
                break

    result = []
    for item in values:
        fy = item.get("fy", 0)
        if fy < min_year:
            continue

        result.append({
            "fy": fy,
            "fp": item.get("fp", ""),        # FY, Q1, Q2, Q3, Q4
            "val": item.get("val"),
            "end": item.get("end", ""),       # Period end date
            "filed": item.get("filed", ""),   # Filing date
            "form": item.get("form", ""),     # 10-K, 10-Q
        })

    return result


def _resolve_tag(
    facts: dict, field_name: str, tag_candidates: list[str], unit_key: str, min_year: int
) -> list[dict]:
    """Try each candidate tag until we find data."""
    for tag in tag_candidates:
        values = _extract_fact_values(facts, tag, unit_key, min_year)
        if values:
            logger.debug(f"  {field_name} → {tag} ({len(values)} values)")
            return values
    logger.debug(f"  {field_name} → NO DATA (tried {len(tag_candidates)} tags)")
    return []


def _pick_annual(values: list[dict], fiscal_year: int) -> int | float | None:
    """Pick the best annual value for a fiscal year.

    Prefer: form='10-K', fp='FY', most recent filing date.
    """
    candidates = [v for v in values if v["fy"] == fiscal_year]
    if not candidates:
        return None

    # Prefer 10-K filings
    k_filings = [c for c in candidates if c["form"] == "10-K"]
    if k_filings:
        candidates = k_filings

    # Prefer FY period
    fy_vals = [c for c in candidates if c["fp"] == "FY"]
    if fy_vals:
        candidates = fy_vals

    # Pick the most recently filed
    candidates.sort(key=lambda x: x.get("filed", ""), reverse=True)
    return candidates[0]["val"]


def _pick_quarterly(values: list[dict], fiscal_year: int, quarter: int) -> int | float | None:
    """Pick the best quarterly value."""
    fp_str = f"Q{quarter}"
    candidates = [v for v in values if v["fy"] == fiscal_year and v["fp"] == fp_str]
    if not candidates:
        return None

    # Prefer 10-Q filings
    q_filings = [c for c in candidates if c["form"] == "10-Q"]
    if q_filings:
        candidates = q_filings

    candidates.sort(key=lambda x: x.get("filed", ""), reverse=True)
    return candidates[0]["val"]


# ──────────────────────────────────────────────
# Main Parsing Functions
# ──────────────────────────────────────────────

def parse_income_statement(
    facts: dict[str, Any], fiscal_year: int, quarter: int | None = None
) -> dict[str, Any]:
    """Parse income statement data for a specific period."""
    pick = _pick_quarterly if quarter else _pick_annual

    result = {"fiscal_year": fiscal_year, "fiscal_quarter": quarter}
    raw_values = {}

    for field, tags in INCOME_STATEMENT_TAGS.items():
        unit = "USD/shares" if field in EPS_FIELDS else "USD"
        if field in ("shares_basic", "shares_diluted"):
            unit = "shares"

        values = _resolve_tag(facts, field, tags, unit, fiscal_year - 1)
        if quarter:
            val = _pick_quarterly(values, fiscal_year, quarter)
        else:
            val = _pick_annual(values, fiscal_year)

        result[field] = val
        if values:
            raw_values[field] = {"tag": tags[0], "values": values[-3:]}  # Keep last 3 for audit

    result["raw_json"] = raw_values
    return result


def parse_balance_sheet(
    facts: dict[str, Any], fiscal_year: int, quarter: int | None = None
) -> dict[str, Any]:
    """Parse balance sheet data for a specific period."""
    result = {"fiscal_year": fiscal_year, "fiscal_quarter": quarter}
    raw_values = {}

    for field, tags in BALANCE_SHEET_TAGS.items():
        values = _resolve_tag(facts, field, tags, "USD", fiscal_year - 1)
        if quarter:
            val = _pick_quarterly(values, fiscal_year, quarter)
        else:
            val = _pick_annual(values, fiscal_year)
        result[field] = val
        if values:
            raw_values[field] = {"tag": tags[0], "values": values[-3:]}

    result["raw_json"] = raw_values
    return result


def parse_cash_flow(
    facts: dict[str, Any], fiscal_year: int, quarter: int | None = None
) -> dict[str, Any]:
    """Parse cash flow statement data for a specific period."""
    result = {"fiscal_year": fiscal_year, "fiscal_quarter": quarter}
    raw_values = {}

    for field, tags in CASH_FLOW_TAGS.items():
        values = _resolve_tag(facts, field, tags, "USD", fiscal_year - 1)
        if quarter:
            val = _pick_quarterly(values, fiscal_year, quarter)
        else:
            val = _pick_annual(values, fiscal_year)
        result[field] = val
        if values:
            raw_values[field] = {"tag": tags[0], "values": values[-3:]}

    # Derived: Free Cash Flow = CFO - CapEx
    cfo = result.get("cash_from_operations")
    capex = result.get("capital_expenditure")
    if cfo is not None and capex is not None:
        # CapEx is reported as a positive number (payment) — FCF = CFO - CapEx
        result["free_cash_flow"] = cfo - abs(capex)

    result["raw_json"] = raw_values
    return result


def get_available_fiscal_years(facts: dict[str, Any], min_year: int = 2020) -> list[int]:
    """Determine which fiscal years have data, using revenue as the anchor."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    # Try revenue tags to find years
    for tag in INCOME_STATEMENT_TAGS["revenue"]:
        tag_data = us_gaap.get(tag, {})
        units = tag_data.get("units", {}).get("USD", [])
        if units:
            years = set()
            for item in units:
                fy = item.get("fy", 0)
                fp = item.get("fp", "")
                if fy >= min_year and fp == "FY":
                    years.add(fy)
            if years:
                return sorted(years)

    return []


def compute_metrics(
    income: dict, balance: dict, cash_flow: dict,
    prev_income: dict | None = None, prev_balance: dict | None = None,
) -> dict[str, float | None]:
    """Compute derived financial metrics from the three statements."""
    metrics: dict[str, float | None] = {}

    rev = income.get("revenue")
    oi = income.get("operating_income")
    ni = income.get("net_income")
    gp = income.get("gross_profit")
    fcf = cash_flow.get("free_cash_flow")
    ta = balance.get("total_assets")
    eq = balance.get("total_stockholders_equity")
    cl = balance.get("total_current_liabilities")
    ca = balance.get("total_current_assets")
    inv = balance.get("inventory")
    ltd = balance.get("long_term_debt") or 0
    std = balance.get("short_term_debt") or 0

    # Margins
    if rev and rev != 0:
        metrics["gross_margin"] = round(gp / rev, 4) if gp else None
        metrics["operating_margin"] = round(oi / rev, 4) if oi else None
        metrics["net_margin"] = round(ni / rev, 4) if ni else None
        metrics["fcf_margin"] = round(fcf / rev, 4) if fcf else None
    else:
        metrics["gross_margin"] = None
        metrics["operating_margin"] = None
        metrics["net_margin"] = None
        metrics["fcf_margin"] = None

    # Growth (YoY)
    if prev_income:
        prev_rev = prev_income.get("revenue")
        prev_oi = prev_income.get("operating_income")
        prev_ni = prev_income.get("net_income")
        prev_eps = prev_income.get("eps_diluted")

        metrics["revenue_growth"] = (
            round((rev - prev_rev) / abs(prev_rev), 4)
            if rev and prev_rev and prev_rev != 0 else None
        )
        metrics["operating_income_growth"] = (
            round((oi - prev_oi) / abs(prev_oi), 4)
            if oi and prev_oi and prev_oi != 0 else None
        )
        metrics["net_income_growth"] = (
            round((ni - prev_ni) / abs(prev_ni), 4)
            if ni and prev_ni and prev_ni != 0 else None
        )
        eps = income.get("eps_diluted")
        metrics["eps_growth"] = (
            round((float(eps) - float(prev_eps)) / abs(float(prev_eps)), 4)
            if eps and prev_eps and float(prev_eps) != 0 else None
        )
    else:
        metrics["revenue_growth"] = None
        metrics["operating_income_growth"] = None
        metrics["net_income_growth"] = None
        metrics["eps_growth"] = None

    # Returns
    if ni and eq and eq != 0:
        metrics["roe"] = round(ni / eq, 4)
    else:
        metrics["roe"] = None

    if ni and ta and ta != 0:
        metrics["roa"] = round(ni / ta, 4)
    else:
        metrics["roa"] = None

    # ROIC = NOPAT / Invested Capital
    # Simplified: NOPAT ≈ OI * (1 - tax_rate), IC ≈ Equity + Debt - Cash
    tax = income.get("income_tax")
    pretax = income.get("pretax_income")
    if oi and pretax and pretax != 0 and tax is not None:
        tax_rate = abs(tax) / abs(pretax) if pretax != 0 else 0.25
        nopat = oi * (1 - tax_rate)
        cash = balance.get("cash_and_equivalents") or 0
        invested_capital = (eq or 0) + ltd + std - cash
        metrics["roic"] = round(nopat / invested_capital, 4) if invested_capital != 0 else None
    else:
        metrics["roic"] = None

    # Leverage
    total_debt = ltd + std
    metrics["debt_to_equity"] = round(total_debt / eq, 4) if eq and eq != 0 else None
    metrics["current_ratio"] = round(ca / cl, 4) if ca and cl and cl != 0 else None
    metrics["quick_ratio"] = (
        round((ca - (inv or 0)) / cl, 4) if ca and cl and cl != 0 else None
    )

    return metrics
