# Skill Development Plan

> Master plan for evolving the skill system from research platform to full portfolio management.

---

## Current Skill Inventory

| # | Skill | Path | Status | Origin |
|---|-------|------|--------|--------|
| 1 | **company-profile** | `skills/company-profile/` | ✅ Production | Adapted from equity-research `initiating-coverage` |
| 2 | **thesis-tracker** | `skills/thesis-tracker/` | ✅ Production | Adapted from equity-research `thesis-tracker` |
| 3 | **etl-coverage** | `skills/etl-coverage/` | ✅ Production | Original |

---

## Part 1: Refactoring Existing Skills

### 1.1 company-profile — Moderate Refactor

The skill works but has structural gaps that will compound as we add more skills that depend on profile data.

| Issue | What to do | Priority |
|-------|-----------|----------|
| **Task 1 is fully AI-driven** | Extract 10-K parsing into a reusable script (`scripts/extract_10k.py`). Keep AI interpretation for narrative fields, but structured field extraction (revenue segments, executives) should be deterministic | P1 |
| **No valuation section** | Add DCF summary to profile output by calling `GET /api/analysis/valuation/{ticker}`. The equity-research `initiating-coverage` Task 3 is a good reference. Profile should include fair value estimate | P2 |
| **Comps depend on yfinance live calls** | `build_comps.py` calls yfinance at runtime. Add caching layer — write `comps_cache.json` with TTL. Comps data changes slowly; no need to re-fetch every run | P2 |
| **No markdown-to-DB persistence for Task 1** | Task 3 posts report to DB, but Task 1 JSON artifacts are only local. Add `POST /api/analysis/reports` call after Task 1 to persist structured data too | P3 |
| **Config triggers are passive** | `config.yaml` defines 10-K trigger, but no active listener. Wire into task dispatcher event matching | P2 |

### 1.2 thesis-tracker — Light Refactor

The best-structured skill. Minimal changes needed, mostly extensions.

| Issue | What to do | Priority |
|-------|-----------|----------|
| **Assumption weights not validated** | Add validation in `thesis_cli.py create` that weights sum to 1.0 (or auto-normalize) | P1 |
| **Subjective score always 50 in CLI** | Design a structured prompt template for the agent to produce real subjective scores. Store the prompt in `references/health-check-prompt.md` | P1 |
| **Catalyst resolution doesn't auto-trigger update** | When resolving a catalyst via `catalyst --resolve`, auto-prompt for update flow (or create a task in the queue) | P2 |
| **No portfolio integration point** | Add `position_size`, `entry_price`, `current_pnl` fields to `thesis.json` (optional fields). The upcoming portfolio skill will populate these | P2 |
| **Health check `--all` has no summary view** | Generate a portfolio-wide health summary markdown when running `check --all` | P2 |

### 1.3 etl-coverage — No Refactor Needed

Working as designed. Low coupling, clear single purpose.

### 1.4 Shared Library (_lib/) — Moderate Refactor

| Issue | What to do | Priority |
|-------|-----------|----------|
| **No portfolio_io.py** | Create `skills/_lib/portfolio_io.py` for position and portfolio artifact I/O (mirrors `thesis_io.py` pattern) | P1 |
| **api_client.py is thin** | Expand to cover all REST endpoints needed by new skills (prices with date range, multiple tickers batch, etc.) | P1 |
| **No shared formatting utils** | Extract number formatting (`fmt_b`, `fmt_pct`, etc.) from `generate_report.py` into `_lib/format_utils.py` | P3 |
| **No date/time helpers** | Add fiscal quarter detection, earnings date lookup, TTM period calculation | P2 |

---

## Part 2: New Skills Development

### Skill Map (Full Vision)

```
skills/
  _lib/                          # Shared utilities (no pfs.* imports)
  ├── api_client.py              # REST API wrapper        ✅ exists
  ├── artifact_io.py             # Versioned artifact I/O  ✅ exists
  ├── thesis_io.py               # Thesis file operations  ✅ exists
  ├── portfolio_io.py            # Portfolio file ops      🆕 Phase 2
  ├── format_utils.py            # Number formatting       🆕 Phase 1
  ├── task_client.py             # Task queue client       ✅ exists
  └── mcp_helpers.py             # Data fetching           ✅ exists
  
  company-profile/               # Company tearsheet       ✅ exists
  thesis-tracker/                # Investment thesis CRUD  ✅ exists
  etl-coverage/                  # Data quality audit      ✅ exists

  portfolio-manager/             # 🆕 Phase 2 — Position & P&L tracking
  earnings-analysis/             # 🆕 Phase 3 — Post-earnings reports
  earnings-preview/              # 🆕 Phase 3 — Pre-earnings scenarios
  risk-manager/                  # 🆕 Phase 3 — Portfolio risk metrics
  morning-briefing/              # 🆕 Phase 3 — Daily research digest
  model-update/                  # 🆕 Phase 3 — Financial model maintenance
  idea-generation/               # 🆕 Phase 4 — Stock screening pipeline
  sector-overview/               # 🆕 Phase 4 — Industry landscape reports
  catalyst-calendar/             # 🆕 Phase 4 — Cross-portfolio event tracking
  knowledge-base/                # 🆕 Phase 5 — External research ingestion
  fund-manager/                  # 🆕 Phase 4 — Multi-agent decision synthesis
```

