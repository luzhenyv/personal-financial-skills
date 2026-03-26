"""Portfolio service — Mini PORT P&L engine, allocation, and snapshot logic."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from pfs.db.models import (
    Company,
    DailyPrice,
    Portfolio,
    PortfolioSnapshot,
    Position,
    Transaction,
)
from pfs.services.companies import _row_to_dict

# ──────────────────────────────────────────────
# Portfolio CRUD
# ──────────────────────────────────────────────


def get_or_create_portfolio(
    db: Session,
    *,
    name: str = "default",
    cash: Decimal | None = None,
    benchmark: str = "SPY",
) -> dict[str, Any]:
    """Return the named portfolio, creating it if necessary."""
    portfolio = db.query(Portfolio).filter(Portfolio.name == name).first()
    if portfolio:
        return _row_to_dict(portfolio)

    portfolio = Portfolio(
        name=name,
        cash=cash if cash is not None else Decimal("100000"),
        inception_date=date.today(),
        benchmark=benchmark,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return _row_to_dict(portfolio)


def get_portfolio(db: Session, portfolio_id: int) -> dict[str, Any] | None:
    """Return a portfolio by ID, or ``None``."""
    row = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    return _row_to_dict(row) if row else None


def _require_portfolio(db: Session, portfolio_id: int) -> Portfolio:
    """Return the Portfolio ORM instance or raise ValueError."""
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not p:
        raise ValueError(f"Portfolio {portfolio_id} not found")
    return p


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _latest_price(db: Session, ticker: str) -> Decimal | None:
    """Return the most recent close price for *ticker*, or ``None``."""
    row = (
        db.query(DailyPrice.close_price)
        .filter(DailyPrice.ticker == ticker)
        .order_by(DailyPrice.date.desc())
        .first()
    )
    return Decimal(str(row[0])) if row and row[0] is not None else None


def _batch_latest_prices(db: Session, tickers: list[str]) -> dict[str, Decimal]:
    """Return {ticker: latest_close} for a list of tickers."""
    if not tickers:
        return {}
    subq = (
        db.query(
            DailyPrice.ticker,
            func.max(DailyPrice.date).label("max_date"),
        )
        .filter(DailyPrice.ticker.in_(tickers))
        .group_by(DailyPrice.ticker)
        .subquery()
    )
    rows = (
        db.query(DailyPrice.ticker, DailyPrice.close_price)
        .join(
            subq,
            (DailyPrice.ticker == subq.c.ticker)
            & (DailyPrice.date == subq.c.max_date),
        )
        .all()
    )
    return {
        r.ticker: Decimal(str(r.close_price))
        for r in rows
        if r.close_price is not None
    }


# ──────────────────────────────────────────────
# Transactions (append-only)
# ──────────────────────────────────────────────


def record_transaction(
    db: Session,
    portfolio_id: int,
    *,
    ticker: str,
    action: str,
    shares: Decimal,
    price: Decimal,
    tx_date: date | None = None,
    fees: Decimal = Decimal("0"),
    notes: str | None = None,
) -> dict[str, Any]:
    """Record a trade and recompute the affected position + cash."""
    ticker = ticker.upper()
    action = action.lower()
    if action not in ("buy", "sell", "dividend"):
        raise ValueError(f"Invalid action '{action}' — must be buy, sell, or dividend")

    portfolio = _require_portfolio(db, portfolio_id)
    tx_date = tx_date or date.today()

    # Validate: company must exist in DB
    if not db.query(Company).filter(Company.ticker == ticker).first():
        raise ValueError(f"Company '{ticker}' not found — run ETL first")

    cost = shares * price + fees

    # Validate sell: must own enough shares
    if action == "sell":
        pos = (
            db.query(Position)
            .filter(Position.portfolio_id == portfolio_id, Position.ticker == ticker)
            .first()
        )
        if not pos or pos.shares < shares:
            owned = pos.shares if pos else Decimal("0")
            raise ValueError(
                f"Cannot sell {shares} shares of {ticker} — only own {owned}"
            )
        # Credit cash
        portfolio.cash += shares * price - fees
    elif action == "buy":
        if portfolio.cash < cost:
            raise ValueError(
                f"Insufficient cash: need ${cost:.2f}, have ${portfolio.cash:.2f}"
            )
        portfolio.cash -= cost
    elif action == "dividend":
        portfolio.cash += shares * price  # shares=1, price=total dividend amount

    # Insert transaction
    tx = Transaction(
        portfolio_id=portfolio_id,
        date=tx_date,
        ticker=ticker,
        action=action,
        shares=shares,
        price=price,
        fees=fees,
        notes=notes,
    )
    db.add(tx)
    db.flush()

    # Recompute position
    _recompute_position(db, portfolio_id, ticker, tx_date)

    db.commit()
    db.refresh(tx)
    return _row_to_dict(tx)


def _recompute_position(
    db: Session,
    portfolio_id: int,
    ticker: str,
    as_of: date,
) -> None:
    """Recompute the position for *ticker* from the transaction history."""
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.portfolio_id == portfolio_id,
            Transaction.ticker == ticker,
        )
        .order_by(Transaction.date, Transaction.id)
        .all()
    )

    total_shares = Decimal("0")
    total_cost = Decimal("0")
    first_date = as_of

    for t in txs:
        if t.action == "buy":
            total_cost += t.shares * t.price
            total_shares += t.shares
            if first_date is None or t.date < first_date:
                first_date = t.date
        elif t.action == "sell":
            if total_shares > 0:
                # Reduce cost basis proportionally
                avg = total_cost / total_shares
                total_shares -= t.shares
                total_cost = avg * total_shares
        # dividends don't change share count or cost basis

    pos = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id, Position.ticker == ticker)
        .first()
    )

    if total_shares <= 0:
        if pos:
            db.delete(pos)
        return

    avg_cost = total_cost / total_shares if total_shares else Decimal("0")

    if pos:
        pos.shares = total_shares
        pos.avg_cost = avg_cost
    else:
        pos = Position(
            portfolio_id=portfolio_id,
            ticker=ticker,
            shares=total_shares,
            avg_cost=avg_cost,
            opened_at=first_date,
        )
        db.add(pos)


def list_transactions(
    db: Session,
    portfolio_id: int,
    *,
    ticker: str | None = None,
    action: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return transaction history with optional filters."""
    _require_portfolio(db, portfolio_id)
    q = db.query(Transaction).filter(Transaction.portfolio_id == portfolio_id)
    if ticker:
        q = q.filter(Transaction.ticker == ticker.upper())
    if action:
        q = q.filter(Transaction.action == action.lower())
    if start:
        q = q.filter(Transaction.date >= start)
    if end:
        q = q.filter(Transaction.date <= end)
    rows = q.order_by(Transaction.date.desc(), Transaction.id.desc()).offset(offset).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ──────────────────────────────────────────────
