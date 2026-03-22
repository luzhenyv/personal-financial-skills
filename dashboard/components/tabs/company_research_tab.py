"""Research tab — competitive landscape, investment thesis, risk factors."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.styles import COLORS
from dashboard.components.utils import fmt_growth, fmt_pct
from dashboard.components.loaders.company import CompanyPageData


def render_research_tab(d: CompanyPageData) -> None:
    """Render the Research tab content.

    Args:
        d: Populated :class:`~dashboard.components.data_loader.CompanyPageData`.
    """
    if not d.has_profile:
        ticker = d.company['ticker']
        st.markdown(
            f"""
            <div class="no-profile-banner">
                <div class="no-profile-icon">🔬</div>
                <h3>No Research Data Available</h3>
                <p>
                    Competitive landscape, thesis, and risk analysis for <strong>{ticker}</strong>
                    haven't been generated yet.<br>
                    Run the <strong>company-profile skill</strong> to generate this content.
                </p>
                <p>Data will appear automatically once JSON files exist in<br>
                <span class="profile-cmd">data/artifacts/{ticker}/profile/</span></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Competitive Landscape ─────────────────────────────────────────────────
    if d.competitive:
        st.markdown('<div class="section-header">🏟️ Competitive Landscape</div>', unsafe_allow_html=True)

        moat = d.competitive.get("moat", "")
        positioning = d.competitive.get("competitive_positioning", "")
        if moat or positioning:
            positioning_html = f'<p style="margin-top:0.5rem">{positioning}</p>' if positioning else ""
            st.markdown(
                f"""
                <div class="moat-banner">
                    <h4>🛡️ Competitive Moat</h4>
                    <p>{moat}</p>
                    {positioning_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

        for comp in d.competitive.get("competitors", []):
            mktcap_val = comp.get("market_cap_b")
            comp_mktcap = f" — Mkt Cap: ${mktcap_val:.0f}B" if mktcap_val else ""
            share = comp.get("market_share_ai_accelerators") or comp.get("market_share", "")
            share_str = f" · Share: {share}" if share else ""
            advantage = comp.get(
                "competitive_advantage_vs_nvda",
                comp.get("competitive_advantage_vs_subject", "N/A"),
            )
            st.markdown(
                f"""
                <div class="competitor-card">
                    <div class="comp-name">{comp.get('name', 'N/A')} ({comp.get('ticker', '')}){comp_mktcap}</div>
                    <div class="comp-detail">
                        <strong>Products:</strong> {comp.get('products_competing', 'N/A')}<br>
                        <strong>Advantage:</strong> {advantage}{share_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Comps Table (from JSON file) ──────────────────────────────────────────
    if d.comps and d.comps.get("peers"):
        st.markdown('<div class="section-header">📊 Comparable Company Analysis</div>', unsafe_allow_html=True)

        ticker = d.company["ticker"]
        peers = d.comps["peers"]
        comps_rows = []
        for p in peers:
            is_target = p.get("ticker", "").upper() == ticker.upper()
            comps_rows.append({
                "Company": (
                    f"⭐ {p.get('name', p.get('ticker', ''))}"
                    if is_target
                    else (p.get("name") or p.get("ticker", ""))
                ),
                "Ticker": p.get("ticker", ""),
                "Mkt Cap ($B)": f"${p.get('market_cap_b', 0):,.0f}B" if p.get("market_cap_b") else "N/A",
                "Rev LTM ($B)": f"${p.get('revenue_ltm_b', 0):,.1f}B" if p.get("revenue_ltm_b") else "N/A",
                "Rev Growth": fmt_growth(p.get("rev_growth_pct")),
                "Gross Margin": fmt_pct(p.get("gross_margin_pct")),
                "Op Margin": fmt_pct(p.get("operating_margin_pct")),
                "P/E Fwd": f"{p['pe_forward']:.1f}x" if p.get("pe_forward") else "N/A",
                "EV/EBITDA": f"{p['ev_ebitda']:.1f}x" if p.get("ev_ebitda") else "N/A",
                "P/S": f"{p['ps_ratio']:.1f}x" if p.get("ps_ratio") else "N/A",
            })

        st.dataframe(pd.DataFrame(comps_rows), width="stretch", hide_index=True)

        summary = d.comps.get("peer_summary")
        if summary:
            st.caption("**Peer Medians** (excluding target)")
            sum_cols = st.columns(5)
            sum_items = [
                ("Rev Growth", summary.get("rev_growth_pct", {}).get("median"), "%"),
                ("Gross Margin", summary.get("gross_margin_pct", {}).get("median"), "%"),
                ("Op Margin", summary.get("operating_margin_pct", {}).get("median"), "%"),
                ("P/E Fwd", summary.get("pe_forward", {}).get("median"), "x"),
                ("EV/EBITDA", summary.get("ev_ebitda", {}).get("median"), "x"),
            ]
            for col, (label, val_data, suffix) in zip(sum_cols, sum_items):
                with col:
                    st.metric(label, f"{val_data:.1f}{suffix}" if val_data is not None else "N/A")

        # Visual comparison bar chart
        st.markdown("")
        chart_metric = st.selectbox(
            "Compare peers by:",
            [
                "gross_margin_pct", "operating_margin_pct", "rev_growth_pct",
                "pe_forward", "ev_ebitda", "ps_ratio", "market_cap_b",
            ],
            format_func=lambda x: {
                "gross_margin_pct": "Gross Margin (%)",
                "operating_margin_pct": "Operating Margin (%)",
                "rev_growth_pct": "Revenue Growth (%)",
                "pe_forward": "P/E Forward",
                "ev_ebitda": "EV/EBITDA",
                "ps_ratio": "P/S Ratio",
                "market_cap_b": "Market Cap ($B)",
            }.get(x, x),
        )

        chart_peers = [p for p in peers if p.get(chart_metric) is not None]
        if chart_peers:
            chart_peers_sorted = sorted(chart_peers, key=lambda p: p[chart_metric], reverse=True)
            names = [p.get("ticker", "") for p in chart_peers_sorted]
            vals = [p[chart_metric] for p in chart_peers_sorted]
            bar_colors = [COLORS["primary"] if t == ticker else COLORS["slate"] for t in names]

            display_name = {
                "gross_margin_pct": "Gross Margin (%)",
                "operating_margin_pct": "Operating Margin (%)",
                "rev_growth_pct": "Revenue Growth (%)",
                "pe_forward": "P/E Forward",
                "ev_ebitda": "EV/EBITDA",
                "ps_ratio": "P/S Ratio",
                "market_cap_b": "Market Cap ($B)",
            }.get(chart_metric, chart_metric)

            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(
                x=names,
                y=vals,
                marker_color=bar_colors,
                text=[f"{v:.1f}" for v in vals],
                textposition="outside",
            ))
            fig_comp.update_layout(
                title=f"Peer Comparison — {display_name}",
                yaxis_title=display_name,
                height=380,
                showlegend=False,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_comp, width="stretch")

    # ── Investment Thesis ─────────────────────────────────────────────────────
    if d.thesis:
        st.markdown('<div class="section-header">📈 Investment Thesis — Bull Case</div>', unsafe_allow_html=True)

        for i, item in enumerate(d.thesis.get("bull_case", []), 1):
            st.markdown(
                f"""
                <div class="insight-card bull">
                    <div class="insight-title">{i}. {item.get('title', '')}</div>
                    <div class="insight-desc">{item.get('description', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        opportunities = d.thesis.get("opportunities", [])
        if opportunities:
            st.markdown('<div class="section-header">🚀 Opportunities & Catalysts</div>', unsafe_allow_html=True)
            for item in opportunities:
                st.markdown(
                    f"""
                    <div class="insight-card opportunity">
                        <div class="insight-title">{item.get('title', '')}</div>
                        <div class="insight-desc">{item.get('description', '')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # ── Risk Factors ──────────────────────────────────────────────────────────
    if d.risks and d.risks.get("risks"):
        st.markdown('<div class="section-header">⚠️ Key Risks</div>', unsafe_allow_html=True)

        cat_colors = {
            "Company-Specific": "#ef4444",
            "Industry/Market": "#f59e0b",
            "Financial": "#8b5cf6",
            "Macro": "#64748b",
        }

        categories: dict[str, list] = {}
        for r in d.risks["risks"]:
            cat = r.get("category", "Other")
            categories.setdefault(cat, []).append(r)

        for cat, cat_risks in categories.items():
            st.markdown(f"**{cat}**")
            for r in cat_risks:
                color = cat_colors.get(cat, "#64748b")
                st.markdown(
                    f"""
                    <div class="insight-card risk" style="border-left-color: {color};">
                        <span class="insight-category">{cat}</span>
                        <div class="insight-title">{r.get('title', '')}</div>
                        <div class="insight-desc">{r.get('description', '')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
