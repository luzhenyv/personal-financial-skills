#!/usr/bin/env bash
# deploy.sh — Pull latest code and restart Agent Server services
# Run on the Agent Server (DMIT): ssh dmitserver "bash /opt/pfs/deploy/scripts/deploy.sh"
# NOTE: Data Server (Mac) has no systemd — restart FastAPI/MCP manually there.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

PROJECT_DIR="/opt/pfs"
cd "$PROJECT_DIR"

echo "=== Pulling latest code ==="
git pull --ff-only

echo "=== Syncing Python dependencies ==="
# uv.lock is gitignored — plain sync generates a local lockfile
uv sync

echo "=== Updating OpenClaw CLAUDE.md ==="
cp "$PROJECT_DIR/agents/openclaw/CLAUDE.md" /root/.openclaw/workspace/CLAUDE.md

echo "=== Restarting services ==="
for service in pfs-api pfs-mcp pfs-prefect pfs-prefect-worker pfs-streamlit pfs-task-dispatcher; do
	if systemctl list-unit-files "$service.service" >/dev/null 2>&1; then
		systemctl restart "$service"
	fi
done

echo "=== Status ==="
for service in pfs-api pfs-mcp pfs-prefect pfs-prefect-worker pfs-streamlit pfs-task-dispatcher; do
	if systemctl list-unit-files "$service.service" >/dev/null 2>&1; then
		systemctl status "$service" --no-pager -l | head -10
		echo "---"
	fi
done
echo "API health:"
source "$PROJECT_DIR/.env"
curl -s "${PFS_API_URL:-http://100.124.144.100:8000}/health" || echo "API not responding"
echo ""
echo "Streamlit: http://100.106.13.112:8501"
echo "=== Deploy complete ==="
