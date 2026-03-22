"""Thesis Tracker — multi-file artifact storage for investment theses.

Thesis data is split across four JSON files under::

    data/artifacts/{TICKER}/thesis/
        thesis.json           — core thesis record
        updates.json          — append-only update log
        health_checks.json    — health check history
        catalysts.json        — upcoming catalyst calendar
        thesis_{TICKER}.md    — generated markdown report

Every JSON file includes ``"schema_version": "1.0"``.

LLM agents and skill scripts create/update these files.  The Streamlit page
reads them via the public functions below.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent
for _ in range(6):
    if (_ROOT / "data" / "artifacts").exists():
        break
    _ROOT = _ROOT.parent

_ARTIFACTS = _ROOT / "data" / "artifacts"


def _thesis_dir(ticker: str) -> Path:
    return _ARTIFACTS / ticker.upper() / "thesis"


# ── Individual file helpers ──────────────────────────────────────────────────


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def _load_thesis_json(ticker: str) -> dict | None:
    return _load_json(_thesis_dir(ticker) / "thesis.json")


def _load_updates_json(ticker: str) -> dict | None:
    return _load_json(_thesis_dir(ticker) / "updates.json")


def _load_health_checks_json(ticker: str) -> dict | None:
    return _load_json(_thesis_dir(ticker) / "health_checks.json")


def _load_catalysts_json(ticker: str) -> dict | None:
    return _load_json(_thesis_dir(ticker) / "catalysts.json")


# ── Legacy single-file migration ────────────────────────────────────────────


def _migrate_legacy(ticker: str) -> None:
    """If the old single-file format exists, migrate to multi-file and remove it."""
    legacy = _thesis_dir(ticker) / f"thesis_{ticker.upper()}.json"
    if not legacy.exists():
        return
    # Only migrate if the new thesis.json doesn't already exist
    if (_thesis_dir(ticker) / "thesis.json").exists():
        return

    data = _load_json(legacy)
    if data is None:
        return

    now = datetime.now(timezone.utc).isoformat()
    thesis = data.get("thesis", {})
    updates = data.get("updates", [])
    health_checks = data.get("health_checks", [])

    d = _thesis_dir(ticker)
    _save_json(d / "thesis.json", {"schema_version": "1.0", **thesis})
    _save_json(d / "updates.json", {"schema_version": "1.0", "ticker": ticker.upper(), "updates": updates})
    _save_json(d / "health_checks.json", {"schema_version": "1.0", "ticker": ticker.upper(), "health_checks": health_checks})
    _save_json(d / "catalysts.json", {"schema_version": "1.0", "ticker": ticker.upper(), "catalysts": []})

    # Remove legacy file after successful migration
    legacy.unlink()


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

        _migrate_legacy(ticker_dir.name)

        thesis_file = ticker_dir / "thesis" / "thesis.json"
        if not thesis_file.exists():
            continue
        try:
            thesis = json.loads(thesis_file.read_text(encoding="utf-8"))
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
    _migrate_legacy(ticker)
    return _load_thesis_json(ticker)


def get_thesis_detail(ticker: str) -> dict | None:
    """Return the full thesis payload used by the Streamlit page.

    Returns::

        {
            "thesis": {...},
            "updates": [...],          # newest-first
            "health_checks": [...],    # newest-first
            "latest_health": {...} | None,
            "catalysts": [...],
        }

    or ``None`` if no thesis file exists.
    """
    _migrate_legacy(ticker)

    thesis = _load_thesis_json(ticker)
    if thesis is None:
        return None

    updates_data = _load_updates_json(ticker) or {}
    health_data = _load_health_checks_json(ticker) or {}
    catalysts_data = _load_catalysts_json(ticker) or {}

    updates = list(reversed(updates_data.get("updates", [])))
    health_checks = list(reversed(health_data.get("health_checks", [])))
    catalysts = catalysts_data.get("catalysts", [])

    return {
        "thesis": thesis,
        "updates": updates,
        "health_checks": health_checks,
        "latest_health": health_checks[0] if health_checks else None,
        "catalysts": catalysts,
    }


def get_catalysts(ticker: str) -> list[dict]:
    """Return the list of catalysts for *ticker*."""
    _migrate_legacy(ticker)
    data = _load_catalysts_json(ticker)
    if data is None:
        return []
    return data.get("catalysts", [])


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
    """Create (or overwrite) thesis artifacts and return the thesis dict."""
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat()
    d = _thesis_dir(ticker)

    thesis: dict[str, Any] = {
        "schema_version": "1.0",
        "ticker": ticker,
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

    _save_json(d / "thesis.json", thesis)
    _save_json(d / "updates.json", {"schema_version": "1.0", "ticker": ticker, "updates": []})
    _save_json(d / "health_checks.json", {"schema_version": "1.0", "ticker": ticker, "health_checks": []})
    _save_json(d / "catalysts.json", {"schema_version": "1.0", "ticker": ticker, "catalysts": []})

    return thesis


def update_thesis(ticker: str, **fields: Any) -> dict:
    """Update mutable fields on an existing thesis and return the updated dict.

    Only the provided keyword arguments are overwritten. Accepted fields:
    ``core_thesis``, ``position``, ``status``, ``buy_reasons``,
    ``assumptions``, ``sell_conditions``, ``risk_factors``,
    ``target_price``, ``stop_loss_price``.
    """
    ticker = ticker.upper()
    _migrate_legacy(ticker)

    thesis = _load_thesis_json(ticker)
    if thesis is None:
        raise ValueError(f"No thesis found for {ticker}. Create one first.")

    allowed = {
        "core_thesis", "position", "status", "buy_reasons",
        "assumptions", "sell_conditions", "risk_factors",
        "target_price", "stop_loss_price",
    }
    for key, value in fields.items():
        if key in allowed:
            thesis[key] = value

    thesis["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_json(_thesis_dir(ticker) / "thesis.json", thesis)
    return thesis


def update_catalyst_notes(
    ticker: str,
    catalyst_id: int,
    *,
    notes: str | None = None,
    event: str | None = None,
    expected_date: str | None = None,
    expected_impact: str | None = None,
) -> dict:
    """Update editable fields on a catalyst entry and return it."""
    ticker = ticker.upper()
    d = _thesis_dir(ticker)
    cat_data = _load_catalysts_json(ticker)
    if cat_data is None:
        raise ValueError(f"No catalysts file for {ticker}.")

    for cat in cat_data.get("catalysts", []):
        if cat.get("id") == catalyst_id:
            if notes is not None:
                cat["notes"] = notes
            if event is not None:
                cat["event"] = event
            if expected_date is not None:
                cat["expected_date"] = expected_date
            if expected_impact is not None:
                cat["expected_impact"] = expected_impact
            _save_json(d / "catalysts.json", cat_data)
            return cat

    raise ValueError(f"Catalyst ID {catalyst_id} not found for {ticker}.")


def delete_catalyst(ticker: str, catalyst_id: int) -> None:
    """Remove a catalyst entry by ID."""
    ticker = ticker.upper()
    d = _thesis_dir(ticker)
    cat_data = _load_catalysts_json(ticker)
    if cat_data is None:
        raise ValueError(f"No catalysts file for {ticker}.")

    original_len = len(cat_data.get("catalysts", []))
    cat_data["catalysts"] = [
        c for c in cat_data.get("catalysts", []) if c.get("id") != catalyst_id
    ]
    if len(cat_data["catalysts"]) == original_len:
        raise ValueError(f"Catalyst ID {catalyst_id} not found for {ticker}.")
    _save_json(d / "catalysts.json", cat_data)


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
    """Append an update entry to updates.json and return it."""
    ticker = ticker.upper()
    _migrate_legacy(ticker)

    thesis = _load_thesis_json(ticker)
    if thesis is None:
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

    d = _thesis_dir(ticker)
    updates_data = _load_updates_json(ticker) or {"schema_version": "1.0", "ticker": ticker, "updates": []}
    updates_data["updates"].append(update)
    _save_json(d / "updates.json", updates_data)

    # Touch thesis updated_at
    thesis["updated_at"] = now
    _save_json(d / "thesis.json", thesis)

    return update


def add_health_check(
    ticker: str,
    *,
    objective_score: float,
    subjective_score: float,
    composite_score: float | None = None,
    assumption_scores: list | dict | None = None,
    key_observations: list | None = None,
    recommendation: str = "hold",
    recommendation_reasoning: str = "",
    check_date: str | None = None,
) -> dict:
    """Append a health-check snapshot to health_checks.json and return it."""
    ticker = ticker.upper()
    _migrate_legacy(ticker)

    thesis = _load_thesis_json(ticker)
    if thesis is None:
        raise ValueError(f"No thesis found for {ticker}. Create one first.")

    if composite_score is None:
        composite_score = objective_score * 0.6 + subjective_score * 0.4

    now = datetime.now(timezone.utc).isoformat()
    check: dict[str, Any] = {
        "check_date": check_date or now[:10],
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "composite_score": round(composite_score, 2),
        "assumption_scores": assumption_scores or [],
        "key_observations": key_observations or [],
        "recommendation": recommendation,
        "recommendation_reasoning": recommendation_reasoning,
        "created_at": now,
    }

    d = _thesis_dir(ticker)
    hc_data = _load_health_checks_json(ticker) or {"schema_version": "1.0", "ticker": ticker, "health_checks": []}
    hc_data["health_checks"].append(check)
    _save_json(d / "health_checks.json", hc_data)

    thesis["updated_at"] = now
    _save_json(d / "thesis.json", thesis)

    return check


def add_catalyst(
    ticker: str,
    *,
    event: str,
    expected_date: str,
    expected_impact: str = "neutral",
    affected_assumptions: list[int] | None = None,
    notes: str = "",
) -> dict:
    """Add a catalyst entry to catalysts.json and return it."""
    ticker = ticker.upper()
    _migrate_legacy(ticker)

    thesis = _load_thesis_json(ticker)
    if thesis is None:
        raise ValueError(f"No thesis found for {ticker}. Create one first.")

    now = datetime.now(timezone.utc).isoformat()
    d = _thesis_dir(ticker)
    cat_data = _load_catalysts_json(ticker) or {"schema_version": "1.0", "ticker": ticker, "catalysts": []}

    existing = cat_data.get("catalysts", [])
    next_id = max((c.get("id", 0) for c in existing), default=0) + 1

    catalyst: dict[str, Any] = {
        "id": next_id,
        "event": event,
        "expected_date": expected_date,
        "expected_impact": expected_impact,
        "affected_assumptions": affected_assumptions or [],
        "notes": notes,
        "status": "pending",
        "resolved_date": None,
        "outcome": None,
        "created_at": now,
    }

    cat_data["catalysts"].append(catalyst)
    _save_json(d / "catalysts.json", cat_data)
    return catalyst


def update_catalyst(
    ticker: str,
    catalyst_id: int,
    *,
    status: str = "resolved",
    outcome: str = "",
    resolved_date: str | None = None,
) -> dict:
    """Mark a catalyst as resolved/expired and return the updated entry."""
    ticker = ticker.upper()
    d = _thesis_dir(ticker)
    cat_data = _load_catalysts_json(ticker)
    if cat_data is None:
        raise ValueError(f"No catalysts file for {ticker}.")

    now = datetime.now(timezone.utc).isoformat()
    for cat in cat_data.get("catalysts", []):
        if cat.get("id") == catalyst_id:
            cat["status"] = status
            cat["outcome"] = outcome
            cat["resolved_date"] = resolved_date or now[:10]
            _save_json(d / "catalysts.json", cat_data)
            return cat

    raise ValueError(f"Catalyst ID {catalyst_id} not found for {ticker}.")


# ──────────────────────────────────────────────
# Markdown generation (used by page & scripts)
# ──────────────────────────────────────────────


def generate_thesis_markdown(ticker: str) -> str:
    """Return the full thesis as a Markdown string, or empty string if missing."""
    ticker = ticker.upper()
    _migrate_legacy(ticker)

    thesis = _load_thesis_json(ticker)
    if thesis is None:
        return ""

    updates_data = _load_updates_json(ticker) or {}
    health_data = _load_health_checks_json(ticker) or {}
    catalysts_data = _load_catalysts_json(ticker) or {}

    updates = updates_data.get("updates", [])
    health_checks = health_data.get("health_checks", [])
    catalysts = catalysts_data.get("catalysts", [])

    lines: list[str] = [
        f"# {ticker} Investment Thesis",
        "",
        f"**Created:** {str(thesis.get('created_at', ''))[:10]}  |  "
        f"**Status:** {thesis.get('status', 'active').title()}  |  "
        f"**Position:** {thesis.get('position', 'long').title()}",
        "",
    ]

    # Target / stop-loss
    target = thesis.get("target_price")
    stop = thesis.get("stop_loss_price")
    if target or stop:
        parts = []
        if target:
            parts.append(f"**Target:** ${target:.2f}")
        if stop:
            parts.append(f"**Stop-loss:** ${stop:.2f}")
        lines.append("  |  ".join(parts))
        lines.append("")

    lines += ["---", "", "## Core Thesis", "", thesis.get("core_thesis", ""), ""]

    # Buy Reasons
    lines.append("## Buy Reasons")
    lines.append("")
    for i, r in enumerate(thesis.get("buy_reasons", []), 1):
        if isinstance(r, str):
            lines.append(f"{i}. {r}")
        else:
            title = r.get("title", f"Reason {i}")
            desc = r.get("description", "")
            lines.append(f"{i}. **{title}**: {desc}")
    lines.append("")

    # Assumptions
    lines.append("## Prerequisite Assumptions")
    lines.append("")
    for a in thesis.get("assumptions", []):
        if isinstance(a, str):
            lines.append(f"- {a}")
        else:
            desc = a.get("description", str(a))
            weight = a.get("weight")
            w_str = f" [Weight: {int(weight * 100)}%]" if weight else ""
            lines.append(f"- {desc}{w_str}")
    lines.append("")

    # Sell Conditions
    lines.append("## Sell Conditions")
    lines.append("")
    for c in thesis.get("sell_conditions", []):
        lines.append(f"- {c}")
    lines.append("")

    # Risks
    lines.append("## Where I Might Be Wrong")
    lines.append("")
    for r in thesis.get("risk_factors", []):
        if isinstance(r, str):
            lines.append(f"- {r}")
        else:
            lines.append(f"- {r.get('description', str(r))}")
    lines.append("")

    # Catalyst Calendar
    pending = [c for c in catalysts if c.get("status") == "pending"]
    resolved = [c for c in catalysts if c.get("status") != "pending"]
    if catalysts:
        lines += ["---", "", "## Catalyst Calendar", ""]
        if pending:
            lines.append("| Date | Event | Expected Impact | Notes |")
            lines.append("|------|-------|-----------------|-------|")
            for c in pending:
                lines.append(
                    f"| {c.get('expected_date', '')} | {c.get('event', '')} | "
                    f"{c.get('expected_impact', '')} | {c.get('notes', '')} |"
                )
            lines.append("")
        if resolved:
            lines.append("### Resolved Catalysts")
            lines.append("")
            for c in resolved:
                lines.append(
                    f"- **{c.get('event', '')}** ({c.get('resolved_date', '')}) — "
                    f"{c.get('outcome', 'No outcome recorded')}"
                )
            lines.append("")

    # Update Log
    if updates:
        lines += ["---", "", "## Thesis Update Log", ""]
        for u in updates:
            lines.append(f"### {u.get('event_date', '')[:10]} | {u.get('event_title', '')}")
            lines.append(f"**Trigger:** {u.get('event_description', '')}")

            impacts = u.get("assumption_impacts", {})
            if impacts:
                lines.append("**Assumption Changes:**")
                assumptions = thesis.get("assumptions", [])
                for idx_str, impact in sorted(impacts.items()):
                    idx = int(idx_str)
                    a_desc = assumptions[idx].get("description", f"Assumption {idx+1}") if idx < len(assumptions) else f"Assumption {idx+1}"
                    lines.append(f"- {a_desc}: {impact.get('status', '—')} — {impact.get('explanation', '')}")

            lines.append(f"**Thesis Strength:** {u.get('strength_change', '').title()}")
            lines.append(f"**Action:** {u.get('action_taken', '').title()}")
            lines.append(f"**Conviction:** {u.get('conviction', '').title()}")
            if u.get("notes"):
                lines.append(f"**Notes:** {u['notes']}")
            lines.append("")

    # Health Check History
    if health_checks:
        lines += ["---", "", "## Health Check History", ""]
        for hc in reversed(health_checks):
            lines.append(f"### Health Check — {hc.get('check_date', '')[:10]}")
            lines.append("")

            # Assumption scorecard table
            scores = hc.get("assumption_scores", [])
            if scores and isinstance(scores, list):
                lines.append("| Assumption | Weight | Objective | Subjective | Combined | Status |")
                lines.append("|------------|--------|-----------|------------|----------|--------|")
                for s in scores:
                    desc = s.get("description", f"Assumption {s.get('assumption_idx', '?')}")
                    weight = s.get("weight")
                    w_str = f"{int(weight * 100)}%" if weight else "—"
                    lines.append(
                        f"| {desc} | {w_str} | "
                        f"{s.get('objective', 'N/A')} | {s.get('subjective', 'N/A')} | "
                        f"{s.get('combined', 'N/A')} | {s.get('status', '—')} |"
                    )
                lines.append("")

            lines.append(f"**Composite Score: {hc.get('composite_score', 0):.0f}/100**")
            lines.append(f"- Objective: {hc.get('objective_score', 0):.0f}/100")
            lines.append(f"- Subjective: {hc.get('subjective_score', 0):.0f}/100")
            lines.append("")

            obs = hc.get("key_observations", [])
            if obs:
                lines.append("**Key Observations:**")
                for o in obs:
                    lines.append(f"- {o}")
                lines.append("")

            lines.append(f"**Recommendation:** {hc.get('recommendation', '').title()}")
            lines.append(f"{hc.get('recommendation_reasoning', '')}")
            lines.append("")

    # Footer
    lines += [
        "---",
        "",
        f"*Report generated on {datetime.now(timezone.utc).strftime('%B %d, %Y')}.*",
    ]

    return "\n".join(lines)
