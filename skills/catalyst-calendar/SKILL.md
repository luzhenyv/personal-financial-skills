---
name: catalyst-calendar
description: Unified cross-portfolio event calendar. Aggregates catalysts from all thesis-tracker instances plus known macro events (FOMC, CPI, GDP, etc.) into one timeline. Triggers on "catalyst calendar", "upcoming events", "what's coming up", "earnings calendar", "event calendar", "catalyst tracker", or "upcoming catalysts".
---

# Catalyst Calendar

Unified cross-portfolio event calendar — aggregates per-ticker catalysts from thesis-tracker plus macro events into a single timeline.

## Architecture

- **Input**: Per-ticker `catalysts.json` artifacts + SEC filing dates + known macro calendar
- **Output**: `data/artifacts/_portfolio/catalysts/`
- **Pattern**: Script-driven aggregation with formatted calendar generation

## Key Difference from thesis-tracker

Thesis-tracker stores catalysts **per-ticker** (`data/artifacts/{ticker}/thesis/catalysts.json`).
This skill aggregates **ALL** catalysts across the portfolio into a unified calendar view with macro events (FOMC, CPI, etc.) overlaid.

## Artifacts

```
data/artifacts/_portfolio/catalysts/
  calendar.json               # Unified catalyst calendar (structured)
  calendar.md                 # Formatted weekly/monthly view
  macro_events.json           # Persistent macro event calendar (user-managed)
```

### calendar.json schema

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-03-31T16:00:00Z",
  "horizon_start": "2026-03-31",
  "horizon_end": "2026-06-30",
  "total_events": 25,
  "events": [
    {
      "date": "2026-04-02",
      "event": "Q1 FY2027 Earnings",
      "ticker": "NVDA",
      "type": "earnings",
      "impact": "positive",
      "source": "thesis-tracker",
      "affected_assumptions": [0, 1],
      "notes": "First full quarter with Blackwell ramp",
      "status": "pending"
    },
    {
      "date": "2026-05-07",
      "event": "FOMC Interest Rate Decision",
      "ticker": null,
      "type": "macro",
      "impact": "neutral",
      "source": "macro_calendar",
      "affected_assumptions": null,
      "notes": "May meeting — market expects hold",
      "status": "pending"
    }
  ],
  "by_week": {
    "2026-W14": [
      {"date": "2026-04-02", "event": "...", "ticker": "NVDA", "type": "earnings"}
    ]
  },
  "by_type": {
    "earnings": 8,
    "corporate": 3,
    "macro": 10,
    "regulatory": 2,
    "conference": 2
  }
}
```

### Event Types

| Type | Description | Source |
|------|-------------|--------|
| `earnings` | Quarterly earnings reports | thesis-tracker catalysts + SEC filings |
| `corporate` | Product launches, M&A, management changes | thesis-tracker catalysts |
| `macro` | FOMC, CPI, GDP, jobs report | macro_events.json |
| `regulatory` | FDA, antitrust, export controls | thesis-tracker catalysts |
| `conference` | Investor days, industry conferences | thesis-tracker catalysts |
| `filing` | 10-K, 10-Q filing deadlines | SEC filing dates |

## Workflow

### Task 1: Collect Catalysts (Script — `collect_catalysts.py`)

1. Scan all ticker directories in `data/artifacts/` for `thesis/catalysts.json`
2. Read each per-ticker catalyst file, filter to pending events
3. Fetch SEC filing dates from `GET /api/filings/{ticker}/` for upcoming deadlines
4. Read `macro_events.json` for macro calendar events
5. Merge all events into unified timeline sorted by date
6. Write `calendar.json` to artifacts

### Task 2: Generate Calendar Report (Script — `generate_calendar.py`)

1. Read `calendar.json`
2. Group events by week and by type
3. Generate weekly preview with impact assessment
4. Highlight high-impact events and thesis-linked catalysts
5. Write `calendar.md` to artifacts

## CLI

```bash
# Collect all catalysts and build unified calendar
uv run python skills/catalyst-calendar/scripts/collect_catalysts.py

# Collect with custom horizon (default: 90 days)
uv run python skills/catalyst-calendar/scripts/collect_catalysts.py --days 30

# Generate formatted calendar report
uv run python skills/catalyst-calendar/scripts/generate_calendar.py

# Generate weekly preview only
uv run python skills/catalyst-calendar/scripts/generate_calendar.py --weekly

# Add a macro event
uv run python skills/catalyst-calendar/scripts/collect_catalysts.py --add-macro \
  --event "FOMC Rate Decision" --date 2026-05-07 --impact neutral

# List upcoming events (next 14 days)
uv run python skills/catalyst-calendar/scripts/collect_catalysts.py --upcoming 14
```

## Macro Events

The `macro_events.json` file stores recurring and one-off macro events. Pre-populated with known 2026 dates for:

- **FOMC meetings** (8 per year)
- **CPI releases** (monthly)
- **GDP reports** (quarterly)
- **Jobs reports** (monthly, first Friday)
- **PCE inflation** (monthly)

Users can add/remove macro events via `--add-macro` flag or by editing the JSON directly.

## Cross-Skill Integration

| Skill | How it uses the catalyst calendar |
|-------|-----------------------------------|
| `morning-briefing` | Reads `calendar.json` for "what's coming this week" section |
| `earnings-preview` | Triggered 5 days before earnings catalyst |
| `fund-manager` | Uses upcoming catalysts as timing signal for decisions |
| `risk-manager` | Flags positions with imminent binary events |

## Important Notes

- Earnings dates shift — verify against company IR pages closer to the date
- Pre-announce risk: companies may report early or issue warnings
- Status tracking: resolved/expired catalysts are kept for pattern recognition
- Color-code by impact in Streamlit: Red = high, Yellow = moderate, Green = routine
- Archive past catalysts with outcomes — builds institutional memory
