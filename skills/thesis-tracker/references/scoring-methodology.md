# Health Check Scoring Methodology

## Composite Score

**Composite Score** = (Objective Score × 60%) + (Subjective Score × 40%)

Each score is 0–100. The breakdown is always visible alongside the composite.

## Objective Score (60% weight)

Computed from quantitative data changes since thesis creation or last check. For each prerequisite assumption, define measurable KPIs with threshold scoring:

| Example Assumption | KPI Metric | Scoring Rule |
|---|---|---|
| "Gross margin stays above 65%" | `gross_margin` | >72%: 100, 65-72%: 80, 58-65%: 50, <58%: 25 |
| "Revenue growth >30% YoY" | `revenue_growth` | >50%: 100, 30-50%: 80, 15-30%: 50, <15%: 20 |
| "No credible competitive threat" | (none — subjective only) | Default 50 (neutral) |

The objective score is the **weighted average** of per-assumption KPI scores, using the weights defined in `thesis.json`.

### KPI Threshold Scoring

Each assumption's `kpi_thresholds` defines four tiers:

```json
{
  "excellent": 0.72,
  "good": 0.65,
  "warning": 0.58,
  "critical": 0.50
}
```

Scoring logic:
- Value ≥ excellent → **100**
- Value ≥ good → **80**
- Value ≥ warning → **50**
- Value ≥ critical → **25**
- Value < critical → **10**

If an assumption has no `kpi_metric` (qualitative-only), the objective score defaults to **50** (neutral). The subjective evaluation carries the full weight for that assumption.

### Data Sources

Financial data is read via REST API:
- `GET /api/financials/{TICKER}/metrics` — latest margins, growth, returns, leverage
- `GET /api/financials/{TICKER}/income-statements?years=3` — earnings trajectory
- `GET /api/financials/{TICKER}/prices?period=3mo` — recent price trend

Available KPI metrics from `GET /api/financials/{TICKER}/metrics`:

| KPI Metric Key | Description |
|---|---|
| `gross_margin` | Gross profit / revenue |
| `operating_margin` | Operating income / revenue |
| `net_margin` | Net income / revenue |
| `revenue_growth` | YoY revenue growth |
| `roe` | Return on equity |
| `roic` | Return on invested capital |
| `debt_to_equity` | Total debt / equity |
| `current_ratio` | Current assets / current liabilities |
| `pe_ratio` | Price / earnings |

## Subjective Score (40% weight)

LLM evaluates qualitative factors that are hard to quantify:
- Competitive dynamics (new entrants, technology shifts)
- Management quality and capital allocation decisions
- Regulatory and geopolitical risks
- Narrative / sentiment shifts in the market
- Whether the original thesis "story" still makes sense

The LLM must reference **specific recent events**, not generic assessments. Each assumption's subjective rating should include a brief justification (1-2 sentences).

## Per-Assumption Combined Score

For each assumption:

**Combined** = (Objective × 60%) + (Subjective × 40%)

Status thresholds:
- Combined ≥ 70 → **✓ Intact**
- Combined ≥ 40 → **⚠️ Watch**
- Combined < 40 → **✗ Broken**

## Recommendation Logic

Based on the composite score:

| Composite Score | Recommendation | Reasoning |
|---|---|---|
| ≥ 75 | **Hold** | Thesis remains strong. Continue monitoring. |
| 50–74 | **Hold** (cautious) | Thesis intact but showing pressure. Watch closely. |
| 30–49 | **Trim** | Thesis weakening materially. Reduce position. |
| < 30 | **Exit** | Multiple assumptions broken. Thesis no longer valid. |
