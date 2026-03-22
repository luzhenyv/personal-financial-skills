"""Thesis Tracker page — manage and visualize investment theses.

Layout:
  - Sidebar: thesis selection
  - Main (3 tabs):
    - 📋 Thesis Summary   — core thesis, assumptions, sell conditions
    - 📝 Update Log       — chronological event log with strength indicators
    - 📊 Health Dashboard — score timeline, assumption heatmap

All rendering is delegated to the tab modules in
``dashboard/components/tabs/``.

Run: streamlit run dashboard/app.py  (then navigate to this page)
"""

import json
import os
import sys

import streamlit as st

# Add project root to path for src.* imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from dashboard.components.styles import inject_css, inject_thesis_css
from dashboard.components.loaders.thesis import load_thesis_page_data
from dashboard.components.tabs.thesis_summary_tab import render_thesis_summary_tab
from dashboard.components.tabs.thesis_updates_tab import render_thesis_updates_tab
from dashboard.components.tabs.thesis_health_tab import render_thesis_health_tab

# ──────────────────────────────────────────────
# Page config & styles
# ──────────────────────────────────────────────

st.set_page_config(page_title="Thesis Tracker", page_icon="🎯", layout="wide")
inject_css()
inject_thesis_css()

st.title("🎯 Thesis Tracker")

# ──────────────────────────────────────────────
# Sidebar — thesis selection
# ──────────────────────────────────────────────

with st.sidebar:
    st.header("Thesis Selection")

    @st.cache_data(ttl=30)
    def _load_all_theses():
        from skills._lib.thesis_io import get_all_active_theses
        return get_all_active_theses()

    all_theses = _load_all_theses()
    ticker_options = [f"{t['ticker']} — {t['position'].title()}" for t in all_theses]

    if ticker_options:
        selected = st.selectbox("Active Theses", ticker_options)
        ticker = selected.split(" — ")[0] if selected else None
    else:
        ticker = None
        st.info("No active theses found. Create one using the thesis-tracker skill.")

    st.markdown("---")
    st.caption("Create/update theses via the thesis-tracker skill commands.")

# ──────────────────────────────────────────────
# Guard — no thesis selected
# ──────────────────────────────────────────────

if not ticker:
    st.info("No active investment theses. Use the thesis-tracker skill to create one.")
    st.markdown(
        """
### Getting Started
Create a thesis using the skill commands:
- **Create:** "create thesis for NVDA"
- **Update:** "update thesis for NVDA"
- **Health Check:** "thesis health check NVDA"
"""
    )
    st.stop()

# ──────────────────────────────────────────────
# Load data
# ──────────────────────────────────────────────

@st.cache_data(ttl=30)
def _load_thesis(t: str):
    return load_thesis_page_data(t)


d = _load_thesis(ticker)
if d is None:
    st.error(f"Could not load thesis for **{ticker}**.")
    st.stop()

# ──────────────────────────────────────────────
# Header — banner + KPI row
# ──────────────────────────────────────────────

position_class = d.thesis["position"]
score_str, score_class = "—", "medium"
if d.latest_health:
    v = d.latest_health["composite_score"]
    score_str = f"{v:.0f}/100"
    score_class = "high" if v >= 70 else "medium" if v >= 40 else "low"

st.markdown(
    f"""
<div class="company-header">
    <h1>{ticker} Investment Thesis</h1>
    <div class="subtitle">
        <span class="thesis-position {position_class}">{d.thesis['position'].upper()}</span>
        &nbsp;·&nbsp; Created {d.thesis['created_at'][:10] if isinstance(d.thesis['created_at'], str) else d.thesis['created_at']}
        &nbsp;·&nbsp; {len(d.updates)} updates
        &nbsp;·&nbsp; {len(d.health_checks)} health checks
    </div>
</div>
""",
    unsafe_allow_html=True,
)

conviction_str = d.updates[0]["conviction"].title() if d.updates else "—"
last_action = d.updates[0]["action_taken"].title() if d.updates else "—"

kpi_items = [
    ("Health Score", score_str),
    ("Conviction", conviction_str),
    ("Last Action", last_action),
    ("Updates", str(len(d.updates))),
    ("Position", d.thesis["position"].title()),
    ("Status", d.thesis["status"].title()),
]
kpi_html = '<div class="kpi-row">' + "".join(
    f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
    f'<div class="kpi-value">{value}</div></div>'
    for label, value in kpi_items
) + "</div>"
st.markdown(kpi_html, unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────

tab_summary, tab_updates, tab_health = st.tabs(
    ["📋 Thesis Summary", "📝 Update Log", "📊 Health Dashboard"]
)

with tab_summary:
    render_thesis_summary_tab(d)

with tab_updates:
    render_thesis_updates_tab(d)

with tab_health:
    render_thesis_health_tab(d)

# ──────────────────────────────────────────────
# Downloads
# ──────────────────────────────────────────────

st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    from skills._lib.thesis_io import generate_thesis_markdown
    md_content = generate_thesis_markdown(ticker)
    if md_content:
        st.download_button(
            "📥 Download Thesis (Markdown)",
            data=md_content,
            file_name=f"thesis_{ticker}.md",
            mime="text/markdown",
        )

with col2:
    st.download_button(
        "📥 Download Thesis (JSON)",
        data=json.dumps(
            {"thesis": d.thesis, "updates": d.updates, "health_checks": d.health_checks},
            indent=2,
            default=str,
        ),
        file_name=f"thesis_{ticker}.json",
        mime="application/json",
    )

st.caption("Data: PostgreSQL thesis tracker | Not financial advice")
