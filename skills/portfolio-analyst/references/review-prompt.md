# Portfolio Review Prompt

Use this structured template when performing the AI portfolio review (Task 2).

## Input

You have `portfolio_snapshot.json` containing:
- `summary` — portfolio totals (cash, value, position count)
- `positions` — each position with shares, avg_cost, current_price, market_value, unrealized_pnl, weight
- `allocation` — breakdown by sector, conviction, position size
- `performance` — YTD return from snapshots
- `pnl` — realized + unrealized per position
- `thesis_data` — per-ticker thesis status, conviction, health score, sell conditions

## Analysis Framework

### 1. Portfolio Summary

State the facts:
- Total portfolio value and cash position (% of portfolio)
- Number of positions
- YTD return vs. benchmark
- Total unrealized and realized P&L

### 2. Conviction Alignment Check

For each position, evaluate weight vs. conviction:

| Conviction | Target Weight | Underweight If | Overweight If |
|------------|--------------|----------------|---------------|
| High | 8–15% | < 5% | > 20% |
| Medium | 3–8% | < 2% | > 12% |
| Low | 1–3% | — | > 5% |
| Unset | — | — | Any (flag for thesis creation) |

For each misalignment, state:
- Current weight and conviction
- Why it's misaligned
- Specific recommended action (buy/sell X shares)

### 3. Thesis Health Alerts

For positions with health check data:
- **Score ≥ 75**: Thesis intact — no action needed
- **Score 50–74**: Thesis cautious — review but hold
- **Score 30–49**: Thesis weakening — recommend trim
- **Score < 30**: Thesis broken — recommend exit

Flag any position where thesis recommendation conflicts with current action (e.g., "exit" recommendation but position is growing).

### 4. Orphaned Positions

List all positions where `has_thesis = false`. For each:
- State the position size and P&L
- Recommend: create thesis OR exit position
- Urgency: larger positions without thesis are more concerning

### 5. Concentration Risk

Check and flag:
- **Sector**: Any sector > 30% → flag with specific positions driving it
- **Single name**: Any position > 15% → flag
- **Cash drag**: Cash > 25% → flag as potential drag on returns
- **Cash too low**: Cash < 5% → flag as insufficient buffer

### 6. Rebalancing Recommendations

Synthesize all findings into concrete actions, ordered by priority:
1. **Exit** — thesis broken, score < 30
2. **Trim** — overweight or thesis weakening
3. **Add** — underweight high-conviction
4. **Create thesis** — orphaned positions needing rationale
5. **Monitor** — approaching thresholds but no action yet

For each trade recommendation, specify:
- Ticker, action (buy/sell), approximate shares
- Current vs. target weight
- Reasoning (conviction alignment, thesis health, concentration)

## Output Format

Write both:
1. **portfolio_review.json** — structured data (see schema in SKILL.md)
2. **portfolio_review.md** — narrative Markdown report with sections matching the analysis framework above
