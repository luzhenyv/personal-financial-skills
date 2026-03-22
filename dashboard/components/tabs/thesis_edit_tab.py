"""Thesis Edit tab — forms for editing thesis text, catalyst notes.

Writes to data/artifacts/ (text files only, never PostgreSQL).
Triggers artifact commit after save.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import streamlit as st

from dashboard.components.loaders.thesis import ThesisPageData


def _artifact_commit(ticker: str, description: str) -> None:
    """Auto-commit artifact changes for the given ticker."""
    artifacts_dir = Path(__file__).resolve().parents[3] / "data" / "artifacts"
    if not (artifacts_dir / ".git").exists():
        return
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(artifacts_dir),
            capture_output=True,
            timeout=10,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(artifacts_dir),
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", f"[thesis-tracker] {ticker}: {description}"],
                cwd=str(artifacts_dir),
                capture_output=True,
                timeout=10,
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def render_thesis_edit_tab(d: ThesisPageData) -> None:
    """Render the Edit tab with forms for thesis text and catalyst notes."""
    from skills._lib.thesis_io import (
        update_thesis,
        add_catalyst,
        update_catalyst_notes,
        delete_catalyst,
    )

    _render_thesis_text_editor(d, update_thesis)
    st.markdown("---")
    _render_sell_conditions_editor(d, update_thesis)
    st.markdown("---")
    _render_catalyst_editor(d, add_catalyst, update_catalyst_notes, delete_catalyst)


# ── Thesis text editing ─────────────────────────────────────────────────────


def _render_thesis_text_editor(d: ThesisPageData, update_fn) -> None:
    st.markdown(
        '<div class="section-header">Edit Core Thesis</div>',
        unsafe_allow_html=True,
    )

    with st.form("edit_thesis_form", clear_on_submit=False):
        new_core = st.text_area(
            "Core Thesis",
            value=d.thesis.get("core_thesis", ""),
            height=150,
            help="Your central investment thesis statement.",
        )

        col1, col2 = st.columns(2)
        with col1:
            new_position = st.selectbox(
                "Position",
                ["long", "short"],
                index=0 if d.thesis.get("position", "long") == "long" else 1,
            )
            target_val = d.thesis.get("target_price")
            new_target = st.number_input(
                "Target Price ($)",
                value=float(target_val) if target_val else 0.0,
                min_value=0.0,
                step=1.0,
                format="%.2f",
            )
        with col2:
            new_status = st.selectbox(
                "Status",
                ["active", "closed", "paused"],
                index=["active", "closed", "paused"].index(
                    d.thesis.get("status", "active")
                ),
            )
            stop_val = d.thesis.get("stop_loss_price")
            new_stop = st.number_input(
                "Stop-Loss Price ($)",
                value=float(stop_val) if stop_val else 0.0,
                min_value=0.0,
                step=1.0,
                format="%.2f",
            )

        # Risk factors
        risk_factors = d.thesis.get("risk_factors", [])
        risk_text = "\n".join(
            r.get("description", str(r)) if isinstance(r, dict) else str(r)
            for r in risk_factors
        )
        new_risks = st.text_area(
            "Risk Factors (one per line)",
            value=risk_text,
            height=100,
            help="Key risks — one per line.",
        )

        submitted = st.form_submit_button("💾 Save Thesis Changes", type="primary")

        if submitted:
            updates = {}
            if new_core != d.thesis.get("core_thesis", ""):
                updates["core_thesis"] = new_core
            if new_position != d.thesis.get("position", "long"):
                updates["position"] = new_position
            if new_status != d.thesis.get("status", "active"):
                updates["status"] = new_status

            new_target_val = new_target if new_target > 0 else None
            if new_target_val != d.thesis.get("target_price"):
                updates["target_price"] = new_target_val

            new_stop_val = new_stop if new_stop > 0 else None
            if new_stop_val != d.thesis.get("stop_loss_price"):
                updates["stop_loss_price"] = new_stop_val

            parsed_risks = [
                {"description": line.strip()}
                for line in new_risks.strip().split("\n")
                if line.strip()
            ]
            if parsed_risks != risk_factors:
                updates["risk_factors"] = parsed_risks

            if updates:
                update_fn(d.ticker, **updates)
                _artifact_commit(d.ticker, "edited thesis text via dashboard")
                st.success("Thesis updated and committed.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("No changes detected.")


# ── Sell conditions editing ──────────────────────────────────────────────────


def _render_sell_conditions_editor(d: ThesisPageData, update_fn) -> None:
    st.markdown(
        '<div class="section-header">Edit Sell Conditions</div>',
        unsafe_allow_html=True,
    )

    sell_conditions = d.thesis.get("sell_conditions", [])
    sell_text = "\n".join(str(c) for c in sell_conditions)

    with st.form("edit_sell_conditions_form", clear_on_submit=False):
        new_sell = st.text_area(
            "Sell Conditions (one per line)",
            value=sell_text,
            height=120,
            help="Conditions that would trigger selling the position.",
        )
        submitted = st.form_submit_button("💾 Save Sell Conditions", type="primary")

        if submitted:
            parsed = [line.strip() for line in new_sell.strip().split("\n") if line.strip()]
            if parsed != sell_conditions:
                update_fn(d.ticker, sell_conditions=parsed)
                _artifact_commit(d.ticker, "edited sell conditions via dashboard")
                st.success("Sell conditions updated and committed.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("No changes detected.")


# ── Catalyst editing ─────────────────────────────────────────────────────────


def _render_catalyst_editor(d: ThesisPageData, add_fn, update_fn, delete_fn) -> None:
    st.markdown(
        '<div class="section-header">Catalyst Calendar</div>',
        unsafe_allow_html=True,
    )

    # Existing catalysts — editable
    pending = [c for c in d.catalysts if c.get("status") == "pending"]
    resolved = [c for c in d.catalysts if c.get("status") != "pending"]

    if pending:
        st.markdown("**Pending Catalysts**")
        for cat in pending:
            cid = cat["id"]
            with st.expander(f"#{cid}: {cat.get('event', 'Untitled')} — {cat.get('expected_date', '?')}"):
                with st.form(f"edit_catalyst_{cid}", clear_on_submit=False):
                    new_event = st.text_input("Event", value=cat.get("event", ""))
                    col1, col2 = st.columns(2)
                    with col1:
                        new_date = st.text_input(
                            "Expected Date",
                            value=cat.get("expected_date", ""),
                        )
                    with col2:
                        impact_options = ["positive", "negative", "neutral", "mixed"]
                        current_impact = cat.get("expected_impact", "neutral")
                        new_impact = st.selectbox(
                            "Expected Impact",
                            impact_options,
                            index=impact_options.index(current_impact)
                            if current_impact in impact_options
                            else 2,
                            key=f"impact_{cid}",
                        )
                    new_notes = st.text_area(
                        "Notes",
                        value=cat.get("notes", ""),
                        height=80,
                        key=f"notes_{cid}",
                    )

                    bcol1, bcol2 = st.columns([3, 1])
                    with bcol1:
                        save = st.form_submit_button("💾 Save", type="primary")
                    with bcol2:
                        remove = st.form_submit_button("🗑️ Delete")

                    if save:
                        update_fn(
                            d.ticker,
                            cid,
                            event=new_event,
                            expected_date=new_date,
                            expected_impact=new_impact,
                            notes=new_notes,
                        )
                        _artifact_commit(d.ticker, f"edited catalyst #{cid} via dashboard")
                        st.success(f"Catalyst #{cid} updated.")
                        st.cache_data.clear()
                        st.rerun()
                    if remove:
                        delete_fn(d.ticker, cid)
                        _artifact_commit(d.ticker, f"deleted catalyst #{cid} via dashboard")
                        st.success(f"Catalyst #{cid} deleted.")
                        st.cache_data.clear()
                        st.rerun()

    if resolved:
        with st.expander(f"Resolved Catalysts ({len(resolved)})"):
            for cat in resolved:
                st.markdown(
                    f"- **{cat.get('event', '')}** ({cat.get('resolved_date', '')}) — "
                    f"{cat.get('outcome', 'No outcome recorded')}"
                )

    # Add new catalyst
    st.markdown("**Add New Catalyst**")
    with st.form("add_catalyst_form", clear_on_submit=True):
        new_event = st.text_input("Event Name")
        col1, col2 = st.columns(2)
        with col1:
            new_date = st.text_input("Expected Date (YYYY-MM-DD or Q format)")
        with col2:
            new_impact = st.selectbox(
                "Expected Impact",
                ["positive", "negative", "neutral", "mixed"],
                index=0,
                key="new_catalyst_impact",
            )
        new_notes = st.text_area("Notes", height=60, key="new_catalyst_notes")
        submitted = st.form_submit_button("➕ Add Catalyst", type="primary")

        if submitted and new_event.strip():
            add_fn(
                d.ticker,
                event=new_event.strip(),
                expected_date=new_date.strip(),
                expected_impact=new_impact,
                notes=new_notes.strip(),
            )
            _artifact_commit(d.ticker, f"added catalyst via dashboard")
            st.success("Catalyst added and committed.")
            st.cache_data.clear()
            st.rerun()
