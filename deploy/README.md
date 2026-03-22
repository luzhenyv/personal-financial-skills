# Deployment Guide — Mini Bloomberg on DMIT Server

## Architecture Critique & Design Decisions

### What the plan gets right

1. **Git-versioned artifacts** — Correct call. Investment theses, financial snapshots, and company profiles are time-series data. Git diff shows exactly what changed between earnings season updates. This is superior to DB storage for this use case (human-readable diffs, blame for when an assumption changed, cheap branching for "what-if" scenario theses).

2. **OpenClaw as intelligence plane** — Perfect fit. OpenClaw's skill system (SKILL.md + scripts/) is architecturally identical to our project's skills. Its cron system replaces Airflow (which would eat your entire 2GB RAM alone). The `exec` tool lets the agent run project scripts directly.

3. **Tailscale-only access** — Zero-trust network. No firewall rules to maintain, no SSL certs to manage, no port exposure.

### What I pushed back on / refined

1. **FastAPI is borderline unnecessary for the server**. Currently Streamlit calls FastAPI via HTTP for DB data (incomes, balances, cash_flows), but loads thesis data and artifact JSON directly from disk/imports. On a 2GB server, the extra ~100MB for a uvicorn process is significant. I'm keeping it for now because it also serves CLI and future integrations, but the cleaner long-term move is to have Streamlit query Postgres directly (like the thesis loader already does). Flag this for a future refactor.

2. **Don't use OpenClaw cron for mechanical ETL**. The daily price sync (`sync-prices`) is a deterministic script — running it through an LLM wastes model tokens and adds a failure mode (model hallucinating extra steps). Use systemd timers for mechanical jobs. Reserve OpenClaw cron for jobs that need reasoning (thesis health checks, earnings analysis, morning briefs).

3. **MiniMax M2.5 quality concern**. Your existing OpenClaw investment-assistant cron job has `consecutiveErrors: 12` and was timing out. For complex multi-step financial analysis (thesis scoring, multi-KPI evaluation), model quality matters. The free MiniMax tier may not have the reasoning depth needed for your skill workflows. Monitor this — if health checks produce garbage, consider adding an Anthropic or OpenAI key as fallback, at least for the financial analysis agent.

4. **RAM budget is tight**. Breakdown with everything running:
   ```
   PostgreSQL 16 (tuned):  ~150MB
   OpenClaw gateway:       ~150MB
   FastAPI (uvicorn):      ~80MB
   Streamlit:              ~200MB
   OS + Tailscale:         ~200MB
   ─────────────────────── ~780MB / 2GB
   ```
   This leaves ~1.2GB for burst (ETL runs, pandas operations). Workable but no room for Docker or Airflow.

5. **Single repo with artifact subdir as separate git** — don't use git submodules (they cause more problems than they solve for a solo project). Instead: the project repo has `data/artifacts/` in `.gitignore`, and on the server `data/artifacts/` is initialized as its own git repository. A systemd timer auto-commits daily.

---

## Server Layout

```
/opt/pfs/                              ← project root (git clone)
├── .env                               ← secrets (not in git)
├── .venv/                             ← uv-managed virtualenv
├── pyproject.toml
├── pfs/                               ← source code
├── dashboard/                     ← Streamlit frontend
├── skills/                            ← skill definitions (symlinked into OpenClaw)
├── scripts/
└── data/
    ├── raw/                           ← SEC filings, company_facts.json
    ├── reports/
    └── artifacts/                     ← **separate git repo**
        ├── .git/
        ├── NVDA/profile/, thesis/
        ├── AMD/profile/
        └── ...

/root/.openclaw/workspace/
├── CLAUDE.md                          ← agent persona (our custom)
├── skills/
│   ├── company-profile -> /opt/pfs/skills/company-profile
│   ├── thesis-tracker  -> /opt/pfs/skills/thesis-tracker
│   └── etl-coverage    -> /opt/pfs/skills/etl-coverage
└── memory/                            ← OpenClaw's own memory
```

## Network Topology

