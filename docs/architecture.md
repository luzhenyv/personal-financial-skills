# System Architecture

This document describes the full design of the Mini Bloomberg personal financial system — how the three planes are structured, why they are decoupled the way they are, and the rules that keep the system maintainable as it grows.

---

## The Three Planes

### Plane 1 · Data Plane (Mini Bloomberg)

The data plane is the only part of the system that talks directly to external sources and writes to PostgreSQL. Everything else in the system reads from this plane through the MCP/REST contract.

**Components:**
- **ETL pipeline** — ingests SEC EDGAR filings (XBRL), validates against yfinance, resolves conflicts via Alpha Vantage
- **PostgreSQL** — structured, queryable facts organized into four schemas
- **`raw/` filesystem** — original SEC filing HTML/PDFs, kept for Agent fallback parsing

**PostgreSQL schemas:**

| Schema | Contents | Access pattern |
|---|---|---|
| `market_data` | Daily prices, volume | Append-only time series |
| `fundamentals` | Income, balance sheet, cash flow | Versioned by fiscal period |
| `metrics` | Computed ratios (P/E, EV/EBITDA, MACD, RSI…) | Refreshed on each ETL run |
| `etl_audit` | Run logs, source provenance, conflict resolution log | Append-only |

**Raw filesystem layout:**
```
raw/
  NVDA/
    10-K_2024.htm
    10-Q_2024-Q3.htm
    8-K_2024-11-15.htm
```

**Rule: ETL is the only writer.** No other component writes to PostgreSQL or to `raw/`. This makes the data plane fully reproducible — you can always re-run ETL from scratch.

---

### Plane 2 · Intelligence Plane (Agent + Skills)

The Agent reads structured data through the MCP server and produces analysis artifacts. It never writes to the database.

**Data access fallback chain:**

```
1. MCP (PostgreSQL)     ← most trustworthy, already validated
2. raw/ SEC parse       ← used when a field is missing from structured data
3. yfinance             ← supplemental price / basic fundamental data
4. Alpha Vantage        ← conflict resolution, alternative data
5. Web search           ← last resort for news, qualitative context
```

The fallback chain is defined in each skill's `SKILL.md`, not in Python code. This makes the Agent's behavior auditable and editable without touching source code.

**Skills:** Each skill is a self-contained agent task with a defined input contract and a single output path:

```
skills/
  company-profile/SKILL.md     → artifacts/{ticker}/profile/
  investment-thesis/SKILL.md   → artifacts/{ticker}/thesis/
  earnings-analysis/SKILL.md   → artifacts/{ticker}/earnings/
  news-monitor/SKILL.md        → artifacts/{ticker}/news/
  trade-advisor/SKILL.md       → (ephemeral, not persisted)
```

**Rule: Skills never call each other directly.** If the `investment-thesis` skill needs profile data, it reads the profile artifact from the filesystem — it does not invoke the `company-profile` skill. This allows any skill to be re-run in isolation.

---

### Plane 3 · Presentation Plane (Streamlit)

Streamlit is a pure read layer. It renders artifacts and calls the MCP API for live data (prices, metrics). It never triggers ETL and never writes artifacts.

**Streamlit page → data source mapping:**

| Page | Reads from |
|---|---|
| Company Profile | `artifacts/{t}/profile/*.json` + `/api/financials/{t}/prices` |
| Investment Thesis | `artifacts/{t}/thesis/` (all versions, sorted) |
| Earnings Feed | `artifacts/{t}/earnings/` (timeline) |
| Watchlist | Portfolio config + `/api/financials/*/metrics` |
| Trade Signals | `/api/financials/{t}/metrics` (MACD, RSI) |
| ETL Status | `/api/etl/runs` |

**`artifact_renderer.py`** is the bridge between the Agent plane and the UI. It reads `.json` for structured fields (metric tables, chart data) and `.md` for narrative sections. Streamlit pages never need to know how an artifact was generated.

---

## Entry Points

### Prefect / CLI

Used to schedule and trigger ETL operations. Prefect handles mechanical scheduling on the Data Server; CLI commands are available for local development.

```bash
# Ingest a single company
uv run python -m pfs.etl.pipeline ingest NVDA --years 5

# Refresh daily prices
uv run python -m pfs.etl.pipeline sync-prices
```

Prefect flows (in `prefect/flows/`) handle recurring tasks:
- **price_sync** — daily price updates (M-F after market close)
- **filing_check** — daily SEC EDGAR scan for new filings
- **data_validation** — weekly cross-checks

