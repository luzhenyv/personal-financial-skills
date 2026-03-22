#!/usr/bin/env bash
# setup.sh — One-shot server setup for Mini Bloomberg
# Run on a fresh Ubuntu 24.04 server with Tailscale already configured
# Usage: ssh dmitserver "bash /opt/pfs/deploy/setup.sh"
set -euo pipefail

echo "=========================================="
echo "  Mini Bloomberg — Server Setup"
echo "=========================================="

PROJECT_DIR="/opt/pfs"

# ── 1. System packages ──
echo ""
echo "=== [1/8] Installing system packages ==="
apt update -qq
apt install -y -qq postgresql-16 postgresql-client-16 git curl

# ── 2. uv (Python package manager) ──
echo ""
echo "=== [2/8] Installing uv ==="
if ! command -v /root/.local/bin/uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
else
    echo "uv already installed"
fi

# ── 3. PostgreSQL config ──
echo ""
echo "=== [3/8] Configuring PostgreSQL ==="
# Ensure conf.d directory exists and is included
PG_CONF_DIR="/etc/postgresql/16/main/conf.d"
mkdir -p "$PG_CONF_DIR"
cp "$PROJECT_DIR/deploy/postgres/pfs-tuning.conf" "$PG_CONF_DIR/"

# Ensure conf.d is included (usually is by default in Ubuntu)
if ! grep -q "include_dir = 'conf.d'" /etc/postgresql/16/main/postgresql.conf 2>/dev/null; then
    echo "include_dir = 'conf.d'" >> /etc/postgresql/16/main/postgresql.conf
fi

# Create database and user
systemctl enable --now postgresql
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='pfs'" | grep -q 1 || \
    sudo -u postgres createuser pfs
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='personal_finance'" | grep -q 1 || \
    sudo -u postgres createdb -O pfs personal_finance

echo "Set the pfs password (you'll need this for .env):"
echo "  sudo -u postgres psql -c \"ALTER USER pfs WITH PASSWORD 'your-password';\""
echo ""

# Apply schema
sudo -u postgres psql -d personal_finance -f "$PROJECT_DIR/src/db/schema.sql" 2>/dev/null || true
systemctl restart postgresql

# ── 4. Python environment ──
echo ""
echo "=== [4/8] Setting up Python environment ==="
cd "$PROJECT_DIR"
/root/.local/bin/uv sync

# ── 5. Environment file ──
echo ""
echo "=== [5/8] Environment configuration ==="
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cp "$PROJECT_DIR/deploy/.env.example" "$PROJECT_DIR/.env"
    echo "Created .env from template — EDIT IT with real credentials:"
    echo "  nano $PROJECT_DIR/.env"
else
    echo ".env already exists — skipping"
fi

# ── 6. Initialize artifact git repo ──
echo ""
echo "=== [6/8] Initializing artifact git repo ==="
ARTIFACTS_DIR="$PROJECT_DIR/data/artifacts"
mkdir -p "$ARTIFACTS_DIR"
if [[ ! -d "$ARTIFACTS_DIR/.git" ]]; then
    cd "$ARTIFACTS_DIR"
    cp "$PROJECT_DIR/deploy/openclaw/artifact-gitignore" .gitignore
    git init
    git add -A
    git commit -m "Initial artifact snapshot" --allow-empty
    echo "Artifact repo initialized at $ARTIFACTS_DIR"
    echo "Optionally add a remote: git -C $ARTIFACTS_DIR remote add origin <url>"
else
    echo "Artifact repo already exists"
fi

# ── 7. Install systemd services ──
echo ""
echo "=== [7/8] Installing systemd services ==="
cd "$PROJECT_DIR"
chmod +x deploy/scripts/*.sh

cp deploy/systemd/pfs-api.service /etc/systemd/system/
cp deploy/systemd/pfs-streamlit.service /etc/systemd/system/
cp deploy/systemd/pfs-price-sync.service /etc/systemd/system/
cp deploy/systemd/pfs-price-sync.timer /etc/systemd/system/
cp deploy/systemd/pfs-artifact-commit.service /etc/systemd/system/
cp deploy/systemd/pfs-artifact-commit.timer /etc/systemd/system/
cp deploy/systemd/pfs-filing-check.service /etc/systemd/system/
cp deploy/systemd/pfs-filing-check.timer /etc/systemd/system/

systemctl daemon-reload

# Enable timers (they'll survive reboots)
systemctl enable pfs-price-sync.timer
systemctl enable pfs-artifact-commit.timer
systemctl enable pfs-filing-check.timer

echo "Services installed. Start them after editing .env:"
echo "  systemctl enable --now pfs-api pfs-streamlit"
echo "  systemctl start pfs-price-sync.timer pfs-artifact-commit.timer pfs-filing-check.timer"

# ── 8. OpenClaw workspace ──
echo ""
echo "=== [8/8] Setting up OpenClaw workspace ==="
bash "$PROJECT_DIR/deploy/scripts/setup-openclaw.sh"

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "Remaining manual steps:"
echo "  1. Edit /opt/pfs/.env with real credentials"
echo "  2. Set Postgres password: sudo -u postgres psql -c \"ALTER USER pfs WITH PASSWORD 'xxx';\""
echo "  3. Start services: systemctl enable --now pfs-api pfs-streamlit"
echo "  4. Start timers: systemctl start pfs-price-sync.timer pfs-artifact-commit.timer pfs-filing-check.timer"
echo "  5. Run initial ETL: cd /opt/pfs && uv run python -m src.etl.pipeline ingest NVDA --years 5"
echo "  6. Set up OpenClaw cron: bash /opt/pfs/deploy/scripts/setup-cron.sh"
echo "  7. Verify Streamlit: curl http://100.106.13.112:8501"
echo ""
