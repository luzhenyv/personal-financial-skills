# Conviction-to-Weight Alignment Rules

Rules for evaluating whether portfolio position sizing matches investment conviction.

## Weight Targets by Conviction Level

| Conviction | Target Range | Min Alert | Max Alert | Notes |
|------------|-------------|-----------|-----------|-------|
| **High** | 8–15% | < 5% | > 20% | Core positions with strong thesis |
| **Medium** | 3–8% | < 2% | > 12% | Moderate conviction, limited sizing |
| **Low** | 1–3% | — | > 5% | Small positions, watching thesis develop |
| **Unset** | — | — | Any size | No thesis = no conviction = flag immediately |

## Alignment Status Definitions

- **Aligned**: Weight is within target range for stated conviction
- **Underweight**: Weight is below minimum alert threshold — consider adding
- **Overweight**: Weight is above maximum alert threshold — consider trimming
- **Orphaned**: No thesis exists — position lacks documented investment rationale

## Priority of Misalignments

When multiple misalignments exist, prioritize by:

1. **Orphaned positions > 5%** — large undocumented positions
2. **Thesis score < 30 (exit recommended)** — broken theses still held
3. **Overweight low-conviction** — outsized bets without conviction
4. **Underweight high-conviction** — not sizing up on best ideas
5. **Sector concentration > 30%** — systematic risk

## Cash Guidelines

| Cash Level | Status | Action |
|-----------|--------|--------|
| < 5% | Too low | Trim weakest position to rebuild buffer |
| 5–15% | Healthy | Normal operating range |
| 15–25% | Elevated | Acceptable if waiting for opportunities |
| > 25% | Cash drag | May hurt returns — deploy or accept drag |
