---
name: fund-manager
description: TradingAgents-inspired decision engine — synthesizes all skill outputs into actionable portfolio-wide trading decisions with human-in-the-loop. Triggers on "fund manager run", "trading decisions", "portfolio review", "bull bear debate", "collect signals", or "what should I trade".
---

# Fund Manager

Core question: **"Given everything I know, what should I buy, sell, hold, trim, or add — and why?"**

Adapted from the [TradingAgents](https://github.com/TauricResearch/TradingAgents) multi-agent framework. Scripts compute quantitative signals into structured artifacts; the AI agent (or human) fills in qualitative reasoning through the review workflow. **No auto-execution — human approves every trade.**

## Workflow

### Step 1: Collect Signals (Script)

Gather quantitative signals from all skill artifacts and the REST API.

```bash
uv run python skills/fund-manager/scripts/fund_cli.py collect
```

**What the script does:**
1. Calls `GET /api/portfolio/positions` — all open positions
2. Per ticker, collects 6 signal sources:
   - **Market**: `GET /api/analysis/signals/{ticker}` — momentum, SMA crossovers, RSI, MACD, Bollinger, ATR, VWMA
   - **Fundamentals**: `GET /api/analysis/signals/{ticker}` + `GET /api/financials/{ticker}/metrics` — P/E, margins, growth, ROE
   - **Thesis**: `data/artifacts/{ticker}/thesis/thesis.json` — health score, catalysts, position type
   - **Risk**: `GET /api/analysis/risk/{ticker}` + `data/artifacts/_portfolio/risk/` — beta, VaR, drawdown, alerts
   - **Earnings**: `data/artifacts/{ticker}/earnings/` — surprises, upcoming previews
   - **Model**: `data/artifacts/{ticker}/model/projections.json` — target price, upside/downside
3. Calls `POST /api/analysis/risk/portfolio` — portfolio-level risk metrics

**Output**: `data/artifacts/_portfolio/decisions/{date}_signals.json`

### Step 2: Bull/Bear Debate (Script)

Classify signals and structure the investment debate.

```bash
uv run python skills/fund-manager/scripts/fund_cli.py debate
uv run python skills/fund-manager/scripts/fund_cli.py debate --ticker NVDA
```

**What the script does per ticker:**
1. Classify each signal as bull / bear / neutral
2. Build investment debate scaffold:
   - **Bull case**: bull signals + thesis alignment
   - **Bear case**: bear signals + risk factors
3. Build risk assessment with three perspectives (from TradingAgents' 3-way risk debate):
   - **Growth view** (aggressive): argues for maintaining/increasing exposure
   - **Risk view** (conservative): advocates capital preservation
   - **Balanced view** (neutral): weighs both, proposes moderate adjustments

**Output**: `data/artifacts/_portfolio/decisions/{date}_debates.json`

### Step 3: Trading Decision (Script)

Produce preliminary action recommendations from debate scores.

```bash
uv run python skills/fund-manager/scripts/fund_cli.py decide
uv run python skills/fund-manager/scripts/fund_cli.py decide --persist
```

**What the script does per ticker:**
1. Quantitative scoring: net bull count minus bear count
2. Map score → preliminary action: BUY / SELL / HOLD / TRIM / ADD
3. Generate decision template with placeholders for agent review
4. Produce markdown report with portfolio context

**Output**: `data/artifacts/_portfolio/decisions/{date}_decisions.json` + `{date}_decisions.md`

### Step 4: Human Review (Interactive)

Review each position's debate and set final actions. **No trade executes without this step.**

```bash
uv run python skills/fund-manager/scripts/fund_cli.py review
uv run python skills/fund-manager/scripts/fund_cli.py review --ticker NVDA
```

The agent (or human) fills in:
- `final_action` — the actual recommended action after qualitative review
- `reasoning` — why this action (quantitative signals + qualitative judgment)
- `position_sizing` — specific sizing recommendation
- `risk_adjusted` — whether the risk debate changed the decision
- `time_horizon` — immediate / this_week / this_month
- `catalyst_trigger` — what would change this decision

Status transitions: `preliminary` → `reviewed`

## Artifacts

Output goes to `data/artifacts/_portfolio/decisions/`:

| File | Contents |
|------|----------|
| `{date}_signals.json` | Raw signal bundle from all 6 sources per ticker |
| `{date}_debates.json` | Bull/bear signal classification + debate scaffolds |
| `{date}_decisions.json` | Preliminary + final action decisions |
| `{date}_decisions.md` | Human-readable decision report |

## REST API Endpoints Used

| Endpoint | What we read |
|----------|-------------|
| `GET /api/portfolio/` | Portfolio summary |
| `GET /api/portfolio/positions` | All open positions with weights and P&L |
| `GET /api/analysis/signals/{ticker}` | Aggregated quant signals (technicals, momentum, fundamentals) |
| `GET /api/analysis/signals/portfolio/summary` | All-position signal aggregation |
| `GET /api/analysis/risk/{ticker}` | Per-ticker risk contribution |
| `POST /api/analysis/risk/portfolio` | Portfolio-level risk (beta, VaR, Sharpe, Sortino, drawdown) |
| `GET /api/financials/{ticker}/income-statements` | Revenue/earnings growth |
| `POST /api/analysis/reports` | Persist decision report to DB |

## Cross-Skill Reads

- `data/artifacts/{ticker}/thesis/thesis.json` — thesis health score, catalysts, position type
- `data/artifacts/{ticker}/thesis/health_checks.json` — latest health check scores
- `data/artifacts/{ticker}/earnings/` — earnings surprises and previews
- `data/artifacts/{ticker}/model/projections.json` — target price, upside/downside
- `data/artifacts/_portfolio/risk/risk_report.json` — latest portfolio risk metrics
- `data/artifacts/_portfolio/risk/alerts.json` — active risk alerts

## Important Notes

- **No auto-execution** — every trade decision requires human review (hard rule)
- Decision history artifacts enable learning from past decisions — review with `fund_cli.py history`
- Run the full pipeline with `fund_cli.py run` for the recommended sequential workflow
- Stale signals degrade debate quality — collect fresh signals before each decision cycle
- The markdown report is auto-generated for Streamlit rendering