# Positions
# ──────────────────────────────────────────────


def get_positions(
    db: Session,
    portfolio_id: int,
) -> list[dict[str, Any]]:
    """Return all open positions with current P&L and weights."""
    _require_portfolio(db, portfolio_id)
    positions = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id)
        .order_by(Position.ticker)
        .all()
    )
    if not positions:
        return []

    tickers = [p.ticker for p in positions]
    prices = _batch_latest_prices(db, tickers)
    portfolio = _require_portfolio(db, portfolio_id)
    total_market = sum(
        Decimal(str(p.shares)) * prices.get(p.ticker, Decimal(str(p.avg_cost)))
        for p in positions
    ) + Decimal(str(portfolio.cash))

    result = []
    for p in positions:
        shares = Decimal(str(p.shares))
        avg_cost = Decimal(str(p.avg_cost))
        current_price = prices.get(p.ticker, avg_cost)
        market_value = shares * current_price
        cost_basis = shares * avg_cost
        unrealized_pnl = market_value - cost_basis
        weight = (market_value / total_market * 100) if total_market else Decimal("0")

        d = _row_to_dict(p)
        d.update({
            "current_price": float(current_price),
            "market_value": float(market_value),
            "cost_basis": float(cost_basis),
            "unrealized_pnl": float(unrealized_pnl),
            "unrealized_pnl_pct": float(
                unrealized_pnl / cost_basis * 100 if cost_basis else 0
            ),
            "weight": float(weight),
        })
        result.append(d)
    return result


def get_position(
    db: Session,
    portfolio_id: int,
    ticker: str,
) -> dict[str, Any] | None:
    """Return a single position with transaction history."""
    ticker = ticker.upper()
    pos = (
        db.query(Position)
        .filter(Position.portfolio_id == portfolio_id, Position.ticker == ticker)
        .first()
    )
    if not pos:
        return None

    current_price = _latest_price(db, ticker)
    shares = Decimal(str(pos.shares))
    avg_cost = Decimal(str(pos.avg_cost))
    cp = current_price if current_price else avg_cost
    market_value = shares * cp
    cost_basis = shares * avg_cost

    d = _row_to_dict(pos)
    d.update({
        "current_price": float(cp),
        "market_value": float(market_value),
        "cost_basis": float(cost_basis),
        "unrealized_pnl": float(market_value - cost_basis),
        "unrealized_pnl_pct": float(
            (market_value - cost_basis) / cost_basis * 100 if cost_basis else 0
        ),
    })

    # Attach transaction history for this position
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.portfolio_id == portfolio_id,
            Transaction.ticker == ticker,
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    d["transactions"] = [_row_to_dict(t) for t in txs]
    return d


