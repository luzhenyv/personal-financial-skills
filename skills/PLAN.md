# Skill Development Plan

> Master plan for evolving the skill system from research platform to full portfolio management.

---

## Core Architecture Decisions

### 1. No MCP — Direct REST API Only

Skills access all data through the FastAPI REST API (`$PFS_API_URL`). No MCP tools, no MCP helpers. Scripts call endpoints directly via `httpx` or `curl`. This keeps skills simple and portable.

### 2. No Shared `_lib/` Directory

Each skill is a **self-contained agent skill** following the [Claude agent skill project structure](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview). There is no `skills/_lib/` shared library. Every script a skill needs lives inside its own `<skill>/scripts/` folder.

- Duplicating small utility functions across skills is acceptable and preferred over cross-skill imports
- If a utility becomes important, high-frequency, or performance-critical, **promote it to a FastAPI server endpoint** rather than sharing it via `_lib/`
- Skills never import from other skills or from a shared skill library

### 3. Heavy Work → FastAPI Server; Light Work → Skill Scripts

The FastAPI server runs on a high-performance server and owns all heavy computation:

| Belongs in **FastAPI server** | Belongs in **skill scripts** |
|-------------------------------|------------------------------|
| Financial calculations (DCF, comps, risk metrics) | Reading API responses, writing artifact JSON/Markdown |
| Database queries and joins | CLI argument parsing |
| Price fetching and batch operations | Prompt templates and AI interaction |
| Stock screening and filtering | Artifact file I/O (simple JSON read/write) |
| Portfolio valuation and P&L computation | Report formatting (Markdown assembly) |
| Correlation and beta calculations | Calling `POST /api/analysis/reports` to persist |

Skills stay thin: fetch data from API → let AI analyze → write artifacts.

---

## Current Skill Inventory

| # | Skill | Path | Status | Origin |
|---|-------|------|--------|--------|
| 1 | **company-profile** | `skills/company-profile/` | ✅ Production | Adapted from equity-research `initiating-coverage` |
| 2 | **thesis-tracker** | `skills/thesis-tracker/` | ✅ Production | Adapted from equity-research `thesis-tracker` |
| 3 | **etl-coverage** | `skills/etl-coverage/` | ✅ Production | Original |
| 4 | **knowledge-base** | `skills/knowledge-base/` | 🏗️ Placeholder | Original — full redesign planned |

---

## Part 1: Refactoring Existing Skills

### 1.0 Delete `skills/_lib/` — Migrate to Per-Skill Scripts + API

The `skills/_lib/` directory violates agent skill project structure. Each file must be migrated:

| Current `_lib/` file | Migration plan | Priority | Status |
|----------------------|----------------|----------|--------|
| `mcp_helpers.py` | **Delete.** All functions are thin REST API wrappers. Skills call the API directly via `httpx` | P0 | ✅ Done |
| `api_client.py` | **Promote to API.** Functions like `get_profile()`, `get_valuation()`, `get_coverage()` already call FastAPI endpoints. Skills call those endpoints directly. Delete this file | P0 | ✅ Done |
| `artifact_io.py` | **Copy into each skill** that needs it (company-profile, thesis-tracker). It's lightweight file I/O — ~80 lines. Each skill gets its own copy in `<skill>/scripts/artifact_io.py` | P0 | ✅ Done |
| `thesis_io.py` | **Move to `thesis-tracker/scripts/thesis_io.py`**. Only thesis-tracker uses it. If portfolio-manager needs to read thesis files, it reads the JSON directly | P0 | ✅ Done |
| `task_client.py` | **Move to `agents/task_client.py`**. Used by the task dispatcher agent, not by skills | P0 | ✅ Done |

### 1.1 company-profile — Moderate Refactor

The skill works but has structural gaps that will compound as we add more skills that depend on profile data.

| Issue | What to do | Priority | Status |
|-------|-----------|----------|--------|
| **Task 1 is fully AI-driven** | Extract 10-K parsing into a reusable script (`scripts/extract_10k.py`). Keep AI interpretation for narrative fields, but structured field extraction (revenue segments, executives) should be deterministic | P1 | ✅ Done — `extract_10k.py` created; outputs `*_skeleton.json` files |
| **No valuation section** | Add DCF summary to profile output by calling `GET /api/analysis/valuation/{ticker}`. Profile should include fair value estimate | P2 | ✅ Done — `section_dcf_summary()` added to `generate_report.py`; loads `valuation_summary.json` |
| **Comps depend on yfinance live calls** | Move comps computation to FastAPI: `GET /api/analysis/comps/{ticker}`. The server handles yfinance calls, caching, and TTL. `build_comps.py` becomes a thin script that calls the API endpoint | P1 | ✅ Done — `pfs/analysis/comps.py` + API endpoint added; `build_comps.py` rewritten as thin client |
| **No markdown-to-DB persistence for Task 1** | Task 3 posts report to DB, but Task 1 JSON artifacts are only local. Add `POST /api/analysis/reports` call after Task 1 to persist structured data too | P3 | ⏭️ Skipped — markdown reports managed via git |
| **Config triggers are passive** | `config.yaml` defines 10-K trigger, but no active listener. Wire into task dispatcher event matching | P2 | ✅ Done — `prefect/flows/filing_check.py` fixed to route 10-K → company-profile |
| **Remove MCP references** | Update `config.yaml`: replace `mcp_tools` with `api_endpoints`. Update `generate_report.py` comments to say "REST API" not "MCP" | P0 | ✅ Done — `config.yaml`, `generate_report.py`, `quality-checks.md` updated |