---

### Phase 2 Skills (Portfolio Management)

#### 2.1 portfolio-manager (P0 — Build First)

**Purpose:** Track positions, calculate P&L, manage allocation. The central nervous system of the fund.

**Adapted from:** Original design. No direct equity-research equivalent (institutional funds use Bloomberg PORT / internal systems).

**Artifacts:** `data/artifacts/_portfolio/`

```
data/artifacts/_portfolio/
  portfolio.json            # Master portfolio state
  transactions.json         # Append-only trade log
  snapshots/
    2025-03-25.json         # Daily portfolio snapshots
  allocation.json           # Current allocation breakdown
```

**portfolio.json schema:**

```json
{
  "schema_version": "1.0",
  "updated_at": "2025-03-25T16:00:00Z",
  "cash": 50000.00,
  "positions": [
    {
      "ticker": "NVDA",
      "shares": 100,
      "avg_cost": 125.50,
      "current_price": 145.20,
      "market_value": 14520.00,
      "unrealized_pnl": 1970.00,
      "unrealized_pnl_pct": 0.157,
      "weight_pct": 0.145,
      "thesis_status": "active",
      "thesis_health_score": 78,
      "sector": "Technology",
      "conviction": "high",
      "position_type": "long"
    }
  ],
  "total_market_value": 100000.00,
  "total_cost_basis": 92000.00,
  "total_unrealized_pnl": 8000.00,
  "total_realized_pnl": 2500.00,
  "inception_date": "2025-01-15",
  "benchmark": "SPY"
}
```

**transactions.json schema:**

```json
{
  "schema_version": "1.0",
  "transactions": [
    {
      "id": 1,
      "date": "2025-01-15",
      "ticker": "NVDA",
      "action": "buy",
      "shares": 50,
      "price": 120.00,
      "total": 6000.00,
      "fees": 0,
      "notes": "Initial position — data center thesis",
      "thesis_ref": "data/artifacts/NVDA/thesis/thesis.json"
    }
  ]
}
```

**CLI (5 subcommands):**

```bash
# Record a trade
uv run python skills/portfolio-manager/scripts/portfolio_cli.py buy NVDA --shares 50 --price 120.00 --notes "Initial position"
uv run python skills/portfolio-manager/scripts/portfolio_cli.py sell NVDA --shares 20 --price 150.00 --notes "Trimming after 25% gain"

# Portfolio snapshot (fetches current prices, updates portfolio.json)
uv run python skills/portfolio-manager/scripts/portfolio_cli.py snapshot

# Allocation analysis
uv run python skills/portfolio-manager/scripts/portfolio_cli.py allocation

# Full portfolio report (markdown)
uv run python skills/portfolio-manager/scripts/portfolio_cli.py report
```

**Key design decisions:**
- **Append-only transactions** — never edit trade history, only append
- **Snapshot-based P&L** — daily snapshots enable historical performance tracking
- **Thesis linkage** — every position links to its thesis artifact; orphaned positions (no thesis) flagged as warnings
- **Cash tracking** — cash balance updated on every buy/sell
- **No broker integration (v1)** — manual trade entry. Broker API integration is a future enhancement

**Data flow:**
```
User logs trade → transactions.json (append) → portfolio.json (recalculated)
                                              → snapshot/{date}.json (daily)
REST API prices → portfolio_cli.py snapshot   → portfolio.json (prices updated)
thesis_io.py    → portfolio.json              → thesis_health_score per position
```

**Cross-skill integration:**
- **Reads from thesis-tracker** — thesis status and health score per position
- **Reads from REST API** — current prices for portfolio valuation
- **Read by risk-manager** — portfolio-level risk analysis
- **Read by morning-briefing** — daily P&L summary
- **Read by fund-manager** — portfolio state for decision-making

**Streamlit page:** New `pages/4_portfolio.py` — positions table, allocation pie chart, P&L waterfall, performance vs. benchmark

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

