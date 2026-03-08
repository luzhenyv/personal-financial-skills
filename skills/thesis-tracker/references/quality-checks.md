# Quality Checks & Integration

## Quality Checks

### After Thesis Creation
- [ ] All 3+ buy reasons have specific, falsifiable claims
- [ ] All assumptions have measurable KPIs and explicit weights summing to 100%
- [ ] Sell conditions are specific enough to be actionable
- [ ] "Where I might be wrong" contains genuine bear case arguments

### After Thesis Update
- [ ] Every assumption has an explicit status (✓ / ⚠️ / ✗ / —)
- [ ] Action taken is recorded (even if "no change")
- [ ] Both DB row and markdown file are updated

### After Health Check
- [ ] Objective score pulls from latest financial data (not stale)
- [ ] Subjective score includes specific event references
- [ ] Score breakdown totals correctly (weights sum to 100%)
- [ ] Previous score shown for comparison

## Integration with Other Skills

### company-profile (existing)
- On thesis creation, reads `investment_thesis.json` to seed bull case / buy reasons
- On thesis creation, reads `competitive_landscape.json` and `risk_factors.json` to seed assumptions and risks

### earnings (future — placeholder)
- After earnings processing, automatically creates a thesis update entry
- Compares actual results against thesis assumption KPIs
- Prompts user for action decision

### catalysts (future — placeholder)
- Maintains a calendar of thesis-relevant upcoming events
- When a catalyst materializes, triggers thesis update flow
- Tracks catalyst outcomes (confirmed / missed / delayed)

## Streamlit Integration

The Thesis Tracker Streamlit page (`streamlit_app/pages/2_thesis_tracker.py`) provides:

1. **Active Theses Overview** — Table of all active theses with latest conviction and composite score
2. **Thesis Detail View** — Full thesis + update log + health history for a selected ticker
3. **Health Score Timeline** — Plotly line chart showing composite, objective, and subjective scores over time
4. **Assumption Heatmap** — Per-assumption score trends across health checks
5. **Update Timeline** — Chronological log of all thesis updates with strength indicators
