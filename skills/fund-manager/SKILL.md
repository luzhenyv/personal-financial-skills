# Fund Manager Skill

> **TradingAgents-inspired decision engine** — synthesizes all skill outputs into actionable trading decisions with human-in-the-loop.

## Inspiration

This skill adapts the [TradingAgents](https://github.com/TauricResearch/TradingAgents) multi-agent framework into PFS's artifact-based architecture:

| TradingAgents Role | PFS Equivalent | Phase |
|---|---|---|
| 4 Analysts (Market, Social, News, Fundamentals) | `collect_signals.py` — gathers from REST API + all skill artifacts | Phase 1 |
| Bull Researcher + Bear Researcher + Research Manager | `generate_debate.py` — structures bull/bear debate scaffold | Phase 2 |
| Aggressive + Conservative + Neutral Debators + Risk Judge | Risk assessment within debate scaffold | Phase 2 |
| Trader + Portfolio Manager | `generate_decision.py` — produces action recommendations | Phase 3 |

**Key Difference:** TradingAgents runs LLM agents in a LangGraph pipeline. PFS collects quantitative signals into structured artifacts, then the AI agent (or human) fills in qualitative reasoning through the review workflow. This gives us:
- Full auditability (every signal is in JSON)
- Human-in-the-loop on every trade (hard rule)
- Cross-skill synthesis (reads thesis, earnings, risk, model artifacts)

## Architecture

```
Phase 1: SIGNAL COLLECTION (≈ TradingAgents Analyst Team)
┌─────────────────────────────────────────────────────────┐
│  collect_signals.py                                      │
│                                                          │
│  REST API → Market signals (momentum, vol, technicals)   │
│  REST API → Fundamental signals (margins, growth, P/E)   │
│  Artifacts → Thesis signals (health score, catalysts)    │
│  API + Art → Risk signals (beta, VaR, drawdown, alerts)  │
│  Artifacts → Earnings signals (surprises, previews)      │
│  Artifacts → Model signals (target price, upside)        │
│                                                          │
│  Output: {date}_signals.json                             │
└──────────────┬──────────────────────────────────────────┘
               │
Phase 2: BULL/BEAR DEBATE (≈ TradingAgents Research + Risk Team)
┌──────────────▼──────────────────────────────────────────┐
│  generate_debate.py                                      │
│                                                          │
│  Per ticker:                                             │
│    Classify signals → bull / bear / neutral              │
│    Build investment debate scaffold                      │
│      Bull case: bull signals + thesis alignment          │
│      Bear case: bear signals + risk factors              │
│    Build risk assessment scaffold                        │
│      Aggressive view + Conservative view + Neutral view  │
│                                                          │
│  Output: {date}_debates.json                             │
└──────────────┬──────────────────────────────────────────┘
               │
Phase 3: TRADING DECISION (≈ TradingAgents Trader + Manager)
┌──────────────▼──────────────────────────────────────────┐
│  generate_decision.py                                    │
│                                                          │
│  Per ticker:                                             │
│    Quantitative scoring (net bull vs bear)               │
│    Preliminary action: BUY / SELL / HOLD / TRIM / ADD    │
│    Decision template with placeholders for agent review  │
│                                                          │
│  Output: {date}_decisions.json + {date}_decisions.md     │
└──────────────┬──────────────────────────────────────────┘
               │
Phase 4: HUMAN REVIEW (≈ TradingAgents Human-in-the-Loop)
┌──────────────▼──────────────────────────────────────────┐
│  fund_cli.py review                                      │
│                                                          │
│  Interactive CLI or agent-driven:                         │
│    Review each position's debate + signals               │
│    Set final action, sizing, reasoning, time horizon     │
│    Status: preliminary → reviewed                        │
│                                                          │
│  NO AUTO-EXECUTION. Human approves every trade.          │
└─────────────────────────────────────────────────────────┘
```

## Artifacts

Output: `data/artifacts/_portfolio/decisions/`

| File | Description |
|------|-------------|
| `{date}_signals.json` | Raw signal bundle from all 6 sources per ticker |
| `{date}_debates.json` | Bull/bear signal classification + debate scaffolds |
| `{date}_decisions.json` | Preliminary + final action decisions |
| `{date}_decisions.md` | Human-readable decision report |

## Signal Sources

The fund manager reads from **all** other skills:

| Signal Source | Artifact / API Path | What it provides |
|---|---|---|
| **Market** | `GET /api/analysis/signals/{ticker}` | Momentum, SMA crossovers, volatility |
| **Fundamentals** | `GET /api/analysis/signals/{ticker}` + `/api/financials/` | P/E, margins, growth, ROE |
| **Thesis** | `data/artifacts/{ticker}/thesis/thesis.json` | Health score, catalysts, position type |
| **Risk** | `GET /api/analysis/risk/{ticker}` + `_portfolio/risk/` | Beta, drawdown, VaR, alerts |
| **Earnings** | `data/artifacts/{ticker}/earnings/` | Surprises, upcoming previews |
| **Model** | `data/artifacts/{ticker}/model/projections.json` | Target price, upside/downside |
| **Portfolio** | `GET /api/portfolio/positions` | Position sizing, P&L, weight |

## REST API Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /api/portfolio/` | Portfolio summary |
| `GET /api/portfolio/positions` | All open positions |
| `GET /api/analysis/signals/{ticker}` | **NEW** — aggregated quant signals |
| `GET /api/analysis/signals/portfolio/summary` | **NEW** — all-position signals |
| `GET /api/analysis/risk/{ticker}` | Per-ticker risk metrics |
| `POST /api/analysis/risk/portfolio` | Portfolio-level risk |
| `GET /api/financials/{ticker}/income-statements` | Revenue/earnings growth |
| `POST /api/analysis/reports` | Persist decision report to DB |

## CLI Commands

```bash
# Full pipeline (recommended)
uv run python skills/fund-manager/scripts/fund_cli.py run
uv run python skills/fund-manager/scripts/fund_cli.py run --persist

# Individual phases
uv run python skills/fund-manager/scripts/fund_cli.py collect             # Phase 1: gather signals
uv run python skills/fund-manager/scripts/fund_cli.py debate              # Phase 2: bull/bear debate
uv run python skills/fund-manager/scripts/fund_cli.py debate --ticker NVDA
uv run python skills/fund-manager/scripts/fund_cli.py decide              # Phase 3: generate decisions
uv run python skills/fund-manager/scripts/fund_cli.py decide --persist

# Review & manage
uv run python skills/fund-manager/scripts/fund_cli.py review              # Phase 4: interactive review
uv run python skills/fund-manager/scripts/fund_cli.py review --ticker NVDA
uv run python skills/fund-manager/scripts/fund_cli.py show                # View latest decisions
uv run python skills/fund-manager/scripts/fund_cli.py history             # View all past decisions
```

## Agent Integration

The AI agent can run this skill end-to-end:

1. **Collect:** Run `fund_cli.py collect` to gather all signals
2. **Debate:** Run `fund_cli.py debate` to structure the bull/bear analysis
3. **Decide:** Run `fund_cli.py decide` to produce preliminary actions
4. **Review:** Read the `_decisions.json` artifact, apply qualitative judgment (thesis conviction, macro outlook, position sizing rules), and update the `final_action` + `reasoning` fields
5. **Report:** The markdown report is auto-generated for Streamlit rendering

The agent should fill in:
- `final_action` — the actual recommended action after qualitative review
- `reasoning` — why this action (combining quantitative signals + qualitative judgment)
- `position_sizing` — specific sizing recommendation
- `risk_adjusted` — whether the risk debate changed the decision
- `time_horizon` — immediate / this_week / this_month
- `catalyst_trigger` — what would change this decision

## TradingAgents Concepts Preserved

| Concept | How it's preserved in PFS |
|---|---|
| **Two-tier LLM** (quick vs deep think) | Quantitative signals are computed by scripts; qualitative synthesis by the AI agent |
| **Bull/Bear debate** | Signal classification into bull/bear/neutral + debate scaffold |
| **3-way risk debate** | Aggressive/conservative/neutral perspectives in risk assessment |
| **Signal processing** | Net score from bull-bear count → preliminary action |
| **Memory/reflection** | Decision history artifacts enable learning from past decisions |
| **Human-in-the-loop** | **Hard rule** — no auto-execution, all decisions require human review |

## Differences from TradingAgents

| TradingAgents | PFS Fund Manager |
|---|---|
| In-memory LangGraph pipeline | Artifact-based pipeline (JSON files) |
| Real-time LLM debate | Pre-computed signal classification + agent review |
| Single-stock focus | Portfolio-wide synthesis |
| Auto-signal extraction | Human reviews every decision |
| External data APIs (yfinance, Alpha Vantage) | PFS REST API + cross-skill artifacts |
| No thesis tracking | Full thesis health integration |
