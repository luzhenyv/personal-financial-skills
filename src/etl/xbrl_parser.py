"""XBRL Company Facts parser.

Parses the SEC XBRL companyfacts JSON into structured financial statement rows.
Maps XBRL US-GAAP taxonomy tags to our database schema fields.

Includes:
- Income statement, balance sheet, cash flow parsing
- Revenue segment extraction (product / geography)
- Derived metric computation (margins, growth, returns, efficiency, valuation)
"""

import logging
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
        "PaymentsToAcquireProductiveAssets",
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

# Revenue segment tags (product and geography breakdowns)
SEGMENT_REVENUE_TAGS: list[str] = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]

# Known segment dimension axes in XBRL
PRODUCT_SEGMENT_AXES = [
    "srt:ProductOrServiceAxis",
    "us-gaap:ProductOrServiceAxis",
    "us-gaap:StatementBusinessSegmentsAxis",
]

GEOGRAPHY_SEGMENT_AXES = [
    "srt:StatementGeographicalAxis",
    "us-gaap:StatementGeographicalAxis",
]

# Fields that use USD/shares units
EPS_FIELDS = {"eps_basic", "eps_diluted"}


# ──────────────────────────────────────────────
# Value Extraction Helpers
# ──────────────────────────────────────────────

def _extract_fact_values(
    facts: dict[str, Any],
    tag: str,
    unit_key: str = "USD",
    min_year: int = 2020,
) -> list[dict]:
    """Extract values for a single XBRL tag, filtered to recent fiscal years."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    tag_data = us_gaap.get(tag, {})
    if not tag_data:
        return []

    units = tag_data.get("units", {})
    values = units.get(unit_key, [])
    if not values:
        for alt_key in ["USD/shares", "shares", "pure"]:
            if alt_key in units:
                values = units[alt_key]
                break

    result = []
    for item in values:
        fy = item.get("fy") or 0
        if fy < min_year:
            continue

        result.append({
            "fy": fy,
            "fp": item.get("fp", ""),
            "val": item.get("val"),
            "end": item.get("end", ""),
            "filed": item.get("filed", ""),
            "form": item.get("form", ""),
        })

    return result


def _resolve_tag_for_year(
    facts: dict,
    field_name: str,
    tag_candidates: list[str],
    unit_key: str,
    min_year: int,
    fiscal_year: int,
    quarter: int | None = None,
) -> tuple[list[dict], Any]:
    """Try each candidate tag until we find data for the specific target year.

    Falls through to the next tag if no value is found for the target period.
    """
    picker = _pick_quarterly if quarter else _pick_annual
    pick_args = (fiscal_year, quarter) if quarter else (fiscal_year,)

    for tag in tag_candidates:
        values = _extract_fact_values(facts, tag, unit_key, min_year)
        if not values:
            continue
        val = picker(values, *pick_args)
        if val is not None:
            logger.debug(f"  {field_name} → {tag} = {val} (FY{fiscal_year})")
            return values, val

    logger.debug(
        f"  {field_name} → NO DATA for FY{fiscal_year} (tried {len(tag_candidates)} tags)"
    )
    return [], None


def _pick_annual(values: list[dict], fiscal_year: int) -> int | float | None:
    """Pick the best annual value for a fiscal year.

    Prefer: form='10-K', fp='FY', latest period end date, most recent filing.
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

    # Pick the latest period end date (current year's data, not prior-year comparisons)
    candidates.sort(key=lambda x: (x.get("end", ""), x.get("filed", "")), reverse=True)
    return candidates[0]["val"]


def _pick_quarterly(values: list[dict], fiscal_year: int, quarter: int) -> int | float | None:
    """Pick the best quarterly value."""
    fp_str = f"Q{quarter}"
    candidates = [v for v in values if v["fy"] == fiscal_year and v["fp"] == fp_str]
    if not candidates:
        return None

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
    result = {"fiscal_year": fiscal_year, "fiscal_quarter": quarter}
    raw_values = {}

    for field, tags in INCOME_STATEMENT_TAGS.items():
        unit = "USD/shares" if field in EPS_FIELDS else "USD"
        if field in ("shares_basic", "shares_diluted"):
            unit = "shares"

        values, val = _resolve_tag_for_year(
            facts, field, tags, unit, fiscal_year - 1, fiscal_year, quarter
        )

        result[field] = val
        if values:
            raw_values[field] = {"tag": tags[0], "values": values[-3:]}

    result["raw_json"] = raw_values
    return result


def parse_balance_sheet(
    facts: dict[str, Any], fiscal_year: int, quarter: int | None = None
) -> dict[str, Any]:
    """Parse balance sheet data for a specific period."""
    result = {"fiscal_year": fiscal_year, "fiscal_quarter": quarter}
    raw_values = {}

    for field, tags in BALANCE_SHEET_TAGS.items():
        values, val = _resolve_tag_for_year(
            facts, field, tags, "USD", fiscal_year - 1, fiscal_year, quarter
        )
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
        values, val = _resolve_tag_for_year(
            facts, field, tags, "USD", fiscal_year - 1, fiscal_year, quarter
        )
        result[field] = val
        if values:
            raw_values[field] = {"tag": tags[0], "values": values[-3:]}

    # Derived: Free Cash Flow = CFO - CapEx
    cfo = result.get("cash_from_operations")
    capex = result.get("capital_expenditure")
    if cfo is not None and capex is not None:
        result["free_cash_flow"] = cfo - abs(capex)

    result["raw_json"] = raw_values
    return result


