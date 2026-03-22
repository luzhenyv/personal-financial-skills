"""Financials tab — revenue, profitability, margins, balance sheet, cash flow."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from dashboard.components.styles import COLORS
from dashboard.components.loaders.company import CompanyPageData


def render_financials_tab(d: CompanyPageData) -> None:
    """Render the Financials tab content.

    Args:
        d: Populated :class:`~dashboard.components.data_loader.CompanyPageData`.
    """
    # ── Revenue & Profitability ───────────────────────────────────────────────
    if d.incomes:
        st.markdown('<div class="section-header">📈 Revenue & Profitability</div>', unsafe_allow_html=True)

        df_inc = pd.DataFrame(d.incomes).sort_values("fiscal_year")

        col1, col2 = st.columns(2)

        with col1:
            fig_rev = go.Figure()
            fig_rev.add_trace(go.Bar(
                x=df_inc["fiscal_year"].astype(str),
                y=df_inc["revenue"].apply(lambda x: x / 1e9 if x else 0),
                name="Revenue",
                marker_color=COLORS["primary"],
                text=df_inc["revenue"].apply(lambda x: f"${x / 1e9:.1f}B" if x else ""),
                textposition="outside",
            ))
            fig_rev.update_layout(
                title="Revenue ($B)",
                yaxis_title="USD Billions",
                xaxis_title="Fiscal Year",
                height=380,
                showlegend=False,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_rev, width="stretch")

        with col2:
            fig_income = go.Figure()
            for col_name, label, color in [
                ("gross_profit", "Gross Profit", COLORS["green"]),
                ("operating_income", "Operating Income", COLORS["amber"]),
                ("net_income", "Net Income", COLORS["red"]),
            ]:
                fig_income.add_trace(go.Bar(
                    x=df_inc["fiscal_year"].astype(str),
                    y=df_inc[col_name].apply(lambda x: x / 1e9 if x else 0),
                    name=label,
                    marker_color=color,
                ))
            fig_income.update_layout(
                title="Profitability ($B)",
                yaxis_title="USD Billions",
                xaxis_title="Fiscal Year",
                barmode="group",
                height=380,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_income, width="stretch")

        # EPS chart
        eps_data = [
            (str(inc["fiscal_year"]), inc.get("eps_diluted"))
            for inc in d.incomes
            if inc.get("eps_diluted")
        ]
        if eps_data:
            eps_df = pd.DataFrame(eps_data, columns=["Year", "EPS"]).sort_values("Year")
            fig_eps = go.Figure()
            fig_eps.add_trace(go.Bar(
                x=eps_df["Year"],
                y=eps_df["EPS"],
                marker_color=COLORS["purple"],
                text=eps_df["EPS"].apply(lambda x: f"${x:.2f}"),
                textposition="outside",
            ))
            fig_eps.update_layout(
                title="Earnings Per Share (Diluted)",
                yaxis_title="EPS ($)",
                height=300,
                showlegend=False,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_eps, width="stretch")

        with st.expander("📋 Income Statement Details"):
            display_df = df_inc.copy()
            dollar_cols = [
                "revenue", "cost_of_revenue", "gross_profit", "operating_income",
                "net_income", "research_and_development", "selling_general_admin",
            ]
            for c in dollar_cols:
                if c in display_df.columns:
                    display_df[c] = display_df[c].apply(
                        lambda x: f"${x / 1e9:,.1f}B" if x else "N/A"
                    )
            if "eps_diluted" in display_df.columns:
                display_df["eps_diluted"] = display_df["eps_diluted"].apply(
                    lambda x: f"${x:.2f}" if x else "N/A"
                )
            st.dataframe(display_df, width="stretch", hide_index=True)

    # ── Margin Analysis ───────────────────────────────────────────────────────
    if d.metrics:
        st.markdown('<div class="section-header">📈 Margin Trends</div>', unsafe_allow_html=True)

        df_metrics = pd.DataFrame(d.metrics).sort_values("fiscal_year")

        fig_margins = go.Figure()
        for margin_col, label, color in [
            ("gross_margin", "Gross Margin", COLORS["primary"]),
            ("operating_margin", "Operating Margin", COLORS["green"]),
            ("net_margin", "Net Margin", COLORS["amber"]),
            ("fcf_margin", "FCF Margin", COLORS["purple"]),
        ]:
            values = df_metrics[margin_col].apply(lambda x: x * 100 if x else None)
            fig_margins.add_trace(go.Scatter(
                x=df_metrics["fiscal_year"].astype(str),
                y=values,
                name=label,
                mode="lines+markers",
                line=dict(color=color, width=2.5),
            ))

        fig_margins.update_layout(
            yaxis_title="Percentage (%)",
            xaxis_title="Fiscal Year",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=30, b=40),
        )
        st.plotly_chart(fig_margins, width="stretch")

        col1, col2, col3 = st.columns(3)
        m = df_metrics.iloc[-1]
        with col1:
            roe = m.get("roe")
            st.metric("Return on Equity", f"{roe * 100:.1f}%" if roe else "N/A")
        with col2:
            roa = m.get("roa")
            st.metric("Return on Assets", f"{roa * 100:.1f}%" if roa else "N/A")
        with col3:
            roic = m.get("roic")
            st.metric("ROIC", f"{roic * 100:.1f}%" if roic else "N/A")

        with st.expander("📋 All Financial Metrics"):
            display_metrics = df_metrics.copy()
            pct_cols = [
                "gross_margin", "operating_margin", "net_margin", "fcf_margin",
                "revenue_growth", "roe", "roa", "roic",
            ]
            for c in pct_cols:
                if c in display_metrics.columns:
                    display_metrics[c] = display_metrics[c].apply(
                        lambda x: f"{x * 100:.1f}%" if x else "N/A"
                    )
            ratio_cols = ["current_ratio", "debt_to_equity", "pe_ratio", "ps_ratio", "ev_to_ebitda"]
            for c in ratio_cols:
                if c in display_metrics.columns:
                    display_metrics[c] = display_metrics[c].apply(
                        lambda x: f"{x:.1f}x" if x else "N/A"
                    )
            st.dataframe(display_metrics, width="stretch", hide_index=True)

    # ── Balance Sheet ─────────────────────────────────────────────────────────
    if d.balances:
        st.markdown('<div class="section-header">🏦 Balance Sheet</div>', unsafe_allow_html=True)

        df_bs = pd.DataFrame(d.balances).sort_values("fiscal_year")
        col1, col2 = st.columns(2)

        with col1:
            fig_bs = go.Figure()
            for series, label, color in [
                ("total_assets", "Total Assets", COLORS["primary"]),
                ("total_liabilities", "Total Liabilities", COLORS["red"]),
                ("total_stockholders_equity", "Equity", COLORS["green"]),
            ]:
                fig_bs.add_trace(go.Bar(
                    x=df_bs["fiscal_year"].astype(str),
                    y=df_bs[series].apply(lambda x: x / 1e9 if x else 0),
                    name=label,
                    marker_color=color,
                ))
            fig_bs.update_layout(
                title="Assets, Liabilities & Equity ($B)",
                barmode="group",
                height=380,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_bs, width="stretch")

        with col2:
            fig_cd = go.Figure()
            fig_cd.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["cash_and_equivalents"].apply(lambda x: x / 1e9 if x else 0),
                name="Cash",
                marker_color=COLORS["green"],
            ))
            fig_cd.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["long_term_debt"].apply(lambda x: x / 1e9 if x else 0),
                name="Long-term Debt",
                marker_color=COLORS["red"],
            ))
            fig_cd.update_layout(
                title="Cash vs Long-term Debt ($B)",
                barmode="group",
                height=380,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_cd, width="stretch")

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    if d.cash_flows:
        st.markdown('<div class="section-header">💰 Cash Flow</div>', unsafe_allow_html=True)

        df_cf = pd.DataFrame(d.cash_flows).sort_values("fiscal_year")

        fig_cf = go.Figure()
        fig_cf.add_trace(go.Bar(
            x=df_cf["fiscal_year"].astype(str),
            y=df_cf["cash_from_operations"].apply(lambda x: x / 1e9 if x else 0),
            name="Operating CF",
            marker_color=COLORS["primary"],
        ))
        fig_cf.add_trace(go.Bar(
            x=df_cf["fiscal_year"].astype(str),
            y=df_cf["capital_expenditure"].apply(lambda x: -abs(x) / 1e9 if x else 0),
            name="CapEx",
            marker_color=COLORS["red"],
        ))
        fig_cf.add_trace(go.Scatter(
            x=df_cf["fiscal_year"].astype(str),
            y=df_cf["free_cash_flow"].apply(lambda x: x / 1e9 if x else 0),
            name="Free Cash Flow",
            mode="lines+markers",
            line=dict(color=COLORS["green"], width=3),
        ))
        fig_cf.update_layout(
            title="Cash Flow ($B)",
            yaxis_title="USD Billions",
            height=400,
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_cf, width="stretch")