**Rule: Prefect/CLI is the only way to trigger ETL.** The Agent cannot trigger ETL — if data is missing, it tells the user to run the ingest command.

### Chat UI

The Chat UI is the interface for interacting with the Agent. Users can:
- Ask the Agent to generate a company profile: *"Generate a profile for NVDA"*
- Request a thesis draft: *"Draft an investment thesis for NVDA based on the current profile"*
- Ask for an earnings summary after a new 10-Q: *"Summarize NVDA's latest earnings call"*
- Request trade advice: *"Given the current NVDA thesis and price, what's a good entry point?"*

### Git

All artifacts in `data/artifacts/` are git-tracked. This provides:
- Full version history of every thesis, profile, and earnings report
- The ability to diff any two versions of a thesis
- A clear audit trail of when and why analysis changed

Users have two ways to edit artifacts:
1. **Direct edit** — open the `.md` or `.json` file in any editor, commit the change
2. **Agent patch** — ask the Agent in the Chat UI to update a specific field or section; the Agent writes the new version and it can be committed

### REST API

FastAPI exposes both the MCP server tools and standard REST endpoints. See [`docs/api.md`](docs/api.md) for the full reference.

---

## Artifact Schema

Every JSON artifact includes a `schema_version` field. When the schema changes, old files are not broken — Streamlit checks the version and applies the appropriate renderer.

Example `profile/2025-Q4.json`:

```json
{
  "schema_version": "1.0",
  "generated_at": "2025-11-15T10:30:00Z",
  "ticker": "NVDA",
  "data_sources": ["mcp", "sec_raw"],
  "fundamentals": {
    "revenue_ttm": 113000000000,
    "gross_margin": 0.745,
    "net_income_ttm": 72000000000,
    "pe_ratio": 42.3,
    "ev_ebitda": 35.1
  },
  "growth": {
    "revenue_yoy": 1.22,
    "eps_yoy": 1.45
  },
  "balance_sheet": {
    "cash": 34000000000,
    "total_debt": 8900000000,
    "net_cash": 25100000000
  },
  "technicals": {
    "rsi_14": 58.3,
    "macd_signal": "bullish_cross"
  },
  "narrative": {
    "business_description": "...",
    "moat": "...",
    "risks": "..."
  }
}
```

For full schema definitions for each artifact type, see [`docs/artifact-schema.md`](docs/artifact-schema.md).

---

## Design Rules

These six rules keep the system decoupled as it grows. Violating any of them tends to create hard-to-debug feedback loops or tight coupling between planes.

| # | Rule | Why |
|---|---|---|
| 01 | **ETL only writes to PostgreSQL + `raw/`** | Makes the data plane fully reproducible |
| 02 | **MCP is read-only — no ETL triggers through MCP** | Prevents Agent from accidentally re-ingesting data |
| 03 | **Each skill writes to exactly one artifact path** | Allows any skill to be re-run in isolation |
| 04 | **Skills never call each other — they read artifacts** | Decouples the intelligence plane from execution order |
| 05 | **Streamlit never writes** | Keeps the presentation layer a pure consumer |
| 06 | **Trust chain is defined in SKILL.md, not Python** | Makes Agent behavior auditable and editable without code changes |

---

## Investment Workflow (End to End)

```
1. INGEST
   Prefect or CLI triggers ETL for NVDA
   → SEC EDGAR XBRL parsed → validated via yfinance
   → conflicts resolved via Alpha Vantage
   → PostgreSQL updated, raw files saved to data/raw/

2. PROFILE
   User asks Agent: "Generate a profile for NVDA"
   → Agent calls MCP: get_financials(), get_metrics(), get_prices()
   → Falls back to raw SEC parse for any missing fields
   → Writes data/artifacts/NVDA/profile/ (.md + .json)

3. THESIS
   User asks Agent: "Create thesis for NVDA"
   → Agent reads MCP data + profile artifacts
   → Generates data/artifacts/NVDA/thesis/ (.json files)
   → Agent commits artifacts (commit-on-write)

4. MONITOR
   Prefect filing_check detects new 10-Q → creates task in registry
   → Task dispatcher routes to Agent
   → Agent runs health check, updates thesis artifacts

5. REVIEW
   User opens Streamlit → Company Profile page
   → Renders profile JSON metrics + price chart
   → Thesis page shows thesis detail + health check history
```