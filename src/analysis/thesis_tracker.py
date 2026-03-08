"""Thesis Tracker data access and operations.

Public API
----------
.. code-block:: python

    from src.analysis.thesis_tracker import (
        create_thesis,
        get_active_thesis,
        get_all_active_theses,
        add_thesis_update,
        add_health_check,
        get_thesis_detail,
        close_thesis,
        generate_thesis_markdown,
    )

All functions operate on PostgreSQL via SQLAlchemy and optionally write the
human-readable markdown file to ``data/processed/{TICKER}/thesis_{TICKER}.md``.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(obj) -> dict[str, Any]:
    """Convert a SQLAlchemy model instance to a plain dict."""
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, (datetime, date)):
            val = val.isoformat()
        elif isinstance(val, Decimal):
            val = float(val)
        result[col.name] = val
    return result


def _thesis_md_path(ticker: str) -> Path:
    """Return the path to the thesis markdown file."""
    return Path("data/processed") / ticker / f"thesis_{ticker}.md"


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

def create_thesis(
    ticker: str,
    *,
    position: str = "long",
    core_thesis: str,
    buy_reasons: list[dict[str, str]],
    assumptions: list[dict[str, Any]],
    sell_conditions: list[str],
    risk_factors: list[dict[str, str]],
    target_price: float | None = None,
    stop_loss_price: float | None = None,
    objective_weight: float = 0.60,
    subjective_weight: float = 0.40,
    save_md: bool = True,
    session: Session | None = None,
) -> dict[str, Any]:
    """Create a new investment thesis for *ticker*.

    Args:
        ticker: Upper-case ticker symbol.
        position: 'long' or 'short'.
        core_thesis: 1-2 sentence thesis statement.
        buy_reasons: List of ``{title, description}`` dicts.
        assumptions: List of ``{description, weight, kpi_metric, kpi_thresholds}`` dicts.
            ``weight`` values must sum to 1.0 (100%).
        sell_conditions: List of condition strings.
        risk_factors: List of ``{description}`` dicts.
        target_price: Optional target price.
        stop_loss_price: Optional stop-loss trigger.
        objective_weight: Weight for objective score in health checks (default 0.60).
        subjective_weight: Weight for subjective score (default 0.40).
        save_md: Whether to write the markdown file.
        session: Optional existing DB session (creates one if not provided).

    Returns:
        Dict representation of the created ``InvestmentThesis`` row.
    """
    from src.db.models import InvestmentThesis
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    try:
        thesis = InvestmentThesis(
            ticker=ticker.upper(),
            position=position,
            status="active",
            core_thesis=core_thesis,
            buy_reasons=buy_reasons,
            assumptions=assumptions,
            sell_conditions=sell_conditions,
            risk_factors=risk_factors,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            objective_weight=objective_weight,
            subjective_weight=subjective_weight,
        )
        session.add(thesis)
        session.commit()
        session.refresh(thesis)

        result = _row_to_dict(thesis)

        if save_md:
            _write_thesis_md(ticker.upper(), result)

        return result
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def get_active_thesis(ticker: str, session: Session | None = None) -> dict[str, Any] | None:
    """Return the active thesis for *ticker*, or ``None``."""
    from src.db.models import InvestmentThesis
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    try:
        row = (
            session.query(InvestmentThesis)
            .filter(InvestmentThesis.ticker == ticker.upper(), InvestmentThesis.status == "active")
            .first()
        )
        return _row_to_dict(row) if row else None
    finally:
        if own_session:
            session.close()


def get_all_active_theses(session: Session | None = None) -> list[dict[str, Any]]:
    """Return all theses with status='active'."""
    from src.db.models import InvestmentThesis
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    try:
        rows = (
            session.query(InvestmentThesis)
            .filter(InvestmentThesis.status == "active")
            .order_by(InvestmentThesis.ticker)
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        if own_session:
            session.close()


def get_thesis_detail(ticker: str, session: Session | None = None) -> dict[str, Any] | None:
    """Return full thesis detail including updates and health checks.

    Returns:
        Dict with keys ``thesis``, ``updates``, ``health_checks``, ``latest_health``.
    """
    from src.db.models import InvestmentThesis, ThesisUpdate, ThesisHealthCheck
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    try:
        thesis = (
            session.query(InvestmentThesis)
            .filter(InvestmentThesis.ticker == ticker.upper(), InvestmentThesis.status == "active")
            .first()
        )
        if thesis is None:
            return None

        updates = (
            session.query(ThesisUpdate)
            .filter(ThesisUpdate.thesis_id == thesis.id)
            .order_by(desc(ThesisUpdate.event_date))
            .all()
        )

        health_checks = (
            session.query(ThesisHealthCheck)
            .filter(ThesisHealthCheck.thesis_id == thesis.id)
            .order_by(ThesisHealthCheck.check_date)
            .all()
        )

        latest_health = health_checks[-1] if health_checks else None

        return {
            "thesis": _row_to_dict(thesis),
            "updates": [_row_to_dict(u) for u in updates],
            "health_checks": [_row_to_dict(h) for h in health_checks],
            "latest_health": _row_to_dict(latest_health) if latest_health else None,
        }
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def add_thesis_update(
    ticker: str,
    *,
    event_date: date | str,
    event_title: str,
    event_description: str | None = None,
    assumption_impacts: dict[str, dict[str, str]] | None = None,
    strength_change: str = "unchanged",
    action_taken: str = "hold",
    conviction: str = "medium",
    notes: str | None = None,
    source: str = "manual",
    save_md: bool = True,
    session: Session | None = None,
) -> dict[str, Any]:
    """Append a thesis update entry.

    Args:
        ticker: Ticker symbol.
        event_date: When the event happened (date or ISO string).
        event_title: Short label for the event.
        event_description: Longer description.
        assumption_impacts: ``{assumption_index: {status: '✓'|'⚠️'|'✗'|'—', explanation: '...'}}``
        strength_change: 'strengthened', 'weakened', or 'unchanged'.
        action_taken: 'hold', 'add', 'trim', or 'exit'.
        conviction: 'high', 'medium', or 'low'.
        notes: Additional context.
        source: 'manual', 'earnings', or 'catalyst'.
        save_md: Whether to append to the markdown file.
        session: Optional DB session.

    Returns:
        Dict of the inserted ``ThesisUpdate`` row.
    """
    from src.db.models import InvestmentThesis, ThesisUpdate
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    if isinstance(event_date, str):
        event_date = date.fromisoformat(event_date)

    try:
        thesis = (
            session.query(InvestmentThesis)
            .filter(InvestmentThesis.ticker == ticker.upper(), InvestmentThesis.status == "active")
            .first()
        )
        if thesis is None:
            raise ValueError(f"No active thesis found for {ticker}")

        update = ThesisUpdate(
            ticker=ticker.upper(),
            thesis_id=thesis.id,
            event_date=event_date,
            event_title=event_title,
            event_description=event_description,
            assumption_impacts=assumption_impacts or {},
            strength_change=strength_change,
            action_taken=action_taken,
            conviction=conviction,
            notes=notes,
            source=source,
        )
        session.add(update)
        session.commit()
        session.refresh(update)

        result = _row_to_dict(update)

        if save_md:
            _append_update_md(ticker.upper(), result, thesis.assumptions)

        # If action is "exit", close the thesis
        if action_taken == "exit":
            close_thesis(ticker, reason=event_title, session=session)

        return result
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def add_health_check(
    ticker: str,
    *,
    check_date: date | str | None = None,
    objective_score: float,
    subjective_score: float,
    assumption_scores: list[dict[str, Any]] | None = None,
    key_observations: list[str] | None = None,
    recommendation: str | None = None,
    recommendation_reasoning: str | None = None,
    save_md: bool = True,
    session: Session | None = None,
) -> dict[str, Any]:
    """Record a thesis health check.

    The composite score is computed as:
        ``composite = objective * obj_weight + subjective * subj_weight``

    using the weights stored on the thesis record.

    Returns:
        Dict of the inserted ``ThesisHealthCheck`` row.
    """
    from src.db.models import InvestmentThesis, ThesisHealthCheck
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    if isinstance(check_date, str):
        check_date = date.fromisoformat(check_date)
    if check_date is None:
        check_date = date.today()

    try:
        thesis = (
            session.query(InvestmentThesis)
            .filter(InvestmentThesis.ticker == ticker.upper(), InvestmentThesis.status == "active")
            .first()
        )
        if thesis is None:
            raise ValueError(f"No active thesis found for {ticker}")

        obj_w = float(thesis.objective_weight)
        subj_w = float(thesis.subjective_weight)
        composite = objective_score * obj_w + subjective_score * subj_w

        check = ThesisHealthCheck(
            ticker=ticker.upper(),
            thesis_id=thesis.id,
            check_date=check_date,
            objective_score=objective_score,
            subjective_score=subjective_score,
            composite_score=round(composite, 2),
            assumption_scores=assumption_scores or [],
            key_observations=key_observations or [],
            recommendation=recommendation,
            recommendation_reasoning=recommendation_reasoning,
        )
        session.add(check)
        session.commit()
        session.refresh(check)

        result = _row_to_dict(check)

        if save_md:
            _append_health_check_md(ticker.upper(), result, thesis.assumptions)

        return result
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def close_thesis(
    ticker: str,
    *,
    reason: str = "",
    session: Session | None = None,
) -> dict[str, Any]:
    """Close the active thesis for *ticker*."""
    from src.db.models import InvestmentThesis
    from src.db.session import get_session as _get_session

    own_session = session is None
    if own_session:
        session = _get_session()

    try:
        thesis = (
            session.query(InvestmentThesis)
            .filter(InvestmentThesis.ticker == ticker.upper(), InvestmentThesis.status == "active")
            .first()
        )
        if thesis is None:
            raise ValueError(f"No active thesis found for {ticker}")

        thesis.status = "closed"
        thesis.closed_at = datetime.utcnow()
        thesis.close_reason = reason
        session.commit()
        session.refresh(thesis)
        return _row_to_dict(thesis)
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _write_thesis_md(ticker: str, thesis: dict[str, Any]) -> None:
    """Write the initial thesis markdown file."""
    path = _thesis_md_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# {ticker} Investment Thesis",
        f"**Created:** {thesis['created_at'][:10] if isinstance(thesis['created_at'], str) else thesis['created_at']}",
        f"**Status:** {thesis['status'].title()}",
        f"**Position:** {thesis['position'].title()}",
        "",
        "## Core Thesis",
        thesis["core_thesis"],
        "",
        "## Buy Reasons",
    ]

    for i, reason in enumerate(thesis["buy_reasons"], 1):
        title = reason.get("title", f"Reason {i}")
        desc = reason.get("description", "")
        lines.append(f"{i}. **{title}**")
        if desc:
            lines.append(f"   {desc}")

    lines.append("")
    lines.append("## Prerequisite Assumptions")

    for i, assumption in enumerate(thesis["assumptions"], 1):
        desc = assumption.get("description", f"Assumption {i}")
        weight = assumption.get("weight", 0)
        weight_pct = f"{weight * 100:.0f}%" if isinstance(weight, (int, float)) and weight <= 1 else f"{weight}%"
        lines.append(f"- **Assumption {i}:** {desc} [Weight: {weight_pct}]")

    lines.append("")
    lines.append("## Sell Conditions")
    for cond in thesis["sell_conditions"]:
        lines.append(f"- {cond}")

    lines.append("")
    lines.append("## Where I Might Be Wrong")
    for risk in thesis["risk_factors"]:
        desc = risk.get("description", str(risk))
        lines.append(f"- {desc}")

    if thesis.get("target_price"):
        lines.append("")
        lines.append(f"**Target Price:** ${thesis['target_price']:.2f}")
    if thesis.get("stop_loss_price"):
        lines.append(f"**Stop-Loss:** ${thesis['stop_loss_price']:.2f}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Thesis Update Log")
    lines.append("")
    lines.append("*(Updates will be appended below)*")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _append_update_md(ticker: str, update: dict[str, Any], assumptions: list[dict]) -> None:
    """Append a thesis update entry to the markdown file."""
    path = _thesis_md_path(ticker)
    if not path.exists():
        return

    lines = [
        "",
        "---",
        "",
        f"### {update['event_date']} | {update['event_title']}",
        f"**Trigger:** {update.get('event_description') or update['event_title']}",
        "**Assumption Changes:**",
    ]

    impacts = update.get("assumption_impacts", {})
    for i, assumption in enumerate(assumptions):
        idx = str(i)
        desc = assumption.get("description", f"Assumption {i + 1}")
        impact = impacts.get(idx, {})
        status = impact.get("status", "—")
        explanation = impact.get("explanation", "No change")
        lines.append(f"- Assumption {i + 1} ({desc}): {status} — {explanation}")

    lines.append("")
    lines.append(f"**Thesis Strength:** {update.get('strength_change', 'unchanged').title()}")
    lines.append(f"**Action:** {update.get('action_taken', 'hold').title()}")
    lines.append(f"**Conviction:** {update.get('conviction', 'medium').title()}")

    if update.get("notes"):
        lines.append(f"**Notes:** {update['notes']}")

    lines.append("")

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _append_health_check_md(
    ticker: str, check: dict[str, Any], assumptions: list[dict]
) -> None:
    """Append a health check section to the markdown file."""
    path = _thesis_md_path(ticker)
    if not path.exists():
        return

    lines = [
        "",
        "---",
        "",
        f"## Thesis Health Check | {check['check_date']}",
        "",
        "### Assumption Scorecard",
        "| Assumption | Weight | Objective | Subjective | Combined | Status |",
        "|------------|--------|-----------|------------|----------|--------|",
    ]

    assumption_scores = check.get("assumption_scores", [])
    for i, assumption in enumerate(assumptions):
        desc = assumption.get("description", f"Assumption {i + 1}")
        weight = assumption.get("weight", 0)
        weight_pct = f"{weight * 100:.0f}%" if isinstance(weight, (int, float)) and weight <= 1 else f"{weight}%"

        score = assumption_scores[i] if i < len(assumption_scores) else {}
        obj = score.get("objective", "—")
        subj = score.get("subjective", "—")
        combined = score.get("combined", "—")
        status = score.get("status", "—")

        lines.append(f"| {desc} | {weight_pct} | {obj} | {subj} | {combined} | {status} |")

    lines.append("")
    lines.append(f"### Composite Score: {check['composite_score']}/100")
    lines.append(f"- Objective: {check['objective_score']}/100")
    lines.append(f"- Subjective: {check['subjective_score']}/100")
    lines.append("")

    observations = check.get("key_observations", [])
    if observations:
        lines.append("### Key Observations")
        for obs in observations:
            lines.append(f"- {obs}")
        lines.append("")

    if check.get("recommendation"):
        lines.append(f"### Recommendation: {check['recommendation'].title()}")
        if check.get("recommendation_reasoning"):
            lines.append(check["recommendation_reasoning"])
        lines.append("")

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Full markdown regeneration (for display / download)
# ---------------------------------------------------------------------------

def generate_thesis_markdown(ticker: str) -> str | None:
    """Generate the complete thesis markdown from DB for *ticker*.

    Useful for Streamlit display or download. Returns ``None`` if no active thesis.
    """
    detail = get_thesis_detail(ticker)
    if detail is None:
        return None

    path = _thesis_md_path(ticker.upper())
    if path.exists():
        return path.read_text(encoding="utf-8")

    # Regenerate from DB if file is missing
    _write_thesis_md(ticker.upper(), detail["thesis"])
    for update in reversed(detail["updates"]):  # oldest first
        _append_update_md(ticker.upper(), update, detail["thesis"]["assumptions"])
    for check in detail["health_checks"]:
        _append_health_check_md(ticker.upper(), check, detail["thesis"]["assumptions"])

    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
