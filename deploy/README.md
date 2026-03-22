# Deployment Guide — Two-Server Architecture

## Overview

The system runs across two servers connected via Tailscale:

| Server | Role | Key Services |
|--------|------|-------------|
| **Data Server** (Mac local) | Database, API, MCP, ETL, Prefect | PostgreSQL, FastAPI :8000, MCP :8001, Prefect :4200 |
| **Agent Server** (DMIT) | Agent, Dashboard, Task Dispatcher | Streamlit :8501, OpenClaw, Task Dispatcher |

**Hard rule**: The Agent Server has zero database dependencies. All data access goes through REST API or MCP HTTP hosted on the Data Server.

---

## Network Topology

```
┌─────────────────────────────────────────────────┐
│  DATA SERVER (Mac / Tailscale: 100.124.x)       │
│                                                  │
│  localhost:5432   ← PostgreSQL (internal only)   │
│  :8000            ← FastAPI  (Tailscale LAN)     │
│  :8001            ← MCP HTTP (Agent Server only) │
│  :4200            ← Prefect UI (LAN only)        │
│  :5050            ← pgAdmin (LAN only)           │
└──────────────────────────────────────────────────┘
       ↕ Tailscale WireGuard tunnel
┌─────────────────────────────────────────────────┐
│  AGENT SERVER (DMIT / Tailscale: 100.106.x)     │
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

```bash
# 1. Start PostgreSQL + pgAdmin
docker compose -f deploy/docker/docker-compose.data.yml up -d

# 2. Install Python dependencies
uv sync

# 3. Start FastAPI
uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000

# 4. Start MCP Server
uv run python -m pfs.mcp.server  # HTTP transport on :8001

# 5. Start Prefect
prefect server start  # UI on :4200
cd prefect/flows && prefect deploy --all
```

Or use the setup script: `bash deploy/scripts/setup-data-server.sh`

---

## Agent Server Setup

```bash
# 1. Install services
bash deploy/scripts/setup-agent-server.sh

# 2. Set up OpenClaw
bash deploy/scripts/setup-openclaw.sh

# 3. Enable systemd services
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pfs-streamlit pfs-task-dispatcher
```

### Remaining systemd services (Agent Server only)

| Service | Purpose |
|---------|---------|
| `pfs-streamlit.service` | Streamlit dashboard on :8501 |
| `pfs-task-dispatcher.service` | Polls `/api/tasks/next`, dispatches to OpenClaw |

---

## Artifact Git Repo

Artifacts in `data/artifacts/` are maintained as a separate git repo. The agent uses commit-on-write (defined in `agents/openclaw/CLAUDE.md`):

```bash
cd data/artifacts
git init && git add -A && git commit -m "Initial snapshot"
# Optionally add remote for backup
```

---

## Updating

```bash
bash deploy/scripts/deploy.sh
```
