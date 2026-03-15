# Skills Directory

This directory contains agent-readable skill definitions for the Mini Bloomberg personal investor toolkit.

## How Agents Should Use These Skills

Each skill is a self-contained directory with:

- `SKILL.md` — The main skill definition. **Read this first.** It tells the agent what the skill does, when to use it, and step-by-step workflow instructions.
- `references/` — Supporting knowledge files with templates, formulas, data source guides, etc.

## Available Skills

| Skill | Purpose | Output Path | Status |
|-------|---------|-------------|--------|
| `company-profile/` | Generate 1-page markdown tearsheet for a company | `data/artifacts/{ticker}/profile/` | ✅ |
| `etl-coverage/` | Audit ETL data coverage, find unmapped XBRL tags, diagnose NULLs | `data/artifacts/_etl/` | ✅ |
| `thesis-tracker/` | Maintain and version investment thesis documents | `data/artifacts/{ticker}/thesis/` | ✅ |
| `three-statements/` | 3-statement financial model in markdown | 🔜 | 🔜 |
| `dcf-valuation/` | Simplified DCF model with sensitivity analysis | 🔜 | 🔜 |
| `comps-analysis/` | Comparable company analysis from DB | 🔜 | 🔜 |
| `earnings-analysis/` | Post-earnings quick take | 🔜 | 🔜 |
| `stock-screening/` | Screen companies by financial criteria | 🔜 | 🔜 |
| `portfolio-monitoring/` | Track holdings, P&L, alerts | 🔜 | 🔜 |

## Invoking a Skill

An agent (Claude Code, GitHub Copilot, etc.) reads the SKILL.md and follows its workflow:

```
Agent: "I need to create a company profile for NVDA"
→ Reads skills/company-profile/SKILL.md
→ Checks prerequisite: is data in MCP? (calls list_companies, get_company)
→ If not, tells user to run ETL first
→ Follows Task 1: Company Research (reads MCP + 10k_raw_sections.json)
→ Follows Task 2: Financial Analysis (build_comps.py)
→ Follows Task 3: Report Generation (generate_report.py)
→ Artifacts saved to data/artifacts/NVDA/profile/
```

## Data Access

Skills access financial data through the MCP server (`personal-finance`), which provides
read-only access to PostgreSQL. The agent **never writes to PostgreSQL directly**.

### Data Source Priority

```
MCP (PostgreSQL) > local SEC files > Alpha Vantage > yfinance > web search
```

## Artifact Output

All skills write to `data/artifacts/{ticker}/{skill}/`. Every JSON file must include
`"schema_version": "1.0"`. Streamlit reads artifacts for display — it never writes.
