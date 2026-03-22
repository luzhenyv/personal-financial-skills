# Deployment Guide — Two-Server Architecture

## Overview

The system runs across two servers connected via Tailscale:

| Server | Role | Tailscale IP | Key Services |
|--------|------|-------------|-------------|
| **Data Server** (Mac local) | Database, API, MCP, ETL, Prefect | `100.124.144.100` | PostgreSQL, FastAPI :8000, MCP :8001, Prefect :4200 |
| **Agent Server** (DMIT) | Agent, Dashboard, Task Dispatcher | `100.106.13.112` | Streamlit :8501, OpenClaw, Task Dispatcher |

**Hard rule**: The Agent Server has zero database dependencies. All data access goes through REST API or MCP HTTP hosted on the Data Server.

---

## Network Topology

```
┌─────────────────────────────────────────────────┐
│  DATA SERVER (Mac / Tailscale: 100.124.144.100) │
│                                                  │
│  localhost:5432   ← PostgreSQL (internal only)   │
│  :8000            ← FastAPI  (Tailscale LAN)     │
│  :8001            ← MCP HTTP (Agent Server only) │
│  :4200            ← Prefect UI (LAN only)        │
│  :5050            ← pgAdmin (LAN only)           │
└──────────────────────────────────────────────────┘
       ↕ Tailscale WireGuard tunnel
┌─────────────────────────────────────────────────┐
│  AGENT SERVER (DMIT / Tailscale: 100.106.13.112)│
│                                                  │
│  :8501            ← Streamlit (LAN only)         │
│  localhost:18789  ← OpenClaw (loopback only)     │
│  Task Dispatcher  ← polls /api/tasks/next        │
└──────────────────────────────────────────────────┘
```

---

## Scheduling: Mechanical vs Intelligent

| Type | Engine | Server | Examples |
|------|--------|--------|----------|
| **Mechanical** | Prefect | Data Server | price_sync, filing_check, data_validation |
| **Intelligent** | OpenClaw (via Task Dispatcher) | Agent Server | morning-brief, thesis health checks, earnings analysis |

All tasks are registered in the unified task registry (`agent_ops.tasks` table) for centralized visibility via `GET /api/tasks/schedule`.

---

## Data Server Setup

### Prerequisites
- Docker Desktop installed and running
- Tailscale connected
- Copy `deploy/docker/.env.data-server.example` → `deploy/docker/.env.data-server` and fill values

### Steps

```bash
# 1. Start PostgreSQL + pgAdmin (must pass explicit env file)
docker compose -f deploy/docker/docker-compose.data.yml \
  --env-file deploy/docker/.env.data-server up -d

# 2. Install Python dependencies
# NOTE: uv.lock is gitignored — always use plain `uv sync` (not --frozen)
uv sync

# 3. Seed task registry (once, or after schema reset)
uv run python scripts/seed_tasks.py

# 4. Start FastAPI (background)
nohup uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000 \
  > /tmp/pfs-api.log 2>&1 &

# 5. Start MCP HTTP server (background)
nohup uv run python -m pfs.mcp.server --http --port 8001 --host 0.0.0.0 \
  > /tmp/pfs-mcp.log 2>&1 &

# 6. Start Prefect (optional)
prefect server start  # UI on :4200
cd prefect/flows && prefect deploy --all
```

### Verify
```bash
curl http://localhost:8000/health          # {"status":"ok"}
curl http://localhost:8000/api/tasks/schedule  # list of seeded tasks
```

Or use the full setup script: `bash deploy/scripts/setup-data-server.sh`

### Important Notes — Data Server

