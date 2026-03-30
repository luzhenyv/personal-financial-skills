---
name: risk-manager
description: Portfolio-level risk monitoring — concentration, correlation, drawdown, thesis health, and rule-based alerts. Adapted from TradingAgents multi-perspective risk debate pattern. Triggers on "risk check", "portfolio risk", "risk report", "risk alerts", "risk rules", or "show risk".
---

# Risk Manager

Core question: **"Does my portfolio as a whole make sense, and where is risk hiding?"**

This is **not** about individual stock analysis (that's thesis-tracker). This skill monitors the *collection* of positions — concentration, correlation, drawdown, and whether the portfolio's aggregate exposure matches your risk tolerance.

## Design Inspiration

Adapted from the [TradingAgents](https://github.com/TauricResearch/TradingAgents) paper's risk management pattern — a multi-perspective debate among three analyst personas (aggressive, conservative, neutral) adjudicated by a risk manager judge. In our implementation:

- **Growth Analyst** (aggressive): Argues for maintaining/increasing risk exposure to capture upside
- **Risk Analyst** (conservative): Advocates capital preservation and reducing concentrated positions
- **Balanced Analyst** (neutral): Weighs both perspectives, proposes moderate adjustments

The AI agent plays the role of the risk manager judge, synthesizing the debate into actionable recommendations.

## Workflow

### Step 1: Compute Risk Metrics (Automated)

The CLI calls API endpoints to compute quantitative risk metrics server-side:

```bash
uv run python skills/risk-manager/scripts/risk_cli.py check
```

This collects:
- **Concentration**: Top position %, top-3 %, sector weights, HHI index
- **Risk metrics**: Portfolio beta, 30-day max drawdown, 90-day Sharpe/Sortino, 1-day 95% VaR
- **Thesis health**: Average score, positions below threshold, stale checks, missing theses

Data sources:
- `GET /api/portfolio/positions` — current positions and weights
- `GET /api/portfolio/allocation` — sector/conviction breakdown
- `POST /api/analysis/risk/portfolio` — server computes beta, correlation, VaR, drawdown
- `GET /api/analysis/risk/{ticker}` — per-ticker risk contribution
- `data/artifacts/{ticker}/thesis/thesis.json` + `health_checks.json` — thesis health data

### Step 2: Evaluate Rules → Generate Alerts

Compare metrics against configurable risk rules:

| Rule | Default | Severity |
|------|---------|----------|
| Max single position % | 15% | warning |
| Max sector % | 40% | warning |
| Max portfolio beta | 1.5 | warning |
| Min thesis health score | 40 | critical |
| Max drawdown alert | -10% | critical |

Alerts are generated automatically when any rule is breached. Alerts are **append-only** — new alerts are added to `alerts.json` without overwriting history.

```bash
uv run python skills/risk-manager/scripts/risk_cli.py alerts
```

### Step 3: AI Narrative Report (Agent)

The agent reads the risk_report.json and produces a narrative assessment using the three-perspective debate pattern:

1. Read computed metrics from `risk_report.json`
2. Synthesize a multi-perspective analysis (growth vs. risk vs. balanced view)
3. Generate actionable recommendations
4. Write `risk_report.md`

```bash
uv run python skills/risk-manager/scripts/risk_cli.py report
```

### Step 4: Edit Risk Rules

View or update the risk rules that govern alert generation:

```bash
uv run python skills/risk-manager/scripts/risk_cli.py rules                   # Show current rules
uv run python skills/risk-manager/scripts/risk_cli.py rules --set max_single_position_pct=0.20
uv run python skills/risk-manager/scripts/risk_cli.py rules --set max_sector_pct=0.35 --set max_portfolio_beta=1.3
```

## Artifacts

All output goes to `data/artifacts/_portfolio/risk/`:

| File | Contents |
|------|----------|
| `risk_report.json` | Latest quantitative risk metrics + rules + alerts |
| `risk_report.md` | AI-generated narrative risk assessment |
| `alerts.json` | Append-only alert history |
| `rules.json` | User-configurable risk rules |

## REST API Endpoints

### Existing (used as inputs)

| Endpoint | What we read |
|----------|-------------|
| `GET /api/portfolio/positions` | All positions with weights and P&L |
| `GET /api/portfolio/allocation` | Sector, conviction, position-size breakdown |
| `GET /api/portfolio/performance` | Time-weighted returns from snapshots |

### New (added by this skill)

| Endpoint | Description |
|----------|-------------|
| `POST /api/analysis/risk/portfolio` | Compute portfolio-level risk: beta, VaR, Sharpe, Sortino, drawdown, correlation matrix |
| `GET /api/analysis/risk/{ticker}` | Per-ticker risk contribution: beta, correlation to portfolio, marginal VaR |

## Cross-Skill Reads (artifacts + API, no imports)

- `GET /api/portfolio/*` — positions, allocation from Mini PORT
- `data/artifacts/{ticker}/thesis/thesis.json` — thesis data per position
- `data/artifacts/{ticker}/thesis/health_checks.json` — latest health scores

## Important Notes

- Never overwrite `alerts.json` — always append new entries
- Risk rules are user-configurable and persist across runs in `rules.json`
- The narrative report should be balanced — acknowledge both risks AND opportunities
- Portfolio beta and VaR require price history; positions without sufficient history are flagged
- Review portfolio risk at least weekly, or after significant market moves
