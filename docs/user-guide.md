# User Guide — Mini Bloomberg

> How to use the deployed system for equity analysis.

## System at a Glance

Two servers, one workflow:

| What you do | Where it runs |
|-------------|---------------|
| Open the dashboard, chat with the agent | **Agent Server** — http://100.106.13.112:8501 |
| Data is fetched, stored, and served | **Data Server** (Mac, always on) |

You only ever interact with the **Streamlit dashboard** at `http://100.106.13.112:8501`. Everything else is automatic.

---

## Before You Analyse a Company

The system only knows about companies that have been ingested via ETL. Run this **once per company** on the Mac (Data Server):

```bash
uv run python -m pfs.etl.pipeline ingest NVDA --years 5
```

Check which companies are already ingested:

```bash
curl -s http://localhost:8000/api/companies/ | python3 -m json.tool
```

Or via the dashboard — the company dropdown on the **Company Profile** page lists every ingested ticker.

---

## The Dashboard — Three Pages

### 🏢 Company Profile (`/1_company_profile`)

A full interactive tearsheet. Select a ticker from the sidebar.

| Tab | Contents |
|-----|----------|
| **Overview** | Business summary, revenue segments, geography, management team |
| **Financials** | Revenue/profit trends, margins, balance sheet, cash flow |
| **Valuation** | DCF model with sensitivity table, peer comps |
| **Research** | Competitive landscape, risks, opportunities, investment thesis |
| **Report** | Full markdown report — download as `.md` |

To **generate or re-generate** the profile report for a company, use Agent Chat (see below) or run:

```bash
# On Mac (Data Server)
uv run python skills/company-profile/scripts/generate_report.py NVDA
```

---

### 🎯 Thesis Tracker (`/2_thesis_tracker`)

Manage long-form investment theses with health scoring over time.

| Tab | Contents |
|-----|----------|
| **Thesis Summary** | Core thesis, key assumptions, valuation target, sell conditions |
| **Update Log** | Chronological event log — each update scored +/– for thesis strength |
| **Health Dashboard** | Score timeline chart, assumption heatmap |
| **Edit** | Edit the thesis inline |

**Common workflows:**

```
# In Agent Chat:
generate profile for NVDA
create thesis for AAPL
update TSLA thesis — beat Q4 earnings, raised guidance
thesis health check TSLA
```

Or via CLI on the Data Server:

```bash
uv run python skills/thesis-tracker/scripts/thesis_cli.py create  AAPL --interactive
uv run python skills/thesis-tracker/scripts/thesis_cli.py update  AAPL --interactive
uv run python skills/thesis-tracker/scripts/thesis_cli.py check   AAPL
uv run python skills/thesis-tracker/scripts/thesis_cli.py catalyst AAPL --add
uv run python skills/thesis-tracker/scripts/thesis_cli.py report  AAPL
```

---

### 💬 Agent Chat (`/3_agent_chat`)

A chat interface that queues tasks to the AI agent (OpenClaw) running on the Agent Server. The task dispatcher picks up requests roughly every 60 seconds.

**Example commands:**

```
generate profile for NVDA
create thesis for AAPL
update MSFT thesis — cloud segment beat, Azure +31% YoY
thesis health check TSLA
```

How it works:
1. You type a command → dashboard sends it to `POST /api/tasks/`
2. Task Dispatcher polls `/api/tasks/next` every 60 s
3. OpenClaw runs the appropriate skill
4. Artifacts are written to `data/artifacts/{TICKER}/`
5. Dashboard auto-refreshes from the artifact files

---

## Routine Maintenance

### Sync Prices

Prices are synced automatically by Prefect. To trigger manually:

```bash
uv run python -m pfs.etl.pipeline sync-prices
```

### Add a New Company

```bash
uv run python -m pfs.etl.pipeline ingest MSFT --years 5
```

### Re-ingest / Refresh Data

```bash
uv run python -m pfs.etl.pipeline ingest NVDA --years 5 --force
```

### Extract 10-K Text Sections

Run after ETL to make 10-K narrative sections (Management Discussion, Risk Factors, etc.) available to the agent:

```bash
uv run python -m pfs.etl.section_extractor NVDA
```

---

## Keeping the System Up

### Data Server (Mac) — check services

```bash
# Docker (PostgreSQL + pgAdmin)
docker ps

# FastAPI and MCP — check if running
lsof -iTCP:8000 -sTCP:LISTEN
lsof -iTCP:8001 -sTCP:LISTEN

# Restart if needed
pkill -f 'uvicorn pfs.api' ; pkill -f 'pfs.mcp.server'
cd /path/to/personal-financial-skills
nohup uv run uvicorn pfs.api.app:app --host 0.0.0.0 --port 8000 > /tmp/pfs-api.log 2>&1 &
nohup uv run python -m pfs.mcp.server --http --port 8001 --host 0.0.0.0 > /tmp/pfs-mcp.log 2>&1 &
```

### Agent Server (DMIT) — check services

```bash
ssh dmitserver 'systemctl status pfs-streamlit pfs-task-dispatcher --no-pager -l'
```

Restart:

```bash
ssh dmitserver 'systemctl restart pfs-streamlit pfs-task-dispatcher'
```

### Deploy Latest Code

```bash
# Push changes from Mac
git push origin main

# Pull and restart on Agent Server
ssh dmitserver 'bash /opt/pfs/deploy/scripts/deploy.sh'
```

---

## API Reference

The FastAPI server at `http://100.124.144.100:8000` (Tailscale) exposes the full API.

Interactive docs: **http://100.124.144.100:8000/docs**

Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/api/companies/` | List all ingested companies |
| `GET` | `/api/companies/{ticker}` | Company details + financials |
| `GET` | `/api/tasks/schedule` | View all registered scheduled tasks |
| `POST` | `/api/tasks/` | Queue a new agent task |
| `GET` | `/api/tasks/next` | (Dispatcher use) Claim next pending task |

---

## Data Locations

| What | Where |
|------|-------|
| Raw SEC filings | `data/raw/{TICKER}/` |
| Analysis artifacts | `data/artifacts/{TICKER}/` |
| Company profiles | `data/artifacts/{TICKER}/profile/` |
| Investment theses | `data/artifacts/{TICKER}/thesis/` |
| Event flags (cron triggers) | `data/artifacts/_flags/` |
| ETL coverage report | `data/artifacts/_etl/coverage_report.json` |
| FastAPI logs | `/tmp/pfs-api.log` (Mac) |
| MCP logs | `/tmp/pfs-mcp.log` (Mac) |
| Agent service logs | `journalctl -u pfs-streamlit -f` (DMIT) |
