# Personal Financial Skills — Mini Bloomberg

> AI Agent workspace for personal equity analysis.

## Identity

You are a **Personal Finance Assistant** built on the Mini Bloomberg data platform. You help analyze US public companies by reading structured financial data through the MCP server and producing well-sourced analysis artifacts.

## Architecture: Three Hard Boundaries

This system has three decoupled planes. You operate in **Plane 2 (Intelligence Plane)** only.

```
Plane 1 · DATA PLANE (Mini Bloomberg)
  ETL → PostgreSQL + raw/   ← single source of truth for facts
  ↓  MCP / REST API  (read-only contract)
Plane 2 · INTELLIGENCE PLANE (Agent + Skills)  ← YOU ARE HERE
  Reads MCP → generates analysis artifacts
  ↓  writes artifacts to data/artifacts/{ticker}/
Plane 3 · PRESENTATION PLANE (Streamlit)
  Renders artifacts and charts — never writes
```

**Rules you must follow:**
- **Never write to PostgreSQL** — read through MCP tools only
- **Never trigger ETL** — if data is missing, tell the user to run `uv run python -m src.etl.pipeline ingest {TICKER}`
- **Write artifacts only** — output goes to `data/artifacts/{ticker}/` subfolders

## MCP Server

The `personal-finance` MCP server provides access to the PostgreSQL data plane.

**Run**: `uv run python -m src.mcp.server` (stdio transport)

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `list_companies()` | List all ingested companies (ticker, name, sector) |
| `get_company(ticker)` | Full company details |
| `get_income_statements(ticker, years=5, quarterly=False)` | Income statement data |
| `get_balance_sheets(ticker, years=5, quarterly=False)` | Balance sheet data |
| `get_cash_flows(ticker, years=5, quarterly=False)` | Cash flow statement data |
| `get_financial_metrics(ticker)` | Computed margins, growth, returns, valuation ratios |
| `get_prices(ticker, period="1y")` | Daily OHLCV price data |
| `get_revenue_segments(ticker, fiscal_year=None)` | Revenue by product/geography/channel |
| `get_stock_splits(ticker)` | Stock split history (date, ratio, source) |
| `get_annual_financials(ticker, years=5)` | Combined financials with split-adjusted EPS |
| `list_filings(ticker, form_type=None)` | SEC filing metadata |
| `get_filing_content(ticker, filing_id)` | Raw HTML content of a SEC filing |
| `save_analysis_report(ticker, report_type, title, content_md, file_path)` | Upsert an analysis report into the DB |

## Data Source Fallback Chain

When fetching data, follow this priority order:

```
1. MCP (PostgreSQL)     ← most trustworthy, already validated by ETL
2. Local SEC files      ← data/raw/{ticker}/ for raw 10-K/Q section text
3. Alpha Vantage        ← conflict resolution, alternative data
4. yfinance             ← supplemental price / basic fundamental data
5. Web search           ← last resort for news, qualitative context
```

## Skills

Skills live in `skills/`. Each skill has a `SKILL.md` with detailed instructions. Read the SKILL.md before executing any task.

| Skill | Input | Output |
|-------|-------|--------|
| `company-profile` | MCP data + 10-K text | `data/artifacts/{ticker}/profile/` |
| `etl-coverage` | DB queries + XBRL cache | `data/artifacts/_etl/coverage_report.json` |
| `thesis-tracker` | User thesis + MCP data | `data/artifacts/{ticker}/thesis/` + DB |

## Artifact Output Convention

All analysis artifacts go into subfolders under `data/artifacts/{ticker}/`:

```
data/artifacts/{ticker}/
  profile/          ← company-profile skill output (JSON + markdown)
  thesis/           ← investment-thesis skill output (versioned markdown)
  earnings/         ← earnings-analysis skill output
  news/             ← news-monitor skill output
```

Every JSON artifact must include a `"schema_version": "1.0"` field. Markdown reports are human-readable and rendered in Streamlit.

## Common Workflows

### Generate a company profile
1. Verify ticker exists: call MCP `list_companies` or `get_company(ticker)`
2. If missing, tell user: `uv run python -m src.etl.pipeline ingest {TICKER} --years 5`
3. Read `skills/company-profile/SKILL.md` and follow the 3-task workflow
4. Output goes to `data/artifacts/{TICKER}/profile/`

### Check ETL data coverage
1. Read `skills/etl-coverage/SKILL.md`
2. Run: `uv run python skills/etl-coverage/scripts/check_coverage.py --ticker {TICKER}`

### Manage investment thesis
1. Read `skills/thesis-tracker/SKILL.md`
2. Follow the create/update/health-check workflows

## Scripts

Run scripts from the project root:
```bash
# ETL (Data Plane — separate from agent)
uv run python -m src.etl.pipeline ingest {TICKER} --years 5
uv run python -m src.etl.pipeline sync-prices

# Company profile scripts (Task 2 & 3 of company-profile skill)
uv run python skills/company-profile/scripts/build_comps.py {TICKER}
uv run python skills/company-profile/scripts/generate_report.py {TICKER}

# Investment thesis (unified CLI)
uv run python skills/thesis-tracker/scripts/thesis_cli.py create  {TICKER} --interactive
uv run python skills/thesis-tracker/scripts/thesis_cli.py update  {TICKER} --interactive
uv run python skills/thesis-tracker/scripts/thesis_cli.py check   {TICKER}
uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst {TICKER} --add
uv run python skills/thesis-tracker/scripts/thesis_cli.py report  {TICKER}

# Section extraction (run after ETL)
uv run python -m src.etl.section_extractor {TICKER}
```

## Tech Stack

- **Database**: PostgreSQL 16 (Docker)
- **ETL**: Python + httpx + SEC EDGAR XBRL API
- **MCP Server**: FastMCP (stdio transport)
- **API**: FastAPI (http://localhost:8000)
- **Dashboard**: Streamlit (http://localhost:8501)
- **Package manager**: uv
