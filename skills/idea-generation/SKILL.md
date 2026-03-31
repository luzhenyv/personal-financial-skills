---
name: idea-generation
description: Systematic stock screening and investment idea sourcing. Scans all ingested companies against quantitative criteria (value, growth, quality, special situation) and surfaces ranked candidates with one-page summaries. Triggers on "screen for", "find ideas", "idea generation", "stock screen", "what looks interesting", "new ideas", or "pitch me something".
---

# Idea Generation

Systematic stock screening — surface new investment ideas from the database.

## Architecture

- **Input**: REST API (`GET /api/companies/`, `GET /api/financials/{ticker}/metrics`)
- **Output**: `data/artifacts/_ideas/`
- **Pattern**: Script-driven screening with AI-assisted narrative generation

## Artifacts

```
data/artifacts/_ideas/
  screen_results.json       # Latest screen results with scores
  screen_results.md         # Formatted idea shortlist
```

### screen_results.json schema

```json
{
  "schema_version": "1.0",
  "screen_type": "growth",
  "screen_params": {},
  "screened_at": "2025-03-25T16:00:00Z",
  "total_companies": 30,
  "passes": 5,
  "results": [
    {
      "ticker": "NVDA",
      "name": "NVIDIA Corporation",
      "sector": "Technology",
      "score": 85,
      "metrics": {
        "revenue_growth": 0.55,
        "eps_growth": 0.62,
        "operating_margin": 0.58,
        "roic": 0.45,
        "pe_ratio": 35.2,
        "ev_to_ebitda": 28.1,
        "fcf_yield": 0.028,
        "debt_to_equity": 0.42
      },
      "flags": ["revenue_acceleration", "expanding_margins", "high_roic"],
      "thesis_hint": "Dominant GPU franchise driving AI infrastructure buildout"
    }
  ]
}
```

## Workflow

### Task 1: Screen (Script — `screen.py`)

1. Fetch all companies from `GET /api/companies/`
2. For each company, fetch metrics from `GET /api/financials/{ticker}/metrics`
3. Apply screen filters based on `--type` (value, growth, quality, special-situation)
4. Score and rank passing companies
5. Write `screen_results.json` to artifacts

### Task 2: Generate Ideas Report (AI — `generate_ideas.py`)

1. Read `screen_results.json`
2. For top candidates, fetch additional context (income statements, prices)
3. Generate one-page summary per idea with thesis hint, key risks, and next steps
4. Write `screen_results.md` to artifacts

## Screen Types

### Value Screen
- P/E below 20 (or sector median)
- EV/EBITDA below 12
- FCF yield > 5%
- P/B below 2.0
- Positive revenue growth (not declining)

### Growth Screen
- Revenue growth > 15% YoY
- EPS growth > 20% YoY
- Operating margin expanding or stable (> 10%)
- ROIC > 15%
- Not excessively valued (P/E < 60)

### Quality Screen
- Consistent revenue growth (positive across available years)
- Operating margin > 15%
- ROE > 15%
- Debt/equity < 1.0
- FCF yield > 2%

### Special Situation Screen
- High revenue growth (> 25%) with low valuation (P/E < 25)
- Margin expansion trend
- Under-covered (fewer analysts, smaller companies)

## CLI

```bash
# Growth screen
uv run python skills/idea-generation/scripts/screen.py --type growth

# Value screen with custom thresholds
uv run python skills/idea-generation/scripts/screen.py --type value --max-pe 15 --min-fcf-yield 0.05

# Quality screen
uv run python skills/idea-generation/scripts/screen.py --type quality

# All screen types combined
uv run python skills/idea-generation/scripts/screen.py --type all

# Generate markdown report from latest screen
uv run python skills/idea-generation/scripts/generate_ideas.py
```

## Important Notes

- Screens surface **candidates**, not conclusions — every idea needs further diligence
- The best ideas often come from intersections (quality company at value price)
- Check if position already held before flagging as "new idea"
- Track screen hit rates over time to improve criteria
- Contrarian ideas need a catalyst — being early without a catalyst is being wrong