```
┌──────────────────────────────────────────────────────┐
│  DMIT Server (Tailscale: 100.106.13.112)             │
│                                                       │
│  localhost:5432   ← PostgreSQL (no external access)   │
│  localhost:8000   ← FastAPI    (no external access)   │
│  100.x:8501       ← Streamlit  (Tailscale LAN only)  │
│  localhost:18789  ← OpenClaw   (loopback only)        │
│                                                       │
│  Outbound only:                                       │
│    → Discord API  (cron delivery)                     │
│    → Telegram API (chat channel)                      │
│    → SEC EDGAR    (ETL data fetch)                    │
│    → Alpha Vantage / yfinance (price data)            │
└──────────────────────────────────────────────────────┘
       ↕ Tailscale WireGuard tunnel
┌──────────────────────┐  ┌─────────────────┐
│  MacBook (100.124.x) │  │  iPhone (100.x) │
│  → Streamlit UI      │  │  → Telegram bot  │
└──────────────────────┘  └─────────────────┘
```

## Scheduling Design: Mechanical vs Intelligent

```
MECHANICAL (systemd timers — no LLM, deterministic)
├── pfs-price-sync.timer      M-F 17:30 ET   uv run python -m pfs.etl.pipeline sync-prices
├── pfs-artifact-commit.timer  Daily 23:55    git -C data/artifacts add -A && commit
└── pfs-etl-filing-check.timer Daily 06:00 ET check for new SEC filings (script only)

INTELLIGENT (OpenClaw cron — needs AI reasoning, delivers to channels)
├── morning-brief             M-F 07:30 ET   Summarize overnight moves, thesis scores, catalysts
├── weekly-health-check       Sat 10:00 ET   Run thesis check --all, diff against last week
├── earnings-analysis         Event-driven   Triggered when new 10-Q detected (by mechanical timer)
└── weekly-portfolio-summary  Fri 18:00 ET   Full portfolio review with score trends
```

The mechanical filing-check timer writes a flag file when new filings are found. The next OpenClaw morning-brief detects the flag and triggers the earnings-analysis flow. This is the event-driven pattern — no polling by the LLM.

---

## Deployment Steps

### 1. Install prerequisites on server

```bash
ssh dmitserver
# PostgreSQL 16
sudo apt update && sudo apt install -y postgresql-16 postgresql-client-16

# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or re-login

# Git (already installed)
```

### 2. Clone project

```bash
sudo mkdir -p /opt/pfs
sudo git clone <YOUR_REPO_URL> /opt/pfs
cd /opt/pfs
```

### 3. Set up Python environment

```bash
cd /opt/pfs
uv sync
```

### 4. Configure PostgreSQL

```bash
# Create database and user
sudo -u postgres createuser pfs
sudo -u postgres createdb -O pfs personal_finance
sudo -u postgres psql -c "ALTER USER pfs WITH PASSWORD '<your-password>';"

# Apply schema
sudo -u postgres psql -d personal_finance -f /opt/pfs/pfs/db/schema.sql

# Apply low-memory tuning
sudo cp /opt/pfs/deploy/postgres/pfs-tuning.conf /etc/postgresql/16/main/conf.d/
sudo systemctl restart postgresql
```

### 5. Configure environment

```bash
cp /opt/pfs/deploy/.env.example /opt/pfs/.env
# Edit .env with real credentials
```

### 6. Initialize artifact git repo

```bash
cd /opt/pfs/data/artifacts
git init
git add -A
git commit -m "Initial artifact snapshot"
# Optionally add a remote for backup:
# git remote add origin git@github.com:<user>/pfs-artifacts.git
```

### 7. Install systemd services

```bash
sudo cp /opt/pfs/deploy/systemd/*.service /etc/systemd/system/
sudo cp /opt/pfs/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

sudo systemctl enable --now pfs-api
sudo systemctl enable --now pfs-streamlit
sudo systemctl enable --now pfs-price-sync.timer
sudo systemctl enable --now pfs-artifact-commit.timer
sudo systemctl enable --now pfs-filing-check.timer
```

### 8. Configure OpenClaw workspace

```bash
# Run the setup script
bash /opt/pfs/deploy/scripts/setup-openclaw.sh
```

### 9. Set up OpenClaw cron jobs

```bash
# Add cron jobs via OpenClaw CLI
bash /opt/pfs/deploy/scripts/setup-cron.sh
```

### 10. Verify

```bash
# Check services
systemctl status pfs-api pfs-streamlit postgresql

# Check Streamlit accessible via Tailscale
curl http://100.106.13.112:8501

# Check API
curl http://localhost:8000/health

# Check cron jobs
openclaw cron list
```

---

## Updating

```bash
cd /opt/pfs
git pull
uv sync
sudo systemctl restart pfs-api pfs-streamlit
```

Or use the deploy script:
```bash
bash /opt/pfs/deploy/scripts/deploy.sh
```
