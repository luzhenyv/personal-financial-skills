# Field Definitions

Every column in the three financial statement tables, its meaning, and the
primary XBRL US-GAAP concepts that feed it.

## Income Statement (`income_statements`)

| Field | Description | Primary XBRL Tags |
|---|---|---|
| `revenue` | Total net revenue / sales | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues` |
| `cost_of_revenue` | Direct cost of goods/services sold | `CostOfRevenue`, `CostOfGoodsAndServicesSold` |
| `gross_profit` | Revenue minus COGS (derived if missing) | `GrossProfit` |
| `research_and_development` | R&D expense | `ResearchAndDevelopmentExpense` |
| `selling_general_admin` | SG&A expense | `SellingGeneralAndAdministrativeExpense` |
| `depreciation_amortization` | D&A on income statement | `DepreciationDepletionAndAmortization` |
| `operating_expenses` | Total opex (derived: GP − OI if missing) | `OperatingExpenses`, `CostsAndExpenses` |
| `operating_income` | EBIT / operating profit | `OperatingIncomeLoss` |
| `interest_expense` | Interest paid on debt | `InterestExpense`, `InterestExpenseDebt` |
| `interest_income` | Interest/investment income | `InterestIncome`, `InvestmentIncomeInterest` |
| `other_income` | Non-operating income/expense | `OtherNonoperatingIncomeExpense` |
| `pretax_income` | Income before tax | `IncomeLossFromContinuingOperationsBeforeIncomeTaxes…` |
| `income_tax` | Tax provision | `IncomeTaxExpenseBenefit` |
| `net_income` | Bottom-line profit | `NetIncomeLoss`, `ProfitLoss` |
| `eps_basic` | Basic earnings per share | `EarningsPerShareBasic` |
| `eps_diluted` | Diluted earnings per share | `EarningsPerShareDiluted` |
| `shares_basic` | Weighted avg shares basic | `WeightedAverageNumberOfSharesOutstandingBasic` |
| `shares_diluted` | Weighted avg shares diluted | `WeightedAverageNumberOfDilutedSharesOutstanding` |

## Balance Sheet (`balance_sheets`)

| Field | Description | Primary XBRL Tags |
|---|---|---|
| `cash_and_equivalents` | Cash + cash equivalents | `CashAndCashEquivalentsAtCarryingValue` |
| `short_term_investments` | Marketable securities (current) | `ShortTermInvestments`, `MarketableSecuritiesCurrent` |
| `accounts_receivable` | Net A/R | `AccountsReceivableNetCurrent` |
| `inventory` | Inventory | `InventoryNet` |
| `total_current_assets` | Total current assets | `AssetsCurrent` |
| `property_plant_equipment` | PP&E net of depreciation | `PropertyPlantAndEquipmentNet` |
| `goodwill` | Goodwill | `Goodwill` |
| `intangible_assets` | Intangibles ex-goodwill | `IntangibleAssetsNetExcludingGoodwill` |
| `total_assets` | Total assets | `Assets` |
| `accounts_payable` | Trade payables | `AccountsPayableCurrent` |
| `deferred_revenue` | Deferred/unearned revenue | `DeferredRevenueCurrent`, `ContractWithCustomerLiabilityCurrent` |
| `short_term_debt` | Current portion of debt | `ShortTermBorrowings`, `DebtCurrent`, `LongTermDebtCurrent` |
| `total_current_liabilities` | Total current liabilities | `LiabilitiesCurrent` |
| `long_term_debt` | Non-current debt | `LongTermDebtNoncurrent`, `LongTermDebt` |
| `total_liabilities` | Total liabilities (derived: TA − Equity if missing) | `Liabilities` |
| `common_stock` | Common stock + APIC | `CommonStockValue`, `CommonStocksIncludingAdditionalPaidInCapital` |
| `retained_earnings` | Retained earnings / accumulated deficit | `RetainedEarningsAccumulatedDeficit` |
| `total_stockholders_equity` | Total equity | `StockholdersEquity` |

## Cash Flow Statement (`cash_flow_statements`)

| Field | Description | Primary XBRL Tags |
|---|---|---|
| `net_income` | Net income (starting point) | `NetIncomeLoss`, `ProfitLoss` |
| `depreciation_amortization` | D&A add-back | `DepreciationDepletionAndAmortization` |
| `stock_based_compensation` | SBC add-back | `ShareBasedCompensation` |
| `change_in_working_capital` | Net working capital change | `IncreaseDecreaseInOperatingCapital` |
| `cash_from_operations` | CFO | `NetCashProvidedByUsedInOperatingActivities` |
| `capital_expenditure` | CapEx (negative = outflow) | `PaymentsToAcquirePropertyPlantAndEquipment` |
| `acquisitions` | M&A payments | `PaymentsToAcquireBusinessesNetOfCashAcquired` |
| `purchases_of_investments` | Investment purchases | `PaymentsToAcquireInvestments` |
| `sales_of_investments` | Investment proceeds | `ProceedsFromSaleAndMaturityOfMarketableSecurities` |
| `cash_from_investing` | CFI | `NetCashProvidedByUsedInInvestingActivities` |
| `debt_issuance` | Debt issued | `ProceedsFromIssuanceOfLongTermDebt` |
| `debt_repayment` | Debt repaid | `RepaymentsOfLongTermDebt` |
| `share_repurchase` | Buybacks | `PaymentsForRepurchaseOfCommonStock` |
| `dividends_paid` | Dividends | `PaymentsOfDividendsCommonStock` |
| `cash_from_financing` | CFF | `NetCashProvidedByUsedInFinancingActivities` |
| `net_change_in_cash` | Net change in cash position | `CashCashEquivalentsRestrictedCash…PeriodIncreaseDecrease…` |
| `free_cash_flow` | FCF = CFO − |CapEx| (always derived) | *(computed, not from XBRL)* |
