---
name: portfolio-analyst
description: AI-driven portfolio analysis — reads portfolio state from the Mini PORT API and thesis artifacts, produces narrative review with rebalancing recommendations, concentration risk flags, and thesis-portfolio alignment checks. Triggers on "review my portfolio", "portfolio analysis", "rebalance recommendations", or weekly Friday after close.
---

# Portfolio Analyst

Core question: **"Is my portfolio positioned correctly given my current theses?"**

## Overview

This skill bridges the **Mini PORT module** (deterministic portfolio data) with the **thesis-tracker** (investment conviction). It reads structured portfolio state from the REST API and thesis artifacts, then produces an AI-driven narrative analysis.

**What this skill does (AI judgment):**
- Interpret allocation vs. conviction alignment
- Identify orphaned positions (no thesis)
- Flag concentration risks
- Recommend rebalancing actions
- Connect thesis developments to position sizing

**What this skill does NOT do (handled by Mini PORT API):**
- Record transactions → `POST /api/portfolio/transactions`
- Compute P&L → `GET /api/portfolio/pnl`
- Take snapshots → `POST /api/portfolio/snapshot`

**Data Flow**: `GET /api/portfolio/* + data/artifacts/{ticker}/thesis/ → Agent → data/artifacts/_portfolio/analysis/`

## Trigger

- User asks for portfolio review, analysis, or rebalancing recommendations
- Weekly cron: Friday 5pm after market close
- After thesis health check runs on multiple positions

## Prerequisite: Portfolio Must Have Positions

Before running, verify the portfolio has data:

1. Call `GET /api/portfolio/` — confirm `position_count > 0`
2. If empty, tell the user:

> Your portfolio has no positions yet. Record some trades first:
> ```bash
> curl -X POST http://localhost:8000/api/portfolio/transactions \
>   -H "Content-Type: application/json" \
>   -d '{"ticker": "NVDA", "action": "buy", "shares": "100", "price": "120"}'
> ```

## Workflow

### Task 1: Data Collection (Script)

Collect all portfolio and thesis data into a single snapshot JSON for analysis.

```bash
uv run python skills/portfolio-analyst/scripts/collect_portfolio.py
```

This script calls the Mini PORT API and reads thesis artifacts:

| API Call | Data Collected |
|----------|---------------|
| `GET /api/portfolio/` | Summary: cash, total value, position count |
| `GET /api/portfolio/positions` | All positions with current prices, P&L, weights |
| `GET /api/portfolio/allocation` | Sector, conviction, and position-size breakdown |
| `GET /api/portfolio/performance?period=ytd` | YTD return from snapshots |
| `GET /api/portfolio/pnl` | Realized + unrealized P&L per position |

For each position ticker, reads:
- `data/artifacts/{ticker}/thesis/thesis.json` — core thesis and conviction
- `data/artifacts/{ticker}/thesis/health_checks.json` — latest health score

**Output**: `data/artifacts/_portfolio/analysis/portfolio_snapshot.json`

### Task 2: Portfolio Review (AI)

Using the snapshot from Task 1, produce a narrative analysis covering:

#### A. Portfolio Summary
- Total value, cash position, number of holdings
- YTD performance vs. benchmark
- Overall P&L (realized + unrealized)

#### B. Conviction Alignment
For each position, compare:
- **Port weight** (actual allocation %) vs. **conviction level** (high/medium/low from thesis)
- Flag misalignments: high-conviction positions that are underweight, or low-conviction positions that are overweight
- Recommended weight adjustments

| Conviction | Target Range | Flag If |
|------------|-------------|---------|
| High | 8–15% | < 5% (underweight) |
| Medium | 3–8% | > 12% (overweight) |
| Low | 1–3% | > 5% (overweight) |

#### C. Thesis Health Integration
For each position with a thesis:
- Latest health check score and recommendation
- Positions where thesis-recommended action (trim/exit) conflicts with current holding
- Catalyst calendar items approaching

#### D. Orphaned Positions
Positions with **no thesis artifact** — these need attention:
- Either create a thesis (`@Personal Finance Assistant create thesis for {TICKER}`)
- Or consider exiting (no investment rationale documented)

#### E. Concentration Risk
- Sector concentration: flag if any sector > 30% of portfolio
- Single-name risk: flag if any position > 15% of portfolio
- Correlation clusters: positions in same industry that move together

#### F. Rebalancing Recommendations
Actionable, specific trade suggestions:
- "Trim NVDA from 18% to 12% (sell ~50 shares at ~$125)"
- "Add to AAPL from 3% to 7% (buy ~40 shares at ~$190)"
- "Exit BA — thesis score 28, below exit threshold"
- "Create thesis for AMD before adding to position"

**Output**:
- `data/artifacts/_portfolio/analysis/portfolio_review.json` — structured analysis
- `data/artifacts/_portfolio/analysis/portfolio_review.md` — narrative report

## Output Files

All artifacts go to `data/artifacts/_portfolio/analysis/`:

| File | Contents |
|------|----------|
| `portfolio_snapshot.json` | Raw data collected in Task 1 |
| `portfolio_review.json` | Structured review with scores and recommendations |
| `portfolio_review.md` | Narrative report for Streamlit dashboard |

## JSON Schema: portfolio_review.json

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-03-27T17:00:00Z",
  "portfolio_id": 1,
  "summary": {
    "total_value": 125000.00,
    "cash": 25000.00,
    "cash_pct": 20.0,
    "position_count": 5,
    "ytd_return_pct": 8.5,
    "benchmark": "SPY",
    "benchmark_return_pct": 6.2
  },
  "alignment": [
    {
      "ticker": "NVDA",
      "weight": 18.0,
      "conviction": "high",
      "target_range": [8, 15],
      "status": "overweight",
      "recommendation": "trim"
    }
  ],
  "orphaned_positions": ["AMD"],
  "concentration_flags": [
    {"type": "sector", "name": "Technology", "weight": 65.0, "threshold": 30.0}
  ],
  "rebalancing_actions": [
    {
      "action": "sell",
      "ticker": "NVDA",
      "shares": 50,
      "reason": "Reduce from 18% to target 12%"
    }
  ],
  "thesis_alerts": [
    {
      "ticker": "BA",
      "health_score": 28,
      "recommendation": "exit",
      "reason": "Below exit threshold of 30"
    }
  ]
}
```

## References

| File | Contents |
|------|----------|
| `references/review-prompt.md` | Structured prompt template for AI portfolio review |
| `references/alignment-rules.md` | Conviction-to-weight alignment rules and thresholds |

## Important Notes

- This skill is **read-only** — it never modifies portfolio positions or transactions
- All trade recommendations are advisory; the user must execute via the portfolio API
- Run after thesis health checks for the most current data
- The snapshot JSON preserves a point-in-time record of portfolio state
