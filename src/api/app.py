"""FastAPI application — serves as the single backend for both Streamlit and MCP."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import companies, financials, analysis
from src.config import settings

logging.basicConfig(level=getattr(logging, settings.log_level))

app = FastAPI(
    title="Personal Financial Skills API",
    description="Mini Bloomberg — REST API for personal equity research",
    version="0.1.0",
)

# CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(companies.router, prefix="/api/companies", tags=["Companies"])
app.include_router(financials.router, prefix="/api/financials", tags=["Financials"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.on_event("startup")
def startup():
    settings.ensure_dirs()
    logging.info("Personal Financial Skills API started")
