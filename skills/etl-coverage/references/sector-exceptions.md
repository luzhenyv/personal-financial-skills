# Sector Exceptions

Fields that are **legitimately NULL** for companies in certain sectors.
These are classified as `"optional"` in the coverage report and should **not**
be treated as parser bugs.

## Technology / SaaS

| Field | Reason |
|---|---|
| `inventory` | Pure software companies carry no physical inventory |
| `cost_of_revenue` | Some tech companies report `CostsAndExpenses` instead |

## Financial Services / Financials (Banks, Insurance, Asset Managers)

| Field | Reason |
|---|---|
| `cost_of_revenue` | Banks use interest expense as "cost"; no COGS concept |
| `gross_profit` | Not meaningful for financial institutions |
| `inventory` | Banks don't hold inventory |
| `accounts_receivable` | Banks use loans/securities instead of trade receivables |
| `accounts_payable` | Banks use deposits/borrowings instead of trade payables |
| `capital_expenditure` | Minimal for asset-light financial firms |
| `depreciation_amortization` | Minimal; often rolled into non-interest expense |

## Real Estate / REITs

| Field | Reason |
|---|---|
| `inventory` | REITs hold real estate assets, not inventory |
| `research_and_development` | REITs typically have zero R&D spend |

## Always Optional (any sector)

These fields are frequently absent because many companies either don't report
them as separate line items or they are zero:

- `acquisitions` — only present in years with M&A activity
- `purchases_of_investments` / `sales_of_investments` — not all companies trade securities
- `debt_issuance` / `debt_repayment` — absent if no debt transactions occurred
- `short_term_investments` — many companies hold none
- `deferred_revenue` — not all business models generate deferred revenue
- `intangible_assets` / `goodwill` — absent for organic-growth companies
- `other_income` / `interest_income` — immaterial for many companies
- `depreciation_amortization` (income stmt) — often not reported as separate line item
- `short_term_debt` — many companies have none
- `share_repurchase` / `dividends_paid` — not all companies return capital
- `change_in_working_capital` — many companies report individual WC components instead
