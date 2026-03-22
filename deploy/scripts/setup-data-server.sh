#!/usr/bin/env bash
# setup-data-server.sh — One-shot setup for Data Server (Mac local)
# Runs: PostgreSQL + pgAdmin (Docker), FastAPI :8000, MCP HTTP :8001
# NO OpenClaw, NO task dispatcher — those run on Agent Server
#
# Prerequisites:
#   - Docker Desktop installed and running
#   - Tailscale connected
#   - deploy/docker/.env.data-server filled in (copy from .env.data-server.example)
#
# Usage: bash deploy/scripts/setup-data-server.sh
set -euo pipefail

echo "=========================================="
echo "  Mini Bloomberg — Data Server Setup"
echo "=========================================="

# Resolve project root regardless of where the script is called from
PROJECT_DIR="$( cd "$(dirname "$0")/../.." && pwd )"
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
if [[ ! -f "$PROJECT_DIR/deploy/docker/.env.data-server" ]]; then
    cp "$PROJECT_DIR/deploy/docker/.env.data-server.example" \
       "$PROJECT_DIR/deploy/docker/.env.data-server"
    echo "Created deploy/docker/.env.data-server — EDIT IT with real values:"
    echo "  nano $PROJECT_DIR/deploy/docker/.env.data-server"
else
    echo "deploy/docker/.env.data-server already exists — skipping"
fi

# Also ensure root .env exists for FastAPI / MCP
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cat > "$PROJECT_DIR/.env" <<'ENVEOF'
# Data Server .env — application config
DATABASE_URL=postgresql://pfs:CHANGE_ME@127.0.0.1:5432/personal_finance
POSTGRES_DB=personal_finance
POSTGRES_USER=pfs
POSTGRES_PASSWORD=CHANGE_ME
SEC_USER_AGENT=PersonalFinanceApp your@email.com
ALPHA_VANTAGE_KEY=
ENVEOF
    echo "Created .env — EDIT IT with real credentials."
else
    echo ".env already exists — skipping"
fi

# ── 5. Start PostgreSQL + pgAdmin (Docker) ──
echo ""
echo "=== [5/8] Starting PostgreSQL + pgAdmin ==="
docker compose -f deploy/docker/docker-compose.data.yml \
    --env-file deploy/docker/.env.data-server up -d
echo "Waiting for PostgreSQL to be healthy..."
for i in $(seq 1 12); do
    docker compose -f deploy/docker/docker-compose.data.yml exec -T postgres \
        pg_isready -U pfs -d personal_finance &>/dev/null && break
    sleep 5
done
docker compose -f deploy/docker/docker-compose.data.yml exec -T postgres \
    pg_isready -U pfs -d personal_finance || {
    echo "PostgreSQL not ready — check logs:"
    echo "  docker compose -f deploy/docker/docker-compose.data.yml logs postgres"
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

# ── 8. Start services (macOS: background processes) ──
echo ""
echo "=== [8/8] Starting services ==="
if [[ "$(uname)" == "Darwin" ]]; then
    # Kill any existing instances
    pkill -f 'uvicorn pfs.api' 2>/dev/null || true
    pkill -f 'pfs.mcp.server' 2>/dev/null || true
    sleep 1

    # FastAPI
    nohup uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000 \
        --log-level info > /tmp/pfs-api.log 2>&1 &
    echo "FastAPI started (PID $!) — logs: /tmp/pfs-api.log"

    # MCP HTTP server (Tailscale-accessible, DNS-rebinding protection disabled)
    nohup uv run python -m pfs.mcp.server --http --port 8001 --host 0.0.0.0 \
        > /tmp/pfs-mcp.log 2>&1 &
    echo "MCP HTTP started (PID $!) — logs: /tmp/pfs-mcp.log"

    sleep 3
    echo "Health check:"
    curl -s http://localhost:8000/health || echo "  WARNING: FastAPI not responding yet"
else
    echo "Linux detected — no systemd services defined for Data Server."
    echo "Run manually:"
    echo "  nohup uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000 > /tmp/pfs-api.log 2>&1 &"
    echo "  nohup uv run python -m pfs.mcp.server --http --port 8001 --host 0.0.0.0 > /tmp/pfs-mcp.log 2>&1 &"
fi

echo ""
echo "=========================================="
echo "  Data Server Setup Complete!"
echo "=========================================="
echo ""
echo "Services running:"
echo "  PostgreSQL :5432  (Docker, data in named volume 'personal-financial-skills_pgdata')"
echo "  pgAdmin    :5050  (Docker)"
echo "  FastAPI    :8000  (logs: /tmp/pfs-api.log)"
echo "  MCP HTTP   :8001  (logs: /tmp/pfs-mcp.log)"
echo ""
echo "Verify:"
echo "  curl http://localhost:8000/health"
echo "  curl http://localhost:8000/api/tasks/schedule"
echo ""
echo "Next steps:"
echo "  1. Edit deploy/docker/.env.data-server and .env with real credentials"
echo "  2. Edit Tailscale IP in deploy/docker/.env.data-server (TAILSCALE_IP=...)"
echo "  3. Run initial ETL: uv run python -m pfs.etl.pipeline ingest NVDA --years 5"
echo ""
