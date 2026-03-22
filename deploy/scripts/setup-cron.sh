#!/usr/bin/env bash
# setup-cron.sh — Configure OpenClaw cron jobs for Mini Bloomberg event-driven system
# Run once after setup-openclaw.sh
set -euo pipefail

# Delivery channel — adjust to your Discord channel ID or Telegram chat ID
# Using Discord channel from existing config
DISCORD_CHANNEL="1476607654221840525"

echo "=== Removing old cron jobs ==="
# List and remove existing investment-related jobs
for job_id in $(openclaw cron list --json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    jobs = data if isinstance(data, list) else data.get('jobs', [])
    for j in jobs:
        name = j.get('name', '')
        if any(k in name.lower() for k in ['english', 'daily post-market', 'weekly investment', 'morning', 'health check', 'portfolio', 'earnings']):
            print(j['id'])
except: pass
" 2>/dev/null); do
    echo "  Removing job: $job_id"
    openclaw cron rm "$job_id" 2>/dev/null || true
done

echo ""
echo "=== Adding Mini Bloomberg cron jobs ==="

# ── 1. Morning Brief (M-F 07:30 ET) ──
echo "Adding: Morning Brief..."
openclaw cron add \
    --name "Morning Brief" \
    --description "Pre-market briefing: overnight moves, thesis scores, catalyst timeline, new filing alerts" \
    --cron "30 7 * * 1-5" \
    --tz "America/New_York" \
    --session "isolated" \
    --timeout-seconds 300 \
    --announce \
    --channel "discord" \
    --to "channel:${DISCORD_CHANNEL}" \
    --message "Generate the morning brief. Follow the Morning Brief workflow in CLAUDE.md:
1. Check for new filing flags at /opt/pfs/data/artifacts/_flags/new_filings.json
2. cd /opt/pfs && uv run python skills/thesis-tracker/scripts/thesis_cli.py check --all
3. Summarize overnight price moves for tracked companies (ls /opt/pfs/data/artifacts/ | grep -v _)
4. List upcoming catalysts from thesis files
5. Format as a concise morning brief for Discord"

# ── 2. Weekly Health Check (Saturday 10:00 ET) ──
echo "Adding: Weekly Health Check..."
openclaw cron add \
    --name "Weekly Health Check" \
    --description "Run thesis health checks for all tracked companies, compare against last week" \
    --cron "0 10 * * 6" \
    --tz "America/New_York" \
    --session "isolated" \
    --timeout-seconds 600 \
    --announce \
    --channel "discord" \
    --to "channel:${DISCORD_CHANNEL}" \
    --message "Run weekly thesis health check. Follow the Weekly Health Check workflow in CLAUDE.md:
1. cd /opt/pfs
2. For each tracked company in data/artifacts/, run: uv run python skills/thesis-tracker/scripts/thesis_cli.py check {TICKER}
3. Review git diff of health_checks.json to see what changed from last week: cd /opt/pfs/data/artifacts && git diff HEAD~1 -- */thesis/health_checks.json
4. Flag any assumptions that flipped status (good→warning, warning→critical)
5. Commit updated artifacts: cd /opt/pfs/data/artifacts && git add -A && git commit -m 'Weekly health check'
6. Deliver summary report"

# ── 3. Weekly Portfolio Summary (Friday 18:00 ET) ──
echo "Adding: Weekly Portfolio Summary..."
openclaw cron add \
    --name "Weekly Portfolio Summary" \
    --description "End-of-week portfolio review with score trends, price performance, catalyst review" \
    --cron "0 18 * * 5" \
    --tz "America/New_York" \
    --session "isolated" \
    --timeout-seconds 600 \
    --announce \
    --channel "discord" \
    --to "channel:${DISCORD_CHANNEL}" \
    --message "Generate the weekly portfolio summary. Follow the Weekly Portfolio Summary workflow in CLAUDE.md:
1. cd /opt/pfs
2. Aggregate thesis scores for all tracked companies
3. Check price performance: uv run python -c \"from pfs.etl.yfinance_client import get_current_price; [print(t, get_current_price(t)) for t in ['NVDA','AMD']]\"
4. Review this week's artifact git log: cd /opt/pfs/data/artifacts && git log --oneline --since='7 days ago'
5. Review upcoming catalyst timeline from thesis catalyst files
6. Format as comprehensive weekly report for Discord"

# ── 4. Earnings Alert Handler (on-demand, triggered by morning brief detecting flags) ──
# Note: This is NOT a cron job — it's triggered by the morning brief agent
# when it detects new_filings.json flag. Documenting here for completeness.

echo ""
echo "=== Cron jobs configured ==="
openclaw cron list 2>/dev/null
echo ""
echo "=== Done ==="
echo ""
echo "Mechanical timers (systemd) handle:"
echo "  - Price sync: M-F 17:30 ET (pfs-price-sync.timer)"
echo "  - Artifact commit: Daily 23:55 (pfs-artifact-commit.timer)"
echo "  - Filing check: Daily 06:00 ET (pfs-filing-check.timer)"
echo ""
echo "Intelligent jobs (OpenClaw cron) handle:"
echo "  - Morning Brief: M-F 07:30 ET"
echo "  - Weekly Health Check: Sat 10:00 ET"
echo "  - Weekly Portfolio Summary: Fri 18:00 ET"
