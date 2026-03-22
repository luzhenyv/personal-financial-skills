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
# Agent Server .env — edit with real values
# Data Server API (via Tailscale)
PFS_API_URL=http://100.124.x.x:8000
# MCP HTTP endpoint (via Tailscale)
PFS_MCP_URL=http://100.124.x.x:8001/mcp
# Dispatcher settings
PFS_POLL_INTERVAL=60
PFS_TASK_TIMEOUT=600
PFS_PROJECT_DIR=/opt/pfs
# GitHub token for artifact push (generate a fine-grained PAT)
GITHUB_TOKEN=
ENVEOF
    echo "Created .env — EDIT IT with real values:"
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
    cp "$PROJECT_DIR/agents/openclaw/artifact-gitignore" .gitignore
    git init
    git checkout -b main
    git add -A
    git commit -m "Initial artifact snapshot" --allow-empty
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

# Task dispatcher
cp deploy/systemd/pfs-task-dispatcher.service /etc/systemd/system/

# Artifact commit timer (daily push)
cp deploy/systemd/pfs-artifact-commit.service /etc/systemd/system/
cp deploy/systemd/pfs-artifact-commit.timer /etc/systemd/system/

systemctl daemon-reload
systemctl enable pfs-artifact-commit.timer

echo "Services installed. Start after editing .env:"
echo "  systemctl enable --now pfs-task-dispatcher"
echo "  systemctl start pfs-artifact-commit.timer"

# ── 7. OpenClaw workspace ──
echo ""
echo "=== [7/7] Setting up OpenClaw workspace ==="
bash "$PROJECT_DIR/deploy/scripts/setup-openclaw.sh"

echo ""
echo "=========================================="
echo "  Agent Server Setup Complete!"
echo "=========================================="
echo ""
echo "Remaining manual steps:"
echo "  1. Edit /opt/pfs/.env with Data Server Tailscale IP + GitHub token"
echo "  2. Add artifact remote: git -C $ARTIFACTS_DIR remote add origin https://github.com/<user>/pfs-artifacts.git"
echo "  3. Verify API access: curl \$PFS_API_URL/health"
echo "  4. Start dispatcher: systemctl enable --now pfs-task-dispatcher"
echo "  5. Start artifact timer: systemctl start pfs-artifact-commit.timer"
echo "  6. Set up OpenClaw cron: bash /opt/pfs/deploy/scripts/setup-cron.sh"
echo ""
