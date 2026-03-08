"""Shared color palette and CSS styles for the Streamlit app."""

import streamlit as st

# ──────────────────────────────────────────────
# Shared color palette
# ──────────────────────────────────────────────

COLORS = {
    "primary": "#2563eb",
    "green": "#10b981",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "purple": "#8b5cf6",
    "cyan": "#06b6d4",
    "indigo": "#6366f1",
    "rose": "#f43f5e",
    "slate": "#64748b",
}

# ──────────────────────────────────────────────
# Global CSS block
# ──────────────────────────────────────────────

_CSS = """
<style>
    /* ── Header card ── */
    .company-header {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        padding: 1.5rem 2rem;
        border-radius: 1rem;
        color: #f1f5f9;
        margin-bottom: 1rem;
    }
    .company-header h1 { margin: 0 0 0.25rem 0; font-size: 2rem; color: #f8fafc; }
    .company-header .subtitle { opacity: 0.75; font-size: 0.95rem; }

    /* ── KPI metric cards ── */
    .kpi-row { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .kpi-card {
        flex: 1 1 140px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 0.75rem 1rem;
        text-align: center;
        min-width: 120px;
    }
    .kpi-card .kpi-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem; }
    .kpi-card .kpi-value { font-size: 1.35rem; font-weight: 700; color: #1e293b; }

    /* ── Section headers ── */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e293b;
        border-bottom: 2px solid #2563eb;
        padding-bottom: 0.35rem;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
    }

    /* ── Exec card ── */
    .exec-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1rem 1.25rem;
        margin-bottom: 0.5rem;
    }
    .exec-card .exec-name { font-weight: 700; font-size: 1.05rem; color: #1e293b; }
    .exec-card .exec-title { font-size: 0.85rem; color: #2563eb; margin-bottom: 0.35rem; }
    .exec-card .exec-meta { font-size: 0.8rem; color: #64748b; }
    .exec-card .exec-bio { font-size: 0.85rem; color: #475569; margin-top: 0.35rem; line-height: 1.5; }

    /* ── Risk / thesis cards ── */
    .insight-card {
        background: #f8fafc;
        border-left: 4px solid #2563eb;
        border-radius: 0 0.5rem 0.5rem 0;
        padding: 0.85rem 1rem;
        margin-bottom: 0.5rem;
    }
    .insight-card.risk { border-left-color: #ef4444; }
    .insight-card.opportunity { border-left-color: #10b981; }
    .insight-card.bull { border-left-color: #2563eb; }
    .insight-card .insight-title { font-weight: 600; font-size: 0.95rem; color: #1e293b; }
    .insight-card .insight-category {
        display: inline-block;
        font-size: 0.7rem;
        padding: 0.1rem 0.5rem;
        border-radius: 1rem;
        background: #e2e8f0;
        color: #475569;
        margin-bottom: 0.3rem;
    }
    .insight-card .insight-desc { font-size: 0.85rem; color: #475569; line-height: 1.55; }

    /* ── Competitor card ── */
    .competitor-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 0.85rem 1rem;
        margin-bottom: 0.5rem;
    }
    .competitor-card .comp-name { font-weight: 600; font-size: 0.95rem; color: #1e293b; }
    .competitor-card .comp-ticker { font-size: 0.8rem; color: #2563eb; }
    .competitor-card .comp-detail { font-size: 0.82rem; color: #475569; line-height: 1.5; margin-top: 0.3rem; }

    /* ── Moat banner ── */
    .moat-banner {
        background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.75rem;
        margin-bottom: 1rem;
    }
    .moat-banner h4 { margin: 0 0 0.3rem 0; font-size: 1rem; }
    .moat-banner p { margin: 0; font-size: 0.9rem; opacity: 0.9; line-height: 1.5; }

    /* ── Tabs styling ── */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 20px; border-radius: 8px 8px 0 0; font-weight: 500; }

    /* ── Remove default metric styling padding ── */
    div[data-testid="stMetricValue"] { font-size: 1.15rem; }

    /* ── Product tag ── */
    .product-tag {
        display: inline-block;
        background: #eff6ff;
        color: #1d4ed8;
        border: 1px solid #bfdbfe;
        padding: 0.25rem 0.65rem;
        border-radius: 1rem;
        font-size: 0.8rem;
        margin: 0.15rem 0.15rem;
    }
</style>
"""


def inject_css() -> None:
    """Inject global CSS into the Streamlit page. Call once per page."""
    st.markdown(_CSS, unsafe_allow_html=True)


_THESIS_CSS = """
<style>
    .thesis-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
    }
    .thesis-card .thesis-ticker { font-weight: 700; font-size: 1.15rem; color: #1e293b; }
    .thesis-card .thesis-position {
        display: inline-block;
        font-size: 0.75rem;
        padding: 0.1rem 0.5rem;
        border-radius: 1rem;
        font-weight: 600;
    }
    .thesis-card .thesis-position.long  { background: #dcfce7; color: #166534; }
    .thesis-card .thesis-position.short { background: #fef2f2; color: #991b1b; }
    .thesis-card .thesis-core { font-size: 0.88rem; color: #475569; margin-top: 0.35rem; line-height: 1.5; }
    .score-badge {
        display: inline-block;
        padding: 0.3rem 0.75rem;
        border-radius: 1rem;
        font-weight: 700;
        font-size: 1.1rem;
    }
    .score-badge.high   { background: #dcfce7; color: #166534; }
    .score-badge.medium { background: #fef9c3; color: #854d0e; }
    .score-badge.low    { background: #fef2f2; color: #991b1b; }
    .status-indicator {
        display: inline-block;
        width: 8px; height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .status-indicator.intact { background: #10b981; }
    .status-indicator.watch  { background: #f59e0b; }
    .status-indicator.broken { background: #ef4444; }
    .update-entry {
        border-left: 3px solid #e2e8f0;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        margin-left: 0.5rem;
    }
    .update-entry.strengthened { border-left-color: #10b981; }
    .update-entry.weakened     { border-left-color: #ef4444; }
    .update-entry.unchanged    { border-left-color: #64748b; }
</style>
"""


def inject_thesis_css() -> None:
    """Inject thesis-tracker-specific CSS. Call once on the Thesis Tracker page."""
    st.markdown(_THESIS_CSS, unsafe_allow_html=True)
