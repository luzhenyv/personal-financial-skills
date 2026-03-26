"""Portfolio (Mini PORT) API tests — in-memory SQLite for full integration.

Portfolio endpoints involve multi-step writes (transaction → position recompute
→ cash update), so mocking the DB session is fragile. Instead we use a real
in-memory SQLite database with all tables created from the ORM models.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pfs.api.deps import get_db
from pfs.app import app
from pfs.db.models import (
    Base, Company, DailyPrice, Portfolio, Position,
    PortfolioSnapshot, Transaction,
)

# Tables needed for portfolio tests (exclude tasks which uses PG schemas)
_PORTFOLIO_TABLES = [
    Base.metadata.tables[t] for t in (
        "companies", "daily_prices",
        "portfolios", "transactions", "positions", "portfolio_snapshots",
    )
]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session():
    """Yield an in-memory SQLite session with portfolio-related tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=_PORTFOLIO_TABLES)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def seeded_db(db_session):
    """DB with a company, prices, and a default portfolio."""
    db_session.add(Company(
        cik="0001045810", ticker="NVDA", name="NVIDIA Corporation",
        sector="Technology", industry="Semiconductors",
    ))
    db_session.add(Company(
        cik="0000002488", ticker="AMD", name="Advanced Micro Devices",
        sector="Technology", industry="Semiconductors",
    ))
    # Add some price data for latest price lookups
    db_session.add(DailyPrice(
        ticker="NVDA", date=date(2026, 3, 26),
        open_price=120, high_price=125, low_price=118,
        close_price=123.50, adjusted_close=123.50, volume=50_000_000,
    ))
    db_session.add(DailyPrice(
        ticker="AMD", date=date(2026, 3, 26),
        open_price=95, high_price=98, low_price=93,
        close_price=96.25, adjusted_close=96.25, volume=30_000_000,
    ))
    # Default portfolio
    db_session.add(Portfolio(
        id=1, name="default", cash=Decimal("100000"),
        inception_date=date(2026, 1, 1), benchmark="SPY",
    ))
    db_session.commit()
    return db_session


@pytest.fixture()
def client(seeded_db):
    """TestClient with the seeded in-memory DB."""
    def _override():
        yield seeded_db

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio CRUD
# ─────────────────────────────────────────────────────────────────────────────


def test_get_portfolio_summary_empty(client):
    resp = client.get("/api/portfolio/", params={"portfolio_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash"] == 100_000
    assert data["position_count"] == 0
    assert data["total_value"] == 100_000


def test_get_portfolio_not_found(client):
    resp = client.get("/api/portfolio/", params={"portfolio_id": 999})
    assert resp.status_code == 404


def test_create_portfolio(client):
    resp = client.post("/api/portfolio/", json={
        "name": "growth", "cash": "50000", "benchmark": "QQQ",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "growth"
    assert float(data["cash"]) == 50_000


# ─────────────────────────────────────────────────────────────────────────────
# Transactions & position recomputation
# ─────────────────────────────────────────────────────────────────────────────


def test_buy_transaction(client):
    resp = client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "120",
        "date": "2026-03-01",
    })
    assert resp.status_code == 200
    tx = resp.json()
    assert tx["ticker"] == "NVDA"
    assert tx["action"] == "buy"
    assert float(tx["shares"]) == 10

    # Check position created
    resp = client.get("/api/portfolio/positions/NVDA", params={"portfolio_id": 1})
    assert resp.status_code == 200
    pos = resp.json()
    assert float(pos["shares"]) == 10
    assert float(pos["avg_cost"]) == 120

    # Check cash reduced
    resp = client.get("/api/portfolio/", params={"portfolio_id": 1})
    data = resp.json()
    assert data["cash"] == 100_000 - (10 * 120)


def test_buy_then_sell(client):
    # Buy 20 shares
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "20", "price": "100",
        "date": "2026-02-01",
    })
    # Sell 5 shares
    resp = client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "sell", "shares": "5", "price": "130",
        "date": "2026-03-15",
    })
    assert resp.status_code == 200

    # Position should have 15 shares remaining at avg $100
    resp = client.get("/api/portfolio/positions/NVDA", params={"portfolio_id": 1})
    pos = resp.json()
    assert float(pos["shares"]) == 15
    assert float(pos["avg_cost"]) == 100

    # Transaction history should have both trades
    assert len(pos["transactions"]) == 2


