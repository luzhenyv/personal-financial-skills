"""Thesis Updates tab — chronological event log with strength indicators."""

from __future__ import annotations

import streamlit as st

from dashboard.components.styles import COLORS
from dashboard.components.loaders.thesis import ThesisPageData


def render_thesis_updates_tab(d: ThesisPageData) -> None:
    """Render the Update Log tab.

    Args:
        d: Populated :class:`~dashboard.components.loaders.thesis.ThesisPageData`.
    """
    if not d.updates:
        st.info("No thesis updates yet. Updates will appear here after events are logged.")
        return

    st.markdown(
        f'<div class="section-header">{len(d.updates)} Thesis Updates</div>',
        unsafe_allow_html=True,
    )

    for u in d.updates:  # already ordered desc by event_date
        strength = u.get("strength_change", "unchanged")
        conviction = u.get("conviction", "medium")
        action = u.get("action_taken", "hold")

        strength_color = {
            "strengthened": COLORS["green"],
            "weakened": COLORS["red"],
            "unchanged": COLORS["slate"],
        }.get(strength, COLORS["slate"])

        conviction_badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conviction, "⚪")

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

        impacts = u.get("assumption_impacts", {})
        if impacts:
            with st.expander("Assumption impacts"):
                for idx_str, impact in sorted(impacts.items()):
                    idx = int(idx_str)
                    a_desc = (
                        d.assumptions[idx]["description"]
                        if idx < len(d.assumptions)
                        else f"Assumption {idx + 1}"
                    )
                    st.markdown(
                        f"- **{a_desc}**: {impact.get('status', '—')} — "
                        f"{impact.get('explanation', '')}"
                    )