**REST API endpoints needed:**
- `GET /api/filings/{ticker}/?form_type=10-Q` — latest quarterly filing
- `GET /api/financials/{ticker}/income-statements?years=2` — compare QoQ / YoY
- `GET /api/financials/{ticker}/metrics` — margin trends

**New REST API endpoints to build:**
- `GET /api/financials/{ticker}/quarterly?quarters=8` — quarterly breakdown (not just annual)

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

**Cross-skill reads:**
- portfolio-manager — positions, allocation
- thesis-tracker — health scores per position
- REST API — prices for beta/correlation calculation

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
2. Query REST API across all ingested companies
3. Rank and filter by criteria
4. Generate one-pager per idea candidate
5. Flag top ideas for full company-profile workflow

**CLI:**

```bash
uv run python skills/idea-generation/scripts/screen.py --type growth --min-revenue-growth 0.20
uv run python skills/idea-generation/scripts/screen.py --type value --max-pe 15 --min-fcf-yield 0.05
```

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
Week 1-2:
  ☐ Refactor thesis-tracker (weight validation, subjective scoring template)
  ☐ Create skills/_lib/portfolio_io.py
  ☐ Create skills/_lib/format_utils.py  
  ☐ Build portfolio-manager skill (CLI + artifacts)
  ☐ Add portfolio.json + transactions.json schemas

Week 3:
  ☐ Build Streamlit portfolio page (positions table, allocation chart, P&L)
  ☐ Wire portfolio-manager to thesis-tracker (thesis health per position)
  ☐ Build portfolio snapshot automation (Prefect flow, daily after market close)

Week 4:
  ☐ Build risk-manager skill (risk metrics, alerts, rules)
  ☐ Wire risk-manager to portfolio-manager
  ☐ Add risk section to Streamlit dashboard
```

### Phase 3: Earnings & Events (Target: May-June 2025)

```
Month 1 (May):
  ☐ Build earnings-analysis skill (4-task workflow)
  ☐ Add quarterly financials endpoint to REST API
  ☐ Wire earnings-analysis → thesis-tracker auto-update
  ☐ Build earnings-preview skill (3-task workflow)
  ☐ Build morning-briefing skill

Month 2 (June):
  ☐ Wire Prefect filing_check → auto-trigger earnings-analysis
  ☐ Wire earnings date calendar → auto-trigger earnings-preview
  ☐ Build catalyst-calendar skill (cross-portfolio aggregation)
  ☐ Refactor company-profile (10-K extraction script, valuation section)
```

### Phase 4: Multi-Agent Intelligence (Target: Q3 2025)

```
  ☐ Build idea-generation skill (screening pipeline)
  ☐ Build sector-overview skill
  ☐ Build model-update skill
  ☐ Build fund-manager skill (multi-signal synthesis)
  ☐ Design agent debate protocol (fund-manager reads all analyst artifacts)
```

### Phase 5: Knowledge Platform (Target: Q4 2025)

```
  ☐ Build knowledge-base skill (PDF ingestion, structured extraction)
  ☐ Build cross-reference engine (knowledge → thesis → morning briefing)
  ☐ Design research report templates for external consumption
```

---

## Part 4: API Extensions Needed

New REST API endpoints required to support upcoming skills:

| Endpoint | Needed by | Purpose |
|----------|-----------|---------|
| `GET /api/financials/{ticker}/quarterly?quarters=8` | earnings-analysis | Quarterly breakdown for QoQ comparison |
| `GET /api/financials/{ticker}/estimates` | earnings-preview | Consensus estimates (if we ingest them) |
| `GET /api/prices/batch?tickers=X,Y,Z` | portfolio-manager | Batch price fetch for portfolio valuation |
| `GET /api/analysis/risk/{ticker}` | risk-manager | Beta, correlation, volatility for a ticker |
| `GET /api/analysis/screen` | idea-generation | Parameterized multi-company screening |
| `POST /api/knowledge/ingest` | knowledge-base | Document ingestion endpoint |

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
8. **_lib/ for shared code** — No `pfs.*` imports in skills. All shared utilities live in `skills/_lib/`
9. **References folder for prompts** — Structured AI prompts live in `references/` not hardcoded in scripts
10. **POST to DB after artifact write** — Call `POST /api/analysis/reports` to persist reports for dashboard access

---

## Appendix: Skill Dependency Graph

```
 DATA PLANE (REST API)
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
    │ analysis     │  │ preview      │  │ manager      │
    └──────┬───────┘  └──────────────┘  └──────┬───────┘
           │ triggers thesis update             │ reads positions
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

  Arrows = "reads artifacts from"
  No skill invokes another skill directly.
```

---

*Last updated: 2025-03-25*
