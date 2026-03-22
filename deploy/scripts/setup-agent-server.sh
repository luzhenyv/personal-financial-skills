#!/usr/bin/env bash
# setup-agent-server.sh — One-shot setup for Agent Server (DMIT)
# Runs: task dispatcher, OpenClaw, artifact git repo
# NO PostgreSQL, NO Prefect — talks to Data Server via HTTP only
#
# Prerequisites:
#   - Tailscale connected (access to Data Server)
#   - .env with PFS_API_URL pointing to Data Server
#
# Usage: ssh agent-server "bash /opt/pfs/deploy/scripts/setup-agent-server.sh"
set -euo pipefail

echo "=========================================="
echo "  Mini Bloomberg — Agent Server Setup"
echo "=========================================="

PROJECT_DIR="/opt/pfs"
cd "$PROJECT_DIR"

# ── 1. System packages ──
echo ""
echo "=== [1/7] Installing system packages ==="
apt update -qq
apt install -y -qq git curl

# ── 2. uv (Python package manager) ──
echo ""
echo "=== [2/7] Installing uv ==="
if ! command -v /root/.local/bin/uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
else
    echo "uv already installed"
fi
export PATH="$HOME/.local/bin:$PATH"

# ── 3. Python environment ──
echo ""
echo "=== [3/7] Setting up Python environment ==="
uv sync

# ── 4. Environment file ──
echo ""
echo "=== [4/7] Environment configuration ==="
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cat > "$PROJECT_DIR/.env" <<'ENVEOF'
# Agent Server .env
# Data Server Tailscale IP: 100.124.144.100
PFS_API_URL=http://100.124.144.100:8000
PFS_MCP_URL=http://100.124.144.100:8001/mcp
PFS_POLL_INTERVAL=60
PFS_TASK_TIMEOUT=600
PFS_PROJECT_DIR=/opt/pfs
GITHUB_TOKEN=
SEC_USER_AGENT=PersonalFinanceApp your@email.com
ALPHA_VANTAGE_KEY=
ENVEOF
    echo "Created .env — update GITHUB_TOKEN and API keys if needed:"
    echo "  nano $PROJECT_DIR/.env"
else
    echo ".env already exists — skipping"
fi

# ── 5. Initialize artifact git repo ──
echo ""
echo "=== [5/7] Initializing artifact git repo ==="
ARTIFACTS_DIR="$PROJECT_DIR/data/artifacts"
mkdir -p "$ARTIFACTS_DIR"
if [[ ! -d "$ARTIFACTS_DIR/.git" ]]; then
    cd "$ARTIFACTS_DIR"
    cp "$PROJECT_DIR/agents/openclaw/artifact-gitignore" .gitignore 2>/dev/null || true
    git init
    git checkout -b main
    git -c user.email="pfs@local" -c user.name="PFS Agent" add -A
    git -c user.email="pfs@local" -c user.name="PFS Agent" \
        commit --allow-empty -m "Initial artifact snapshot"
    echo "Artifact repo initialized at $ARTIFACTS_DIR"
    echo ""
    echo "Add GitHub remote:"
    echo "  git -C $ARTIFACTS_DIR remote add origin https://github.com/<user>/pfs-artifacts.git"
else
    echo "Artifact repo already exists"
fi
cd "$PROJECT_DIR"

# ── 6. Install systemd services ──
echo ""
echo "=== [6/7] Installing systemd services ==="
chmod +x deploy/scripts/*.sh

cp deploy/systemd/pfs-streamlit.service /etc/systemd/system/
cp deploy/systemd/pfs-task-dispatcher.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable pfs-streamlit pfs-task-dispatcher

echo "Services installed."

# ── 7. OpenClaw workspace ──
echo ""
echo "=== [7/7] Setting up OpenClaw workspace ==="
bash "$PROJECT_DIR/deploy/scripts/setup-openclaw.sh"

echo ""
echo "=========================================="
echo "  Agent Server Setup Complete!"
echo "=========================================="
echo ""
echo "Starting services..."
systemctl start pfs-streamlit pfs-task-dispatcher
sleep 3
systemctl is-active pfs-streamlit pfs-task-dispatcher || true
echo ""
echo "Streamlit:        http://100.106.13.112:8501"
echo "API reachable at: http://100.124.144.100:8000"
echo ""
echo "Verify:"
echo "  systemctl status pfs-streamlit pfs-task-dispatcher"
echo "  curl http://100.124.144.100:8000/health"
echo ""
echo "Optional — add artifact GitHub remote:"
echo "  git -C $ARTIFACTS_DIR remote add origin https://github.com/<user>/pfs-artifacts.git"
echo "  6. Set up OpenClaw cron: bash /opt/pfs/deploy/scripts/setup-cron.sh"
echo ""
