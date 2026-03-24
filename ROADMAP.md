# ROADMAP — AI-Driven Personal Hedge Fund

> Where it came from, where it is, where it's going.

---

## Origin Story

This project started from reading Ray Dalio's *Principles* — and asking one question: **What if a solo investor could run a systematic, institutional-quality investment process with AI agents doing the analyst work?**

Bridgewater's edge is radical transparency, systematic decision-making, and a team of 1,500+ people executing research workflows. We replace the people with AI agents, keep the systematic rigor, and add one advantage Bridgewater doesn't have: we can iterate on our process in minutes, not months.

### Inspirations

| Source | What we took |
|--------|-------------|
| **Ray Dalio / Bridgewater** | Systematic principles-based investing, radical transparency, machine-driven decisions |
| **Anthropic's equity-research plugin** | Skill-based architecture for equity research workflows (initiating coverage, earnings analysis, thesis tracking, etc.) — [github.com/anthropics/financial-services-plugins](https://github.com/anthropics/financial-services-plugins) |
| **TradingAgents (paper)** | Multi-agent LLM trading framework — specialized analyst roles (fundamentals, sentiment, news, technicals), risk management agent, fund manager agent combining signals into trading decisions, [GitHub](https://github.com/TauricResearch/TradingAgents) |
| **Mini Bloomberg (self-built)** | The data plane — ETL from SEC EDGAR + yfinance + Alpha Vantage into a structured PostgreSQL database, served by a FastAPI REST API |

### Core Thesis (about the project itself)

> A well-structured skill system + reliable data pipeline + AI agents = one person operating at the research output of a 10-analyst team.

Not a trading bot. Not a "vibe-based" chatbot with market opinions. An **institutional-quality research and portfolio management system** where every decision is grounded in data, every thesis is tracked and falsifiable, and every position has a documented reason for entry and exit.

---

## Architecture (Current)

Three decoupled planes:

```
┌─────────────────────────────────────────────────────────┐
│  PLANE 1 · DATA PLANE (Mini Bloomberg)                  │
│  ETL → PostgreSQL + data/raw/                           │
│  Exposed via FastAPI REST API (read-only contract)      │
│  30 companies ingested, 5 years of data each            │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────┐
│  PLANE 2 · INTELLIGENCE PLANE (Agent + Skills)          │
│  AI agent reads REST API → runs skill workflows →       │
│  outputs versioned artifacts to data/artifacts/         │
│  Skills: company-profile, thesis-tracker, etl-coverage  │
└──────────────────────┬──────────────────────────────────┘
                       │ Reads artifacts
┌──────────────────────▼──────────────────────────────────┐
│  PLANE 3 · PRESENTATION PLANE (Streamlit)               │
│  Renders artifacts + live API data                      │
│  Never writes. Never triggers ETL.                      │
└─────────────────────────────────────────────────────────┘
```

---

## Current Status (March 2025)

### What's Built & Working

| Component | Status | Notes |
|-----------|--------|-------|
| **Data Plane** | ✅ Production | PostgreSQL + FastAPI with 30 companies, 5yr data |
| **REST API** | ✅ Full | Companies, financials, filings, metrics, prices, segments, analysis endpoints |
| **ETL Pipeline** | ✅ Stable | SEC EDGAR XBRL + yfinance validation + Alpha Vantage conflict resolution |
| **Company Profile skill** | ✅ Ready | 3-task workflow: research → comps → report |
| **Thesis Tracker skill** | ✅ Ready | 5-subcommand CLI: create, update, check, catalyst, report |
| **ETL Coverage skill** | ✅ Ready | Data quality auditing |
| **Streamlit Dashboard** | ✅ Basic | Company profile + thesis tracker pages |
| **Task Dispatcher** | ✅ Built | Polls REST API, dispatches to OpenClaw, commits artifacts |
| **Two-Server Topology** | 📋 Designed | Migration plan written, not yet deployed |
| **Prefect Scheduling** | ✅ Configured | Flows for price sync, filing checks |

### What's Missing

| Gap | Impact |
|-----|--------|
| **No portfolio tracking** | Can't track positions, P&L, allocation |
| **No earnings analysis** | Can't react systematically to quarterly reports |
| **No risk management** | No portfolio-level risk metrics, no drawdown alerts |
| **No multi-agent collaboration** | Each skill runs independently, no agent debate or cross-validation |
| **No idea generation pipeline** | No systematic screening for new ideas |
| **No morning briefing** | No automated daily research digest |
| **No knowledge base** | Can't ingest external research (Morningstar, sell-side reports) |
| **No financial modeling** | No forward projections, sensitivity analysis beyond basic DCF |

---

## Where It's Going

### Vision: The One-Person Hedge Fund

```
Phase 1 — RESEARCH PLATFORM (← we are here)
  Company profiles, thesis tracking, data quality
  "Know what you own and why"

Phase 2 — PORTFOLIO MANAGEMENT
  Position tracking, P&L, allocation, risk metrics
  "Manage the book"

Phase 3 — EARNINGS & EVENT REACTION
  Earnings analysis, catalyst tracking, event-driven updates
  "React fast, react systematically"

Phase 4 — MULTI-AGENT INTELLIGENCE
  Specialized analyst agents (fundamental, technical, sentiment, news)
  Risk management agent, fund manager agent combining signals
  "The AI analyst team"

Phase 5 — KNOWLEDGE PLATFORM
  Ingest external research, build knowledge base, generate reports
  "Know what the market knows, then know more"

Phase 6 — MONETIZATION (Aspirational)
  Generate institutional-quality reports for sale
  Build proprietary research products
  "Sell knowledge"
```

### Phase 2: Portfolio Management (Next)

The immediate next step. We need to track what we own, how it's performing, and whether our allocation makes sense.

**New capabilities:**
- Track positions (entry date, price, size, current value)
- Real-time P&L per position and total portfolio
- Allocation analysis (by sector, by conviction level, by thesis strength)
- Rebalancing suggestions based on thesis health scores
- Position sizing rules (max position size, correlation limits)
- Transaction log (buys, sells, dividends)

**Key principle from Dalio:** Every position must have a clear, documented thesis. The thesis-tracker skill already does this — portfolio management extends it with execution tracking.

### Phase 3: Earnings & Event Reaction

**New capabilities:**
- Pre-earnings preview (consensus, key metrics to watch, bull/bear scenarios)
- Post-earnings analysis (beat/miss, guidance changes, thesis impact)
- Automatic thesis health check triggered by earnings
- Catalyst calendar with event-driven workflows
- 10-K/10-Q section extraction and change detection

### Phase 4: Multi-Agent Intelligence (TradingAgents-Inspired)

Drawing from the TradingAgents paper's multi-agent framework:

```
┌──────────────────────────────────────────────────────────┐
│                   FUND MANAGER AGENT                     │
│   Synthesizes all analyst signals → trading decisions    │
└───────┬──────────┬──────────┬──────────┬────────────────┘
        │          │          │          │
   ┌────▼───┐ ┌───▼────┐ ┌──▼───┐ ┌───▼─────┐
   │FUNDAMTL│ │TECHNLCL│ │ NEWS │ │SENTIMENT│
   │ANALYST │ │ANALYST │ │ANALST│ │ ANALYST │
   └────────┘ └────────┘ └──────┘ └─────────┘
        │          │          │          │
   ┌────▼──────────▼──────────▼──────────▼────────────────┐
   │              RISK MANAGEMENT AGENT                    │
   │   Position limits, correlation, drawdown, VaR        │
   └──────────────────────────────────────────────────────┘
```

**Agents:**
- **Fundamental Analyst** — Earnings quality, growth trajectory, balance sheet health
- **Technical Analyst** — Price action, momentum, support/resistance, volume patterns
- **News Analyst** — News flow, sentiment shifts, management tone changes
- **Sentiment Analyst** — Social media, options flow, short interest, institutional positioning
- **Risk Manager** — Portfolio-level risk, correlation, drawdown limits, position sizing
- **Fund Manager** — Synthesizes analyst inputs, makes final calls, documents reasoning

Each "agent" is implemented as a skill that writes structured artifacts. The fund manager skill reads all analyst artifacts and produces a decision artifact.

### Phase 5: Knowledge Platform

**New capabilities:**
- Ingest external research PDFs/reports into structured knowledge base
- Sector overview generation (market dynamics, competitive positioning)
- Cross-company thematic analysis (e.g., "AI infrastructure spending across my portfolio")
- Morning briefing note (overnight developments, what matters today)
- Research report generation for external consumption

---

## Design Principles (Immutable)

These don't change no matter how big the system gets:

1. **Data is sacred** — ETL is the only writer to the database. Period.
2. **Every position needs a thesis** — No position without a documented, falsifiable reason.
3. **Skills are independent** — Skills read artifacts, never call each other. Any skill can re-run alone.
4. **Artifacts are versioned** — Git tracks every analysis change. You can always diff and audit.
5. **Agent never hallucinates into the database** — Agent reads via REST API, writes only artifacts.
6. **Systematic over discretionary** — Rules-based decision framework. The agent follows the process, not vibes.
7. **Transparency** — Every decision artifact includes data sources, reasoning chain, and confidence level.

---

## Success Metrics

How we know the system is working:

| Metric | Target | How measured |
|--------|--------|-------------|
| **Coverage breadth** | 50+ companies with active profiles | Count of `data/artifacts/*/profile/` |
| **Thesis discipline** | Every position has an active, health-checked thesis | `thesis_cli.py check --all` all pass |
| **Reaction speed** | Earnings analysis within 24h of report | Artifact timestamps vs. filing dates |
| **Portfolio tracking** | Real-time P&L and allocation visibility | Dashboard portfolio page |
| **Risk awareness** | No single position > 15% of portfolio | Automated allocation checks |
| **Research output** | 2+ reports/month publishable quality | Manual quality review |
| **System uptime** | ETL + API + Dashboard always available | Health check monitoring |

---

## Tech Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| Database | PostgreSQL 16 (Docker) / SQLite (dev) | ✅ |
| ETL | Python + httpx + SEC EDGAR XBRL | ✅ |
| API | FastAPI | ✅ |
| Agent | Claude + Copilot + OpenClaw | ✅ |
| Scheduling | Prefect | ✅ |
| Dashboard | Streamlit + Plotly | ✅ |
| Artifact storage | Git-tracked JSON + Markdown | ✅ |
| Package manager | uv | ✅ |
| Deployment | Two-server (Mac data + DMIT agent) | 📋 Planned |

---

*Last updated: 2025-03-25*
