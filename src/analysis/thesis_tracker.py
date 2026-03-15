"""Thesis Tracker — file-backed storage for investment theses.

Theses are stored as JSON files under:
    data/artifacts/{TICKER}/thesis/thesis_{TICKER}.json

Each file has the structure::

    {
        "schema_version": "1.0",
        "thesis": { ... },
        "updates":  [ ... ],
        "health_checks": [ ... ]
    }

LLM agents create/update these files directly.  The Streamlit page reads
them via the public functions below.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────

_HERE = Path(__file__).resolve()
# Walk up until we find the project root (contains data/artifacts)
_ROOT = _HERE.parent
for _ in range(6):
    if (_ROOT / "data" / "artifacts").exists():
        break
    _ROOT = _ROOT.parent

_ARTIFACTS = _ROOT / "data" / "artifacts"


def _thesis_path(ticker: str) -> Path:
    return _ARTIFACTS / ticker.upper() / "thesis" / f"thesis_{ticker.upper()}.json"


def _load_file(ticker: str) -> dict | None:
    path = _thesis_path(ticker)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_file(ticker: str, data: dict) -> None:
    path = _thesis_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


# ──────────────────────────────────────────────
# Public read functions
# ──────────────────────────────────────────────


def get_all_active_theses() -> list[dict[str, Any]]:
    """Return brief summaries of all theses with status != 'closed'."""
    results: list[dict] = []
    if not _ARTIFACTS.exists():
        return results

    for ticker_dir in sorted(_ARTIFACTS.iterdir()):
        if not ticker_dir.is_dir() or ticker_dir.name.startswith("_"):
            continue
        thesis_file = ticker_dir / "thesis" / f"thesis_{ticker_dir.name}.json"
        if not thesis_file.exists():
            continue
        try:
            data = json.loads(thesis_file.read_text(encoding="utf-8"))
            thesis = data.get("thesis", {})
            if thesis.get("status", "active") == "closed":
                continue
            results.append(
                {
                    "ticker": ticker_dir.name,
                    "position": thesis.get("position", "long"),
                    "status": thesis.get("status", "active"),
                    "core_thesis": thesis.get("core_thesis", ""),
                    "created_at": thesis.get("created_at", ""),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    return results


def get_active_thesis(ticker: str) -> dict | None:
    """Return the thesis dict for *ticker*, or ``None`` if not found."""
    data = _load_file(ticker)
    if data is None:
        return None
    return data.get("thesis")


def get_thesis_detail(ticker: str) -> dict | None:
    """Return the full thesis payload used by the Streamlit page.

    Returns::

        {
            "thesis": {...},
            "updates": [...],          # newest-first
            "health_checks": [...],    # newest-first
            "latest_health": {...} | None,
        }

    or ``None`` if no thesis file exists.
    """
    data = _load_file(ticker)
    if data is None:
        return None

    updates = list(reversed(data.get("updates", [])))
    health_checks = list(reversed(data.get("health_checks", [])))

    return {
        "thesis": data.get("thesis", {}),
        "updates": updates,
        "health_checks": health_checks,
        "latest_health": health_checks[0] if health_checks else None,
    }


# ──────────────────────────────────────────────
# Public write functions (used by skill scripts)
# ──────────────────────────────────────────────


def create_thesis(
    ticker: str,
    *,
    position: str = "long",
    core_thesis: str = "",
    buy_reasons: list | None = None,
    assumptions: list | None = None,
    sell_conditions: list | None = None,
    risk_factors: list | None = None,
    target_price: float | None = None,
    stop_loss_price: float | None = None,
) -> dict:
    """Create (or overwrite) a thesis JSON file and return the thesis dict."""
    now = datetime.now(timezone.utc).isoformat()
    thesis: dict[str, Any] = {
        "ticker": ticker.upper(),
        "position": position.lower(),
        "status": "active",
        "core_thesis": core_thesis,
        "buy_reasons": buy_reasons or [],
        "assumptions": assumptions or [],
        "sell_conditions": sell_conditions or [],
        "risk_factors": risk_factors or [],
        "target_price": target_price,
        "stop_loss_price": stop_loss_price,
        "created_at": now,
        "updated_at": now,
    }
    _save_file(
        ticker,
        {
            "schema_version": "1.0",
            "thesis": thesis,
            "updates": [],
            "health_checks": [],
        },
    )
    return thesis


def add_thesis_update(
    ticker: str,
    *,
    event_title: str,
    event_description: str = "",
    event_date: str | None = None,
    assumption_impacts: dict | None = None,
    strength_change: str = "unchanged",
    action_taken: str = "hold",
    conviction: str = "medium",
    notes: str = "",
    source: str = "manual",
) -> dict:
    """Append an update entry to the thesis file and return it."""
    data = _load_file(ticker)
    if data is None:
        raise ValueError(f"No thesis found for {ticker}. Create one first.")

    now = datetime.now(timezone.utc).isoformat()
    update: dict[str, Any] = {
        "event_date": event_date or now[:10],
        "event_title": event_title,
        "event_description": event_description,
        "assumption_impacts": assumption_impacts or {},
        "strength_change": strength_change,
        "action_taken": action_taken,
        "conviction": conviction,
        "notes": notes,
        "source": source,
        "created_at": now,
    }
    data.setdefault("updates", []).append(update)
    data["thesis"]["updated_at"] = now
    _save_file(ticker, data)
    return update


def add_health_check(
    ticker: str,
    *,
    objective_score: float,
    subjective_score: float,
    composite_score: float | None = None,
    assumption_scores: dict | None = None,
    key_observations: list | None = None,
    recommendation: str = "hold",
    recommendation_reasoning: str = "",
    check_date: str | None = None,
) -> dict:
    """Append a health-check snapshot to the thesis file and return it."""
    data = _load_file(ticker)
    if data is None:
        raise ValueError(f"No thesis found for {ticker}. Create one first.")

    if composite_score is None:
        composite_score = objective_score * 0.6 + subjective_score * 0.4

    now = datetime.now(timezone.utc).isoformat()
    check: dict[str, Any] = {
        "check_date": check_date or now[:10],
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "composite_score": composite_score,
        "assumption_scores": assumption_scores or {},
        "key_observations": key_observations or [],
        "recommendation": recommendation,
        "recommendation_reasoning": recommendation_reasoning,
        "created_at": now,
    }
    data.setdefault("health_checks", []).append(check)
    data["thesis"]["updated_at"] = now
    _save_file(ticker, data)
    return check


# ──────────────────────────────────────────────
# Markdown generation (used by page & scripts)
# ──────────────────────────────────────────────


def generate_thesis_markdown(ticker: str) -> str:
    """Return the full thesis as a Markdown string, or empty string if missing."""
    data = _load_file(ticker)
    if data is None:
        return ""

    thesis = data.get("thesis", {})
    updates = data.get("updates", [])
    health_checks = data.get("health_checks", [])

    lines: list[str] = [
        f"# {ticker.upper()} Investment Thesis",
        f"**Created:** {str(thesis.get('created_at', ''))[:10]}",
        f"**Status:** {thesis.get('status', 'active').title()}",
        f"**Position:** {thesis.get('position', 'long').title()}",
        "",
        "## Core Thesis",
        thesis.get("core_thesis", ""),
        "",
        "## Buy Reasons",
    ]
    for i, r in enumerate(thesis.get("buy_reasons", []), 1):
        reason = r if isinstance(r, str) else r.get("reason", str(r))
        lines.append(f"{i}. {reason}")

    lines += ["", "## Prerequisite Assumptions"]
    for a in thesis.get("assumptions", []):
        desc = a if isinstance(a, str) else a.get("description", str(a))
        weight = "" if isinstance(a, str) else f" [Weight: {a.get('weight', '')}%]"
        lines.append(f"- {desc}{weight}")

    lines += ["", "## Sell Conditions"]
    for c in thesis.get("sell_conditions", []):
        lines.append(f"- {c}")

    lines += ["", "## Where I Might Be Wrong"]
    for r in thesis.get("risk_factors", []):
        lines.append(f"- {r}")

    if updates:
        lines += ["", "## Thesis Update Log"]
        for u in updates:
            lines += [
                f"### {u.get('event_date', '')[:10]} | {u.get('event_title', '')}",
                f"**Trigger:** {u.get('event_description', '')}",
                f"**Thesis Strength:** {u.get('strength_change', '').title()}",
                f"**Action:** {u.get('action_taken', '').title()}",
                f"**Conviction:** {u.get('conviction', '').title()}",
                "",
            ]

    if health_checks:
        lines += ["", "## Health Check History"]
        for hc in reversed(health_checks):
            lines += [
                f"### {hc.get('check_date', '')[:10]}",
                f"- Composite Score: **{hc.get('composite_score', 0):.0f}/100**",
                f"- Recommendation: {hc.get('recommendation', '').title()}",
                f"- {hc.get('recommendation_reasoning', '')}",
                "",
            ]

    return "\n".join(lines)
