"""Personal Finance API — FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pfs.api.routers import companies, etl, filings, financials, analysis, tasks
from pfs.config import settings

app = FastAPI(title="Personal Finance API", version="1.0.0")

# CORS — allow Streamlit dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(etl.router)
app.include_router(companies.router)
app.include_router(financials.router)
app.include_router(filings.router)
app.include_router(analysis.router)
app.include_router(tasks.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
