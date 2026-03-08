"""Thesis Tracker page — manage and visualize investment theses.

Layout:
  - Sidebar: thesis selection, quick actions
  - Main: Active theses overview, detail view with tabs
    - Tab 1: Thesis Summary — core thesis, assumptions, sell conditions
    - Tab 2: Update Log — chronological event log with strength indicators
    - Tab 3: Health Dashboard — score timeline, assumption heatmap

Run: streamlit run streamlit_app/app.py  (then navigate to this page)
"""

import os
import sys

import streamlit as st
import plotly.graph_objects as go

# Add project root to path for src.* imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from streamlit_app.components.styles import inject_css, COLORS

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────

st.set_page_config(page_title="Thesis Tracker", page_icon="🎯", layout="wide")
inject_css()

# ──────────────────────────────────────────────
# Extra CSS for thesis tracker
# ──────────────────────────────────────────────

st.markdown(
    """
<style>
    .thesis-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
    }
    .thesis-card .thesis-ticker {
        font-weight: 700;
        font-size: 1.15rem;
        color: #1e293b;
    }
    .thesis-card .thesis-position {
        display: inline-block;
        font-size: 0.75rem;
        padding: 0.1rem 0.5rem;
        border-radius: 1rem;
        font-weight: 600;
    }
    .thesis-card .thesis-position.long {
        background: #dcfce7; color: #166534;
    }
    .thesis-card .thesis-position.short {
        background: #fef2f2; color: #991b1b;
    }
    .thesis-card .thesis-core {
        font-size: 0.88rem;
        color: #475569;
        margin-top: 0.35rem;
        line-height: 1.5;
    }
    .score-badge {
        display: inline-block;
        padding: 0.3rem 0.75rem;
        border-radius: 1rem;
        font-weight: 700;
        font-size: 1.1rem;
    }
    .score-badge.high { background: #dcfce7; color: #166534; }
    .score-badge.medium { background: #fef9c3; color: #854d0e; }
    .score-badge.low { background: #fef2f2; color: #991b1b; }
    .status-indicator {
        display: inline-block;
        width: 8px; height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .status-indicator.intact { background: #10b981; }
    .status-indicator.watch { background: #f59e0b; }
    .status-indicator.broken { background: #ef4444; }
    .update-entry {
        border-left: 3px solid #e2e8f0;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        margin-left: 0.5rem;
    }
    .update-entry.strengthened { border-left-color: #10b981; }
    .update-entry.weakened { border-left-color: #ef4444; }
    .update-entry.unchanged { border-left-color: #64748b; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🎯 Thesis Tracker")


# ──────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────

@st.cache_data(ttl=30)
def _load_all_theses():
    from src.analysis.thesis_tracker import get_all_active_theses
    return get_all_active_theses()


@st.cache_data(ttl=30)
def _load_thesis_detail(ticker: str):
    from src.analysis.thesis_tracker import get_thesis_detail
    return get_thesis_detail(ticker)


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────

with st.sidebar:
    st.header("Thesis Selection")

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
# Load thesis detail
# ──────────────────────────────────────────────

detail = _load_thesis_detail(ticker)
if detail is None:
    st.error(f"Could not load thesis for **{ticker}**.")
    st.stop()

thesis = detail["thesis"]
updates = detail["updates"]
health_checks = detail["health_checks"]
latest_health = detail.get("latest_health")


# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────

position_class = thesis["position"]
score_str = "—"
score_class = "medium"

if latest_health:
    score_val = latest_health["composite_score"]
    score_str = f"{score_val:.0f}/100"
    if score_val >= 70:
        score_class = "high"
    elif score_val >= 40:
        score_class = "medium"
    else:
        score_class = "low"

st.markdown(
    f"""
<div class="company-header">
    <h1>{ticker} Investment Thesis</h1>
    <div class="subtitle">
        <span class="thesis-position {position_class}">{thesis['position'].upper()}</span>
        &nbsp;·&nbsp; Created {thesis['created_at'][:10] if isinstance(thesis['created_at'], str) else thesis['created_at']}
        &nbsp;·&nbsp; {len(updates)} updates
        &nbsp;·&nbsp; {len(health_checks)} health checks
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# KPI row
conviction_str = updates[0]["conviction"].title() if updates else "—"
last_action = updates[0]["action_taken"].title() if updates else "—"

kpi_items = [
    ("Health Score", score_str),
    ("Conviction", conviction_str),
    ("Last Action", last_action),
    ("Updates", str(len(updates))),
    ("Position", thesis["position"].title()),
    ("Status", thesis["status"].title()),
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


# ────── Tab 1: Thesis Summary ──────

with tab_summary:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<div class="section-header">Core Thesis</div>', unsafe_allow_html=True)
        st.markdown(f"**{thesis['core_thesis']}**")

        st.markdown('<div class="section-header">Buy Reasons</div>', unsafe_allow_html=True)
        for i, reason in enumerate(thesis.get("buy_reasons", []), 1):
            title = reason.get("title", f"Reason {i}")
            desc = reason.get("description", "")
            st.markdown(
                f'<div class="insight-card bull">'
                f'<div class="insight-title">{i}. {title}</div>'
                f'<div class="insight-desc">{desc}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="section-header">Prerequisite Assumptions</div>',
            unsafe_allow_html=True,
        )
        assumptions = thesis.get("assumptions", [])
        for i, a in enumerate(assumptions, 1):
            desc = a.get("description", f"Assumption {i}")
            weight = a.get("weight", 0)
            w_pct = f"{weight * 100:.0f}%" if isinstance(weight, (int, float)) and weight <= 1 else f"{weight}%"

            # Determine status from latest health check
            status_emoji = "—"
            if latest_health and latest_health.get("assumption_scores"):
                scores = latest_health["assumption_scores"]
                if i - 1 < len(scores):
                    status_emoji = scores[i - 1].get("status", "—")

            st.markdown(
                f"**{i}.** {desc} &nbsp; `Weight: {w_pct}` &nbsp; Status: {status_emoji}"
            )

    with col2:
        st.markdown(
            '<div class="section-header">Sell Conditions</div>', unsafe_allow_html=True
        )
        for cond in thesis.get("sell_conditions", []):
            st.markdown(f"- {cond}")

        st.markdown(
            '<div class="section-header">Where I Might Be Wrong</div>',
            unsafe_allow_html=True,
        )
        for risk in thesis.get("risk_factors", []):
            desc = risk.get("description", str(risk)) if isinstance(risk, dict) else str(risk)
            st.markdown(
                f'<div class="insight-card risk">'
                f'<div class="insight-desc">{desc}</div></div>',
                unsafe_allow_html=True,
            )

        if thesis.get("target_price"):
            st.metric("Target Price", f"${thesis['target_price']:.2f}")
        if thesis.get("stop_loss_price"):
            st.metric("Stop-Loss", f"${thesis['stop_loss_price']:.2f}")


# ────── Tab 2: Update Log ──────

with tab_updates:
    if not updates:
        st.info("No thesis updates yet. Updates will appear here after events are logged.")
    else:
        st.markdown(
            f'<div class="section-header">{len(updates)} Thesis Updates</div>',
            unsafe_allow_html=True,
        )

        for u in updates:  # already ordered desc by event_date
            strength = u.get("strength_change", "unchanged")
            conviction = u.get("conviction", "medium")
            action = u.get("action_taken", "hold")

            strength_color = {
                "strengthened": COLORS["green"],
                "weakened": COLORS["red"],
                "unchanged": COLORS["slate"],
            }.get(strength, COLORS["slate"])

            conviction_badge = {
                "high": "🟢",
                "medium": "🟡",
                "low": "🔴",
            }.get(conviction, "⚪")

            st.markdown(
                f'<div class="update-entry {strength}">'
                f'<strong>{u["event_date"]}</strong> &nbsp;·&nbsp; '
                f'{u["event_title"]} &nbsp; {conviction_badge}<br>'
                f'<span style="font-size:0.85rem;color:#475569;">'
                f'{u.get("event_description", "")}</span><br>'
                f'<span style="font-size:0.82rem;">'
                f'Strength: <strong style="color:{strength_color}">{strength.title()}</strong>'
                f' &nbsp;·&nbsp; Action: <strong>{action.title()}</strong>'
                f' &nbsp;·&nbsp; Conviction: <strong>{conviction.title()}</strong>'
                f' &nbsp;·&nbsp; Source: {u.get("source", "manual")}'
                f"</span></div>",
                unsafe_allow_html=True,
            )

            # Show assumption impacts if present
            impacts = u.get("assumption_impacts", {})
            if impacts:
                with st.expander("Assumption impacts"):
                    for idx_str, impact in sorted(impacts.items()):
                        idx = int(idx_str)
                        a_desc = (
                            assumptions[idx]["description"]
                            if idx < len(assumptions)
                            else f"Assumption {idx + 1}"
                        )
                        st.markdown(
                            f"- **{a_desc}**: {impact.get('status', '—')} — "
                            f"{impact.get('explanation', '')}"
                        )


# ────── Tab 3: Health Dashboard ──────

with tab_health:
    if not health_checks:
        st.info(
            "No health checks recorded yet. Run a health check with: "
            '"thesis health check ' + ticker + '"'
        )
    else:
        # ── Score Timeline Chart ──
        st.markdown(
            '<div class="section-header">Health Score Timeline</div>',
            unsafe_allow_html=True,
        )

        dates = [h["check_date"] for h in health_checks]
        composites = [float(h["composite_score"]) if h["composite_score"] else None for h in health_checks]
        objectives = [float(h["objective_score"]) if h["objective_score"] else None for h in health_checks]
        subjectives = [float(h["subjective_score"]) if h["subjective_score"] else None for h in health_checks]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates, y=composites, mode="lines+markers",
                name="Composite", line=dict(color=COLORS["primary"], width=3),
                marker=dict(size=8),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=objectives, mode="lines+markers",
                name="Objective (60%)", line=dict(color=COLORS["green"], width=2, dash="dot"),
                marker=dict(size=6),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=subjectives, mode="lines+markers",
                name="Subjective (40%)", line=dict(color=COLORS["purple"], width=2, dash="dot"),
                marker=dict(size=6),
            )
        )

        # Reference lines
        fig.add_hline(y=70, line_dash="dash", line_color=COLORS["green"], opacity=0.4,
                       annotation_text="Strong (70)")
        fig.add_hline(y=40, line_dash="dash", line_color=COLORS["red"], opacity=0.4,
                       annotation_text="Weak (40)")

        fig.update_layout(
            yaxis=dict(title="Score (0-100)", range=[0, 105]),
            xaxis=dict(title="Date"),
            height=400,
            margin=dict(l=40, r=20, t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template="plotly_white",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Assumption Heatmap ──
        if assumptions and any(h.get("assumption_scores") for h in health_checks):
            st.markdown(
                '<div class="section-header">Assumption Score Trends</div>',
                unsafe_allow_html=True,
            )

            a_labels = [
                a.get("description", f"A{i+1}")[:40] for i, a in enumerate(assumptions)
            ]
            z_data = []
            x_dates = []

            for h in health_checks:
                scores = h.get("assumption_scores", [])
                row = []
                for i in range(len(assumptions)):
                    if i < len(scores):
                        row.append(float(scores[i].get("combined", 0)))
                    else:
                        row.append(0)
                z_data.append(row)
                x_dates.append(h["check_date"])

            # Transpose for heatmap (assumptions on y, dates on x)
            z_transposed = list(map(list, zip(*z_data))) if z_data else []

            if z_transposed:
                heatmap = go.Figure(
                    data=go.Heatmap(
                        z=z_transposed,
                        x=x_dates,
                        y=a_labels,
                        colorscale=[
                            [0, COLORS["red"]],
                            [0.4, COLORS["amber"]],
                            [0.7, COLORS["green"]],
                            [1, "#065f46"],
                        ],
                        zmin=0,
                        zmax=100,
                        text=[[f"{v:.0f}" for v in row] for row in z_transposed],
                        texttemplate="%{text}",
                        colorbar=dict(title="Score"),
                    )
                )
                heatmap.update_layout(
                    height=max(200, 60 * len(assumptions)),
                    margin=dict(l=200, r=20, t=20, b=40),
                    yaxis=dict(autorange="reversed"),
                    template="plotly_white",
                )
                st.plotly_chart(heatmap, use_container_width=True)

        # ── Latest Health Check Detail ──
        st.markdown(
            '<div class="section-header">Latest Health Check</div>',
            unsafe_allow_html=True,
        )

        lh = health_checks[-1]
        col1, col2, col3 = st.columns(3)

        composite_val = float(lh["composite_score"]) if lh["composite_score"] else 0
        obj_val = float(lh["objective_score"]) if lh["objective_score"] else 0
        subj_val = float(lh["subjective_score"]) if lh["subjective_score"] else 0

        with col1:
            badge_class = "high" if composite_val >= 70 else "medium" if composite_val >= 40 else "low"
            st.markdown(
                f'<div style="text-align:center">'
                f'<div style="font-size:0.8rem;color:#64748b;text-transform:uppercase">Composite</div>'
                f'<div class="score-badge {badge_class}">{composite_val:.0f}/100</div></div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f'<div style="text-align:center">'
                f'<div style="font-size:0.8rem;color:#64748b;text-transform:uppercase">Objective</div>'
                f'<div style="font-size:1.3rem;font-weight:700;color:{COLORS["green"]}">{obj_val:.0f}</div></div>',
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                f'<div style="text-align:center">'
                f'<div style="font-size:0.8rem;color:#64748b;text-transform:uppercase">Subjective</div>'
                f'<div style="font-size:1.3rem;font-weight:700;color:{COLORS["purple"]}">{subj_val:.0f}</div></div>',
                unsafe_allow_html=True,
            )

        if lh.get("recommendation"):
            st.markdown(f"**Recommendation:** {lh['recommendation'].title()}")
            if lh.get("recommendation_reasoning"):
                st.markdown(lh["recommendation_reasoning"])

        observations = lh.get("key_observations", [])
        if observations:
            st.markdown("**Key Observations:**")
            for obs in observations:
                st.markdown(f"- {obs}")

        # ── Assumption detail table ──
        a_scores = lh.get("assumption_scores", [])
        if a_scores and assumptions:
            st.markdown("")
            import pandas as pd

            rows = []
            for i, a in enumerate(assumptions):
                s = a_scores[i] if i < len(a_scores) else {}
                rows.append({
                    "Assumption": a.get("description", f"A{i+1}")[:50],
                    "Weight": f"{a.get('weight', 0) * 100:.0f}%",
                    "Objective": s.get("objective", "—"),
                    "Subjective": s.get("subjective", "—"),
                    "Combined": s.get("combined", "—"),
                    "Status": s.get("status", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ──────────────────────────────────────────────
# Download
# ──────────────────────────────────────────────

st.markdown("---")

col_dl1, col_dl2 = st.columns(2)

with col_dl1:
    from src.analysis.thesis_tracker import generate_thesis_markdown

    md_content = generate_thesis_markdown(ticker)
    if md_content:
        st.download_button(
            "📥 Download Thesis (Markdown)",
            data=md_content,
            file_name=f"thesis_{ticker}.md",
            mime="text/markdown",
        )

with col_dl2:
    import json as json_mod

    st.download_button(
        "📥 Download Thesis (JSON)",
        data=json_mod.dumps(detail, indent=2, default=str),
        file_name=f"thesis_{ticker}.json",
        mime="application/json",
    )

st.caption("Data: PostgreSQL thesis tracker | Not financial advice")
