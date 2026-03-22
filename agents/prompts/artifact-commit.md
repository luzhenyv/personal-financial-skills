# Artifact Version Control — MANDATORY

After writing ANY file(s) under `data/artifacts/`, you MUST immediately commit:

```bash
cd {PROJECT_ROOT}/data/artifacts
git add -A
git commit -m "[{skill}] {TICKER}: {brief description of what changed}"
```

Examples:
- `[company-profile] NVDA: generated profile v1`
- `[thesis-tracker] AAPL: Q1 2026 health check — score 72→68`
- `[thesis-tracker] MSFT: added catalyst — Azure AI revenue milestone`

If the commit fails (nothing to commit), that's fine — continue.
Do NOT push. Push is handled by a separate daily cron or manual trigger.
