#!/usr/bin/env bash
# deploy.sh — Pull latest code and restart services
# Usage: ssh dmitserver "bash /opt/pfs/deploy/scripts/deploy.sh"
set -euo pipefail

PROJECT_DIR="/opt/pfs"
cd "$PROJECT_DIR"

echo "=== Pulling latest code ==="
git pull --ff-only

echo "=== Syncing Python dependencies ==="
/root/.local/bin/uv sync

echo "=== Restarting services ==="
systemctl restart pfs-api
systemctl restart pfs-streamlit

echo "=== Updating OpenClaw CLAUDE.md ==="
cp "$PROJECT_DIR/deploy/openclaw/CLAUDE.md" /root/.openclaw/workspace/CLAUDE.md

echo "=== Status ==="
systemctl status pfs-api --no-pager -l | head -10
echo "---"
systemctl status pfs-streamlit --no-pager -l | head -10
echo "---"
echo "API health:"
curl -s http://localhost:8000/health || echo "API not responding"
echo ""
echo "=== Deploy complete ==="
