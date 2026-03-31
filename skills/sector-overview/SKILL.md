---
name: sector-overview
description: Generate comprehensive industry landscape reports for sectors represented in the portfolio or coverage universe. Covers market dynamics, competitive positioning, valuation context, and thematic trends. Triggers on "sector overview", "industry report", "market landscape", "sector analysis", "industry deep dive", or "thematic research".
---

# Sector Overview

Industry landscape reports — competitive positioning, valuation context, key trends, and thematic analysis for sectors in our coverage universe.

## Architecture

- **Input**: REST API (`GET /api/companies/`, `GET /api/financials/{ticker}/metrics`, `GET /api/financials/{ticker}/income-statements`)
- **Output**: `data/artifacts/_sectors/{sector_slug}/`
- **Pattern**: Script-driven data collection with AI-assisted narrative generation

## Artifacts

```
data/artifacts/_sectors/
  technology/
    sector_data.json          # Structured sector data (companies, metrics, comps)
    sector_overview.md        # Narrative report
  healthcare/
    sector_data.json
    sector_overview.md
```

### sector_data.json schema

```json
{
  "schema_version": "1.0",
  "sector": "Technology",
  "sector_slug": "technology",
  "generated_at": "2026-03-31T16:00:00Z",
  "company_count": 8,
  "companies": [
    {
      "ticker": "NVDA",
      "name": "NVIDIA Corporation",
      "industry": "Semiconductors",
      "market_cap": 2800000000000,
      "metrics": {
        "revenue": 130497000000,
        "revenue_growth": 0.55,
        "operating_margin": 0.58,
        "net_margin": 0.52,
        "roe": 0.85,
        "roic": 0.45,
        "pe_ratio": 35.2,
        "ev_to_ebitda": 28.1,
        "fcf_yield": 0.028,
        "debt_to_equity": 0.42
      }
    }
  ],
  "sector_aggregates": {
    "median_revenue_growth": 0.12,
    "median_operating_margin": 0.22,
    "median_pe_ratio": 28.5,
    "median_ev_ebitda": 20.3,
    "median_roe": 0.22,
    "total_market_cap": 15000000000000,
    "avg_debt_to_equity": 0.65
  },
  "subsectors": {
    "Semiconductors": ["NVDA", "AMD", "AVGO"],
    "Software": ["MSFT", "CRM"],
    "Internet": ["GOOGL", "META", "AMZN"]
  },
  "valuation_range": {
    "pe_low": 15.2,
    "pe_high": 65.0,
    "pe_median": 28.5,
    "ev_ebitda_low": 10.1,
    "ev_ebitda_high": 45.0,
    "ev_ebitda_median": 20.3
  }
}
```

## Workflow

### Task 1: Collect Sector Data (Script — `collect_sector.py`)

1. Fetch all companies from `GET /api/companies/`
2. Group companies by sector (and optionally by industry/subsector)
3. For each company in the target sector, fetch metrics and latest income statement
4. Compute sector-level aggregates (medians, ranges, totals)
5. Write `sector_data.json` to artifacts

### Task 2: Generate Sector Report (Script + AI — `generate_sector_report.py`)

1. Read `sector_data.json`
2. Build competitive comparison tables
3. Compute valuation context (premium/discount to sector median)
4. Generate narrative report covering:
   - Sector overview and market size
   - Competitive landscape with company profiles
   - Valuation comparison table
   - Key trends and investment implications
5. Write `sector_overview.md` to artifacts

## CLI

```bash
# Generate sector overview for a specific sector
uv run python skills/sector-overview/scripts/collect_sector.py --sector Technology

# List all available sectors
uv run python skills/sector-overview/scripts/collect_sector.py --list

# Generate report from collected data
uv run python skills/sector-overview/scripts/generate_sector_report.py --sector Technology

# Full pipeline: collect + generate
uv run python skills/sector-overview/scripts/collect_sector.py --sector Technology && \
uv run python skills/sector-overview/scripts/generate_sector_report.py --sector Technology

# Generate for all sectors with 3+ companies
uv run python skills/sector-overview/scripts/collect_sector.py --all --min-companies 3

# Persist report to database
uv run python skills/sector-overview/scripts/generate_sector_report.py --sector Technology --persist
```

## Report Structure

The markdown report follows this outline:

1. **Sector Overview** — sector name, company count, total market cap, key characteristics
2. **Competitive Landscape** — comparison table of all companies with key metrics
3. **Subsector Breakdown** — companies grouped by industry with mini-profiles
4. **Valuation Context** — current multiples, sector median, premium/discount per company
5. **Growth & Profitability** — revenue growth vs. margin scatter, who's best positioned
6. **Key Themes** — AI-generated thematic observations (requires agent step)
7. **Investment Implications** — where are the opportunities within the sector

## Sector Slug Convention

Sectors are normalized to URL-safe slugs for directory names:

| Sector | Slug |
|--------|------|
| Technology | `technology` |
| Healthcare | `healthcare` |
| Financials | `financials` |
| Consumer Discretionary | `consumer-discretionary` |
| Consumer Staples | `consumer-staples` |
| Energy | `energy` |
| Industrials | `industrials` |
| Materials | `materials` |
| Real Estate | `real-estate` |
| Utilities | `utilities` |
| Communication Services | `communication-services` |

## Cross-Skill Integration

| Skill | How it uses sector overviews |
|-------|------------------------------|
| `idea-generation` | Cross-references screen results with sector context |
| `company-profile` | Sector comps section references sector-level data |
| `fund-manager` | Sector allocation decisions informed by sector health |
| `risk-manager` | Sector concentration checks against sector landscape |

## Important Notes

- Sector overviews age fast — include generation date prominently
- Charts are handled by Streamlit — output structured data, not images
- Source all market size data — cite methodology or note "based on ingested companies only"
- Distinguish between our coverage universe and the full sector — we only have ~30 companies
- Subsector grouping uses the `industry` field from the companies table
