"""Overview tab — business summary, segments, geography, management team."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from streamlit_app.components.styles import COLORS
from streamlit_app.components.utils import fmt_growth
from streamlit_app.components.loaders.company import CompanyPageData


def render_overview_tab(d: CompanyPageData) -> None:
    """Render the Overview tab content.

    Args:
        d: Populated :class:`~streamlit_app.components.data_loader.CompanyPageData`.
    """
    if not d.has_profile:
        st.info(
            f"No AI-generated profile data found for **{d.company['ticker']}**. "
            "Run the company-profile skill (Tasks 1–2) to generate overview, management, risks, and thesis data. "
            f"The data will appear here automatically once the JSON files exist in "
            f"`data/processed/{d.company['ticker']}/`."
        )
        if d.company.get("description"):
            st.markdown('<div class="section-header">📄 Business Description</div>', unsafe_allow_html=True)
            st.write(d.company["description"])
        return

    # ── Business Summary ──────────────────────────────────────────────────────
    if d.overview:
        st.markdown('<div class="section-header">📄 Business Summary</div>', unsafe_allow_html=True)

        desc = d.overview.get("description", "")
        if len(desc) > 1500:
            cut = desc[:1500].rfind(". ")
            desc = desc[: cut + 1] if cut > 500 else desc[:1500] + "..."
        st.markdown(desc)

        if d.overview.get("business_overview"):
            with st.expander("Read more about the business"):
                st.markdown(d.overview["business_overview"])

        st.markdown("")

        col_left, col_right = st.columns(2)
        with col_left:
            if d.overview.get("revenue_model"):
                st.markdown("**Revenue Model**")
                st.caption(d.overview["revenue_model"])
        with col_right:
            if d.overview.get("customers"):
                st.markdown("**Key Customers**")
                st.caption(d.overview["customers"])

        products = d.overview.get("products", [])
        if products:
            st.markdown("**Key Products & Platforms**")
            tags_html = "".join(f'<span class="product-tag">{p}</span>' for p in products)
            st.markdown(tags_html, unsafe_allow_html=True)

    # ── Revenue Segments ─────────────────────────────────────────────────────
    seg_source = d.segments or d.overview
    segments = seg_source.get("segments", []) if seg_source else []
    geo_data = None
    if d.segments and d.segments.get("geographic_revenue_fy2026"):
        geo_data = d.segments["geographic_revenue_fy2026"]
    elif d.overview and d.overview.get("geographic_revenue"):
        geo_data = d.overview["geographic_revenue"]

    if segments or geo_data:
        st.markdown('<div class="section-header">📊 Revenue Breakdown</div>', unsafe_allow_html=True)
        col_seg, col_geo = st.columns(2)

        with col_seg:
            if segments:
                seg_names, seg_revs = [], []
                for s in segments:
                    seg_names.append(s.get("name", ""))
                    rev = (
                        s.get("revenue_fy_b")
                        or s.get("revenue_fy2026_b")
                        or s.get("revenue_b")
                        or 0
                    )
                    seg_revs.append(float(rev))

                if any(r > 0 for r in seg_revs):
                    fig_seg = go.Figure(data=[go.Pie(
                        labels=seg_names,
                        values=seg_revs,
                        hole=0.45,
                        marker_colors=[
                            COLORS["primary"], COLORS["green"], COLORS["amber"],
                            COLORS["purple"], COLORS["cyan"], COLORS["rose"],
                        ],
                        textinfo="label+percent",
                        textposition="outside",
                        pull=[0.03] * len(seg_names),
                    )])
                    fig_seg.update_layout(
                        title=dict(text="Revenue by Segment", font=dict(size=14)),
                        height=340,
                        margin=dict(t=50, b=20, l=20, r=20),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_seg, width="stretch")

                    seg_rows = []
                    for s in segments:
                        rev = (
                            s.get("revenue_fy_b")
                            or s.get("revenue_fy2026_b")
                            or s.get("revenue_b")
                            or 0
                        )
                        growth = s.get("yoy_growth_pct")
                        seg_rows.append({
                            "Segment": s.get("name", ""),
                            "Revenue": f"${float(rev):.1f}B" if rev else "N/A",
                            "YoY Growth": fmt_growth(growth),
                            "Description": (s.get("description", ""))[:80],
                        })
                    st.dataframe(pd.DataFrame(seg_rows), width="stretch", hide_index=True)

        with col_geo:
            if geo_data:
                geo_labels, geo_values = [], []
                for region, info in geo_data.items():
                    geo_labels.append(region.replace("_", " ").replace("incl HK", "(incl. HK)"))
                    if isinstance(info, dict):
                        geo_values.append(info.get("revenue_b", info.get("pct", 0)))
                    else:
                        try:
                            geo_values.append(float(str(info).replace("~", "").replace("%", "")))
                        except (ValueError, TypeError):
                            geo_values.append(0)

                fig_geo = go.Figure(data=[go.Pie(
                    labels=geo_labels,
                    values=geo_values,
                    hole=0.45,
                    marker_colors=[
                        COLORS["primary"], COLORS["amber"], COLORS["red"],
                        COLORS["purple"], COLORS["cyan"], COLORS["green"],
                    ],
                    textinfo="label+percent",
                    textposition="outside",
                    pull=[0.03] * len(geo_labels),
                )])
                fig_geo.update_layout(
                    title=dict(text="Revenue by Geography", font=dict(size=14)),
                    height=340,
                    margin=dict(t=50, b=20, l=20, r=20),
                    showlegend=False,
                )
                st.plotly_chart(fig_geo, width="stretch")

    # ── Management Team ───────────────────────────────────────────────────────
    if d.management and d.management.get("executives"):
        st.markdown('<div class="section-header">👥 Management Team</div>', unsafe_allow_html=True)

        execs = d.management["executives"]
        for i in range(0, len(execs), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(execs):
                    e = execs[idx]
                    tenure = e.get("tenure_years", "?")
                    age = e.get("age", "?")
                    ownership = e.get("insider_ownership_pct", "N/A")
                    prior = ", ".join(e.get("prior_roles", [])[:2]) if e.get("prior_roles") else ""
                    bio = e.get("accomplishments", "")

                    with col:
                        prior_html = f'<div class="exec-bio">Prior: {prior}</div>' if prior else ""
                        bio_html = f'<div class="exec-bio">{bio}</div>' if bio else ""
                        st.markdown(
                            f"""
                            <div class="exec-card">
                                <div class="exec-name">{e.get('name', 'N/A')}</div>
                                <div class="exec-title">{e.get('title', '')}</div>
                                <div class="exec-meta">Age {age} · {tenure}yr tenure · Ownership: {ownership}</div>
                                {prior_html}
                                {bio_html}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

        board = d.management.get("board", {})
        if board:
            st.caption(
                f"**Board:** {board.get('size', '?')} directors, "
                f"{board.get('independent_directors', '?')} independent. "
                f"{d.management.get('governance_notes', '')}"
            )