### 1.2 thesis-tracker — Light Refactor

The best-structured skill. Minimal changes needed, mostly extensions.

| Issue | What to do | Priority | Status |
|-------|-----------|----------|--------|
| **Inline `thesis_io.py`** | Move `skills/_lib/thesis_io.py` → `skills/thesis-tracker/scripts/thesis_io.py`. Update imports in `thesis_cli.py` | P0 | ✅ Done |
| **Inline `artifact_io.py`** | Copy `skills/_lib/artifact_io.py` → `skills/thesis-tracker/scripts/artifact_io.py` if used | P0 | ✅ Done |
| **Assumption weights not validated** | Add validation in `thesis_cli.py create` that weights sum to 1.0 (or auto-normalize) | P1 | ✅ Done — `_normalize_weights()` added to `thesis_cli.py` |
| **Subjective score always 50 in CLI** | Design a structured prompt template for the agent to produce real subjective scores. Store the prompt in `references/health-check-prompt.md` | P1 | ✅ Done — `references/health-check-prompt.md` created |
| **Catalyst resolution doesn't auto-trigger update** | When resolving a catalyst via `catalyst --resolve`, auto-prompt for update flow (or create a task in the queue) | P2 | ⏭️ Skipped |
| **No portfolio integration point** | Add `position_size`, `entry_price`, `current_pnl` fields to `thesis.json` (optional fields). The upcoming portfolio skill will populate these | P2 | ⏭️ Skipped |
| **Health check `--all` has no summary view** | Generate a portfolio-wide health summary markdown when running `check --all` | P2 | ⏭️ Skipped |
| **Remove MCP references** | Update `config.yaml`: replace `mcp_tools` with `api_endpoints` | P0 | ✅ Done |
| **Simplify SKILL.md** | Rewrite SKILL.md to match reference style from financial-services-plugins (workflow steps, not task-oriented CLI docs) | P0 | ✅ Done |

### 1.3 etl-coverage — Light Refactor

| Issue | What to do | Priority | Status |
|-------|-----------|----------|--------|
| **Remove MCP references** | Update `config.yaml`: replace `mcp_tools` with `api_endpoints` | P0 | ✅ Done |

---

## Part 2: New Skills Development

### Skill Map (Full Vision)

Each skill is self-contained: `SKILL.md` + `config.yaml` + `scripts/` + `references/`. No shared `_lib/`. Heavy computation lives in the FastAPI server as API endpoints.

```
skills/
  company-profile/               # Company tearsheet       ✅ exists
  ├── SKILL.md
  ├── config.yaml
  ├── scripts/
  │   ├── artifact_io.py         # Local copy — JSON/Markdown I/O
  │   ├── build_comps.py         # Thin: calls GET /api/analysis/comps/{ticker}
  │   ├── extract_10k.py         # 10-K section parsing
  │   └── generate_report.py     # Markdown report assembly
  └── references/

  thesis-tracker/                # Investment thesis CRUD  ✅ exists
  ├── SKILL.md
  ├── config.yaml
  ├── scripts/
  │   ├── artifact_io.py         # Local copy
  │   ├── thesis_io.py           # Thesis file ops (moved from _lib/)
  │   └── thesis_cli.py          # CLI: create/update/check/catalyst/report
  └── references/

  etl-coverage/                  # Data quality audit      ✅ exists
  ├── SKILL.md
  ├── config.yaml
  └── scripts/
      └── check_coverage.py      # Calls GET /api/analysis/coverage/{ticker}

  portfolio-analyst/              # 🆕 Phase 2 — AI portfolio review (data lives in Mini PORT API)
  ├── SKILL.md
  ├── config.yaml
  ├── scripts/
  │   ├── artifact_io.py         # Local copy
  │   └── collect_portfolio.py   # Calls GET /api/portfolio/* endpoints
  └── references/

  earnings-analysis/             # 🆕 Phase 3 — Post-earnings reports
  earnings-preview/              # 🆕 Phase 3 — Pre-earnings scenarios
  risk-manager/                  # 🆕 Phase 3 — Portfolio risk metrics
  morning-briefing/              # 🆕 Phase 3 — Daily research digest
  model-update/                  # 🆕 Phase 3 — Financial model maintenance
  idea-generation/               # 🆕 Phase 4 — Stock screening pipeline
  sector-overview/               # 🆕 Phase 4 — Industry landscape reports
  catalyst-calendar/             # 🆕 Phase 4 — Cross-portfolio event tracking
  knowledge-base/                # �️ Placeholder — External research ingestion (full redesign planned)
  fund-manager/                  # 🆕 Phase 4 — Multi-agent decision synthesis
```

---

### Phase 2: Portfolio Management

