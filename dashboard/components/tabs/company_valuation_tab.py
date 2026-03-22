"""Valuation tab — DCF model, sensitivity heatmap, scenarios, peer comps."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.styles import COLORS
from dashboard.components.loaders.company import CompanyPageData

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def render_valuation_tab(d: CompanyPageData, rev_growth: float, wacc: float) -> None:
    """Render the Valuation tab content.

    Args:
        d: Populated :class:`~dashboard.components.data_loader.CompanyPageData`.
        rev_growth: Revenue growth rate (decimal, e.g. ``0.12``).
        wacc: Weighted average cost of capital (decimal, e.g. ``0.10``).
    """
    st.markdown('<div class="section-header">💰 Valuation Analysis</div>', unsafe_allow_html=True)
    st.caption("Adjust parameters in the sidebar. DCF + Scenario + Peer analysis.")

    with st.spinner("Running valuation models..."):
        try:
            ticker = d.company["ticker"]
            resp = httpx.get(
                f"{API_BASE_URL}/api/analysis/valuation/{ticker}",
                params={"revenue_growth": rev_growth, "wacc": wacc},
                timeout=60,
            )
            resp.raise_for_status()
            val = resp.json()

            # ── Rating Banner ──────────────────────────────────────────────────
            recommendation = val.get("recommendation", "HOLD")
            if recommendation == "BUY":
                rating_emoji = "🟢"
            elif recommendation == "SELL":
                rating_emoji = "🔴"
            else:
                rating_emoji = "🟡"

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Rating", f"{rating_emoji} {recommendation}")
            with col2:
                tp = val.get("target_price")
                st.metric("Target Price", f"${tp:.2f}" if tp else "N/A")
            with col3:
                st.metric(
                    "Current Price",
                    f"${d.current_price:,.2f}" if d.current_price else "N/A",
                )
            with col4:
                upside = val.get("upside_pct")
                if upside is not None:
                    st.metric("Upside/Downside", f"{upside * 100:+.1f}%")
                else:
                    st.metric("Upside/Downside", "N/A")

            st.markdown("---")

            # ── DCF Model ──────────────────────────────────────────────────────
            dcf = val.get("dcf")
            if dcf:
                _render_dcf_section(dcf, d.current_price)

            st.markdown("---")

            # ── Scenario Analysis ──────────────────────────────────────────────
            scenarios = val.get("scenarios")
            if scenarios and scenarios.get("scenarios"):
                _render_scenarios_section(scenarios, d.current_price)

            # ── Peer Comps ────────────────────────────────────────────────────
            comps = val.get("comps")
            if comps and comps.get("peers"):
                st.markdown("---")
                _render_comps_section(comps)

        except Exception as e:
            st.error(f"Valuation error: {e}")
            st.exception(e)


# ──────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────

def _render_dcf_section(dcf: dict, current_price: float | None) -> None:
    st.markdown('<div class="section-header">📐 DCF Model</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Enterprise Value", f"${dcf['enterprise_value'] / 1e9:.1f}B")
    with col2:
        st.metric("Net Debt", f"${dcf['net_debt'] / 1e9:.1f}B")
    with col3:
        st.metric("Equity Value", f"${dcf['equity_value'] / 1e9:.1f}B")
    with col4:
        st.metric("Implied Price", f"${dcf['implied_price']:.2f}")

    fcf_years = list(range(1, dcf["projection_years"] + 1))
    fig_fcf = go.Figure()
    fig_fcf.add_trace(go.Bar(
        x=[f"Year {y}" for y in fcf_years],
        y=[f / 1e9 for f in dcf["projected_fcf"]],
        marker_color=COLORS["primary"],
        text=[f"${f / 1e9:.1f}B" for f in dcf["projected_fcf"]],
        textposition="outside",
    ))
    fig_fcf.update_layout(
        title="Projected Free Cash Flow",
        yaxis_title="USD Billions",
        height=350,
        showlegend=False,
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig_fcf, width="stretch")

    with st.expander("DCF Assumptions", expanded=False):
        assumptions_df = pd.DataFrame({
            "Parameter": [
                "Revenue Growth (Year 1)", "Operating Margin", "WACC",
                "Terminal Growth", "Tax Rate", "CapEx % Revenue",
                "Projection Years", "Shares Outstanding",
            ],
            "Value": [
                f"{dcf['revenue_growth_rates'][0] * 100:.1f}%",
                f"{dcf['operating_margin'] * 100:.1f}%",
                f"{dcf['wacc'] * 100:.1f}%",
                f"{dcf['terminal_growth'] * 100:.1f}%",
                f"{dcf['tax_rate'] * 100:.1f}%",
                f"{dcf['capex_pct_revenue'] * 100:.1f}%",
                str(dcf["projection_years"]),
                f"{dcf['shares_outstanding'] / 1e6:,.0f}M",
            ],
        })
        st.dataframe(assumptions_df, width="stretch", hide_index=True)

    sensitivity = dcf.get("sensitivity")
    if sensitivity:
        st.markdown('<div class="section-header">🔥 Sensitivity Analysis</div>', unsafe_allow_html=True)
        st.caption("Implied price at different WACC / Terminal Growth combinations")

        waccs = sorted(set(s["wacc"] for s in sensitivity))
        tgs = sorted(set(s["terminal_growth"] for s in sensitivity))
        price_map = {(s["wacc"], s["terminal_growth"]): s["price"] for s in sensitivity}

        z_data = [
            [price_map.get((w, tg), 0) or 0 for tg in tgs]
            for w in waccs
        ]

        fig_heatmap = go.Figure(data=go.Heatmap(
            z=z_data,
            x=[f"{tg * 100:.1f}%" for tg in tgs],
            y=[f"{w * 100:.1f}%" for w in waccs],
            text=[[f"${v:.2f}" if v else "" for v in row] for row in z_data],
            texttemplate="%{text}",
            textfont={"size": 12},
            colorscale="RdYlGn",
            hovertemplate="WACC: %{y}<br>Terminal Growth: %{x}<br>Price: $%{z:.2f}<extra></extra>",
        ))
        fig_heatmap.update_layout(
            xaxis_title="Terminal Growth Rate",
            yaxis_title="WACC",
            height=350,
            margin=dict(t=20, b=40),
        )
        st.plotly_chart(fig_heatmap, width="stretch")


def _render_scenarios_section(scenarios_result: dict, current_price: float | None) -> None:
    st.markdown('<div class="section-header">📊 Scenario Analysis</div>', unsafe_allow_html=True)

    scenarios = scenarios_result["scenarios"]
    scenario_names, scenario_prices, scenario_colors = [], [], []

    for name, label, color in [
        ("bear", "🔴 Bear", COLORS["red"]),
        ("base", "🟡 Base", COLORS["amber"]),
        ("bull", "🟢 Bull", COLORS["green"]),
    ]:
        s = scenarios.get(name)
        if s:
            scenario_names.append(label)
            scenario_prices.append(s["implied_price"])
            scenario_colors.append(color)

    fig_scenario = go.Figure()
    fig_scenario.add_trace(go.Bar(
        x=scenario_names,
        y=scenario_prices,
        marker_color=scenario_colors,
        text=[f"${p:.2f}" for p in scenario_prices],
        textposition="outside",
        width=0.5,
    ))

    if current_price:
        fig_scenario.add_hline(
            y=current_price,
            line_dash="dash",
            line_color="white",
            annotation_text=f"Current: ${current_price:.2f}",
            annotation_position="top right",
        )

    fig_scenario.update_layout(
        title="Implied Price by Scenario",
        yaxis_title="Implied Price ($)",
        height=400,
        showlegend=False,
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig_scenario, width="stretch")

    with st.expander("Scenario Details"):
        scenario_rows = []
        for name in ["bull", "base", "bear"]:
            s = scenarios.get(name)
            if s:
                scenario_rows.append({
                    "Scenario": name.title(),
                    "Revenue Growth": f"{s['revenue_growth'] * 100:.0f}%",
                    "Op Margin": f"{s['operating_margin'] * 100:.1f}%",
                    "Terminal Growth": f"{s['terminal_growth'] * 100:.1f}%",
                    "Implied Price": f"${s['implied_price']:.2f}",
                    "Upside": (
                        f"{s['upside'] * 100:+.1f}%"
                        if s.get("upside") is not None
                        else "N/A"
                    ),
                })
        st.dataframe(pd.DataFrame(scenario_rows), width="stretch", hide_index=True)


def _render_comps_section(comps_result: dict) -> None:
    st.markdown('<div class="section-header">🏢 Peer Comparison</div>', unsafe_allow_html=True)

    peer_rows = []
    t = comps_result["target_metrics"]
    peer_rows.append({
        "Ticker": f"⭐ {t['ticker']}",
        "Name": (t.get("name") or "")[:25],
        "P/E": f"{t['pe_ratio']:.1f}x" if t.get("pe_ratio") else "N/A",
        "P/S": f"{t['ps_ratio']:.1f}x" if t.get("ps_ratio") else "N/A",
        "EV/EBITDA": f"{t['ev_to_ebitda']:.1f}x" if t.get("ev_to_ebitda") else "N/A",
        "Gross Margin": f"{t['gross_margin'] * 100:.1f}%" if t.get("gross_margin") else "N/A",
        "Op Margin": f"{t['operating_margin'] * 100:.1f}%" if t.get("operating_margin") else "N/A",
    })
    for p in comps_result["peers"]:
        peer_rows.append({
            "Ticker": p["ticker"],
            "Name": (p.get("name") or "")[:25],
            "P/E": f"{p['pe_ratio']:.1f}x" if p.get("pe_ratio") else "N/A",
            "P/S": f"{p['ps_ratio']:.1f}x" if p.get("ps_ratio") else "N/A",
            "EV/EBITDA": f"{p['ev_to_ebitda']:.1f}x" if p.get("ev_to_ebitda") else "N/A",
            "Gross Margin": f"{p['gross_margin'] * 100:.1f}%" if p.get("gross_margin") else "N/A",
            "Op Margin": f"{p['operating_margin'] * 100:.1f}%" if p.get("operating_margin") else "N/A",
        })

    st.dataframe(pd.DataFrame(peer_rows), width="stretch", hide_index=True)

    if comps_result.get("implied_pe") or comps_result.get("implied_ps"):
        col1, col2, col3 = st.columns(3)
        with col1:
            if comps_result.get("implied_pe"):
                st.metric("Implied (Peer P/E)", f"${comps_result['implied_pe']:.2f}")
        with col2:
            if comps_result.get("implied_ps"):
                st.metric("Implied (Peer P/S)", f"${comps_result['implied_ps']:.2f}")
        with col3:
            if comps_result.get("median_implied_price"):
                st.metric("Median Implied", f"${comps_result['median_implied_price']:.2f}")
