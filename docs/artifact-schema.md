# Artifact Schema Reference

All agent-generated analysis is stored under `artifacts/{ticker}/`. Every JSON artifact includes a `schema_version` field. Streamlit checks this field to apply the correct renderer when schemas evolve.

---

## Directory Layout

```
artifacts/
  {ticker}/
    profile/
      {YYYY-QN}.md          # markdown tearsheet (human-readable)
      {YYYY-QN}.json        # structured data (machine-readable, Streamlit renders this)
    thesis/
      v1_{YYYY-MM-DD}.md    # initial draft
      v2_{YYYY-MM-DD}.md    # revision (after earnings, user edit, or Agent patch)
    earnings/
      {YYYY-QN}_call.md
      {YYYY-QN}_call.json
    news/
      {YYYY-MM-DD}_{slug}.md
```

---

## Profile Schema (`profile/*.json`)

```json
{
  "schema_version": "1.0",
  "generated_at": "2025-11-15T10:30:00Z",
  "ticker": "NVDA",
  "company_name": "NVIDIA Corporation",
  "sector": "Technology",
  "industry": "Semiconductors",
  "exchange": "NASDAQ",
  "data_sources": ["rest_api", "sec_raw"],

  "fundamentals": {
    "revenue_ttm": 113000000000,
    "gross_margin": 0.745,
    "operating_margin": 0.621,
    "net_margin": 0.557,
    "net_income_ttm": 72000000000,
    "eps_ttm": 2.92,
    "pe_ratio": 42.3,
    "ev_ebitda": 35.1,
    "price_to_sales": 18.4,
    "price_to_book": 31.2
  },

  "growth": {
    "revenue_yoy": 1.22,
    "revenue_3yr_cagr": 0.87,
    "eps_yoy": 1.45,
    "eps_3yr_cagr": 1.12
  },

  "balance_sheet": {
    "cash_and_equivalents": 34000000000,
    "total_debt": 8900000000,
    "net_cash": 25100000000,
    "debt_to_equity": 0.41,
    "current_ratio": 4.17
  },

  "cash_flow": {
    "free_cash_flow_ttm": 60000000000,
    "fcf_margin": 0.531,
    "capex_ttm": 3200000000
  },

  "technicals": {
    "price": 131.50,
    "52w_high": 153.13,
    "52w_low": 86.42,
    "rsi_14": 58.3,
    "macd_signal": "bullish_cross",
    "sma_50": 126.40,
    "sma_200": 119.85
  },

  "narrative": {
    "business_description": "...",
    "moat": "...",
    "bull_case": "...",
    "bear_case": "...",
    "risks": "..."
  }
}
```

---

## Earnings Schema (`earnings/*.json`)

```json
{
  "schema_version": "1.0",
  "generated_at": "2025-11-21T08:00:00Z",
  "ticker": "NVDA",
  "period": "2025-Q3",
  "filing_type": "10-Q",
  "data_sources": ["rest_api", "sec_raw"],

  "headline_metrics": {
    "revenue": 35082000000,
    "revenue_vs_estimate": 0.021,
    "revenue_yoy": 0.942,
    "eps_gaap": 0.78,
    "eps_vs_estimate": 0.065,
    "gross_margin": 0.748,
    "gross_margin_delta_qoq": 0.003
  },

  "guidance": {
    "next_quarter_revenue_midpoint": 37500000000,
    "next_quarter_gross_margin_midpoint": 0.73
  },

  "key_themes": [
    "Data center demand accelerating into Q4",
    "Blackwell ramp on track — no supply constraints cited",
    "Gaming revenue softer than expected, -8% QoQ"
  ],

  "thesis_impact": {
    "change_recommended": false,
    "rationale": "Results consistent with existing thesis; data center trajectory intact."
  },

  "narrative": {
    "summary": "...",
    "management_tone": "...",
    "analyst_questions": "..."
  }
}
```

---

## Editing Artifacts

Users have two options for updating artifacts after they are generated:

**Option 1 — Direct edit:** Open the `.md` or `.json` file in any editor, make changes, commit to git. This is appropriate for correcting factual errors, adding personal notes, or revising the narrative.

**Option 2 — Agent patch:** Ask the Agent in the Chat UI to update a specific section. The Agent writes a new versioned file (e.g. `v2_2025-12-01.md`) rather than overwriting the existing one. Both versions are preserved in git history.

---

## Schema Versioning

When a schema field is added or renamed, increment `schema_version` in new artifacts. Streamlit's `artifact_renderer.py` checks `schema_version` and applies the correct field mappings. Old artifacts are never broken by schema changes — they simply render with the fields available in their version.