# Personal Financial Skills — Mini Bloomberg

A personal investor toolkit that extracts financial data from SEC EDGAR filings,
stores it in PostgreSQL, and provides interactive analysis through Streamlit.

> Adapted from [financial-services-plugins](https://github.com/anthropics/financial-services-plugins) —
> institutional-grade skills refactored for personal use.

## Architecture

```
SEC EDGAR API → XBRL Parser → PostgreSQL
                                    ↓
Alpha Vantage → Price Data ──→ PostgreSQL
                                    ↓
                          FastAPI (REST + MCP)
                                    ↓
                          Streamlit Dashboard
```

## Quick Start

### 1. Start PostgreSQL

```bash
cp .env.example .env
# Edit .env — set SEC_USER_AGENT to your email

docker compose up -d postgres
```

### 2. Install Python Dependencies

```bash
uv sync
```

### 3. Ingest a Company

```python
from src.etl.pipeline import ingest_company

result = ingest_company("NVDA", years=5)
print(result)
```

### 4. Generate a Tearsheet

```python
from src.analysis.company_profile import generate_tearsheet

md = generate_tearsheet("NVDA")
print(md)
```

### 5. Start the API

```bash
uv run uvicorn src.api.app:app --reload
# → http://localhost:8000/docs
```

### 6. Start Streamlit

```bash
uv run streamlit run streamlit_app/app.py
# → http://localhost:8501
```

### Or launch everything with Docker Compose

```bash
docker compose up -d
```

## Skills

Agent-readable skill definitions in `skills/`:

| Skill | Purpose | Status |
|-------|---------|--------|
| `company-profile` | 1-page markdown tearsheet | ✅ Ready |
| `financial-etl` | SEC XBRL → PostgreSQL pipeline | ✅ Ready |
| `three-statements` | 3-statement financial model | 🔜 Planned |
| `dcf-valuation` | DCF model with scenarios | 🔜 Planned |
| `comps-analysis` | Peer comparison | 🔜 Planned |
| `earnings-analysis` | Post-earnings quick take | 🔜 Planned |
| `stock-screening` | Filter by financial criteria | 🔜 Planned |
| `portfolio-monitoring` | Track holdings & P&L | 🔜 Planned |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/companies/` | List all companies |
| POST | `/api/companies/ingest` | Trigger ETL for a ticker |
| GET | `/api/financials/{ticker}/income-statements` | Income statements |
| GET | `/api/financials/{ticker}/balance-sheets` | Balance sheets |
| GET | `/api/financials/{ticker}/cash-flows` | Cash flow statements |
| GET | `/api/financials/{ticker}/metrics` | Computed metrics |
| GET | `/api/financials/{ticker}/prices` | Price data |
| GET | `/api/analysis/{ticker}/profile` | Structured profile (JSON) |
| POST | `/api/analysis/{ticker}/tearsheet` | Generate tearsheet |
| GET | `/api/analysis/{ticker}/tearsheet` | Get saved tearsheet |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Database | PostgreSQL 16 (Docker) |
| ETL | Python + httpx + SEC EDGAR XBRL API |
| Backend | FastAPI |
| Dashboard | Streamlit + Plotly |
| Agent Interface | Skills (Markdown) + MCP (planned) |
| Scheduling | Airflow (planned) |

## Cost

| Item | Cost |
|------|------|
| SEC EDGAR API | Free |
| Alpha Vantage (optional) | $0–50/mo |
| PostgreSQL (Docker) | Free |
| Total | ~$0–50/mo |

## License

MIT