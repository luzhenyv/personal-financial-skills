"""Earnings Analysis page — view post-earnings analysis reports.

Layout:
  - Sidebar: ticker + quarter selection
  - Main: earnings report rendered from markdown artifact

All data read from ``data/artifacts/{ticker}/earnings/`` — never writes.

Run: streamlit run dashboard/app.py  (then navigate to this page)
"""

import json
import os
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from dashboard.components.styles import inject_css

# ── Locate artifacts root ────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_ROOT = _ROOT / "data" / "artifacts"

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Earnings Analysis", page_icon="📊", layout="wide")
inject_css()

st.title("📊 Earnings Analysis")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_earnings_tickers() -> list[str]:
    """Find all tickers with earnings artifacts."""
    tickers = []
    if ARTIFACTS_ROOT.exists():
        for d in sorted(ARTIFACTS_ROOT.iterdir()):
            if d.is_dir() and not d.name.startswith("_"):
                earnings_dir = d / "earnings"
                if earnings_dir.exists() and any(earnings_dir.glob("*_analysis.md")):
                    tickers.append(d.name)
    return tickers


def _find_quarters(ticker: str) -> list[str]:
    """Find all available earnings quarters for a ticker."""
    earnings_dir = ARTIFACTS_ROOT / ticker / "earnings"
    if not earnings_dir.exists():
        return []
    quarters = []
    for f in sorted(earnings_dir.glob("*_analysis.md")):
        # e.g. Q4_2024_analysis.md → Q4 FY2024
        name = f.stem.replace("_analysis", "")
        parts = name.split("_")
        if len(parts) == 2:
            quarters.append(f"{parts[0]} FY{parts[1]}")
    return quarters


def _load_report(ticker: str, quarter_label: str) -> str | None:
    """Load the markdown report for a ticker + quarter."""
    # "Q4 FY2024" → "Q4_2024"
    parts = quarter_label.replace("FY", "").split()
    if len(parts) != 2:
        return None
    filename = f"{parts[0]}_{parts[1]}_analysis.md"
    path = ARTIFACTS_ROOT / ticker / "earnings" / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _load_json(ticker: str, quarter_label: str) -> dict | None:
    """Load structured earnings JSON for a ticker + quarter."""
    parts = quarter_label.replace("FY", "").split()
    if len(parts) != 2:
        return None
    filename = f"{parts[0]}_{parts[1]}.json"
    path = ARTIFACTS_ROOT / ticker / "earnings" / filename
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Earnings Selection")

    tickers = _find_earnings_tickers()

    if not tickers:
        st.info(
            "No earnings analysis reports found.\n\n"
            "Generate one with:\n"
            "```\n"
            "uv run python skills/earnings-analysis/scripts/collect_earnings.py TICKER\n"
            "uv run python skills/earnings-analysis/scripts/generate_earnings_report.py TICKER\n"
            "```"
        )
        st.stop()

    ticker = st.selectbox("Company", tickers)
    quarters = _find_quarters(ticker)

    if not quarters:
        st.warning(f"No earnings reports for {ticker}")
        st.stop()

    quarter_label = st.selectbox("Quarter", quarters, index=len(quarters) - 1)

# ── Main content ─────────────────────────────────────────────────────────────

report_md = _load_report(ticker, quarter_label)
earnings_data = _load_json(ticker, quarter_label)

if report_md:
    st.markdown(report_md, unsafe_allow_html=False)
else:
    st.warning("Report markdown not found.")

# ── Structured data sidebar (optional detail) ───────────────────────────────

if earnings_data:
    with st.sidebar:
        st.divider()
        st.subheader("Structured Data")

        results = earnings_data.get("results", {})
        if results.get("revenue"):
            rev_b = float(results["revenue"]) / 1e9
            st.metric("Revenue", f"${rev_b:,.1f}B")
        if results.get("eps_diluted"):
            st.metric("EPS (Diluted)", f"${float(results['eps_diluted']):.2f}")
        if earnings_data.get("recommendation"):
            st.metric("Recommendation", earnings_data["recommendation"])

        st.caption(f"Analysis date: {earnings_data.get('analysis_date', 'N/A')}")
        st.caption(f"Freshness: {earnings_data.get('freshness_check', 'N/A')}")