def test_sell_too_many_shares(client):
    resp = client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "sell", "shares": "100", "price": "120",
    })
    assert resp.status_code == 400
    assert "Cannot sell" in resp.json()["detail"]


def test_buy_insufficient_cash(client):
    resp = client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10000", "price": "120",
    })
    assert resp.status_code == 400
    assert "Insufficient cash" in resp.json()["detail"]


def test_invalid_action(client):
    resp = client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "short", "shares": "10", "price": "120",
    })
    assert resp.status_code == 422  # pydantic validation


def test_unknown_ticker(client):
    resp = client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "FAKE", "action": "buy", "shares": "10", "price": "50",
    })
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_transaction_list_filters(client):
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "100",
        "date": "2026-01-15",
    })
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "AMD", "action": "buy", "shares": "20", "price": "90",
        "date": "2026-02-15",
    })

    # All
    resp = client.get("/api/portfolio/transactions", params={"portfolio_id": 1})
    assert len(resp.json()) == 2

    # Filter by ticker
    resp = client.get("/api/portfolio/transactions", params={"portfolio_id": 1, "ticker": "NVDA"})
    assert len(resp.json()) == 1

    # Filter by date range
    resp = client.get("/api/portfolio/transactions", params={
        "portfolio_id": 1, "start": "2026-02-01",
    })
    assert len(resp.json()) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Positions
# ─────────────────────────────────────────────────────────────────────────────


def test_positions_with_pnl(client):
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "100",
        "date": "2026-01-15",
    })
    resp = client.get("/api/portfolio/positions", params={"portfolio_id": 1})
    assert resp.status_code == 200
    positions = resp.json()
    assert len(positions) == 1
    pos = positions[0]
    assert pos["ticker"] == "NVDA"
    # Current price is 123.50 from seeded data
    assert pos["current_price"] == 123.50
    assert pos["market_value"] == 10 * 123.50
    assert pos["unrealized_pnl"] == (123.50 - 100) * 10


def test_position_not_found(client):
    resp = client.get("/api/portfolio/positions/MSFT", params={"portfolio_id": 1})
    assert resp.status_code == 404


def test_update_conviction(client):
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "100",
    })
    resp = client.patch("/api/portfolio/positions/NVDA", params={"portfolio_id": 1}, json={
        "conviction": "high",
    })
    assert resp.status_code == 200
    assert resp.json()["conviction"] == "high"


# ─────────────────────────────────────────────────────────────────────────────
# Allocation
# ─────────────────────────────────────────────────────────────────────────────


def test_allocation(client):
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "100",
    })
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "AMD", "action": "buy", "shares": "20", "price": "90",
    })
    resp = client.get("/api/portfolio/allocation", params={"portfolio_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["by_sector"]) >= 1
    assert data["by_sector"][0]["sector"] == "Technology"
    assert len(data["by_position"]) == 2
    assert data["cash_weight"] > 0


def test_allocation_empty(client):
    resp = client.get("/api/portfolio/allocation", params={"portfolio_id": 1})
    assert resp.status_code == 200
    assert resp.json()["cash_weight"] == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# P&L
# ─────────────────────────────────────────────────────────────────────────────


def test_pnl(client):
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "100",
    })
    resp = client.get("/api/portfolio/pnl", params={"portfolio_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    # Unrealized: (123.50 - 100) * 10 = 235
    assert data["total_unrealized_pnl"] == pytest.approx(235.0, abs=0.1)
    assert data["total_realized_pnl"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Snapshots & Performance
# ─────────────────────────────────────────────────────────────────────────────


def test_snapshot(client):
    client.post("/api/portfolio/transactions", params={"portfolio_id": 1}, json={
        "ticker": "NVDA", "action": "buy", "shares": "10", "price": "100",
    })
    resp = client.post("/api/portfolio/snapshot", params={"portfolio_id": 1}, json={
        "date": "2026-03-27",
    })
    assert resp.status_code == 200
    snap = resp.json()
    assert float(snap["total_market_value"]) > 0
    assert float(snap["cash"]) > 0


def test_performance_empty(client):
    resp = client.get("/api/portfolio/performance", params={"portfolio_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["period"] == "ytd"
    assert data["total_return_pct"] == 0
