"""Thesis Health Dashboard tab — score timeline and assumption heatmap."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.styles import COLORS
from dashboard.components.loaders.thesis import ThesisPageData


def render_thesis_health_tab(d: ThesisPageData) -> None:
    """Render the Health Dashboard tab.

    Args:
        d: Populated :class:`~dashboard.components.loaders.thesis.ThesisPageData`.
    """
    if not d.health_checks:
        st.info(
            "No health checks recorded yet. Run a health check with: "
            f'"thesis health check {d.ticker}"'
        )
        return

    _render_score_timeline(d)
    _render_assumption_heatmap(d)
    _render_latest_health_detail(d)


# ── Private helpers ────────────────────────────────────────────────────────────

def _render_score_timeline(d: ThesisPageData) -> None:
    st.markdown(
        '<div class="section-header">Health Score Timeline</div>',
        unsafe_allow_html=True,
    )

    dates = [h["check_date"] for h in d.health_checks]
    composites = [float(h["composite_score"]) if h["composite_score"] else None for h in d.health_checks]
    objectives = [float(h["objective_score"]) if h["objective_score"] else None for h in d.health_checks]
    subjectives = [float(h["subjective_score"]) if h["subjective_score"] else None for h in d.health_checks]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=composites, mode="lines+markers",
        name="Composite", line=dict(color=COLORS["primary"], width=3),
        marker=dict(size=8),
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=objectives, mode="lines+markers",
        name="Objective (60%)", line=dict(color=COLORS["green"], width=2, dash="dot"),
        marker=dict(size=6),
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=subjectives, mode="lines+markers",
        name="Subjective (40%)", line=dict(color=COLORS["purple"], width=2, dash="dot"),
        marker=dict(size=6),
    ))
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


def _render_assumption_heatmap(d: ThesisPageData) -> None:
    if not d.assumptions or not any(h.get("assumption_scores") for h in d.health_checks):
        return

    st.markdown(
        '<div class="section-header">Assumption Score Trends</div>',
        unsafe_allow_html=True,
    )

    a_labels = [a.get("description", f"A{i+1}")[:40] for i, a in enumerate(d.assumptions)]
    z_data, x_dates = [], []

    for h in d.health_checks:
        scores = h.get("assumption_scores", [])
        row = [
            float(scores[i].get("combined", 0)) if i < len(scores) else 0
            for i in range(len(d.assumptions))
        ]
        z_data.append(row)
        x_dates.append(h["check_date"])

    z_transposed = list(map(list, zip(*z_data))) if z_data else []
    if not z_transposed:
        return

    heatmap = go.Figure(data=go.Heatmap(
        z=z_transposed, x=x_dates, y=a_labels,
        colorscale=[
            [0, COLORS["red"]], [0.4, COLORS["amber"]],
            [0.7, COLORS["green"]], [1, "#065f46"],
        ],
        zmin=0, zmax=100,
        text=[[f"{v:.0f}" for v in row] for row in z_transposed],
        texttemplate="%{text}",
        colorbar=dict(title="Score"),
    ))
    heatmap.update_layout(
        height=max(200, 60 * len(d.assumptions)),
        margin=dict(l=200, r=20, t=20, b=40),
        yaxis=dict(autorange="reversed"),
        template="plotly_white",
    )
    st.plotly_chart(heatmap, use_container_width=True)


def _render_latest_health_detail(d: ThesisPageData) -> None:
    st.markdown(
        '<div class="section-header">Latest Health Check</div>',
        unsafe_allow_html=True,
    )

    lh = d.health_checks[-1]
    composite_val = float(lh["composite_score"]) if lh["composite_score"] else 0
    obj_val = float(lh["objective_score"]) if lh["objective_score"] else 0
    subj_val = float(lh["subjective_score"]) if lh["subjective_score"] else 0

    col1, col2, col3 = st.columns(3)
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

    a_scores = lh.get("assumption_scores", [])
    if a_scores and d.assumptions:
        rows = []
        for i, a in enumerate(d.assumptions):
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
