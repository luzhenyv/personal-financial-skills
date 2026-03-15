# Health Check Scoring Methodology

## Composite Score

**Composite Score** = (Objective Score × 60%) + (Subjective Score × 40%)

Each score is 0–100. The breakdown is always visible alongside the composite.

## Objective Score (60% weight)

Computed from quantitative data changes since thesis creation or last check. For each prerequisite assumption, define measurable KPIs:

| Example Assumption | KPI | Scoring Rule |
|---|---|---|
| "Gross margin stays above 60%" | Latest gross margin | >65%: 100, 60-65%: 75, 55-60%: 40, <55%: 10 |
| "Revenue growth >20% YoY" | TTM revenue growth | >25%: 100, 20-25%: 80, 15-20%: 50, <15%: 20 |
| "No credible competitive threat" | Market share trend | Stable/growing: 90, slight decline: 60, major decline: 20 |

The objective score is the weighted average of per-assumption KPI scores, using the weights defined at thesis creation.

### Data Sources

- PostgreSQL tables: `income_statements`, `balance_sheets`, `financial_metrics`
- Latest price data: `daily_prices`
- Artifact JSON: `data/artifacts/{TICKER}/*.json`

## Subjective Score (40% weight)

LLM evaluates qualitative factors that are hard to quantify:
- Competitive dynamics (new entrants, technology shifts)
- Management quality and capital allocation decisions
- Regulatory and geopolitical risks
- Narrative / sentiment shifts in the market
- Whether the original thesis "story" still makes sense

The LLM should reference specific recent events, not just give a generic assessment. The subjective score must include a brief justification (2-3 sentences) for each assumption rating.
