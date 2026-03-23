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

ENABLE_LOCAL_DATA_PLANE=0
for arg in "$@"; do
    case "$arg" in
        --with-local-data-plane)
            ENABLE_LOCAL_DATA_PLANE=1
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

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
    if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
        cat > "$PROJECT_DIR/.env" <<'ENVEOF'
# Agent Server .env — local SQLite demo mode
DATABASE_URL=sqlite:////opt/pfs/data/personal_finance.db
PFS_TAILSCALE_IP=100.106.13.112
PFS_API_URL=http://100.106.13.112:8000
PFS_MCP_URL=http://100.106.13.112:8001/mcp
API_BASE_URL=http://100.106.13.112:8000
PFS_API_BIND_HOST=100.106.13.112
PFS_API_PORT=8000
PFS_MCP_BIND_HOST=100.106.13.112
PFS_MCP_PORT=8001
PFS_STREAMLIT_BIND_HOST=100.106.13.112
PFS_STREAMLIT_PORT=8501
PFS_PREFECT_BIND_HOST=100.106.13.112
PFS_PREFECT_PORT=4200
PFS_PREFECT_POOL=pfs-demo-pool
PREFECT_API_URL=http://100.106.13.112:4200/api
PFS_POLL_INTERVAL=60
PFS_TASK_TIMEOUT=600
PFS_PROJECT_DIR=/opt/pfs
CORS_ORIGINS=http://localhost:8501,http://100.106.13.112:8501
GITHUB_TOKEN=
SEC_USER_AGENT=PersonalFinanceApp your@email.com
ALPHA_VANTAGE_KEY=
ENVEOF
    else
        cat > "$PROJECT_DIR/.env" <<'ENVEOF'
# Agent Server .env
# Data Server Tailscale IP: 100.124.144.100
PFS_API_URL=http://100.124.144.100:8000
PFS_MCP_URL=http://100.124.144.100:8001/mcp
API_BASE_URL=http://100.124.144.100:8000
PFS_STREAMLIT_BIND_HOST=100.106.13.112
PFS_STREAMLIT_PORT=8501
PFS_POLL_INTERVAL=60
PFS_TASK_TIMEOUT=600
PFS_PROJECT_DIR=/opt/pfs
CORS_ORIGINS=http://localhost:8501,http://100.106.13.112:8501
GITHUB_TOKEN=
SEC_USER_AGENT=PersonalFinanceApp your@email.com
ALPHA_VANTAGE_KEY=
ENVEOF
    fi
    echo "Created .env — update GITHUB_TOKEN and API keys if needed:"
    echo "  nano $PROJECT_DIR/.env"
else
    echo ".env already exists — skipping"
    if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
        cat >> "$PROJECT_DIR/.env" <<'ENVEOF'

# Local SQLite demo mode overrides
DATABASE_URL=sqlite:////opt/pfs/data/personal_finance.db
PFS_API_URL=http://100.106.13.112:8000
PFS_MCP_URL=http://100.106.13.112:8001/mcp
API_BASE_URL=http://100.106.13.112:8000
PFS_API_BIND_HOST=100.106.13.112
PFS_API_PORT=8000
PFS_MCP_BIND_HOST=100.106.13.112
PFS_MCP_PORT=8001
PFS_STREAMLIT_BIND_HOST=100.106.13.112
PFS_STREAMLIT_PORT=8501
PFS_PREFECT_BIND_HOST=100.106.13.112
PFS_PREFECT_PORT=4200
PFS_PREFECT_POOL=pfs-demo-pool
PREFECT_API_URL=http://100.106.13.112:4200/api
CORS_ORIGINS=http://localhost:8501,http://100.106.13.112:8501
ENVEOF
    fi
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

if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
    cp deploy/systemd/pfs-api.service /etc/systemd/system/
    cp deploy/systemd/pfs-mcp.service /etc/systemd/system/
    cp deploy/systemd/pfs-prefect.service /etc/systemd/system/
    cp deploy/systemd/pfs-prefect-worker.service /etc/systemd/system/
fi

systemctl daemon-reload
systemctl enable pfs-streamlit pfs-task-dispatcher
if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
    systemctl enable pfs-api pfs-mcp pfs-prefect pfs-prefect-worker
fi

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
if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
    uv run python scripts/init_db.py --seed-tasks
    systemctl start pfs-api pfs-mcp pfs-prefect
    sleep 5
    /root/.local/bin/uv run prefect work-pool inspect pfs-demo-pool >/dev/null 2>&1 || \
        /root/.local/bin/uv run prefect work-pool create pfs-demo-pool --type process
    (cd "$PROJECT_DIR/prefect/flows" && /root/.local/bin/uv run prefect deploy --all) || true
    systemctl start pfs-prefect-worker
fi

systemctl start pfs-streamlit pfs-task-dispatcher
sleep 3
systemctl is-active pfs-streamlit pfs-task-dispatcher || true
if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
    systemctl is-active pfs-api pfs-mcp pfs-prefect pfs-prefect-worker || true
fi
echo ""
echo "Streamlit:        http://100.106.13.112:8501"
if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
    echo "API reachable at: http://100.106.13.112:8000"
    echo "MCP reachable at: http://100.106.13.112:8001/mcp"
    echo "Prefect UI:       http://100.106.13.112:4200"
else
    echo "API reachable at: http://100.124.144.100:8000"
fi
echo ""
echo "Verify:"
echo "  systemctl status pfs-streamlit pfs-task-dispatcher"
if [[ "$ENABLE_LOCAL_DATA_PLANE" -eq 1 ]]; then
    echo "  systemctl status pfs-api pfs-mcp pfs-prefect pfs-prefect-worker"
    echo "  curl http://100.106.13.112:8000/health"
else
    echo "  curl http://100.124.144.100:8000/health"
fi
echo ""
echo "Optional — add artifact GitHub remote:"
echo "  git -C $ARTIFACTS_DIR remote add origin https://github.com/<user>/pfs-artifacts.git"
echo "  6. Set up OpenClaw cron: bash /opt/pfs/deploy/scripts/setup-cron.sh"
echo ""
