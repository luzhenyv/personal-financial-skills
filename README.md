# Personal Financial Skills — Mini Bloomberg

A personal investor toolkit built around three decoupled planes: a **Mini Bloomberg** data engine, an **AI Agent** layer that generates analysis artifacts, and a **Streamlit** dashboard for review.

> Adapted from [financial-services-plugins](https://github.com/anthropics/financial-services-plugins) —
> institutional-grade skills refactored for personal use.

---

## System Architecture

The system is organized into three planes that never bleed into each other.

```
┌─────────────────────────────────────────────────────────────────┐
│  PLANE 1 · DATA PLANE  (Mini Bloomberg)                         │
│  ETL → PostgreSQL + raw/  ← single source of truth for facts   │
└─────────────────────────────────────────────────────────────────┘
          ↓  MCP / REST API  (read-only contract)
┌─────────────────────────────────────────────────────────────────┐
│  PLANE 2 · INTELLIGENCE PLANE  (Agent + Skills)                 │
│  Reads MCP → generates analysis artifacts (profile, thesis…)   │
└─────────────────────────────────────────────────────────────────┘
          ↓  reads artifacts + API
┌─────────────────────────────────────────────────────────────────┐
│  PLANE 3 · PRESENTATION PLANE  (Streamlit)                      │
│  Renders artifacts and charts — never writes, never triggers ETL│
└─────────────────────────────────────────────────────────────────┘
```

**Three hard boundaries:**
- Streamlit **never writes** — it only reads artifacts and calls the API
- The Agent **never touches PostgreSQL** — it reads through the MCP contract
- ETL **never calls the Agent** — data ingestion is a separate, scheduled process

For a detailed walkthrough see [`docs/architecture.md`](docs/architecture.md).

---

## Entry Points

| Entry Point | Purpose |
|---|---|
| **Airflow / CLI** | Schedule ETL pipelines, S&P 500 batch ingestion, daily price sync, earnings watch |
| **Chat UI** | Interact with the Agent — generate profiles, request thesis drafts, ask questions |
| **REST API** | Direct HTTP calls to trigger ingestion or fetch structured data |
| **Git** | Version-control all analysis artifacts; edit `.md` / `.json` directly or ask the Agent to patch |

---

## Data Flow

```
SEC EDGAR ──┐
yfinance  ──┼──► Mini Bloomberg ETL ──► PostgreSQL (schemas: market_data,
Alpha Vantage┘    raw/ filesystem              fundamentals, metrics, etl_audit)
                                                    │
                                      MCP Server (FastAPI) ◄── read-only
                                                    │
                                             Agent + Skills
                                                    │
                                         artifacts/{ticker}/
                                         ├── profile/   (.md + .json)
                                         ├── thesis/    (v1 → vN .md)
                                         ├── earnings/  (.md + .json)
                                         └── news/      (DATE.md)
                                                    │
                                           Streamlit Dashboard
```

### Data Source Trust Chain

When the Agent fetches data, it follows this priority order:

```
MCP (PostgreSQL) > raw SEC parse > yfinance > Alpha Vantage > web search
```

MCP-sourced data is the most trustworthy — it has already been validated and conflict-resolved during ETL. Raw SEC files are the fallback when structured data is missing. Web search is the last resort.

---

## Skills

Agent-readable skill definitions live in `skills/`. Each skill has a single input contract and writes to exactly one artifact path. Skills never call each other directly.

| Skill | Input | Output | Status |
|---|---|---|---|
| `company-profile` | MCP financials | `artifacts/{t}/profile/YYYY-QN.md+json` | ✅ Ready |
| `financial-etl` | SEC XBRL | PostgreSQL + `raw/` | ✅ Ready |
| `investment-thesis` | Profile JSON + user notes | `artifacts/{t}/thesis/vN.md` | 🔜 Planned |
| `earnings-analysis` | New 10-Q/8-K + prior thesis | `artifacts/{t}/earnings/YYYY-QN.md` | 🔜 Planned |
| `news-monitor` | Web search results | `artifacts/{t}/news/DATE_slug.md` | 🔜 Planned |
| `trade-advisor` | Thesis + price + technicals | Advisory text (ephemeral) | 🔜 Planned |
| `three-statements` | MCP financials | 3-statement model artifact | 🔜 Planned |
| `dcf-valuation` | 3-statement model | DCF artifact with scenarios | 🔜 Planned |
| `comps-analysis` | Peer tickers | Comparable company table | 🔜 Planned |
| `stock-screening` | Filter criteria | Screener results | 🔜 Planned |
| `portfolio-monitoring` | Holdings + prices | P&L report | 🔜 Planned |

---

## Artifact Store

All agent-generated analysis is stored as git-tracked files under `artifacts/`:

```
artifacts/
  NVDA/
    profile/
      2025-Q4.md          # markdown tearsheet
      2025-Q4.json        # structured data (rendered by Streamlit)
    thesis/
      v1_2025-11-01.md    # initial draft
      v2_2025-11-15.md    # after user edits or earnings update
    earnings/
      2025-Q4_call.md
      2025-Q4_call.json
    news/
      2025-11-15_antitrust.md
```

Every JSON artifact includes a `schema_version` field so Streamlit rendering stays stable across schema changes. Users may edit `.md` or `.json` files directly in git, or ask the Agent to apply a patch.

---

## Streamlit Pages

| Page | Data Source |
|---|---|
| Company Profile | `artifacts/{ticker}/profile/*.json` + price API |
| Investment Thesis | `artifacts/{ticker}/thesis/` (versioned) |
| Earnings Feed | `artifacts/{ticker}/earnings/` timeline |
| Watchlist | Portfolio holdings + trade signals |
| Trade Signals | Technicals API (MACD, RSI) |
| ETL Status | `etl_audit` schema — last run times, gaps |

---

## Quick Start

See [`docs/quickstart.md`](docs/quickstart.md) for full setup. The short version:

```bash
# 1. Configure environment
cp .env.example .env          # set SEC_USER_AGENT to your email

# 2. Start PostgreSQL
docker compose up -d postgres

# 3. Install dependencies
uv sync

# 4. Ingest a company
uv run python -m src.etl.pipeline ingest NVDA --years 5

# 5. Start API + Streamlit
docker compose up -d          # → http://localhost:8000/docs
                              # → http://localhost:8501
```

---

## API Reference

See [`docs/api.md`](docs/api.md) for full endpoint documentation.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/companies/ingest` | Trigger ETL for a ticker |
| `GET` | `/api/companies/` | List all ingested companies |
| `GET` | `/api/financials/{ticker}/income-statements` | Income statements |
| `GET` | `/api/financials/{ticker}/balance-sheets` | Balance sheets |
| `GET` | `/api/financials/{ticker}/cash-flows` | Cash flow statements |
| `GET` | `/api/financials/{ticker}/metrics` | Computed metrics (P/E, EV/EBITDA…) |
| `GET` | `/api/financials/{ticker}/prices` | Price history |
| `GET` | `/api/analysis/{ticker}/profile` | Structured profile (JSON) |
| `POST` | `/api/analysis/{ticker}/tearsheet` | Generate tearsheet via Agent |
| `GET` | `/api/analysis/{ticker}/tearsheet` | Get saved tearsheet |

---

## Tech Stack

| Component | Technology |
|---|---|
| Database | PostgreSQL 16 (Docker) |
| ETL | Python + httpx + SEC EDGAR XBRL API |
| Validation | yfinance |
| Conflict resolution | Alpha Vantage API |
| Backend / MCP | FastAPI |
| Agent | Claude + Skills (Markdown) |
| Dashboard | Streamlit + Plotly |
| Artifact versioning | Git |
| Scheduling | Airflow (planned) |

---

## Cost

| Item | Cost |
|---|---|
| SEC EDGAR API | Free |
| yfinance | Free |
| Alpha Vantage (optional) | $0–50/mo |
| PostgreSQL (Docker) | Free |
| **Total** | **~$0–50/mo** |

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Full system design, decoupling rules, data plane details |
| [`docs/quickstart.md`](docs/quickstart.md) | Step-by-step setup and first ingest |
| [`docs/api.md`](docs/api.md) | Full API endpoint reference |
| [`docs/artifact-schema.md`](docs/artifact-schema.md) | JSON schema for each artifact type |
| [`docs/skills.md`](docs/skills.md) | How to write and extend skills |

---

## License

Apache-2.0