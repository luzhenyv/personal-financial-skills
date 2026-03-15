"""Shared formatting helpers and JSON/report file loaders.

Re-usable across multiple Streamlit pages.
"""

import json
from pathlib import Path


# ──────────────────────────────────────────────
# File loaders
# ──────────────────────────────────────────────

def load_json(ticker: str, filename: str, base: str = "data/artifacts") -> dict | None:
    """Load an artifact JSON file for a ticker.

    Args:
        ticker: Company ticker symbol (e.g. ``"NVDA"``).
        filename: JSON filename inside the artifacts folder (e.g. ``"company_overview.json"``).
        base: Base directory relative to the CWD. Defaults to ``"data/artifacts"``.

    Returns:
        Parsed dict, or ``None`` if the file does not exist.
    """
    path = Path(base) / ticker / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def load_report_md(ticker: str, filename: str = "company_profile.md") -> str | None:
    """Load a generated markdown report for a ticker.

    Args:
        ticker: Company ticker symbol.
        filename: Markdown filename inside ``data/reports/<ticker>/``.

    Returns:
        Report text, or ``None`` if the file does not exist.
    """
    path = Path("data/reports") / ticker / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


# ──────────────────────────────────────────────
# Numeric formatters
# ──────────────────────────────────────────────

def fmt_b(val) -> str:
    """Format a numeric value as a dollar-billion string (e.g. ``$12.3B``, ``$450M``)."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if abs(v) >= 1:
            return f"${v:,.1f}B"
        return f"${v * 1000:,.0f}M"
    except (TypeError, ValueError):
        return "N/A"


def fmt_pct(val) -> str:
    """Format a numeric value as a percentage string (e.g. ``"34.5%"``)."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.1f}%"
    except (TypeError, ValueError):
        return str(val)


def fmt_growth(val) -> str:
    """Format a growth value with sign and directional arrow (e.g. ``"+12.3%↑"``)."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        arrow = "↑" if v > 0 else "↓" if v < 0 else "→"
        return f"{v:+.1f}%{arrow}"
    except (TypeError, ValueError):
        return str(val)
