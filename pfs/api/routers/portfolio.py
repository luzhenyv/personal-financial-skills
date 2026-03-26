"""Portfolio router — Mini PORT endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pfs.api.deps import get_db
from pfs.api.schemas.portfolio import (
    PortfolioCreate,
    PositionUpdate,
    SnapshotRequest,
    TransactionCreate,
)
from pfs.services import portfolio as port_svc

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# ── Portfolio ────────────────────────────────────────────────


@router.get("/")
def get_portfolio_summary(
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Get portfolio summary with positions, cash, and total value."""
    try:
        return port_svc.get_summary(db, portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/")
def create_portfolio(body: PortfolioCreate, db: Session = Depends(get_db)):
    """Create or return a named portfolio."""
    return port_svc.get_or_create_portfolio(
        db, name=body.name, cash=body.cash, benchmark=body.benchmark
    )


# ── Positions ────────────────────────────────────────────────


@router.get("/positions")
def list_positions(
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """All open positions with current prices and P&L."""
    try:
        return port_svc.get_positions(db, portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/positions/{ticker}")
def get_position(
    ticker: str,
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Single position details with transaction history."""
    try:
        result = port_svc.get_position(db, portfolio_id, ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail=f"No position in {ticker.upper()}")
    return result


@router.patch("/positions/{ticker}")
def update_position_conviction(
    ticker: str,
    body: PositionUpdate,
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Update conviction level on a position."""
    from pfs.db.models import Position

    ticker = ticker.upper()
    pos = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id, Position.ticker == ticker)
        .first()
    )
    if not pos:
        raise HTTPException(status_code=404, detail=f"No position in {ticker}")
    if body.conviction is not None:
        pos.conviction = body.conviction
    db.commit()
    db.refresh(pos)
    from pfs.services.companies import _row_to_dict
    return _row_to_dict(pos)


# ── Transactions ─────────────────────────────────────────────


@router.get("/transactions")
def list_transactions(
    portfolio_id: int = Query(1, ge=1),
    ticker: str | None = Query(None),
    action: str | None = Query(None),
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Transaction history with filters."""
    try:
        return port_svc.list_transactions(
            db, portfolio_id, ticker=ticker, action=action,
            start=start, end=end, limit=limit, offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/transactions")
def record_transaction(
    body: TransactionCreate,
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Record a trade (buy/sell/dividend). Updates position and cash."""
    try:
        return port_svc.record_transaction(
            db,
            portfolio_id,
            ticker=body.ticker,
            action=body.action,
            shares=body.shares,
            price=body.price,
            tx_date=body.date,
            fees=body.fees,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Snapshot ─────────────────────────────────────────────────


@router.post("/snapshot")
def take_snapshot(
    body: SnapshotRequest = SnapshotRequest(),
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Take a daily snapshot — compute P&L and persist."""
    try:
        return port_svc.take_snapshot(db, portfolio_id, snap_date=body.date)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Allocation ───────────────────────────────────────────────


@router.get("/allocation")
def get_allocation(
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Allocation breakdown by sector, conviction, and position size."""
    try:
        return port_svc.get_allocation(db, portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Performance ──────────────────────────────────────────────


@router.get("/performance")
def get_performance(
    portfolio_id: int = Query(1, ge=1),
    period: str = Query("ytd"),
    db: Session = Depends(get_db),
):
    """Time-weighted return from snapshots."""
    try:
        return port_svc.get_performance(db, portfolio_id, period=period)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── P&L ──────────────────────────────────────────────────────


@router.get("/pnl")
def get_pnl(
    portfolio_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Realized + unrealized P&L breakdown per position."""
    try:
        return port_svc.get_pnl(db, portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
