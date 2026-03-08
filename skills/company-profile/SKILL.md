# Company Profile / Tearsheet

## Skill Metadata
- **Name**: company-profile
- **Description**: Generate a concise 1-page markdown tearsheet for a US public company
- **Trigger**: User asks for company overview, tearsheet, profile, or "tell me about {ticker}"
- **Prerequisites**: Company data must exist in PostgreSQL (run `financial-etl` skill first if not)
- **Output**: Markdown tearsheet saved to `data/reports/{ticker}/tearsheet.md` and `analysis_reports` table

## Origin
Adapted from `equity-research/skills/initiating-coverage/` in [financial-services-plugins](https://github.com/anthropics/financial-services-plugins).

| Original (Institutional) | This Skill (Personal) |
|--------------------------|----------------------|
| 6,000–8,000 word research report | 1-page markdown tearsheet |
| 30–50 page Word document | Single `.md` file |
| 20–30 Excel charts | Key metrics table + "see Streamlit" |
| 5 separate tasks | 1 streamlined workflow |
| Bloomberg/CapIQ data | SEC EDGAR + PostgreSQL |

## When to Use
- First look at a new stock you're considering
- Quick reference before an earnings call
- Adding a company to your watchlist
- Comparing companies side by side

## Workflow

### Step 0: Ensure Data Exists
Check if the company has financial data in PostgreSQL:
```sql
SELECT COUNT(*) FROM income_statements WHERE ticker = '{ticker}';
```
If count = 0, **first run the `financial-etl` skill** to ingest data:
```python
from src.etl.pipeline import ingest_company
result = ingest_company("{ticker}")
```

### Step 1: Query Company Info
```sql
SELECT * FROM companies WHERE ticker = '{ticker}';
```

### Step 2: Query Latest Financials
```sql
-- Most recent annual income statement
SELECT * FROM income_statements
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;

-- Most recent balance sheet
SELECT * FROM balance_sheets
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;

-- Most recent cash flow statement
SELECT * FROM cash_flow_statements
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;

-- Computed metrics
SELECT * FROM financial_metrics
WHERE ticker = '{ticker}' AND fiscal_quarter IS NULL
ORDER BY fiscal_year DESC LIMIT 5;
```

### Step 3: Query Latest Price
```sql
SELECT * FROM daily_prices
WHERE ticker = '{ticker}'
ORDER BY date DESC LIMIT 1;
```

### Step 4: Fill Template
Use the template in `references/tearsheet-template.md`.

Key formatting rules:
- All dollar amounts in billions (divide by 1,000,000,000) for revenue/assets, millions for smaller items
- Percentages to 1 decimal place
- Growth rates with + or - prefix and arrow: `+25.3%↑` or `-4.1%↓`
- Use `N/A` for missing data, never leave blank

### Step 5: Generate Investment Context
Based on the financial data, add:
- **Business Summary**: 2-3 sentences describing what the company does (from SEC description or agent knowledge)
- **Investment Thesis**: 3-5 bullet points (bull case)
- **Key Risks**: 3-5 bullet points (bear case)
- **Catalysts**: Upcoming events that could move the stock

### Step 6: Save Report
1. Write markdown to `data/reports/{ticker}/tearsheet.md`
2. Upsert to `analysis_reports` table:
```sql
INSERT INTO analysis_reports (ticker, report_type, title, content_md, generated_by, file_path)
VALUES ('{ticker}', 'tearsheet', '{name} Tearsheet', '{content}', '{agent_name}', '{path}')
ON CONFLICT (ticker, report_type) DO UPDATE SET content_md = EXCLUDED.content_md;
```

## Python API
You can also generate the profile programmatically:
```python
from src.analysis.company_profile import generate_tearsheet

# Returns markdown string and saves to DB + file
markdown = generate_tearsheet("NVDA")
```

## Quality Checks
- [ ] All metric rows have values (not all N/A)
- [ ] Revenue figures are in correct magnitude (billions vs millions)
- [ ] Growth rates match: (current - prior) / prior
- [ ] Margins are between -100% and +100% (sanity check)
- [ ] At least 3 years of historical data shown
- [ ] File saved to both filesystem and database

## Reference Files
- `references/tearsheet-template.md` — Markdown template to fill
- `references/data-sources.md` — Where each data point comes from