# ──────────────────────────────────────────────
# Portfolio summary
# ──────────────────────────────────────────────


def get_summary(db: Session, portfolio_id: int) -> dict[str, Any]:
    """Return portfolio summary: positions, cash, total value."""
    portfolio = _require_portfolio(db, portfolio_id)
    positions = get_positions(db, portfolio_id)

    total_market_value = sum(p["market_value"] for p in positions)
    total_cost_basis = sum(p["cost_basis"] for p in positions)
    cash = float(portfolio.cash)
    total_value = total_market_value + cash
    total_unrealized_pnl = total_market_value - total_cost_basis

    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "benchmark": portfolio.benchmark,
        "inception_date": portfolio.inception_date,
        "cash": cash,
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost_basis,
        "total_value": total_value,
        "unrealized_pnl": total_unrealized_pnl,
        "unrealized_pnl_pct": (
            total_unrealized_pnl / total_cost_basis * 100 if total_cost_basis else 0
        ),
        "position_count": len(positions),
        "positions": positions,
    }


# ──────────────────────────────────────────────
# Allocation breakdown
# ──────────────────────────────────────────────


def get_allocation(db: Session, portfolio_id: int) -> dict[str, Any]:
    """Return allocation breakdown by sector, conviction, and size."""
    portfolio = _require_portfolio(db, portfolio_id)
    positions = get_positions(db, portfolio_id)

    if not positions:
        return {"by_sector": [], "by_conviction": [], "by_position": [], "cash_weight": 100.0}

    # Look up sectors for all tickers
    tickers = [p["ticker"] for p in positions]
    companies = (
        db.query(Company.ticker, Company.sector)
        .filter(Company.ticker.in_(tickers))
        .all()
    )
    sector_map = {c.ticker: c.sector or "Unknown" for c in companies}

    total_value = sum(p["market_value"] for p in positions) + float(portfolio.cash)

    # By sector
    sector_totals: dict[str, float] = {}
    for p in positions:
        sector = sector_map.get(p["ticker"], "Unknown")
        sector_totals[sector] = sector_totals.get(sector, 0) + p["market_value"]
    by_sector = [
        {"sector": s, "market_value": v, "weight": v / total_value * 100 if total_value else 0}
        for s, v in sorted(sector_totals.items(), key=lambda x: -x[1])
    ]

    # By conviction
    conviction_totals: dict[str, float] = {}
    for p in positions:
        conv = p.get("conviction") or "unset"
        conviction_totals[conv] = conviction_totals.get(conv, 0) + p["market_value"]
    by_conviction = [
        {"conviction": c, "market_value": v, "weight": v / total_value * 100 if total_value else 0}
        for c, v in sorted(conviction_totals.items(), key=lambda x: -x[1])
    ]

    # By position (largest first)
    by_position = [
        {"ticker": p["ticker"], "market_value": p["market_value"], "weight": p["weight"]}
        for p in sorted(positions, key=lambda x: -x["market_value"])
    ]

    cash_weight = float(portfolio.cash) / total_value * 100 if total_value else 0

    return {
        "by_sector": by_sector,
        "by_conviction": by_conviction,
        "by_position": by_position,
        "cash_weight": cash_weight,
    }


# ──────────────────────────────────────────────
# P&L breakdown
# ──────────────────────────────────────────────


