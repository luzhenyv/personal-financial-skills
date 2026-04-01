# UPGRADE PLAN — From Research Tool to Personal Hedge Fund

> Synthesized from a Socratic design session, April 2026.
> This plan upgrades the existing Mini Bloomberg + Skills system into a complete
> personal investment operating system with AI-enforced discipline.

---

## The Diagnosis

The system currently has a **brain** (research + analysis agents) but lacks:

- A **spine** — principles and discipline enforcement
- A **nervous system** — real-time portfolio state + stop loss monitoring
- A **memory** — decision logging, retrospectives, learning loop
- A **senses** — macro environment awareness (Fed, yields, VIX, sectors)
- A **rhythm** — a daily ritual that replaces anxiety with structured attention

This plan addresses all five gaps in priority order.

---

## Investment Philosophy (The "Edge")

**AI-era GARP** — Growth at a Reasonable Price, with a macro conviction that AI transformation is the secular tailwind of the decade, and Mean Reversion as the discipline that prevents overpaying for that tailwind.

Core beliefs:
- The market is a machine with its own running laws (mean reversion, cycles)
- AI will reshape all industries — many companies will structurally benefit
- No single valuation metric is sufficient — multi-indicator decision-making (DCF, PE, PEG, macro, sentiment)
- Intrinsic value exists and prices eventually converge to it

---

## Portfolio Framework (The Rules)

### Allocation Rules

| Bucket | Allocation (of 80% equity) | Max Positions | Strategy |
|--------|---------------------------|---------------|----------|
| Equity total | 80% of assets | 10 hard cap | — |
| Cash reserve | 20% of assets | — | Dry powder |
| Mag 7 | ~40% of equity | ≤ 4 | Core holdings, thesis-driven |
| AI-benefit / Mid-cap | ~40% of equity | 4-6 | Growth at reasonable price |
| Small / Speculative | ~10% of equity | ≤ 2 | Higher risk, tighter stops |

### Entry Rules

| Context | Strategy | Logic |
|---------|----------|-------|
| New sector / first entry | Right-side only | Wait for trend confirmation |
| Averaging down on existing | Left-side only | Only if thesis is intact |
| Chasing a confirmed rally | Right-side, scale in | Reserve cash for later tranches |

### Exit / Stop Loss Rules

| Position Type | Stop Loss Type | Rule | Example |
|---------------|---------------|------|---------|
| Large cap, familiar | Thesis invalidation | Specific KPI breach triggers alert | MSFT: AI revenue growth < 5% QoQ → reduce |
| Small cap, speculative | Price-based | Percentage drop from cost basis | -15% → exit |
| Any position | Overvaluation | Price significantly exceeds intrinsic value | Trim or exit |

### The 5 Core Principles (v1.0)

1. **Only buy companies I believe are structurally benefiting from AI transformation**
2. **Don't overpay — wait for price to reflect reasonable intrinsic value, not hype**
3. **Cut losses before they become existential — enforce stop loss rules**
4. **Understand why I bought before I sell — every position has a documented thesis**
5. **If the thesis breaks, the position breaks — don't hold for price recovery alone**

---

## The Human + AI Contract

```
HUMAN (CIO) responsibilities:        AI (Agent) responsibilities:
  ✦ Buy/sell decisions                  ✦ Monitor thesis KPIs continuously
  ✦ Thesis construction                ✦ Trigger stop loss alerts
  ✦ Macro conviction & override         ✦ Enforce logging (never let you skip)
  ✦ Final trade execution               ✦ Morning briefing & evening review
  ✦ Principle evolution                  ✦ Challenge you when you violate rules
                                        ✦ Paper trading: obey rules mechanically
                                        ✦ Retrospectives: extract lessons
```

When the agent triggers a stop loss or principle violation:
> *"MSFT Q2 AI revenue growth was 3.2%, below your 5% threshold. Your stop loss rule says reduce. Do you want to: (a) execute, (b) extend one quarter, (c) revise the rule?"*

Option (c) forces a **conscious** principle update — never a silent ignore.

---

## The Daily Ritual (1 Hour)

The system's most important output is not a report — it's a **structured daily ritual** that replaces anxious price-checking with purposeful attention.

### Pre-Market (20 min, before open)