The original design had "portfolio-manager" as a skill with CLI commands for buy/sell/snapshot. But that's really a data management module — CRUD operations, P&L math, price fetching. These belong on the **FastAPI server**, not in an agent skill.

**The split:**
- **Mini PORT module** (FastAPI server) — all portfolio data, transactions, positions, P&L computation, allocation. Lives in `pfs/api/routers/portfolio.py` + `pfs/db/` tables. This is the portfolio equivalent of how we already handle financial data.
- **portfolio-analyst skill** (agent skill) — thin AI layer that reads portfolio state from API and produces *analysis* artifacts: portfolio review narratives, rebalancing recommendations, thesis-portfolio alignment checks.

---

#### 2.0 Mini PORT — FastAPI Portfolio Module (P0 — Build First)

**Purpose:** Server-side portfolio tracking, P&L computation, transaction history, and allocation analysis. Our mini version of Bloomberg PORT.

**Why server-side, not a skill:**
- Transactions, positions, and snapshots are **data** — they belong in the database alongside financials
- P&L computation, allocation breakdown, and price fetching are **deterministic math** — no AI needed
- Other skills (risk-manager, morning-briefing, fund-manager) all need portfolio data — a REST API is the clean contract
- The Streamlit dashboard reads portfolio data the same way it reads financial data — via API

**Implementation:**

```
pfs/
  db/
    models.py             # Add: Portfolio, Position, Transaction, Snapshot models
    schema.sql            # Add: portfolio tables
  analysis/
    portfolio.py          # P&L engine, allocation, snapshot logic
  api/
    routers/
      portfolio.py        # REST API endpoints
```

**Database tables:**

```sql
CREATE TABLE portfolios (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'default',
    cash NUMERIC(14,2) NOT NULL DEFAULT 100000.00,
    inception_date DATE NOT NULL,
    benchmark TEXT DEFAULT 'SPY',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id),
    date DATE NOT NULL,
    ticker TEXT NOT NULL REFERENCES companies(ticker),
    action TEXT NOT NULL CHECK (action IN ('buy', 'sell', 'dividend')),
    shares NUMERIC(12,4) NOT NULL,
    price NUMERIC(12,4) NOT NULL,
    fees NUMERIC(8,2) DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id),
    ticker TEXT NOT NULL REFERENCES companies(ticker),
    shares NUMERIC(12,4) NOT NULL,
    avg_cost NUMERIC(12,4) NOT NULL,
    conviction TEXT CHECK (conviction IN ('high', 'medium', 'low')),
    position_type TEXT DEFAULT 'long' CHECK (position_type IN ('long', 'short')),
    opened_at DATE NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(portfolio_id, ticker)
);

CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id),
    date DATE NOT NULL,
    total_market_value NUMERIC(14,2),
    total_cost_basis NUMERIC(14,2),
    cash NUMERIC(14,2),
    unrealized_pnl NUMERIC(14,2),
    realized_pnl NUMERIC(14,2),
    positions_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(portfolio_id, date)
);
```

**REST API endpoints (new router: `/api/portfolio/`):**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/portfolio/` | GET | Get portfolio summary (current positions, cash, total value) |
| `/api/portfolio/positions` | GET | All open positions with current prices, P&L, weights |
| `/api/portfolio/positions/{ticker}` | GET | Single position details with transaction history |
| `/api/portfolio/transactions` | GET | Transaction history with filters (ticker, date range, action) |
| `/api/portfolio/transactions` | POST | Record a trade (buy/sell/dividend). Server updates position + cash |
| `/api/portfolio/snapshot` | POST | Take daily snapshot — server fetches prices, computes P&L, saves |
| `/api/portfolio/allocation` | GET | Allocation breakdown by sector, conviction, position size |
| `/api/portfolio/performance?period=ytd` | GET | Time-weighted return, vs benchmark, drawdown |
| `/api/portfolio/pnl` | GET | Realized + unrealized P&L breakdown per position |

**Key design decisions:**
- **Append-only transactions** — `transactions` table is insert-only, never updated or deleted
- **Positions computed from transactions** — `positions` table is a materialized view of net shares + avg cost, recomputed on each trade
- **Server-side snapshots** — Prefect cron triggers `POST /api/portfolio/snapshot` daily after market close. Server fetches batch prices and persists
- **No broker integration (v1)** — manual trade entry via API. Broker API integration is a future enhancement
- **Thesis linkage via ticker** — positions reference `companies(ticker)`, thesis data read from `data/artifacts/{ticker}/thesis/` or a future thesis DB table

**Data flow:**
```
POST /api/portfolio/transactions     → transactions table (append)
  Server auto-updates:               → positions table (recalculated)
                                      → portfolios.cash (adjusted)

POST /api/portfolio/snapshot          → Server fetches GET /api/prices/batch
                                      → portfolio_snapshots table (daily)
                                      → Positions updated with current_price

