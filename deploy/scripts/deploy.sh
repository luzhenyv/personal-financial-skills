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
systemctl restart pfs-streamlit
systemctl restart pfs-task-dispatcher

echo "=== Status ==="
systemctl status pfs-streamlit --no-pager -l | head -10
echo "---"
systemctl status pfs-task-dispatcher --no-pager -l | head -10
echo "---"
echo "Data Server API health (via Tailscale):"
curl -s http://100.124.144.100:8000/health || echo "Data Server not responding"
echo ""
echo "Streamlit: http://100.106.13.112:8501"
echo "=== Deploy complete ==="