| Step | Duration | What the Agent Delivers |
|------|----------|------------------------|
| Macro pulse | 3 min | Futures, VIX, 10Y yield, DXY → one sentence: "Risk-on" or "Risk-off" |
| Portfolio health | 7 min | Each position vs. thesis KPIs, stop loss proximity, upcoming earnings |
| Today's action | 5 min | Is anything actionable? If not: "No action needed. Hold." |
| Log intent | 5 min | Any planned trades? Agent records reasoning *before* the market opens |

### During Market (Permission-Based Only)

**Only open the portfolio if:**
- Agent sent an alert (stop loss breach, breaking news, earnings drop)
- You have a planned trade to execute from the morning ritual
- An earnings report just dropped for a position you hold

**Otherwise: the morning briefing told you everything you need.** Close the tab.

### Post-Market (20 min, after close)

| Step | Duration | What the Agent Delivers |
|------|----------|------------------------|
| Day summary | 5 min | Price action, thesis-relevant news, unusual volume |
| Trade log | 5 min | Did you trade? Log it. If not: "No trades. Thesis intact." |
| Anxiety check | 5 min | Rate 1-5. Override any urge? This is behavioral data. |
| Tomorrow's focus | 5 min | Scheduled events, positions to watch, one question to research |

### Weekly (20 min, Friday post-market)

- Portfolio vs. SPY this week
- Decisions made: were they principled?
- Any principle violations?
- One lesson to carry forward

### Monthly (1 hour, last Friday)

- Full portfolio review against thesis health
- Paper portfolio vs. actual vs. SPY comparison
- Principle update: add, revise, or reaffirm
- One-page written reflection

---

## Architecture Upgrades

### Current State (March 2025 → April 2026)

```
DATA PLANE    ✅ SEC EDGAR + prices + financials for 30 companies
INTEL PLANE   ✅ 14 skills built (company-profile through fund-manager)
PRESENTATION  ✅ Streamlit dashboard with profile + thesis + earnings pages
```

### What's Missing (Mapped to Gaps)

```
┌──────────────────────────────────────────────────────────────┐
│  GAP 1 — PRINCIPLES LAYER (the spine)            ← NEW      │
│    investment_handbook.md    — living principles              │
│    decision_log.json        — every trade + reason + outcome │
│    retrospective engine     — closed position review         │
│    principle conflict check — pre-trade validation           │
├──────────────────────────────────────────────────────────────┤
│  GAP 2 — PORTFOLIO STATE (the nervous system)    ← NEW      │
│    portfolio.json           — positions, cost basis, thesis  │
│    stop_loss_monitor        — rule-based alerts per position │
│    paper_portfolio.json     — shadow portfolio (rules only)  │
│    portfolio sync ritual    — human ↔ system reconciliation  │
├──────────────────────────────────────────────────────────────┤
│  GAP 3 — MACRO DATA (the senses)                ← NEW      │
│    FRED ETL                 — Fed rate, yields, VIX, CPI    │
│    Sector ETF tracking      — XLK, XLV, XLF relative perf   │
│    macro_snapshot.json      — daily context for briefing     │
├──────────────────────────────────────────────────────────────┤
│  GAP 4 — DAILY RITUAL (the rhythm)              ← NEW      │
│    morning_briefing upgrade — macro + portfolio + action     │
│    evening_review agent     — trade log + anxiety + tomorrow │
│    weekly_retro agent       — SPY comparison + lessons       │
├──────────────────────────────────────────────────────────────┤
│  GAP 5 — LEARNING LOOP (the memory)             ← UPGRADE   │
│    position_retrospective   — post-close analysis            │
│    principle_evolution_log  — how rules changed and why      │
│    override_tracker         — human vs AI recommendation     │
│    behavioral_analytics     — anxiety vs. returns correl.    │
└──────────────────────────────────────────────────────────────┘
```

---

## Build Sequence (90-Day Plan)

### Week 1 — The Foundation (No Code, Just Writing)

**Goal: The system can't enforce rules it doesn't know.**

| Task | Output | Location |
|------|--------|----------|
| Write investment handbook | `investment_handbook.md` | `data/artifacts/_portfolio/` |
| Record current positions | `portfolio.json` | `data/artifacts/_portfolio/` |
| Write stop loss rules per position | Embedded in `portfolio.json` | — |
| Retroactively document why you bought each position | Thesis artifacts per ticker | `data/artifacts/{ticker}/thesis/` |