GET /api/portfolio/positions          → Returns positions with live P&L
GET /api/portfolio/allocation         → Returns sector/conviction/size breakdown
GET /api/portfolio/performance        → Returns time-series from snapshots
```

**Streamlit page:** New `pages/4_portfolio.py` — reads all data from `/api/portfolio/*` endpoints. Positions table, allocation pie chart, P&L waterfall, performance vs. benchmark chart.

---

#### 2.1 portfolio-analyst (Agent Skill)

**Purpose:** AI-driven portfolio analysis — what the portfolio manager skill was trying to do, but only the parts that actually need intelligence. Reads portfolio state from Mini PORT API and thesis artifacts, produces narrative analysis.

**This is an actual agent skill** because it requires AI judgment: interpreting portfolio health, recommending rebalancing, connecting thesis developments to position sizing.

**Artifacts:** `data/artifacts/_portfolio/analysis/`

```
data/artifacts/_portfolio/analysis/
  portfolio_review.json       # Structured analysis
  portfolio_review.md         # Narrative report
```

**Workflow (2 tasks):**

| Task | Type | Description |
|------|------|-------------|
| 1 | Script | **Data Collection** — Call `GET /api/portfolio/positions`, `GET /api/portfolio/allocation`, `GET /api/portfolio/performance`. Read thesis artifacts for each position. Write `portfolio_snapshot.json` to artifacts |
| 2 | AI | **Portfolio Review** — Interpret allocation vs. conviction alignment, identify orphaned positions (no thesis), flag concentration risks, recommend rebalancing actions. Write review narrative |

**Skill scripts (thin):**
- `scripts/collect_portfolio.py` — calls Mini PORT API endpoints, reads thesis artifacts, assembles data
- `scripts/artifact_io.py` — local copy of JSON/Markdown I/O helpers

**config.yaml:**
```yaml
name: portfolio-analyst
version: "1.0"
description: "AI portfolio review and rebalancing recommendations"

triggers:
  - cron: "0 17 * * 5"    # Weekly Friday after close
    action: review
  - event: task_request
    action: review

inputs:
  api_endpoints:
    - GET /api/portfolio/positions
    - GET /api/portfolio/allocation
    - GET /api/portfolio/performance
  artifacts:
    - "{ticker}/thesis/thesis.json"

outputs:
  path: "data/artifacts/_portfolio/analysis/"
  files:
    - portfolio_review.json
    - portfolio_review.md
```

**CLI:**
```bash
# Collect data + generate analysis
uv run python skills/portfolio-analyst/scripts/collect_portfolio.py
# Agent then produces the AI narrative review
```

**Cross-skill reads (artifacts only):**
- `data/artifacts/{ticker}/thesis/thesis.json` — thesis health per position
- Mini PORT API — portfolio positions, allocation, performance

**Read by:** risk-manager, morning-briefing, fund-manager

---

### Phase 3 Skills (Earnings & Event Reaction + Risk)

#### 3.1 earnings-analysis (P1)

**Purpose:** Professional post-earnings analysis reports. The most important reactive skill — when a company reports, we need to assess thesis impact within 24h.

**Adapted from:** equity-research `earnings-analysis` skill. Simplified for our scale (no team distribution, no morning meeting format), but maintains the rigor on data freshness verification and source citations.

**Artifacts:** `data/artifacts/{ticker}/earnings/`

```
data/artifacts/{ticker}/earnings/
  Q4_2024.json              # Structured earnings data
  Q4_2024_analysis.md       # Narrative report
```

**Workflow (4 tasks):**

| Task | Type | Description |
|------|------|-------------|
| 1 | Script | **Data Collection** — Fetch latest 10-Q + earnings call transcript from REST API / SEC. Confirm the data is for the correct quarter. ⚠️ Critical freshness check |
| 2 | AI + Script | **Beat/Miss Analysis** — Revenue, EPS, margins vs. consensus and our model. Segment-level breakdown. Guidance changes |
| 3 | AI | **Thesis Impact** — How do results affect each thesis assumption? Auto-run thesis health check. Recommend hold/add/trim/exit |
| 4 | Script | **Report Generation** — Combine into markdown report, persist to DB |

**Key difference from equity-research version:**
- No chart generation (Streamlit handles visualization)
- Thesis impact assessment is built-in (equity-research doesn't have thesis integration)
- Auto-triggers thesis-tracker update when analysis completes

**REST API endpoints used:**
- `GET /api/filings/{ticker}/?form_type=10-Q` — latest quarterly filing
- `GET /api/financials/{ticker}/income-statements?years=2` — compare QoQ / YoY
- `GET /api/financials/{ticker}/metrics` — margin trends
- `GET /api/financials/{ticker}/quarterly?quarters=8` — quarterly breakdown ✅ **implemented**

**Skill scripts (thin, API-driven):**
- `scripts/collect_earnings.py` — calls REST API endpoints, writes raw JSON to artifacts
- `scripts/generate_earnings_report.py` — assembles Markdown from JSON artifacts + AI analysis
- `scripts/artifact_io.py` — local copy of JSON/Markdown I/O helpers

**Trigger:** Task dispatcher creates earnings-analysis task when new 10-Q detected by Prefect `filing_check` flow.

#### 3.2 earnings-preview (P2)

**Purpose:** Pre-earnings scenario analysis. Before a company reports, outline what to expect, what to watch, and how each scenario affects the thesis.

**Adapted from:** equity-research `earnings-preview` skill.

**Artifacts:** `data/artifacts/{ticker}/earnings/preview_Q1_2025.json`

**Workflow (3 tasks):**

| Task | Type | Description |
|------|------|-------------|
| 1 | Script | **Consensus & Context** — Gather consensus estimates, recent guidance, options-implied move |
| 2 | AI | **Scenario Framework** — Bull/Base/Bear scenarios with specific numbers for revenue, EPS, key drivers, expected stock reaction |
| 3 | AI | **Key Metrics & Catalyst Checklist** — What specific metrics and management commentary will strengthen or weaken the thesis? |

**Trigger:** Calendar-based — auto-create task 5 days before expected earnings date (from catalyst calendar).

#### 3.3 risk-manager (P1)

**Purpose:** Portfolio-level risk monitoring. Not about individual stock analysis (that's thesis-tracker) but about the collection of positions — concentration, correlation, drawdown, and whether the portfolio as a whole makes sense.

**Adapted from:** TradingAgents paper's risk management agent concept. No direct equity-research equivalent.

**Artifacts:** `data/artifacts/_portfolio/risk/`

```
data/artifacts/_portfolio/risk/
  risk_report.json          # Latest risk metrics
  risk_report.md            # Narrative risk assessment
  alerts.json               # Active risk alerts (append-only)
```

**risk_report.json schema:**

```json
{
  "schema_version": "1.0",
  "generated_at": "2025-03-25T16:00:00Z",
  "concentration": {
    "top_position_pct": 0.15,
    "top3_positions_pct": 0.38,
    "sector_weights": {"Technology": 0.45, "Healthcare": 0.20, "Financials": 0.15},
    "hhi_index": 0.12
  },
  "risk_metrics": {
    "portfolio_beta": 1.15,
    "max_drawdown_30d": -0.08,
    "sharpe_ratio_90d": 1.2,
    "sortino_ratio_90d": 1.5,
    "var_95_1d": -2500.00
  },
  "thesis_health": {
    "avg_health_score": 72,
    "positions_below_50": ["BA"],
    "positions_without_thesis": [],
    "stale_checks": ["KO"]
  },
  "alerts": [
    {"type": "concentration", "message": "Technology sector at 45% (limit: 40%)", "severity": "warning"},
    {"type": "thesis_health", "message": "BA thesis score 38 — below critical threshold", "severity": "critical"}
  ],
  "rules": {
    "max_single_position_pct": 0.15,
    "max_sector_pct": 0.40,
    "max_portfolio_beta": 1.5,
    "min_thesis_health_score": 40,
    "max_drawdown_alert_pct": -0.10
  }
}
```

**CLI:**

```bash
uv run python skills/risk-manager/scripts/risk_cli.py check             # Full risk report
uv run python skills/risk-manager/scripts/risk_cli.py alerts            # Current active alerts
uv run python skills/risk-manager/scripts/risk_cli.py rules             # Show/edit risk rules
uv run python skills/risk-manager/scripts/risk_cli.py report            # Generate markdown report
```

**REST API endpoints used:**
- `POST /api/analysis/risk/portfolio` — server computes beta, correlation, VaR, drawdown *(new endpoint)*
- `GET /api/analysis/risk/{ticker}` — per-ticker risk metrics *(new endpoint)*
- `GET /api/portfolio/positions` — current positions from Mini PORT
- `GET /api/portfolio/allocation` — allocation breakdown from Mini PORT

**Skill scripts (thin):**
- `scripts/risk_cli.py` — calls risk + portfolio API endpoints, reads thesis artifacts, writes risk report
- `scripts/artifact_io.py` — local copy of JSON/Markdown I/O helpers

**Cross-skill reads (artifacts + API, no imports):**
- `GET /api/portfolio/*` — positions, allocation from Mini PORT
- `data/artifacts/{ticker}/thesis/thesis.json` — health scores per position

#### 3.4 morning-briefing (P2)

**Purpose:** Automated daily research digest. What happened overnight, what matters today, how the portfolio is affected.

**Adapted from:** equity-research `morning-note` skill. Simplified to single-person format (no team meeting).

**Artifacts:** `data/artifacts/_daily/YYYY-MM-DD.md`

**Content:**
1. **Portfolio performance** — yesterday's P&L, notable movers
2. **Market context** — index moves, sector rotation, macro data releases
3. **Position updates** — news affecting portfolio holdings
4. **Catalyst calendar** — what's coming this week
5. **Action items** — thesis checks due, earnings previews needed, risk alerts

**Trigger:** Daily via Prefect cron (6:30 AM before market open).

#### 3.5 model-update (P3)

**Purpose:** Maintain and update financial projections when new data arrives.

**Adapted from:** equity-research `model-update` skill.

**Artifacts:** `data/artifacts/{ticker}/model/`

**Scope for our system:** No Excel models. Instead, maintain a `projections.json` per ticker with forward revenue/EPS estimates, scenario assumptions. Updated when earnings-analysis completes or when macro assumptions change.

---

### Phase 4 Skills (Multi-Agent Intelligence)

#### 4.1 idea-generation (P2)

**Purpose:** Systematic stock screening — surface new investment ideas from the database.

**Adapted from:** equity-research `idea-generation` skill.

**Artifacts:** `data/artifacts/_ideas/`

**Workflow:**
1. Define screen criteria (value, growth, quality, special situation)
2. Call `GET /api/analysis/screen` with filter parameters — server does the heavy DB queries
3. Rank and filter results
4. Generate one-pager per idea candidate
5. Flag top ideas for full company-profile workflow

**CLI:**

```bash
uv run python skills/idea-generation/scripts/screen.py --type growth --min-revenue-growth 0.20
uv run python skills/idea-generation/scripts/screen.py --type value --max-pe 15 --min-fcf-yield 0.05
```

**REST API endpoints used:**
- `GET /api/analysis/screen?type=growth&min_revenue_growth=0.20` — parameterized screening *(new endpoint)*
- `GET /api/companies/` — list all ingested companies
- `GET /api/financials/{ticker}/metrics` — per-ticker fundamentals

#### 4.2 sector-overview (P3)

**Purpose:** Industry landscape reports for sectors in the portfolio.

**Adapted from:** equity-research `sector-overview` skill.

**Artifacts:** `data/artifacts/_sectors/{sector}/`

#### 4.3 catalyst-calendar (P2)

**Purpose:** Unified cross-portfolio event calendar. Aggregates catalysts from all thesis-tracker instances plus known macro events.

**Adapted from:** equity-research `catalyst-calendar` + thesis-tracker's per-ticker catalysts.

**Difference from thesis-tracker catalysts:** Thesis-tracker stores catalysts per-ticker. This skill aggregates ALL catalysts across the portfolio into a unified calendar view with macro events (FOMC, CPI, etc.) overlaid.

**Artifacts:** `data/artifacts/_portfolio/catalysts/`

#### 4.4 fund-manager (P3 — TradingAgents-Inspired)

**Purpose:** The "meta-skill" that synthesizes all other skill outputs into actionable trading decisions. Inspired by TradingAgents paper's fund manager agent.

**Artifacts:** `data/artifacts/_portfolio/decisions/`

**Design (Multi-Agent Debate Pattern):**

```
Inputs:
  ├── thesis-tracker health checks  (fundamental signal)
  ├── risk-manager alerts            (risk constraints)
  ├── earnings-analysis results      (event signal)
  ├── morning-briefing highlights    (news/sentiment signal)
  ├── portfolio-manager state        (current positions)
  └── catalyst-calendar upcoming     (timing signal)
  
Processing:
  1. Collect latest signals from all skill artifacts
  2. For each position: assess signal alignment (all bullish? conflicting?)
  3. Apply risk manager constraints (position limits, sector limits)
  4. Generate decision recommendations with reasoning chain
  
Output:
  decisions/YYYY-MM-DD.json
  {
    "decisions": [
      {
        "ticker": "NVDA",
        "action": "hold",
        "signals": {
          "thesis_health": 78,
          "earnings_impact": "positive",
          "risk_flag": null,
          "catalyst_upcoming": "Q4 earnings in 5 days"
        },
        "reasoning": "Thesis intact, wait for earnings before adding",
        "confidence": "high"
      }
    ]
  }
```

This skill does NOT auto-execute trades. It produces decision artifacts that the human reviews before acting. **Human-in-the-loop is a hard rule** for actual execution.

---

### Phase 5 Skills (Knowledge Platform)

#### 5.1 knowledge-base (P3)

**Purpose:** Ingest and index external research (Morningstar reports, sell-side research, market studies, academic papers) into a queryable knowledge store.

**Artifacts:** `data/artifacts/_knowledge/`

```
data/artifacts/_knowledge/
  index.json                # Master index of all ingested documents
  sources/
    morningstar_oil_2025.json   # Structured extraction from report
    morningstar_oil_2025.md     # Summary + key takeaways
  sectors/
    energy_market.json          # Aggregated sector knowledge
```

**Workflow:**
1. User provides PDF/report → skill extracts structured data
2. Key findings tagged by sector, theme, company mentions
3. Queryable by the agent during thesis creation/updates
4. Cross-referenced during morning briefings

**This is the foundation for the "sell knowledge" aspiration** — from curated knowledge base to generated research products.

---

## Part 3: Implementation Roadmap

### Phase 2: Portfolio Management (Target: April 2025)

```
Week 1:
  ☐ Delete skills/_lib/ — migrate files per Section 1.0
  ☐ Move thesis_io.py → thesis-tracker/scripts/thesis_io.py, update imports
  ☐ Copy artifact_io.py into company-profile/scripts/ and thesis-tracker/scripts/
  ☐ Move task_client.py → agents/task_client.py
  ☐ Delete mcp_helpers.py and api_client.py (skills call API directly)
  ☐ Update config.yaml in all 3 existing skills: mcp_tools → api_endpoints
  ☐ Build new FastAPI endpoint: GET /api/analysis/comps/{ticker}

Week 2 — Mini PORT module:
  ☐ Add portfolio DB tables (portfolios, transactions, positions, portfolio_snapshots)
  ☐ Build pfs/analysis/portfolio.py — P&L engine, allocation, snapshot logic
  ☐ Build pfs/api/routers/portfolio.py — full REST API (9 endpoints)
  ☐ Register router in app.py
  ☐ Build Prefect flow for daily POST /api/portfolio/snapshot

Week 3:
  ☐ Refactor thesis-tracker (weight validation, subjective scoring template)
  ☐ Build Streamlit portfolio page (positions table, allocation chart, P&L)
  ☐ Build portfolio-analyst skill (collect_portfolio.py + AI review workflow)

Week 4:
  ☐ Build risk-manager skill (risk metrics, alerts, rules)
  ☐ Build new FastAPI endpoints: risk/portfolio, risk/{ticker}, correlation-matrix
  ☐ Add risk section to Streamlit dashboard
```

### Phase 3: Earnings & Events (Target: May-June 2025)

```
Month 1 (May):
  ☐ Build FastAPI endpoint: GET /api/financials/{ticker}/quarterly
  ☐ Build earnings-analysis skill (4-task workflow, thin scripts calling API)
  ☐ Wire earnings-analysis → thesis-tracker auto-update (reads/writes thesis artifacts)
  ☐ Build earnings-preview skill (3-task workflow)
  ☐ Build morning-briefing skill

Month 2 (June):
  ☐ Build FastAPI endpoints: risk/{ticker}, risk/portfolio, correlation-matrix
  ☐ Wire Prefect filing_check → auto-trigger earnings-analysis
  ☐ Wire earnings date calendar → auto-trigger earnings-preview
  ☐ Build catalyst-calendar skill (cross-portfolio aggregation)
  ☐ Refactor company-profile (10-K extraction script, valuation section)
```

### Phase 4: Multi-Agent Intelligence (Target: Q3 2025)

```
  ☐ Build FastAPI endpoints: screen, catalysts/upcoming
  ☐ Build idea-generation skill (thin screening script calling GET /api/analysis/screen)
  ☐ Build sector-overview skill
  ☐ Build model-update skill
  ☐ Build fund-manager skill (multi-signal synthesis, reads all skill artifacts)
  ☐ Design agent debate protocol (fund-manager reads all analyst artifacts)
```

### Phase 5: Knowledge Platform (Target: Q4 2025)

```
  ☐ Build FastAPI endpoint: POST /api/knowledge/ingest
  ☐ Build knowledge-base skill (PDF ingestion via API, structured extraction)
  ☐ Build cross-reference engine (knowledge → thesis → morning briefing)
  ☐ Design research report templates for external consumption
```

---

## Part 4: FastAPI Server Endpoint Plan

The FastAPI server is the **computation and data hub**. Skills are thin clients that call these endpoints. When a skill needs heavy work done, we build an endpoint — not a shared library.

### Existing Endpoints

| Endpoint | Used by |
|----------|---------|
| `GET /api/companies/` | all skills |
| `GET /api/companies/{ticker}` | company-profile, thesis-tracker |
| `GET /api/financials/{ticker}/income-statements?years=5` | company-profile, earnings-analysis |
| `GET /api/financials/{ticker}/balance-sheets?years=5` | company-profile |
| `GET /api/financials/{ticker}/cash-flows?years=5` | company-profile |
| `GET /api/financials/{ticker}/metrics` | thesis-tracker, earnings-analysis, idea-generation |
| `GET /api/financials/{ticker}/prices?period=1y` | company-profile |
| `GET /api/financials/{ticker}/segments` | company-profile |
| `GET /api/financials/{ticker}/stock-splits` | company-profile |
| `GET /api/financials/{ticker}/annual?years=5` | company-profile |
| `GET /api/filings/{ticker}/` | earnings-analysis |
| `GET /api/filings/{ticker}/{id}/content` | earnings-analysis |
| `GET /api/analysis/profile/{ticker}` | company-profile |
| `GET /api/analysis/valuation/{ticker}` | company-profile |
| `GET /api/analysis/coverage/{ticker}` | etl-coverage |
| `GET /api/analysis/current-price/{ticker}` | all skills |
| `POST /api/analysis/reports` | all skills (persist to DB) |

### New Endpoints to Build

**Phase 2 — Mini PORT module (new router: `/api/portfolio/`)**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/portfolio/` | GET | Portfolio summary — cash, total value, position count |
| `/api/portfolio/positions` | GET | All open positions with current prices, P&L, weights |
| `/api/portfolio/positions/{ticker}` | GET | Single position details with transaction history |
| `/api/portfolio/transactions` | GET | Transaction history (filterable by ticker, date range, action) |
| `/api/portfolio/transactions` | POST | Record a trade — server updates position + cash automatically |
| `/api/portfolio/snapshot` | POST | Daily snapshot — server fetches prices, computes P&L, saves |
| `/api/portfolio/allocation` | GET | Allocation by sector, conviction, position size |
| `/api/portfolio/performance?period=ytd` | GET | Time-weighted return, vs benchmark, drawdown |
| `/api/portfolio/pnl` | GET | Realized + unrealized P&L breakdown per position |

**Phase 2 — Other new endpoints**

| Endpoint | Needed by | Purpose |
|----------|-----------|---------|
| **`GET /api/analysis/comps/{ticker}`** | company-profile | Server-side comps with yfinance + caching + TTL |

**Phase 3 — Earnings & Risk**

| Endpoint | Needed by | Purpose |
|----------|-----------|---------|
| **`GET /api/financials/{ticker}/quarterly?quarters=8`** | earnings-analysis | Quarterly breakdown for QoQ comparison |
| **`GET /api/analysis/risk/{ticker}`** | risk-manager | Per-ticker beta, volatility, correlation vs benchmark |
| **`POST /api/analysis/risk/portfolio`** | risk-manager | Portfolio-level beta, VaR, max drawdown, sector concentration |
| **`GET /api/analysis/correlation-matrix?tickers=X,Y,Z`** | risk-manager, fund-manager | Pairwise correlation matrix from price data |

**Phase 4 — Intelligence**

| Endpoint | Needed by | Purpose |
|----------|-----------|---------|
| **`GET /api/analysis/screen`** | idea-generation | Parameterized stock screening across all companies |
| **`GET /api/catalysts/upcoming?days=30`** | catalyst-calendar, morning-briefing | Aggregated catalyst events |

**Phase 5 — Knowledge**

| Endpoint | Needed by | Purpose |
|----------|-----------|---------|
| **`POST /api/knowledge/ingest`** | knowledge-base | Document ingestion and structured extraction |

### Design Principles for New Endpoints

1. **Compute-heavy → server endpoint** — If it needs price data, DB joins, or math beyond simple arithmetic, it's an endpoint
2. **Cacheable** — Comps, risk metrics, screening results should include server-side caching with TTL
3. **Batch-friendly** — Multi-ticker operations in a single request to reduce round trips
4. **JSON in, JSON out** — Consistent schema with `schema_version` where appropriate
5. **Stateless** — Endpoints compute from current DB state, no session tracking

---

## Part 5: Skill Architecture Rules

These rules govern how ALL skills are built, current and future:

1. **One SKILL.md per skill** — The agent's instruction manual. No code understanding required. If you can't describe the workflow in SKILL.md, it's too complex
2. **One artifact path per skill** — `data/artifacts/{ticker}/{skill}/` or `data/artifacts/_{global_skill}/`
3. **Skills read artifacts, never call each other** — If earnings-analysis needs thesis data, it reads `thesis.json`, it doesn't invoke thesis-tracker
4. **JSON for structured data, Markdown for narrative** — Every skill outputs both
5. **Append-only for history** — Updates, health checks, transactions, decisions: always append, never overwrite
6. **CLI mirrors agent capability** — Everything the agent can do, a human can do via CLI
7. **Config-driven triggers** — `config.yaml` defines what events activate the skill. The task dispatcher reads these
8. **Self-contained skills** — Each skill's scripts live in `<skill>/scripts/`. No shared `_lib/` directory. Duplicating small utilities across skills is preferred over cross-skill imports
9. **Heavy work → FastAPI server** — If a computation is performance-critical, shared across skills, or needs DB access, it belongs as a server endpoint. Skill scripts stay thin (call API → AI analysis → write artifacts)
10. **Direct REST API access** — Skills call the FastAPI server via `httpx`/`curl`. No MCP, no wrapper libraries, no intermediary abstractions
11. **References folder for prompts** — Structured AI prompts live in `references/` not hardcoded in scripts
12. **POST to DB after artifact write** — Call `POST /api/analysis/reports` to persist reports for dashboard access

---

## Appendix: Skill Dependency Graph

```
 DATA PLANE (REST API + Mini PORT)
        │
        ▼
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 │  etl-coverage │     │ company-     │     │ idea-        │
 │               │     │ profile      │     │ generation   │
 └──────────────┘     └──────┬───────┘     └──────┬───────┘
                             │ reads profile        │ surfaces candidates
                             ▼                      ▼
                      ┌──────────────┐     ┌──────────────┐
                      │ thesis-      │◄────│ sector-      │
                      │ tracker      │     │ overview     │
                      └──────┬───────┘     └──────────────┘
                             │ reads thesis
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                  ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ earnings-    │  │ earnings-    │  │ portfolio-   │
    │ analysis     │  │ preview      │  │ analyst      │
    └──────┬───────┘  └──────────────┘  └──────┬───────┘
           │ triggers thesis update             │ reads portfolio API
           ▼                                    ▼
    ┌──────────────┐                    ┌──────────────┐
    │ model-       │                    │ risk-        │
    │ update       │                    │ manager      │
    └──────────────┘                    └──────┬───────┘
                                               │
           ┌───────────────────────────────────┘
           ▼
    ┌──────────────┐     ┌──────────────┐
    │ morning-     │────▶│ fund-        │
    │ briefing     │     │ manager      │
    └──────────────┘     └──────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ knowledge-   │
                         │ base         │
                         └──────────────┘

  Skills read from REST API (data + portfolio) and other skill artifacts.
  No skill invokes another skill directly.
```

---

*Last updated: 2025-03-25*
