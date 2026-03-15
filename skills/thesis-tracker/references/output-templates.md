# Output Templates

Markdown templates for thesis files written to `data/artifacts/{TICKER}/thesis_{TICKER}.md`.

## Thesis Creation Template

```markdown
# {TICKER} Investment Thesis
**Created:** {date}
**Status:** Active
**Position:** Long

## Core Thesis
{One-sentence thesis statement}

## Buy Reasons
1. {Reason 1}
2. {Reason 2}
3. {Reason 3}

## Prerequisite Assumptions
- Assumption 1: {description} [Weight: X%]
- Assumption 2: {description} [Weight: Y%]
- Assumption 3: {description} [Weight: Z%]

## Sell Conditions
- {Condition 1}
- {Condition 2}
- {Condition 3}

## Where I Might Be Wrong
- {Risk 1}
- {Risk 2}
- {Risk 3}

## Thesis Update Log
(Updates will be appended below)
```

## Thesis Update Template

Appended to thesis file under the Update Log section:

```markdown
### {date} | {event_title}
**Trigger:** {what happened}
**Assumption Changes:**
- Assumption 1: {status_emoji} — {brief explanation}
- Assumption 2: {status_emoji} — {brief explanation}
- Assumption 3: {status_emoji} — {brief explanation}

**Thesis Strength:** {Strengthened/Weakened/Unchanged}
**Action:** {action taken}
**Conviction:** {High/Medium/Low}
```

## Health Check Template

Appended to thesis file:

```markdown
## Thesis Health Check | {date}

### Assumption Scorecard
| Assumption | Weight | Objective | Subjective | Combined | Status |
|------------|--------|-----------|------------|----------|--------|
| {Assumption 1} | 40% | 85 | 80 | 83 | ✓ Intact |
| {Assumption 2} | 35% | 70 | 65 | 68 | ⚠️ Watch |
| {Assumption 3} | 25% | 90 | 85 | 88 | ✓ Intact |

### Composite Score: 80/100 (prev: 91/100)
- Objective: 82/100
- Subjective: 77/100

### Key Observations
- {What strengthened}
- {What weakened}
- {What to monitor}

### Recommendation
{Hold / Trim / Add / Exit — with reasoning}
```