### Weeks 2-3 — Wire The Stop Loss Monitor

**Goal: Prove the alert loop works with one stock.**

| Task | Detail |
|------|--------|
| Pick one stock (MSFT or NVDA) | Define KPI rule: `ai_revenue_growth_qoq > 5%` |
| Add thesis KPI monitoring to morning briefing | Agent checks KPI vs. threshold |
| Build alert flow | KPI breach → agent prompts: execute / extend / revise |
| Wire portfolio.json reader | Morning briefing reads your actual positions |

**New skill or upgrade**: `portfolio-analyst` skill — reads `portfolio.json`, computes allocation, flags stop loss proximity, generates portfolio health section for morning briefing.

### Weeks 3-4 — Decision Logging (The Compliance Fix)

**Goal: Every trade gets logged with zero friction.**

| Task | Detail |
|------|--------|
| Morning briefing ends with: "Any planned trades?" | Agent records pre-trade reasoning |
| Evening review always asks: "Did you trade today?" | If yes: log. If no: "Thesis intact" |
| Decision log schema | `{date, ticker, action, price, reasoning, principle_ref, thesis_ref}` |
| One-sentence minimum | Lower the bar so it always gets done |

### Month 2 — Macro Awareness

**Goal: Morning briefing becomes actually useful for market context.**

| Task | Detail |
|------|--------|
| FRED API ETL | 6 indicators: Fed funds, 10Y-2Y spread, VIX, DXY, CPI YoY, ISM |
| Sector ETF tracking | XLK, XLV, XLF, XLE — relative strength vs. SPY |
| `macro_snapshot.json` | Daily artifact, consumed by morning briefing |
| One-sentence macro interpretation | "Risk environment: cautious. Yields rising, VIX elevated." |

**New skill**: `macro-monitor` — daily FRED pull + sector ETL + snapshot generation.

**API endpoint additions**:
- `GET /api/macro/snapshot` — latest macro indicators
- `GET /api/macro/history?indicator=VIX&period=1y` — historical macro data

### Month 2-3 — Principles Engine MVP

**Goal: Close the learning loop on the first position.**

| Task | Detail |
|------|--------|
| Post-close retrospective prompt | 3 questions: thesis correct? timing correct? what differently? |
| Handbook update flow | Retrospective → principle suggestion → human approval → handbook updated |
| Pre-trade principle check | Before any new position: "Does this violate Principle 2?" |
| Principle violation tracker | Log when you override a principle + reason |

### Month 3 — Paper Trading Shadow

**Goal: Measure the cost of human emotion vs. mechanical rules.**

| Task | Detail |
|------|--------|
| `paper_portfolio.json` | Starts as a copy of your actual portfolio |
| Paper trading agent | Follows handbook rules mechanically — no emotion, no override |
| Monthly comparison | Paper vs. actual vs. SPY, with attribution |
| Override cost calculation | "You overrode the stop loss 3 times. Net impact: -$X" |

---

## New Skills to Build

| Skill | Purpose | Priority |
|-------|---------|----------|
| `portfolio-analyst` | Portfolio state, allocation, stop loss monitoring, P&L | P0 — Week 2 |
| `macro-monitor` | FRED indicators, sector ETFs, macro snapshot | P1 — Month 2 |
| `daily-ritual` | Morning briefing upgrade + evening review + weekly retro | P1 — Month 1-2 |
| `principles-engine` | Handbook CRUD, retrospectives, pre-trade checks, violation tracker | P1 — Month 2-3 |
| `paper-trader` | Shadow portfolio management, mechanical rule execution | P2 — Month 3 |

### Skills to Upgrade

| Existing Skill | Upgrade | When |
|---------------|---------|------|
| `morning-briefing` | Add macro pulse, portfolio health, "action or hold" section | Month 1-2 |
| `thesis-tracker` | Add KPI threshold rules, auto health check on earnings | Week 2-3 |
| `fund-manager` | Integrate principle conflict check before decisions | Month 2-3 |
| `risk-manager` | Read portfolio.json for real position data | Week 2-3 |

---

## Data Layer Upgrades

### New Data Sources (All Free)