- **Docker env file**: `docker-compose.data.yml` requires `--env-file deploy/docker/.env.data-server`. Running without it will fail due to missing `PFS_DB_PASSWORD`.
- **Postgres data**: stored in Docker named volume `personal-financial-skills_pgdata` — survives `docker compose down`, but not `docker compose down -v`.
- **Stale container warning**: If postgres was ever started with a different compose file (e.g., before the `src/` → `pfs/` rename), the container will have incorrect volume mounts and fail to start. Fix: `docker rm pfs-postgres` then re-run compose (data volume is safe).
- **MCP host headers**: The MCP HTTP server disables FastMCP's DNS-rebinding protection (`enable_dns_rebinding_protection=False` in `pfs/mcp/server.py`). This is intentional — the server is only reachable over the Tailscale WireGuard tunnel, not the public internet.
- **uv.lock is gitignored**: On fresh clones, run `uv sync` (not `uv sync --frozen`).

---

## Agent Server Setup

### Prerequisites
- Tailscale connected (must reach Data Server at `100.124.144.100`)
- OpenClaw already installed (pre-installed on DMIT server)
- Code cloned at `/opt/pfs`

### Steps

```bash
# 1. Clone project (first time only)
git clone https://github.com/luzhenyv/personal-financial-skills.git /opt/pfs
cd /opt/pfs

# 2. Install Python dependencies
export PATH="$HOME/.local/bin:$PATH"  # ensure uv is in PATH
uv sync  # NOT --frozen (uv.lock is gitignored)

# 3. Write .env (Data Server Tailscale IP — not localhost)
cat > /opt/pfs/.env << 'EOF'
PFS_API_URL=http://100.124.144.100:8000
PFS_MCP_URL=http://100.124.144.100:8001/mcp
PFS_POLL_INTERVAL=60
PFS_TASK_TIMEOUT=600
PFS_PROJECT_DIR=/opt/pfs
EOF

# 4. Install and start systemd services
cp deploy/systemd/pfs-streamlit.service /etc/systemd/system/
cp deploy/systemd/pfs-task-dispatcher.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pfs-streamlit pfs-task-dispatcher
```

### Verify
```bash
systemctl status pfs-streamlit pfs-task-dispatcher
# Streamlit accessible at http://100.106.13.112:8501
```

### Updating Agent Server
```bash
ssh dmitserver 'cd /opt/pfs && git pull origin main && systemctl restart pfs-streamlit pfs-task-dispatcher'
```

### Remaining systemd services (Agent Server only)

| Service | Purpose |
|---------|---------|
| `pfs-streamlit.service` | Streamlit dashboard on :8501 |
| `pfs-task-dispatcher.service` | Polls `/api/tasks/next` every 60 s, dispatches to OpenClaw |

### Important Notes — Agent Server

- **`API_BASE_URL` in streamlit service**: must be `http://100.124.144.100:8000` (Data Server Tailscale IP), **not** `http://127.0.0.1:8000`.
- **Task dispatcher 500 errors on startup**: if postgres is not yet ready on the Data Server when the dispatcher first polls, it logs a 500. This is harmless — it retries every `PFS_POLL_INTERVAL` seconds. 204 No Content = no tasks queued (normal).
- **OpenClaw is pre-installed**: do not re-run `setup-openclaw.sh` unless reinstalling from scratch.

---

## Artifact Git Repo

Artifacts in `data/artifacts/` are maintained as a separate git repo. The agent uses commit-on-write (defined in `agents/openclaw/CLAUDE.md`):

```bash
cd /opt/pfs/data/artifacts
git init && git checkout -b main
git -c user.email="pfs@local" -c user.name="PFS Agent" commit --allow-empty -m "Initial snapshot"
# Optionally add remote for backup
git remote add origin https://github.com/<user>/pfs-artifacts.git
```

---

## Updating Both Servers

```bash
# On Mac (Data Server) — push changes
git push origin main

# On DMIT (Agent Server) — pull and restart
ssh dmitserver 'cd /opt/pfs && git pull origin main && systemctl restart pfs-streamlit pfs-task-dispatcher'
```

Or use the full update script: `bash deploy/scripts/deploy.sh`
