#!/usr/bin/env bash
# setup-data-server.sh — One-shot setup for Data Server (Mac Mini)
# Runs: PostgreSQL (Docker), FastAPI, MCP HTTP server, Prefect, Streamlit
# NO OpenClaw, NO task dispatcher — those run on Agent Server
#
# Prerequisites:
#   - Docker Desktop installed and running
#   - Tailscale connected
#
# Usage: bash /opt/pfs/deploy/scripts/setup-data-server.sh
set -euo pipefail

echo "=========================================="
echo "  Mini Bloomberg — Data Server Setup"
echo "=========================================="

PROJECT_DIR="/opt/pfs"
cd "$PROJECT_DIR"

# ── 1. Check Docker ──
echo ""
echo "=== [1/8] Checking Docker ==="
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker not found. Install Docker Desktop first."
    exit 1
fi
if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker daemon not running. Start Docker Desktop."
    exit 1
fi
echo "Docker OK"

# ── 2. uv (Python package manager) ──
echo ""
echo "=== [2/8] Installing uv ==="
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "uv already installed"
fi

# ── 3. Python environment ──
echo ""
echo "=== [3/8] Setting up Python environment ==="
uv sync

# ── 4. Environment file ──
echo ""
echo "=== [4/8] Environment configuration ==="
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cat > "$PROJECT_DIR/.env" <<'ENVEOF'
# Data Server .env — edit with real values
# PostgreSQL (Docker)
POSTGRES_USER=pfs
PFS_DB_PASSWORD=changeme
POSTGRES_DB=personal_finance
DATABASE_URL=postgresql://pfs:changeme@127.0.0.1:5432/personal_finance
# Tailscale bind address (for remote access)
TAILSCALE_IP=100.124.x.x
# pgAdmin
PGADMIN_EMAIL=admin@local.dev
PGADMIN_PASSWORD=admin
# API keys
ALPHA_VANTAGE_API_KEY=
SEC_USER_AGENT=YourName your@email.com
ENVEOF
    echo "Created .env — EDIT IT with real values:"
    echo "  nano $PROJECT_DIR/.env"
else
    echo ".env already exists — skipping"
fi

# ── 5. Start PostgreSQL (Docker) ──
echo ""
echo "=== [5/8] Starting PostgreSQL ==="
docker compose -f deploy/docker/docker-compose.data.yml --env-file .env up -d
echo "Waiting for PostgreSQL to be ready..."
sleep 5
docker compose -f deploy/docker/docker-compose.data.yml exec postgres pg_isready -U pfs -d personal_finance || {
    echo "PostgreSQL not ready — check logs: docker compose -f deploy/docker/docker-compose.data.yml logs postgres"
    exit 1
}
echo "PostgreSQL OK"

# ── 6. Apply agent_ops schema ──
echo ""
echo "=== [6/8] Applying agent_ops schema ==="
# The schema.sql and agent_ops.sql are auto-applied via Docker init scripts
# But if DB already existed, apply manually:
if [[ -f "$PROJECT_DIR/.env" ]]; then
    source "$PROJECT_DIR/.env"
fi
PGPASSWORD="${PFS_DB_PASSWORD:-changeme}" psql -h 127.0.0.1 -U "${POSTGRES_USER:-pfs}" -d "${POSTGRES_DB:-personal_finance}" \
    -f "$PROJECT_DIR/pfs/db/agent_ops.sql" 2>/dev/null || true
echo "agent_ops schema applied"

# ── 7. Seed recurring tasks ──
echo ""
echo "=== [7/8] Seeding task registry ==="
uv run python scripts/seed_tasks.py || echo "Seed script failed (may need DB connection)"

# ── 8. Install systemd services (if Linux) / launchd (if macOS) ──
echo ""
echo "=== [8/8] Service configuration ==="
if [[ "$(uname)" == "Darwin" ]]; then
    echo "macOS detected — use launchd or run manually:"
    echo "  # FastAPI"
    echo "  uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000"
    echo ""
    echo "  # MCP HTTP server"
    echo "  uv run python -m pfs.mcp.server  # (configure HTTP transport on :8001)"
    echo ""
    echo "  # Streamlit"
    echo "  uv run streamlit run dashboard/app.py --server.address 0.0.0.0"
else
    # Linux (systemd)
    cp deploy/systemd/pfs-api.service /etc/systemd/system/
    cp deploy/systemd/pfs-streamlit.service /etc/systemd/system/
    cp deploy/systemd/pfs-price-sync.service /etc/systemd/system/
    cp deploy/systemd/pfs-price-sync.timer /etc/systemd/system/
    cp deploy/systemd/pfs-filing-check.service /etc/systemd/system/
    cp deploy/systemd/pfs-filing-check.timer /etc/systemd/system/

    systemctl daemon-reload
    systemctl enable pfs-price-sync.timer
    systemctl enable pfs-filing-check.timer

    echo "Services installed. Start them:"
    echo "  systemctl enable --now pfs-api pfs-streamlit"
    echo "  systemctl start pfs-price-sync.timer pfs-filing-check.timer"
fi

echo ""
echo "=========================================="
echo "  Data Server Setup Complete!"
echo "=========================================="
echo ""
echo "Remaining manual steps:"
echo "  1. Edit /opt/pfs/.env with real credentials"
echo "  2. Start FastAPI: uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000"
echo "  3. Start MCP HTTP: uv run python -m pfs.mcp.server (bind :8001)"
echo "  4. Start Streamlit: uv run streamlit run dashboard/app.py"
echo "  5. Run initial ETL: uv run python -m pfs.etl.pipeline ingest NVDA --years 5"
echo "  6. Seed tasks: uv run python scripts/seed_tasks.py"
echo "  7. Test API: curl http://localhost:8000/health"
echo "  8. Test task schedule: curl http://localhost:8000/api/tasks/schedule"
echo ""
