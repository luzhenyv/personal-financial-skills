# Quick Start

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- A free SEC EDGAR account (just an email address as user agent)
- Optional: Alpha Vantage API key (for conflict resolution in ETL)

---

## 1. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
SEC_USER_AGENT=your.email@example.com   # required by SEC EDGAR fair-use policy
POSTGRES_USER=finance
POSTGRES_PASSWORD=finance
POSTGRES_DB=finance
# Optional
ALPHA_VANTAGE_API_KEY=your_key_here
```

---

## 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

The database is initialized with the four schemas (`market_data`, `fundamentals`, `metrics`, `etl_audit`) on first boot via the init scripts in `docker/postgres/`.

---

## 3. Install Python Dependencies

```bash
uv sync
```

---

## 4. Ingest Your First Company

```bash
# Ingest 5 years of NVDA filings
uv run python -m src.etl.pipeline ingest NVDA --years 5
```

This will:
1. Fetch 10-K, 10-Q, and 8-K filings from SEC EDGAR and save them to `raw/NVDA/`
2. Parse XBRL structured data into PostgreSQL `fundamentals`
3. Validate key fields against yfinance
4. Fetch price history into `market_data`
5. Compute metrics (P/E, EV/EBITDA, MACD, RSI…) into `metrics`
6. Log the run in `etl_audit`

To batch-ingest all S&P 500 companies (takes time):

```bash
uv run python -m src.etl.pipeline ingest-sp500
```

---

## 5. Generate a Company Profile

Via Python:

```python
from src.analysis.company_profile import generate_tearsheet

md = generate_tearsheet("NVDA")
print(md)
```

Via the Agent (after starting the API):

```
User: Generate a profile for NVDA
```

The profile is saved to `artifacts/NVDA/profile/`.

---

## 6. Start the API

```bash
uv run uvicorn src.api.app:app --reload
# → http://localhost:8000/docs
```

---

## 7. Start Streamlit

```bash
uv run streamlit run streamlit_app/app.py
# → http://localhost:8501
```

---

## Or: Launch Everything with Docker Compose

```bash
docker compose up -d
```

This starts PostgreSQL, the FastAPI server, and Streamlit together.

| Service | URL |
|---|---|
| Streamlit dashboard | http://localhost:8501 |
| FastAPI + Swagger docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

---

## Typical First Session

```bash
# Start services
docker compose up -d

# Ingest a company
uv run python -m src.etl.pipeline ingest NVDA --years 5

# Open Streamlit and view the Company Profile page
open http://localhost:8501

# Ask the Agent to draft a thesis (in the Chat UI or via API)
curl -X POST http://localhost:8000/api/analysis/NVDA/tearsheet
```