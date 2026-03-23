# Task 1 JSON Schemas

Task 1 is AI-driven — no script needed. Read data from the REST API and `data/artifacts/{TICKER}/profile/10k_raw_sections.json`, then create each file below in `data/artifacts/{TICKER}/profile/`.

## Guidelines

- Use REST API endpoints (`GET /api/financials/{TICKER}/income-statements`, `GET /api/financials/{TICKER}/segments`, `GET /api/companies/{TICKER}`, etc.) as the primary data source
- Source qualitative content from Item 1, Item 1A, or Item 7 of the 10-K (via `10k_raw_sections.json`)
- For `risk_factors.json`: quote or closely paraphrase actual Item 1A language
- For `competitive_landscape.json`: use tickers that `build_comps.py` can look up on Yahoo Finance
- Cross-check revenue segment figures against `GET /api/financials/{TICKER}/segments` data
- Every JSON file must include a `"schema_version": "1.0"` field

---

## `company_overview.json`

```json
{
  "schema_version": "1.0",
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "cik": "0000320193",
  "fiscal_year": 2025,
  "fiscal_year_end": "September",
  "source": "10-K FY2025 Item 1",
  "description": "...",        // 2-3 sentence business description from Item 1
  "business_overview": "...",  // additional detail, 1-2 paragraphs
  "revenue_model": "...",      // how the company monetizes
  "customers": "...",          // key customer segments
  "segments": [
    {
      "name": "iPhone",
      "description": "...",
      "revenue_fy_b": 210.0,
      "yoy_growth_pct": 5.2
    }
  ],
  "products": ["...", "..."],
  "geographic_revenue": {
    "Americas": "~42%",
    "Europe": "~25%"
  }
}
```

## `management_team.json`

```json
{
  "schema_version": "1.0",
  "ticker": "AAPL",
  "source": "10-K FY2025 Item 10 + proxy DEF 14A",
  "executives": [
    {
      "name": "Tim Cook",
      "title": "Chief Executive Officer",
      "age": 64,
      "tenure_years": 14,
      "prior_roles": ["COO at Apple", "VP Operations at Compaq"],
      "accomplishments": "...",
      "insider_ownership_pct": "~0.02%"
    }
  ],
  "board": {
    "size": 8,
    "independent_directors": 7,
    "notable_members": ["..."]
  },
  "governance_notes": "..."
}
```

## `risk_factors.json`

Include **8–12 risks** across 4 categories: Company-Specific (4–6), Industry/Market (2–3), Financial (1–2), Macro (1–2).

```json
{
  "schema_version": "1.0",
  "ticker": "AAPL",
  "source": "10-K FY2025 Item 1A",
  "risks": [
    {
      "category": "Company-Specific",   // Company-Specific | Industry/Market | Financial | Macro
      "title": "Supply chain concentration",
      "description": "..."              // 1-2 sentences, verbatim or close paraphrase from 10-K
    }
  ]
}
```

## `competitive_landscape.json`

Include **5–8 competitors** (direct + indirect). The `ticker` field is used by `build_comps.py` for peer data — use the primary exchange ticker (e.g. `SAMSG` → use `SSNLF` for OTC, or omit non-tradeable).

```json
{
  "schema_version": "1.0",
  "ticker": "AAPL",
  "source": "10-K FY2025 + market research",
  "moat": "...",
  "competitive_positioning": "...",
  "competitors": [
    {
      "name": "Samsung Electronics",
      "ticker": "005930.KS",
      "market_cap_b": 280,
      "products_competing": "...",
      "competitive_advantage_vs_subject": "...",
      "market_share": "..."
    }
  ]
}
```

## `financial_segments.json`

```json
{
  "schema_version": "1.0",
  "ticker": "AAPL",
  "source": "10-K FY2025 MD&A",
  "fiscal_year": 2025,
  "segments": [
    { "name": "iPhone", "revenue_fy_b": 210.0, "revenue_prior_fy_b": 200.6, "yoy_growth_pct": 4.7, "description": "..." }
  ],
  "geographic_revenue_fy": {
    "Americas": { "revenue_b": 165.0, "pct": 42.0 }
  }
}
```

## `investment_thesis.json`

Include **4–6 bull case points** and **3–5 opportunities**, each with specific data or filing references.

```json
{
  "schema_version": "1.0",
  "ticker": "AAPL",
  "source": "10-K FY2025 MD&A + analysis",
  "bull_case": [
    {
      "title": "Services revenue flywheel",
      "description": "..."     // 2-3 sentences with specific data points
    }
  ],
  "opportunities": [
    {
      "title": "Apple Intelligence / AI expansion",
      "description": "..."
    }
  ]
}
```
