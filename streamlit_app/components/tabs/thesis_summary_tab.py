"""Thesis Summary tab — core thesis, assumptions, sell conditions, risks."""

from __future__ import annotations

import streamlit as st

from streamlit_app.components.loaders.thesis import ThesisPageData


def render_thesis_summary_tab(d: ThesisPageData) -> None:
    """Render the Thesis Summary tab.

    Args:
        d: Populated :class:`~streamlit_app.components.loaders.thesis.ThesisPageData`.
    """
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<div class="section-header">Core Thesis</div>', unsafe_allow_html=True)
        st.markdown(f"**{d.thesis['core_thesis']}**")

        st.markdown('<div class="section-header">Buy Reasons</div>', unsafe_allow_html=True)
        for i, reason in enumerate(d.thesis.get("buy_reasons", []), 1):
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
        for i, a in enumerate(d.assumptions, 1):
            desc = a.get("description", f"Assumption {i}")
            weight = a.get("weight", 0)
            w_pct = (
                f"{weight * 100:.0f}%"
                if isinstance(weight, (int, float)) and weight <= 1
                else f"{weight}%"
            )

            status_emoji = "—"
            if d.latest_health and d.latest_health.get("assumption_scores"):
                scores = d.latest_health["assumption_scores"]
                if i - 1 < len(scores):
                    status_emoji = scores[i - 1].get("status", "—")

            st.markdown(
                f"**{i}.** {desc} &nbsp; `Weight: {w_pct}` &nbsp; Status: {status_emoji}"
            )

    with col2:
        st.markdown(
            '<div class="section-header">Sell Conditions</div>', unsafe_allow_html=True
        )
        for cond in d.thesis.get("sell_conditions", []):
            st.markdown(f"- {cond}")

        st.markdown(
            '<div class="section-header">Where I Might Be Wrong</div>',
            unsafe_allow_html=True,
        )
        for risk in d.thesis.get("risk_factors", []):
            desc = risk.get("description", str(risk)) if isinstance(risk, dict) else str(risk)
            st.markdown(
                f'<div class="insight-card risk">'
                f'<div class="insight-desc">{desc}</div></div>',
                unsafe_allow_html=True,
            )

        if d.thesis.get("target_price"):
            st.metric("Target Price", f"${d.thesis['target_price']:.2f}")
        if d.thesis.get("stop_loss_price"):
            st.metric("Stop-Loss", f"${d.thesis['stop_loss_price']:.2f}")
