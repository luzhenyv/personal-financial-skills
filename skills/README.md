# Skills Directory

This directory contains agent-readable skill definitions for the Mini Bloomberg personal investor toolkit.

## How Agents Should Use These Skills

Each skill is a self-contained directory with:

- `SKILL.md` — The main skill definition. **Read this first.** It tells the agent what the skill does, when to use it, and step-by-step workflow instructions.
- `references/` — Supporting knowledge files with templates, formulas, data source guides, etc.

## Available Skills

| Skill | Purpose | Status |
|-------|---------|--------|
| `company-profile/` | Generate 1-page markdown tearsheet for a company | ✅ |
| `financial-etl/` | Fetch SEC XBRL data → parse → store in PostgreSQL | ✅ |
| `etl-coverage/` | Audit ETL data coverage, find unmapped XBRL tags, diagnose NULLs | ✅ |
| `three-statements/` | 3-statement financial model in markdown | 🔜 |
| `dcf-valuation/` | Simplified DCF model with sensitivity analysis | 🔜 |
| `comps-analysis/` | Comparable company analysis from DB | 🔜 |
| `earnings-analysis/` | Post-earnings quick take | 🔜 |
| `stock-screening/` | Screen companies by financial criteria | 🔜 |
| `portfolio-monitoring/` | Track holdings, P&L, alerts | 🔜 |

## Invoking a Skill

An agent (Claude Code, GitHub Copilot, etc.) reads the SKILL.md and follows its workflow:

```
Agent: "I need to create a company profile for NVDA"
→ Reads skills/company-profile/SKILL.md
→ Follows Step 1: check if data exists in DB
→ If not, triggers skills/financial-etl/SKILL.md first
→ Follows Step 2-5: query DB, fill template, save
```

## Database Connection

All skills that query data expect PostgreSQL at the URL in `.env`:
```
DATABASE_URL=postgresql://pfs:pfs_dev_2024@localhost:5432/personal_finance
```

Skills that write analysis reports save:
1. Markdown file to `data/reports/{ticker}/`
2. Record to `analysis_reports` table in PostgreSQL
