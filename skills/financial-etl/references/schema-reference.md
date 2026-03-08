# XBRL Tag → Database Schema Reference

Complete mapping of XBRL US-GAAP tags to our PostgreSQL schema fields.

Tags are listed in priority order — the parser tries each until it finds data.

## Income Statement (`income_statements`)

| DB Column | XBRL Tags (priority order) | Unit |
|-----------|---------------------------|------|
| `revenue` | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `RevenueFromContractWithCustomerIncludingAssessedTax`, `SalesRevenueNet`, `SalesRevenueGoodsNet` | USD |
| `cost_of_revenue` | `CostOfRevenue`, `CostOfGoodsAndServicesSold`, `CostOfGoodsSold` | USD |
| `gross_profit` | `GrossProfit` | USD |
| `research_and_development` | `ResearchAndDevelopmentExpense`, `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` | USD |
| `selling_general_admin` | `SellingGeneralAndAdministrativeExpense`, `GeneralAndAdministrativeExpense` | USD |
| `operating_expenses` | `OperatingExpenses`, `CostsAndExpenses` | USD |
| `operating_income` | `OperatingIncomeLoss` | USD |
| `interest_expense` | `InterestExpense`, `InterestExpenseDebt` | USD |
| `interest_income` | `InterestIncome`, `InvestmentIncomeInterest` | USD |
| `other_income` | `OtherNonoperatingIncomeExpense`, `NonoperatingIncomeExpense` | USD |
| `pretax_income` | `IncomeLossFromContinuingOperationsBeforeIncomeTaxes...` | USD |
| `income_tax` | `IncomeTaxExpenseBenefit` | USD |
| `net_income` | `NetIncomeLoss`, `ProfitLoss`, `NetIncomeLossAvailableToCommonStockholdersBasic` | USD |
| `eps_basic` | `EarningsPerShareBasic` | USD/shares |
| `eps_diluted` | `EarningsPerShareDiluted` | USD/shares |
| `shares_basic` | `WeightedAverageNumberOfSharesOutstandingBasic`, `CommonStockSharesOutstanding` | shares |
| `shares_diluted` | `WeightedAverageNumberOfDilutedSharesOutstanding` | shares |

## Balance Sheet (`balance_sheets`)

| DB Column | XBRL Tags (priority order) | Unit |
|-----------|---------------------------|------|
| `cash_and_equivalents` | `CashAndCashEquivalentsAtCarryingValue`, `Cash` | USD |
| `short_term_investments` | `ShortTermInvestments`, `MarketableSecuritiesCurrent` | USD |
| `accounts_receivable` | `AccountsReceivableNetCurrent`, `AccountsReceivableNet` | USD |
| `inventory` | `InventoryNet`, `InventoryFinishedGoodsAndWorkInProcess` | USD |
| `total_current_assets` | `AssetsCurrent` | USD |
| `property_plant_equipment` | `PropertyPlantAndEquipmentNet` | USD |
| `goodwill` | `Goodwill` | USD |
| `intangible_assets` | `IntangibleAssetsNetExcludingGoodwill`, `FiniteLivedIntangibleAssetsNet` | USD |
| `total_assets` | `Assets` | USD |
| `accounts_payable` | `AccountsPayableCurrent`, `AccountsPayableAndAccruedLiabilitiesCurrent` | USD |
| `short_term_debt` | `ShortTermBorrowings`, `DebtCurrent`, `LongTermDebtCurrent` | USD |
| `total_current_liabilities` | `LiabilitiesCurrent` | USD |
| `long_term_debt` | `LongTermDebtNoncurrent`, `LongTermDebt` | USD |
| `total_liabilities` | `Liabilities` | USD |
| `common_stock` | `CommonStockValue`, `CommonStocksIncludingAdditionalPaidInCapital` | USD |
| `retained_earnings` | `RetainedEarningsAccumulatedDeficit` | USD |
| `total_stockholders_equity` | `StockholdersEquity`, `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` | USD |

## Cash Flow Statement (`cash_flow_statements`)

| DB Column | XBRL Tags (priority order) | Unit |
|-----------|---------------------------|------|
| `net_income` | `NetIncomeLoss`, `ProfitLoss` | USD |
| `depreciation_amortization` | `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization` | USD |
| `stock_based_compensation` | `ShareBasedCompensation`, `AllocatedShareBasedCompensationExpense` | USD |
| `change_in_working_capital` | `IncreaseDecreaseInOperatingCapital`, `IncreaseDecreaseInOperatingLiabilities` | USD |
| `cash_from_operations` | `NetCashProvidedByUsedInOperatingActivities` | USD |
| `capital_expenditure` | `PaymentsToAcquirePropertyPlantAndEquipment` | USD |
| `acquisitions` | `PaymentsToAcquireBusinessesNetOfCashAcquired` | USD |
| `purchases_of_investments` | `PaymentsToAcquireInvestments` | USD |
| `sales_of_investments` | `ProceedsFromSaleAndMaturityOfMarketableSecurities` | USD |
| `cash_from_investing` | `NetCashProvidedByUsedInInvestingActivities` | USD |
| `debt_issuance` | `ProceedsFromIssuanceOfLongTermDebt` | USD |
| `debt_repayment` | `RepaymentsOfLongTermDebt`, `RepaymentsOfDebt` | USD |
| `share_repurchase` | `PaymentsForRepurchaseOfCommonStock` | USD |
| `dividends_paid` | `PaymentsOfDividendsCommonStock`, `PaymentsOfDividends` | USD |
| `cash_from_financing` | `NetCashProvidedByUsedInFinancingActivities` | USD |
| `net_change_in_cash` | `CashCashEquivalentsRestrictedCash...PeriodIncreaseDecrease...` | USD |
| `free_cash_flow` | **Calculated**: `cash_from_operations - abs(capital_expenditure)` | USD |

## Derived Metrics (`financial_metrics`)

| DB Column | Formula |
|-----------|---------|
| `gross_margin` | `gross_profit / revenue` |
| `operating_margin` | `operating_income / revenue` |
| `net_margin` | `net_income / revenue` |
| `fcf_margin` | `free_cash_flow / revenue` |
| `revenue_growth` | `(revenue_t - revenue_t-1) / abs(revenue_t-1)` |
| `roe` | `net_income / stockholders_equity` |
| `roa` | `net_income / total_assets` |
| `roic` | `NOPAT / invested_capital` |
| `debt_to_equity` | `(short_term_debt + long_term_debt) / stockholders_equity` |
| `current_ratio` | `total_current_assets / total_current_liabilities` |
| `quick_ratio` | `(total_current_assets - inventory) / total_current_liabilities` |
