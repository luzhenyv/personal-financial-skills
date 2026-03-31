---
name: morning-briefing
description: Automated daily research digest — portfolio performance, market movers, position updates, catalyst calendar, and action items. Triggers on "morning briefing", "daily brief", "what happened overnight", "morning note", or "daily digest".
---

# Morning Briefing

Core question: **"What happened, what matters today, and what do I need to do?"**

Adapted from Anthropic's equity-research `morning-note` skill, simplified to single-person format (no team meeting, no distribution list).

## Workflow

### Step 1: Collect Data (Script)

```bash
uv run python skills/morning-briefing/scripts/collect_briefing.py
uv run python skills/morning-briefing/scripts/collect_briefing.py --date 2026-03-28
```

Collects from REST API:
- Portfolio positions with P&L (`GET /api/portfolio/positions`)
- Portfolio summary (`GET /api/portfolio/`)
- Recent price moves for all positions (`GET /api/financials/{TICKER}/prices?period=5d`)
- Catalyst calendar from thesis artifacts
- Risk alerts from `data/artifacts/_portfolio/risk/alerts.json`
- Thesis health scores from `data/artifacts/{TICKER}/thesis/health_checks.json`

Writes `{YYYY-MM-DD}_raw.json` to artifacts.

### Step 2: Generate Briefing (Script + AI)

```bash
uv run python skills/morning-briefing/scripts/generate_briefing.py
uv run python skills/morning-briefing/scripts/generate_briefing.py --date 2026-03-28 --persist
```

Produces a structured markdown briefing:

1. **Portfolio Snapshot** — total value, daily P&L, top movers
2. **Notable Movers** — positions with significant price changes (>2%)
3. **Catalyst Calendar** — upcoming events this week
4. **Risk Alerts** — active alerts from risk-manager
5. **Action Items** — thesis checks due, stale health checks, earnings upcoming

## Artifacts

Output goes to `data/artifacts/_daily/`:

| File | Contents |
|------|----------|
| `{YYYY-MM-DD}_raw.json` | Collected data snapshot |
| `{YYYY-MM-DD}.md` | Morning briefing markdown |

## REST API Endpoints Used

| Endpoint | What we read |
|----------|-------------|
| `GET /api/portfolio/` | Portfolio summary (cash, total value, P&L) |
| `GET /api/portfolio/positions` | Positions with current P&L |
| `GET /api/financials/{TICKER}/prices?period=5d` | Recent price action per position |
| `GET /api/companies/{TICKER}` | Company name for display |

## Cross-Skill Reads

- `data/artifacts/{TICKER}/thesis/catalysts.json` — catalyst calendar per position
- `data/artifacts/{TICKER}/thesis/health_checks.json` — thesis health scores
- `data/artifacts/_portfolio/risk/alerts.json` — active risk alerts
- `data/artifacts/_portfolio/risk/risk_report.json` — latest risk metrics

## Important Notes

- Be opinionated — a briefing that just lists numbers without commentary is useless
- Lead with the most important thing
- "Nothing material" is a valid briefing — say so and move on
- Keep it to 1-page readable in 2 minutes
- Trigger: Daily via Prefect cron (6:30 AM) or manual
