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
POSTGRES_USER=pfs
POSTGRES_PASSWORD=pfs_dev_2024
POSTGRES_DB=personal_finance
# Optional
ALPHA_VANTAGE_API_KEY=your_key_here
```

---

## 2. Start PostgreSQL

```bash
docker compose -f deploy/docker/docker-compose.data.yml up -d
```

The database is initialized with the schemas on first boot via the init SQL scripts mounted from `pfs/db/`.

---

## 3. Install Python Dependencies

```bash
uv sync
```

---

## 4. Ingest Your First Company

```bash
# Ingest 5 years of NVDA filings
uv run python -m pfs.etl.pipeline ingest NVDA --years 5
```

This will:
1. Fetch 10-K, 10-Q, and 8-K filings from SEC EDGAR and save them to `data/raw/NVDA/`
2. Parse XBRL structured data into PostgreSQL `fundamentals`
3. Validate key fields against yfinance
4. Fetch price history into `market_data`
5. Compute metrics (P/E, EV/EBITDA, MACD, RSI…) into `metrics`
6. Log the run in `etl_audit`

---

## 5. Generate a Company Profile

Via Python:

```python
from pfs.analysis.company_profile import generate_tearsheet

md = generate_tearsheet("NVDA")
print(md)
```

Via the Agent:

```
@Personal Finance Assistant generate profile for NVDA
```

The profile is saved to `data/artifacts/NVDA/profile/`.

---

## 6. Start the API

```bash
uv run uvicorn pfs.api.app:app --reload
# → http://localhost:8000/docs
```

---

## 7. Start Streamlit

```bash
uv run streamlit run dashboard/app.py
# → http://localhost:8501
```

---

## Typical First Session

```bash
# Start PostgreSQL
docker compose -f deploy/docker/docker-compose.data.yml up -d

# Ingest a company
uv run python -m pfs.etl.pipeline ingest NVDA --years 5

# Start API
uv run uvicorn pfs.api.app:app --reload &

# Start Streamlit
uv run streamlit run dashboard/app.py &

# Or ingest via API
curl -s -X POST http://localhost:8000/api/etl/ingest \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "years": 5}'

# Check ingestion status
curl "http://localhost:8000/api/etl/runs?ticker=NVDA&limit=1"

# Open Streamlit
open http://localhost:8501
```