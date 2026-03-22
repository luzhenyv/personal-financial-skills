"""Shared formatting helpers and JSON/report file loaders.

Re-usable across multiple Streamlit pages.
"""

import json
import re
from pathlib import Path


# ──────────────────────────────────────────────
# Markdown helpers
# ──────────────────────────────────────────────

def escape_currency_dollars(text: str) -> str:
    """Escape currency dollar signs so Streamlit doesn't render them as LaTeX.

    Rules:
    - Already-escaped \\$ → kept as-is
    - LaTeX display math $$...$$ → kept as-is
    - LaTeX inline math $...$ (where char after $ is NOT a digit/comma/period) → kept as-is
    - Currency $ (followed by digit, comma, or period) → escaped to \\$
    """
    result = []
    i = 0
    n = len(text)

    while i < n:
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            result.append('\\$')
            i += 2
            continue

        if text[i] == '$':
            # Display math: $$...$$
            if i + 1 < n and text[i + 1] == '$':
                end = text.find('$$', i + 2)
                if end != -1:
                    result.append(text[i:end + 2])
                    i = end + 2
                    continue

            # Inline math: $...$ where next char is NOT a digit/comma/period
            if i + 1 < n and not re.match(r'[\d.,]', text[i + 1]):
                end = text.find('$', i + 1)
                if end != -1:
                    result.append(text[i:end + 1])
                    i = end + 1
                    continue

            # Currency dollar sign — escape it
            result.append('\\$')
            i += 1
            continue

        result.append(text[i])
        i += 1

    return ''.join(result)


# ──────────────────────────────────────────────
# File loaders
# ──────────────────────────────────────────────

def load_json(ticker: str, filename: str, base: str = "data/artifacts", subdir: str = "") -> dict | None:
    """Load an artifact JSON file for a ticker.

    Args:
        ticker: Company ticker symbol (e.g. ``"NVDA"``).
        filename: JSON filename inside the artifacts folder (e.g. ``"company_overview.json"``).
        base: Base directory relative to the CWD. Defaults to ``"data/artifacts"``.
        subdir: Optional subdirectory under ``<base>/<ticker>/`` (e.g. ``"profile"``).

    Returns:
        Parsed dict, or ``None`` if the file does not exist.
    """
    path = Path(base) / ticker / subdir / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def load_report_md(ticker: str, filename: str = "company_profile.md") -> str | None:
    """Load a generated markdown report for a ticker.

    Args:
        ticker: Company ticker symbol.
        filename: Markdown filename. Checks ``data/artifacts/<ticker>/profile/`` first,
            then falls back to ``data/reports/<ticker>/``.

    Returns:
        Report text, or ``None`` if the file does not exist.
    """
    profile_path = Path("data/artifacts") / ticker / "profile" / filename
    if profile_path.exists():
        return profile_path.read_text(encoding="utf-8")
    legacy_path = Path("data/reports") / ticker / filename
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")
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