def get_available_fiscal_years(facts: dict[str, Any], min_year: int = 2020) -> list[int]:
    """Determine which fiscal years have data, using revenue as the anchor.

    Checks ALL revenue tag candidates and merges available years,
    since companies may switch XBRL tags across different fiscal years.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    all_years: set[int] = set()

    for tag in INCOME_STATEMENT_TAGS["revenue"]:
        tag_data = us_gaap.get(tag, {})
        units = tag_data.get("units", {}).get("USD", [])
        for item in units:
            fy = item.get("fy")
            fp = item.get("fp", "")
            if fy is not None and fy >= min_year and fp == "FY":
                all_years.add(fy)

    return sorted(all_years)


# ──────────────────────────────────────────────
# Revenue Segment Parsing
# ──────────────────────────────────────────────

def parse_revenue_segments(
    facts: dict[str, Any], fiscal_year: int, quarter: int | None = None
) -> list[dict[str, Any]]:
    """Parse revenue segment breakdowns (product and geography) from XBRL facts.

    Returns a list of dicts: {segment_type, segment_name, revenue, pct_of_total}

    Segment data in XBRL is encoded via dimensional qualifiers on revenue tags.
    Not all companies report segment data through XBRL; many only include it
    in the 10-K HTML narrative (Item 7 MD&A).
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    segments: list[dict[str, Any]] = []

    # Look for segment-qualified revenue data
    for tag in SEGMENT_REVENUE_TAGS:
        tag_data = us_gaap.get(tag, {})
        if not tag_data:
            continue

        # Check for dimensional data (segments appear as separate sub-entries)
        units = tag_data.get("units", {}).get("USD", [])
        segment_values: dict[str, int | float] = {}

        for item in units:
            fy = item.get("fy", 0)
            fp = item.get("fp", "")
            form = item.get("form", "")

            # Match the target period
            if quarter:
                if fy != fiscal_year or fp != f"Q{quarter}":
                    continue
            else:
                if fy != fiscal_year or fp != "FY":
                    continue

            # Items with segment dimension info have a "frame" or are
            # structured differently. In practice, the SEC companyfacts
            # endpoint flattens segment data into the same arrays.
            # We look for entries that have a segment member in their accn.
            val = item.get("val")
            if val is not None:
                # The base (unsegmented) entry typically has the largest value
                # or is the only one with form="10-K"
                end = item.get("end", "")
                key = f"{end}_{form}"
                if key not in segment_values:
                    segment_values[key] = val

        # If we found data under this tag, we got the aggregate; break
        if segment_values:
            break

    # Try to find explicit segment reporting tags
    segment_specific_tags = [
        "RevenueFromExternalCustomersByGeographicAreasTableTextBlock",
        "ScheduleOfRevenueByMajorCustomersByReportingSegmentsTableTextBlock",
    ]

    # Look for product/service segment revenue in explicitly segmented tags
    product_segments = _extract_segment_dimension(
        facts, fiscal_year, quarter, "product"
    )
    geo_segments = _extract_segment_dimension(
        facts, fiscal_year, quarter, "geography"
    )

    segments.extend(product_segments)
    segments.extend(geo_segments)

    # Compute pct_of_total if we have segment data
    total_rev = sum(s["revenue"] for s in segments if s["revenue"]) or None
    if total_rev:
        for s in segments:
            if s["revenue"]:
                s["pct_of_total"] = round(s["revenue"] / total_rev, 4)

    return segments


def _extract_segment_dimension(
    facts: dict[str, Any],
    fiscal_year: int,
    quarter: int | None,
    segment_type: str,
) -> list[dict[str, Any]]:
    """Extract segment data from XBRL facts using dimension axes.

    This handles the case where segment data is reported as separate XBRL
    facts with segment dimension qualifiers. The SEC companyfacts endpoint
    may not always include these; they're more reliably found in XBRL
    instance documents.
    """
    # For companyfacts JSON, segment data is not reliably separated.
    # Return empty — the skill script extracts segments from 10-K HTML (MD&A) instead.
    # This is a placeholder for future XBRL instance document parsing.
    return []


# ──────────────────────────────────────────────
# Derived Metrics Computation
# ──────────────────────────────────────────────