def get_pnl(db: Session, portfolio_id: int) -> dict[str, Any]:
    """Return realized + unrealized P&L per position."""
    _require_portfolio(db, portfolio_id)
    positions = get_positions(db, portfolio_id)

    # Compute realized P&L from sell transactions
    sells = (
        db.query(Transaction)
        .filter(
            Transaction.portfolio_id == portfolio_id,
            Transaction.action == "sell",
        )
        .all()
    )

    # We need cost basis at time of sale — approximate using current avg_cost
    # (accurate for FIFO-like tracking; good enough for v1)
    realized_by_ticker: dict[str, float] = {}
    for s in sells:
        # Look up current position avg_cost as proxy for the historical cost
        pos = next((p for p in positions if p["ticker"] == s.ticker), None)
        avg_cost = Decimal(str(pos["avg_cost"])) if pos else Decimal("0")
        realized = float((Decimal(str(s.price)) - avg_cost) * Decimal(str(s.shares)) - Decimal(str(s.fees)))
        realized_by_ticker[s.ticker] = realized_by_ticker.get(s.ticker, 0) + realized

    total_realized = sum(realized_by_ticker.values())
    total_unrealized = sum(p["unrealized_pnl"] for p in positions)

    per_position = []
    for p in positions:
        per_position.append({
            "ticker": p["ticker"],
            "unrealized_pnl": p["unrealized_pnl"],
            "realized_pnl": realized_by_ticker.get(p["ticker"], 0),
            "total_pnl": p["unrealized_pnl"] + realized_by_ticker.get(p["ticker"], 0),
        })

    return {
        "total_unrealized_pnl": total_unrealized,
        "total_realized_pnl": total_realized,
        "total_pnl": total_unrealized + total_realized,
        "per_position": per_position,
    }


# ──────────────────────────────────────────────
# Snapshots
# ──────────────────────────────────────────────


def take_snapshot(db: Session, portfolio_id: int, snap_date: date | None = None) -> dict[str, Any]:
    """Take a portfolio snapshot — compute and persist current state."""
    portfolio = _require_portfolio(db, portfolio_id)
    snap_date = snap_date or date.today()
    positions = get_positions(db, portfolio_id)

    total_market_value = sum(p["market_value"] for p in positions)
    total_cost_basis = sum(p["cost_basis"] for p in positions)
    unrealized_pnl = total_market_value - total_cost_basis

    # Realized P&L from pnl breakdown
    pnl_data = get_pnl(db, portfolio_id)

    # Upsert snapshot
    existing = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.date == snap_date,
        )
        .first()
    )

    positions_json = [
        {
            "ticker": p["ticker"],
            "shares": float(p["shares"]),
            "avg_cost": float(p["avg_cost"]),
            "current_price": p["current_price"],
            "market_value": p["market_value"],
            "unrealized_pnl": p["unrealized_pnl"],
        }
        for p in positions
    ]

    if existing:
        existing.total_market_value = total_market_value
        existing.total_cost_basis = total_cost_basis
        existing.cash = portfolio.cash
        existing.unrealized_pnl = unrealized_pnl
        existing.realized_pnl = pnl_data["total_realized_pnl"]
        existing.positions_json = positions_json
        snap = existing
    else:
        snap = PortfolioSnapshot(
            portfolio_id=portfolio_id,
            date=snap_date,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            cash=portfolio.cash,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=pnl_data["total_realized_pnl"],
            positions_json=positions_json,
        )
        db.add(snap)

    db.commit()
    db.refresh(snap)
    return _row_to_dict(snap)


# ──────────────────────────────────────────────
# Performance
# ──────────────────────────────────────────────


def get_performance(
    db: Session,
    portfolio_id: int,
    *,
    period: str = "ytd",
) -> dict[str, Any]:
    """Return time-series performance from snapshots."""
    _require_portfolio(db, portfolio_id)

    # Determine start date
    today = date.today()
    period_map = {
        "1m": 30,
        "3m": 90,
        "6m": 180,
        "ytd": (today - date(today.year, 1, 1)).days,
        "1y": 365,
        "all": 9999,
    }
    days = period_map.get(period, period_map["ytd"])
    start = date(today.year, 1, 1) if period == "ytd" else date.fromordinal(today.toordinal() - days)

    snapshots = (
        db.query(PortfolioSnapshot)
        .filter(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.date >= start,
        )
        .order_by(PortfolioSnapshot.date)
        .all()
    )

    series = []
    for s in snapshots:
        total = float(s.total_market_value or 0) + float(s.cash or 0)
        series.append({
            "date": s.date,
            "total_value": total,
            "market_value": float(s.total_market_value or 0),
            "cash": float(s.cash or 0),
            "unrealized_pnl": float(s.unrealized_pnl or 0),
        })

    # Simple return calculation
    if len(series) >= 2:
        first_val = series[0]["total_value"]
        last_val = series[-1]["total_value"]
        total_return = ((last_val - first_val) / first_val * 100) if first_val else 0
    else:
        total_return = 0

    return {
        "period": period,
        "total_return_pct": total_return,
        "snapshots": series,
    }
