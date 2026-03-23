# Deployment Guide — Two-Server Architecture

## Overview

The system runs across two servers connected via Tailscale:

| Server | Role | Tailscale IP | Key Services |
|--------|------|-------------|-------------|
| **Data Server** (Mac local) | Database, API, ETL, Prefect | `100.124.144.100` | PostgreSQL, FastAPI :8000, Prefect :4200 |
| **Agent Server** (DMIT) | Agent, Dashboard, Task Dispatcher | `100.106.13.112` | Streamlit :8501, OpenClaw, Task Dispatcher |

**Hard rule**: The Agent Server has zero database dependencies. All data access goes through the REST API hosted on the Data Server.

---

## Network Topology

```
┌─────────────────────────────────────────────────┐
│  DATA SERVER (Mac / Tailscale: 100.124.144.100) │
│                                                  │
│  localhost:5432   ← PostgreSQL (internal only)   │
│  :8000            ← FastAPI  (Tailscale LAN)     │
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

# 5. Start Prefect (optional)
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

## Agent Server Demo Mode (SQLite + Local Data Plane)

Use this mode on the smaller DMIT box when you want to run the full demo stack on one machine without PostgreSQL. PostgreSQL support stays in the codebase and deployment scripts, but the local demo path uses SQLite to reduce RAM and operational overhead.

### What Runs Locally

| Component | Port | Storage / Notes |
|----------|------|------------------|
| **FastAPI** | `8000` | backed by SQLite file at `/opt/pfs/data/personal_finance.db` |
| **Prefect UI** | `4200` | Prefect server metadata stays in Prefect's own local state |
| **Prefect Worker** | n/a | runs mechanical flows on the same server |
| **Streamlit** | `8501` | still served from the agent server |

### Access Model

- Bind UI/API services to the server's **Tailscale IP**, not `0.0.0.0`
- Keep OpenClaw loopback-only
- Point Streamlit and the dispatcher at the same-server FastAPI endpoints over the Tailscale address
- If you want stricter enforcement than bind-address isolation, add host firewall rules that only allow inbound `4200`, `8000`, `8001`, and `8501` from `100.64.0.0/10`

### Setup

```bash
ssh dmitserver
cd /opt/pfs
bash deploy/scripts/setup-agent-server.sh --with-local-data-plane
```

The setup script will:

- write local SQLite-oriented values into `/opt/pfs/.env`
- initialize `/opt/pfs/data/personal_finance.db`
- seed the unified task registry
- install and enable `pfs-api`, `pfs-prefect`, `pfs-prefect-worker`, `pfs-streamlit`, and `pfs-task-dispatcher`
- register Prefect deployments and start a process worker pool

### Optional: Migrate Existing PostgreSQL Data

If you want the DMIT demo to keep the current database contents instead of starting from an empty SQLite file, run:

```bash
cd /opt/pfs
uv run python scripts/migrate_postgres_to_sqlite.py \
  --source-url 'postgresql://pfs:<password>@100.124.144.100:5432/personal_finance' \
  --target-url 'sqlite:////opt/pfs/data/personal_finance.db' \
  --init-target
```

### Verify

```bash
systemctl status pfs-api pfs-prefect pfs-prefect-worker pfs-streamlit pfs-task-dispatcher
curl http://100.106.13.112:8000/health
curl http://100.106.13.112:8000/api/tasks/schedule
```

### Future Upgrade Path

When you move to the larger 4-6 GB server, switch `DATABASE_URL` back to PostgreSQL, keep the same FastAPI/Prefect topology, and treat SQLite demo mode as a lightweight deployment profile rather than a permanent architecture fork.

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

---

## Troubleshooting

### Chrome returns 502 but `curl` works (Clash / ClashX proxy)

If you're running **Clash**, **ClashX**, or a similar proxy on your Mac, Chrome routes traffic through the local proxy (typically `127.0.0.1:7897`). The proxy cannot resolve Tailscale CGNAT addresses (`100.64.0.0/10`), so it returns **HTTP 502 Bad Gateway** — even though `curl` (which bypasses system proxy) works fine.

**Fix — add a DIRECT rule in your Clash config:**

```yaml
rules:
  - IP-CIDR,100.64.0.0/10,DIRECT
```

This tells Clash to bypass the proxy for all Tailscale IPs. After saving the config and reloading Clash, hard-refresh Chrome (`Cmd + Shift + R`) — the dashboard should load.