| Source | Data | API | Cost |
|--------|------|-----|------|
| FRED (St. Louis Fed) | Fed funds, yields, CPI, ISM, unemployment | `api.stlouisfed.org` | Free |
| Yahoo Finance | Sector ETFs (XLK, XLV, etc.), VIX, DXY | yfinance | Free |
| SEC EDGAR 13F | Institutional ownership changes (quarterly) | EDGAR | Free |

### New API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/portfolio/positions` | Current portfolio state |
| `GET /api/portfolio/pnl` | P&L per position and total |
| `GET /api/portfolio/allocation` | Allocation by bucket / sector |
| `GET /api/macro/snapshot` | Latest macro indicators |
| `GET /api/portfolio/decisions` | Decision log with reasoning |
| `GET /api/portfolio/paper` | Paper portfolio state + comparison |

---

## The Meta-Experiment

This system is also a laboratory for answering:

> *"What does a high-stakes, knowledge-intensive, human+AI collaborative workflow look like when done well?"*

### Measurable Research Questions

1. **Which decision classes should be AI-led vs. human-led?**
   - Track: AI recommendations, human overrides, outcomes
   - Metric: override cost/benefit over 12 months

2. **Does formalized principle-tracking improve returns?**
   - Track: decisions aligned with principles vs. violations
   - Metric: risk-adjusted return of principled vs. unprincipled trades

3. **Does the daily ritual reduce behavioral drag?**
   - Track: anxiety scores, checking frequency, overtrade count
   - Metric: trading frequency before/after ritual adoption

4. **Can a paper portfolio (rules only, no emotion) beat the human?**
   - Track: paper vs. actual portfolio monthly
   - Metric: cumulative return delta over 6-12 months

### 12-Month Deliverables

- **Track record**: documented decisions with reasoning and outcomes
- **Living handbook**: principles evolved through real market contact
- **Behavioral profile**: when you add alpha, when you destroy it
- **Methodology paper**: case study in AI-augmented personal investing
- **System**: that knows your rules better than you remember them

---

## Success Metrics (Revised)

| Metric | Target | Measured By |
|--------|--------|-------------|
| Beat SPY (risk-adjusted) | > 0% alpha over 12 months | Monthly comparison |
| Decision logging rate | > 90% of trades logged with reasoning | Decision log completeness |
| Morning ritual adherence | > 25 days/month for 6 months | Briefing artifact timestamps |
| Principle violations caught | 100% flagged before trade | Pre-trade check logs |
| Retrospectives completed | Every closed position reviewed | Retrospective artifacts |
| Anxiety trend | Declining over 6 months | Self-reported daily scores |
| Paper vs. actual delta | Measured and explained | Monthly attribution |

---

## Three Horizons

```
HORIZON 1 (0-3 months): "Make the system your co-pilot"
  → Portfolio state wired in
  → Stop loss monitoring live
  → Daily ritual operational
  → Decision logging at >90%
  
HORIZON 2 (3-9 months): "Close the learning loop"  
  → Principles engine running
  → First retrospective completed
  → Paper trading shadow active
  → Macro awareness in briefings
  
HORIZON 3 (9-12 months): "Validate and publish"
  → 12 months of tracked decisions
  → Paper vs. actual comparison
  → Methodology write-up
  → One publishable insight about human+AI workflow
```

---

## What This Is Not

- **Not a trading bot** — you make all buy/sell decisions
- **Not a hedge fund** — you manage family money, not outside capital
- **Not a replacement for judgment** — it's a cognitive prosthetic that makes your judgment *consistent and accountable*
- **Not over-engineered** — start with text files and simple JSON, upgrade only when the habit is proven

---

## What This Is

> A systematized, AI-augmented, learning-first personal investment framework, managed by you with AI as analyst + memory + discipline enforcer, running on a personal Bloomberg infrastructure, with the secondary goal of proving a methodology for AI-augmented knowledge work.

The hedge fund clothing — the agents, the Bloomberg, the fund manager CLI — is scaffolding. The building underneath is: **a system that makes you accountable to your own best thinking, captures your insights before you forget them, protects you from your own anxiety, and learns from every decision you make.**

---

*Created: 2026-04-02*
*Based on: Socratic design session exploring personal hedge fund architecture*