def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Safe division returning None if either value is None or denominator is zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def compute_metrics(
    income: dict,
    balance: dict,
    cash_flow: dict,
    prev_income: dict | None = None,
    prev_balance: dict | None = None,
    market_data: dict | None = None,
) -> dict[str, float | None]:
    """Compute derived financial metrics from the three statements.

    Args:
        income: Parsed income statement dict
        balance: Parsed balance sheet dict
        cash_flow: Parsed cash flow dict
        prev_income: Prior year income statement (for growth calcs)
        prev_balance: Prior year balance sheet (unused currently, reserved)
        market_data: Optional dict with 'price', 'market_cap', 'shares_outstanding'
                     for computing valuation metrics (PE, PS, PB, EV/EBITDA, FCF yield)
    """
    metrics: dict[str, float | None] = {}

    rev = income.get("revenue")
    oi = income.get("operating_income")
    ni = income.get("net_income")
    gp = income.get("gross_profit")
    cogs = income.get("cost_of_revenue")
    fcf = cash_flow.get("free_cash_flow")
    da = cash_flow.get("depreciation_amortization")
    ta = balance.get("total_assets")
    eq = balance.get("total_stockholders_equity")
    cl = balance.get("total_current_liabilities")
    ca = balance.get("total_current_assets")
    inv = balance.get("inventory")
    ar = balance.get("accounts_receivable")
    ap = balance.get("accounts_payable")
    ltd = balance.get("long_term_debt") or 0
    std = balance.get("short_term_debt") or 0
    cash = balance.get("cash_and_equivalents") or 0

    # ── EBITDA ──
    ebitda = None
    if oi is not None and da is not None:
        ebitda = oi + abs(da)
    metrics["ebitda"] = ebitda

    # ── Margins ──
    metrics["gross_margin"] = round(_safe_div(gp, rev), 4) if _safe_div(gp, rev) is not None else None
    metrics["operating_margin"] = round(_safe_div(oi, rev), 4) if _safe_div(oi, rev) is not None else None
    metrics["ebitda_margin"] = round(_safe_div(ebitda, rev), 4) if _safe_div(ebitda, rev) is not None else None
    metrics["net_margin"] = round(_safe_div(ni, rev), 4) if _safe_div(ni, rev) is not None else None
    metrics["fcf_margin"] = round(_safe_div(fcf, rev), 4) if _safe_div(fcf, rev) is not None else None

    # ── Growth (YoY) ──
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

    # ── Returns ──
    metrics["roe"] = round(_safe_div(ni, eq), 4) if _safe_div(ni, eq) is not None else None
    metrics["roa"] = round(_safe_div(ni, ta), 4) if _safe_div(ni, ta) is not None else None

    # ROIC = NOPAT / Invested Capital
    tax = income.get("income_tax")
    pretax = income.get("pretax_income")
    if oi and pretax and pretax != 0 and tax is not None:
        tax_rate = abs(tax) / abs(pretax) if pretax != 0 else 0.25
        nopat = oi * (1 - tax_rate)
        invested_capital = (eq or 0) + ltd + std - cash
        metrics["roic"] = (
            round(nopat / invested_capital, 4) if invested_capital != 0 else None
        )
    else:
        metrics["roic"] = None

    # ── Leverage ──
    total_debt = ltd + std
    metrics["debt_to_equity"] = (
        round(total_debt / eq, 4) if eq and eq != 0 else None
    )
    metrics["current_ratio"] = (
        round(ca / cl, 4) if ca and cl and cl != 0 else None
    )
    metrics["quick_ratio"] = (
        round((ca - (inv or 0)) / cl, 4) if ca and cl and cl != 0 else None
    )

    # ── Efficiency (working capital) ──
    # DSO = (Accounts Receivable / Revenue) × 365
    metrics["dso"] = (
        round(ar / rev * 365, 2) if ar and rev and rev != 0 else None
    )

    # DIO = (Inventory / COGS) × 365
    metrics["dio"] = (
        round(inv / cogs * 365, 2)
        if inv and cogs and cogs != 0 else None
    )

    # DPO = (Accounts Payable / COGS) × 365
    metrics["dpo"] = (
        round(ap / cogs * 365, 2)
        if ap and cogs and cogs != 0 else None
    )

    # ── Valuation (requires market data) ──
    if market_data:
        price = market_data.get("price")
        mkt_cap = market_data.get("market_cap")
        shares = market_data.get("shares_outstanding")

        eps_diluted = income.get("eps_diluted")

        # PE ratio
        metrics["pe_ratio"] = (
            round(float(price) / float(eps_diluted), 2)
            if price and eps_diluted and float(eps_diluted) != 0 else None
        )

        # PS ratio
        metrics["ps_ratio"] = (
            round(mkt_cap / rev, 2)
            if mkt_cap and rev and rev != 0 else None
        )

        # PB ratio
        metrics["pb_ratio"] = (
            round(mkt_cap / eq, 2)
            if mkt_cap and eq and eq != 0 else None
        )

        # EV/EBITDA
        if mkt_cap and ebitda and ebitda != 0:
            ev = mkt_cap + total_debt - cash
            metrics["ev_to_ebitda"] = round(ev / ebitda, 2)
        else:
            metrics["ev_to_ebitda"] = None

        # FCF yield
        metrics["fcf_yield"] = (
            round(fcf / mkt_cap, 4)
            if fcf and mkt_cap and mkt_cap != 0 else None
        )
    else:
        metrics["pe_ratio"] = None
        metrics["ps_ratio"] = None
        metrics["pb_ratio"] = None
        metrics["ev_to_ebitda"] = None
        metrics["fcf_yield"] = None

    return metrics
