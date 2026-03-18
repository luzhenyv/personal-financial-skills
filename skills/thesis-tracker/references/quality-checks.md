# Quality Checks

Run these checks after completing each task for a given ticker.

## Prerequisite: Company Data

- [ ] Company exists in MCP: `list_companies` shows the ticker
- [ ] `get_company(ticker)` returns valid company data
- [ ] If creating a new thesis, check for existing profile artifacts to seed from

## After Thesis Creation (Task 1)

- [ ] `data/artifacts/{TICKER}/thesis/thesis.json` exists with all required fields
- [ ] `thesis.json` includes `"schema_version": "1.0"`
- [ ] Core thesis is falsifiable (not a tautology or vague hope)
- [ ] All 3-5 buy reasons have specific, evidence-based claims
- [ ] All assumptions have measurable KPIs where possible and explicit weights summing to 100%
- [ ] Sell conditions are specific enough to be actionable
- [ ] "Where I might be wrong" (`risk_factors`) contains genuine bear case arguments
- [ ] Empty `updates.json`, `health_checks.json`, and `catalysts.json` are initialized
- [ ] `thesis_{TICKER}.md` is generated and readable

## After Thesis Update (Task 2)

- [ ] New entry appended to `updates.json` (never overwrites existing entries)
- [ ] Every assumption has an explicit impact status (✓ / ⚠️ / ✗ / —)
- [ ] Action taken is recorded (even if "hold" / no change)
- [ ] Source field tracks origin (manual, earnings, catalyst, news)
- [ ] `thesis_{TICKER}.md` is regenerated with the new update

## After Health Check (Task 3)

- [ ] New entry appended to `health_checks.json` (never overwrites)
- [ ] Objective score pulls from latest MCP financial data (not stale)
- [ ] Subjective score includes specific event references (not generic)
- [ ] Per-assumption score breakdown is complete (all assumptions scored)
- [ ] Weights in assumption scores match weights in `thesis.json`
- [ ] Composite score = objective × 0.6 + subjective × 0.4
- [ ] Previous score shown for comparison in observations
- [ ] `thesis_{TICKER}.md` is regenerated

## After Catalyst Update (Task 4)

- [ ] New catalyst added to `catalysts.json` with unique ID
- [ ] Expected date and impact are specified
- [ ] When resolved, `status` changed to `"resolved"` with `resolved_date` and `outcome`
- [ ] Resolved catalysts trigger a thesis update (Task 2)

## Output

- [ ] `thesis_{TICKER}.md` saved to `data/artifacts/{TICKER}/thesis/`
- [ ] Report persisted via MCP `save_analysis_report(ticker, 'thesis_tracker', ...)` to `analysis_reports` table

**CLI**: All tasks run via `uv run python skills/thesis-tracker/scripts/thesis_cli.py <subcommand> {TICKER}`

## Cross-Skill Integration

### company-profile (existing)
- On thesis creation, optionally reads `data/artifacts/{TICKER}/profile/investment_thesis.json` to seed buy reasons
- On thesis creation, optionally reads `data/artifacts/{TICKER}/profile/risk_factors.json` to seed risk factors
- On thesis creation, reads `data/artifacts/{TICKER}/profile/competitive_landscape.json` for competitive context

### earnings (future — placeholder)
- After earnings processing, automatically creates a thesis update entry
- Compares actual results against thesis assumption KPIs

### catalysts (built-in)
- When a catalyst resolves, triggers the thesis update flow (Task 2)
- Tracks catalyst outcomes (confirmed / missed / delayed)

## Streamlit Integration

The Thesis Tracker Streamlit page (`streamlit_app/pages/2_thesis_tracker.py`) provides:

1. **Active Theses Overview** — Table of all active theses with latest conviction and composite score
2. **Thesis Detail View** — Full thesis + update log + health history for a selected ticker
3. **Health Score Timeline** — Plotly line chart showing composite, objective, and subjective scores over time
4. **Assumption Heatmap** — Per-assumption score trends across health checks
5. **Update Timeline** — Chronological log of all thesis updates with strength indicators
