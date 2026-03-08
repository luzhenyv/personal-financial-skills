"""Company Profile page — enhanced interactive tearsheet with valuation & investment report.

Provides:
  - Company header with live price
  - Revenue & income trend charts
  - Margin analysis (line chart)
  - Balance sheet & cash flow charts
  - Valuation summary (DCF, comps, scenarios)
  - Full investment report (rendered + download)
"""

import os
import sys

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.db.session import get_session
from src.db.models import Company
from src.analysis.company_profile import (
    generate_tearsheet,
    get_profile_data,
    load_company,
)

st.set_page_config(page_title="Company Profile", page_icon="🏢", layout="wide")

# ──────────────────────────────────────────────
# Custom CSS for a cleaner look
# ──────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.75rem;
        color: white;
        text-align: center;
    }
    .metric-card h3 { margin: 0; font-size: 0.85rem; opacity: 0.8; }
    .metric-card h1 { margin: 0; font-size: 1.8rem; }
    .rating-buy { color: #10b981; font-weight: bold; font-size: 1.5rem; }
    .rating-sell { color: #ef4444; font-weight: bold; font-size: 1.5rem; }
    .rating-hold { color: #f59e0b; font-weight: bold; font-size: 1.5rem; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 8px 8px 0 0;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏢 Company Profile")

# ──────────────────────────────────────────────
# Sidebar — Company Selection & Actions
# ──────────────────────────────────────────────

with st.sidebar:
    st.header("Company Selection")

    session = get_session()
    companies = session.query(Company).order_by(Company.ticker).all()
    ticker_options = [f"{c.ticker} — {c.name}" for c in companies]

    if ticker_options:
        selected = st.selectbox("Select Company", ticker_options)
        ticker = selected.split(" — ")[0] if selected else None
    else:
        ticker = None
        st.info("No companies loaded yet. Use the form below to add one.")

    st.markdown("---")
    st.subheader("Add New Company")

    with st.form("ingest_form"):
        new_ticker = st.text_input("Ticker Symbol", placeholder="NVDA")
        years = st.slider("Years of History", 1, 10, 5)
        include_prices = st.checkbox("Include Price Data", value=True)
        submitted = st.form_submit_button("📥 Ingest Data")

        if submitted and new_ticker:
            with st.spinner(f"Fetching data for {new_ticker.upper()}..."):
                from src.etl.pipeline import ingest_company

                result = ingest_company(
                    new_ticker, years=years, include_prices=include_prices
                )

                if result["errors"]:
                    st.warning(f"Completed with warnings: {result['errors']}")
                else:
                    st.success(
                        f"✅ Loaded {result['income_statements']} years of data for {new_ticker.upper()}"
                    )
                st.rerun()

    st.markdown("---")
    st.subheader("Valuation Parameters")
    rev_growth = st.slider("Revenue Growth (%)", 0, 40, 12) / 100.0
    wacc_param = st.slider("WACC (%)", 5, 20, 10) / 100.0
    st.caption("Used for DCF & investment report")

    session.close()

# ──────────────────────────────────────────────
# Guard — no ticker selected
# ──────────────────────────────────────────────

if not ticker:
    st.info("👈 Select or add a company from the sidebar to get started.")
    st.stop()

# ──────────────────────────────────────────────
# Load Data
# ──────────────────────────────────────────────

data = get_profile_data(ticker)
if "error" in data:
    st.error(data["error"])
    st.stop()

company = data["company"]
incomes = data["income_statements"]
balances = data["balance_sheets"]
cash_flows = data["cash_flows"]
metrics = data["metrics"]
price = data.get("latest_price")

# Fetch live price from yfinance
yf_price = None
yf_info = {}
try:
    from src.etl.yfinance_client import get_stock_info, get_current_price

    yf_price = get_current_price(ticker)
    yf_info = get_stock_info(ticker)
except Exception:
    pass

current_price = yf_price or (price["adjusted_close"] if price else None)

# ──────────────────────────────────────────────
# Header — Key Metrics Row
# ──────────────────────────────────────────────

st.markdown(f"## {company['name']} ({company['ticker']})")

if company.get("description"):
    with st.expander("Business Description", expanded=False):
        st.write(company["description"])

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    if current_price:
        st.metric("Price", f"${current_price:,.2f}")
    else:
        st.metric("Price", "N/A")

with col2:
    mkt_cap = yf_info.get("market_cap") or company.get("market_cap")
    if mkt_cap:
        st.metric("Market Cap", f"${mkt_cap / 1e9:,.1f}B")
    else:
        st.metric("Market Cap", "N/A")

with col3:
    sector = yf_info.get("sector") or company.get("sector") or "N/A"
    st.metric("Sector", sector[:18])

with col4:
    if incomes:
        latest_rev = incomes[0].get("revenue")
        if latest_rev:
            st.metric("Revenue (LTM)", f"${latest_rev / 1e9:,.1f}B")
        else:
            st.metric("Revenue", "N/A")
    else:
        st.metric("Revenue", "N/A")

with col5:
    if metrics:
        gm = metrics[0].get("gross_margin")
        st.metric("Gross Margin", f"{gm * 100:.1f}%" if gm else "N/A")
    else:
        st.metric("Gross Margin", "N/A")

with col6:
    if metrics:
        rev_g = metrics[0].get("revenue_growth")
        st.metric("Rev Growth", f"{rev_g * 100:+.1f}%" if rev_g else "N/A")
    else:
        st.metric("Rev Growth", "N/A")

st.markdown("---")

# ──────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────

tab_financials, tab_valuation, tab_report = st.tabs([
    "📊 Financials", "💰 Valuation", "📝 Investment Report"
])

# ══════════════════════════════════════════════
# Tab 1: Financials
# ══════════════════════════════════════════════

with tab_financials:

    if incomes:
        st.subheader("Revenue & Profitability")

        df_inc = pd.DataFrame(incomes).sort_values("fiscal_year")

        col1, col2 = st.columns(2)

        with col1:
            fig_rev = go.Figure()
            fig_rev.add_trace(go.Bar(
                x=df_inc["fiscal_year"].astype(str),
                y=df_inc["revenue"].apply(lambda x: x / 1e9 if x else 0),
                name="Revenue",
                marker_color="#2563eb",
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
            st.plotly_chart(fig_rev, use_container_width=True)

        with col2:
            fig_income = go.Figure()
            for col_name, label, color in [
                ("gross_profit", "Gross Profit", "#10b981"),
                ("operating_income", "Operating Income", "#f59e0b"),
                ("net_income", "Net Income", "#ef4444"),
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
            st.plotly_chart(fig_income, use_container_width=True)

        # EPS chart
        eps_data = [(str(inc["fiscal_year"]), inc.get("eps_diluted")) for inc in incomes if inc.get("eps_diluted")]
        if eps_data:
            eps_df = pd.DataFrame(eps_data, columns=["Year", "EPS"]).sort_values("Year")
            fig_eps = go.Figure()
            fig_eps.add_trace(go.Bar(
                x=eps_df["Year"],
                y=eps_df["EPS"],
                marker_color="#8b5cf6",
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
            st.plotly_chart(fig_eps, use_container_width=True)

        with st.expander("📋 Income Statement Details"):
            display_df = df_inc.copy()
            dollar_cols = ["revenue", "cost_of_revenue", "gross_profit", "operating_income",
                           "net_income", "research_and_development", "selling_general_admin"]
            for c in dollar_cols:
                if c in display_df.columns:
                    display_df[c] = display_df[c].apply(
                        lambda x: f"${x / 1e9:,.1f}B" if x else "N/A"
                    )
            if "eps_diluted" in display_df.columns:
                display_df["eps_diluted"] = display_df["eps_diluted"].apply(
                    lambda x: f"${x:.2f}" if x else "N/A"
                )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Margin Analysis ──
    if metrics:
        st.markdown("---")
        st.subheader("📈 Margin Trends")

        df_metrics = pd.DataFrame(metrics).sort_values("fiscal_year")

        fig_margins = go.Figure()
        for margin_col, label, color in [
            ("gross_margin", "Gross Margin", "#2563eb"),
            ("operating_margin", "Operating Margin", "#10b981"),
            ("net_margin", "Net Margin", "#f59e0b"),
            ("fcf_margin", "FCF Margin", "#8b5cf6"),
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
        st.plotly_chart(fig_margins, use_container_width=True)

        # Return metrics
        col1, col2, col3 = st.columns(3)
        m = df_metrics.iloc[-1]  # Most recent year

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
            pct_cols = ["gross_margin", "operating_margin", "net_margin", "fcf_margin",
                        "revenue_growth", "roe", "roa", "roic"]
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
            st.dataframe(display_metrics, use_container_width=True, hide_index=True)

    # ── Balance Sheet ──
    if balances:
        st.markdown("---")
        st.subheader("🏦 Balance Sheet")

        df_bs = pd.DataFrame(balances).sort_values("fiscal_year")

        col1, col2 = st.columns(2)

        with col1:
            fig_bs = go.Figure()
            fig_bs.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["total_assets"].apply(lambda x: x / 1e9 if x else 0),
                name="Total Assets",
                marker_color="#2563eb",
            ))
            fig_bs.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["total_liabilities"].apply(lambda x: x / 1e9 if x else 0),
                name="Total Liabilities",
                marker_color="#ef4444",
            ))
            fig_bs.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["total_stockholders_equity"].apply(lambda x: x / 1e9 if x else 0),
                name="Equity",
                marker_color="#10b981",
            ))
            fig_bs.update_layout(
                title="Assets, Liabilities & Equity ($B)",
                barmode="group",
                height=380,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_bs, use_container_width=True)

        with col2:
            fig_cd = go.Figure()
            fig_cd.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["cash_and_equivalents"].apply(lambda x: x / 1e9 if x else 0),
                name="Cash",
                marker_color="#10b981",
            ))
            fig_cd.add_trace(go.Bar(
                x=df_bs["fiscal_year"].astype(str),
                y=df_bs["long_term_debt"].apply(lambda x: x / 1e9 if x else 0),
                name="Long-term Debt",
                marker_color="#ef4444",
            ))
            fig_cd.update_layout(
                title="Cash vs Long-term Debt ($B)",
                barmode="group",
                height=380,
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(fig_cd, use_container_width=True)

    # ── Cash Flow ──
    if cash_flows:
        st.markdown("---")
        st.subheader("💰 Cash Flow")

        df_cf = pd.DataFrame(cash_flows).sort_values("fiscal_year")

        fig_cf = go.Figure()
        fig_cf.add_trace(go.Bar(
            x=df_cf["fiscal_year"].astype(str),
            y=df_cf["cash_from_operations"].apply(lambda x: x / 1e9 if x else 0),
            name="Operating CF",
            marker_color="#2563eb",
        ))
        fig_cf.add_trace(go.Bar(
            x=df_cf["fiscal_year"].astype(str),
            y=df_cf["capital_expenditure"].apply(lambda x: -abs(x) / 1e9 if x else 0),
            name="CapEx",
            marker_color="#ef4444",
        ))
        fig_cf.add_trace(go.Scatter(
            x=df_cf["fiscal_year"].astype(str),
            y=df_cf["free_cash_flow"].apply(lambda x: x / 1e9 if x else 0),
            name="Free Cash Flow",
            mode="lines+markers",
            line=dict(color="#10b981", width=3),
        ))
        fig_cf.update_layout(
            title="Cash Flow ($B)",
            yaxis_title="USD Billions",
            height=400,
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_cf, use_container_width=True)


# ══════════════════════════════════════════════
# Tab 2: Valuation
# ══════════════════════════════════════════════

with tab_valuation:

    st.subheader("💰 Valuation Analysis")
    st.caption("Adjust parameters in the sidebar. DCF + Scenario + Peer analysis.")

    with st.spinner("Running valuation models..."):
        try:
            from src.analysis.valuation import (
                simple_dcf,
                scenario_analysis,
                peer_comps,
                valuation_summary,
            )

            val = valuation_summary(ticker, revenue_growth=rev_growth, wacc=wacc_param)

            # ── Rating Banner ──
            if val.recommendation == "BUY":
                rating_color, rating_emoji = "#10b981", "🟢"
            elif val.recommendation == "SELL":
                rating_color, rating_emoji = "#ef4444", "🔴"
            else:
                rating_color, rating_emoji = "#f59e0b", "🟡"

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Rating", f"{rating_emoji} {val.recommendation}")
            with col2:
                st.metric("Target Price", f"${val.target_price:.2f}" if val.target_price else "N/A")
            with col3:
                st.metric("Current Price", f"${current_price:,.2f}" if current_price else "N/A")
            with col4:
                if val.upside_pct is not None:
                    st.metric("Upside/Downside", f"{val.upside_pct * 100:+.1f}%")
                else:
                    st.metric("Upside/Downside", "N/A")

            st.markdown("---")

            # ── DCF Results ──
            if val.dcf:
                dcf = val.dcf
                st.subheader("📐 DCF Model")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Enterprise Value", f"${dcf.enterprise_value / 1e9:.1f}B")
                with col2:
                    st.metric("Net Debt", f"${dcf.net_debt / 1e9:.1f}B")
                with col3:
                    st.metric("Equity Value", f"${dcf.equity_value / 1e9:.1f}B")
                with col4:
                    st.metric("Implied Price", f"${dcf.implied_price:.2f}")

                # Projected FCF chart
                fcf_years = list(range(1, dcf.projection_years + 1))
                fig_fcf = go.Figure()
                fig_fcf.add_trace(go.Bar(
                    x=[f"Year {y}" for y in fcf_years],
                    y=[f / 1e9 for f in dcf.projected_fcf],
                    marker_color="#2563eb",
                    text=[f"${f / 1e9:.1f}B" for f in dcf.projected_fcf],
                    textposition="outside",
                ))
                fig_fcf.update_layout(
                    title="Projected Free Cash Flow",
                    yaxis_title="USD Billions",
                    height=350,
                    showlegend=False,
                    margin=dict(t=40, b=40),
                )
                st.plotly_chart(fig_fcf, use_container_width=True)

                # DCF Assumptions
                with st.expander("DCF Assumptions", expanded=False):
                    assumptions_df = pd.DataFrame({
                        "Parameter": [
                            "Revenue Growth (Year 1)", "Operating Margin", "WACC",
                            "Terminal Growth", "Tax Rate", "CapEx % Revenue",
                            "Projection Years", "Shares Outstanding"
                        ],
                        "Value": [
                            f"{dcf.revenue_growth_rates[0] * 100:.1f}%",
                            f"{dcf.operating_margin * 100:.1f}%",
                            f"{dcf.wacc * 100:.1f}%",
                            f"{dcf.terminal_growth * 100:.1f}%",
                            f"{dcf.tax_rate * 100:.1f}%",
                            f"{dcf.capex_pct_revenue * 100:.1f}%",
                            str(dcf.projection_years),
                            f"{dcf.shares_outstanding / 1e6:,.0f}M",
                        ]
                    })
                    st.dataframe(assumptions_df, use_container_width=True, hide_index=True)

                # Sensitivity Heatmap
                if dcf.sensitivity:
                    st.subheader("🔥 Sensitivity Analysis")
                    st.caption("Implied share price at different WACC / Terminal Growth combinations")

                    waccs = sorted(set(s["wacc"] for s in dcf.sensitivity))
                    tgs = sorted(set(s["terminal_growth"] for s in dcf.sensitivity))
                    price_map = {(s["wacc"], s["terminal_growth"]): s["price"] for s in dcf.sensitivity}

                    z_data = []
                    for w in waccs:
                        row = []
                        for tg in tgs:
                            p = price_map.get((w, tg), None)
                            row.append(p if p else 0)
                        z_data.append(row)

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
                    st.plotly_chart(fig_heatmap, use_container_width=True)

            st.markdown("---")

            # ── Scenario Analysis ──
            if val.scenarios and val.scenarios.scenarios:
                st.subheader("📊 Scenario Analysis")

                scenarios = val.scenarios.scenarios
                scenario_names = []
                scenario_prices = []
                scenario_colors = []

                for name, label, color in [("bear", "🔴 Bear", "#ef4444"), ("base", "🟡 Base", "#f59e0b"), ("bull", "🟢 Bull", "#10b981")]:
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

                # Add current price line
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
                st.plotly_chart(fig_scenario, use_container_width=True)

                # Scenario details table
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
                                "Upside": f"{s['upside'] * 100:+.1f}%" if s.get('upside') is not None else "N/A",
                            })
                    st.dataframe(pd.DataFrame(scenario_rows), use_container_width=True, hide_index=True)

            # ── Peer Comps ──
            if val.comps and val.comps.peers:
                st.markdown("---")
                st.subheader("🏢 Peer Comparison")

                peer_rows = []
                # Target company first
                t = val.comps.target_metrics
                peer_rows.append({
                    "Ticker": f"⭐ {t['ticker']}",
                    "Name": (t.get("name") or "")[:25],
                    "P/E": f"{t['pe_ratio']:.1f}x" if t.get("pe_ratio") else "N/A",
                    "P/S": f"{t['ps_ratio']:.1f}x" if t.get("ps_ratio") else "N/A",
                    "EV/EBITDA": f"{t['ev_to_ebitda']:.1f}x" if t.get("ev_to_ebitda") else "N/A",
                    "Gross Margin": f"{t['gross_margin'] * 100:.1f}%" if t.get("gross_margin") else "N/A",
                    "Op Margin": f"{t['operating_margin'] * 100:.1f}%" if t.get("operating_margin") else "N/A",
                })
                for p in val.comps.peers:
                    peer_rows.append({
                        "Ticker": p["ticker"],
                        "Name": (p.get("name") or "")[:25],
                        "P/E": f"{p['pe_ratio']:.1f}x" if p.get("pe_ratio") else "N/A",
                        "P/S": f"{p['ps_ratio']:.1f}x" if p.get("ps_ratio") else "N/A",
                        "EV/EBITDA": f"{p['ev_to_ebitda']:.1f}x" if p.get("ev_to_ebitda") else "N/A",
                        "Gross Margin": f"{p['gross_margin'] * 100:.1f}%" if p.get("gross_margin") else "N/A",
                        "Op Margin": f"{p['operating_margin'] * 100:.1f}%" if p.get("operating_margin") else "N/A",
                    })

                st.dataframe(pd.DataFrame(peer_rows), use_container_width=True, hide_index=True)

                if val.comps.implied_pe or val.comps.implied_ps:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if val.comps.implied_pe:
                            st.metric("Implied (Peer P/E)", f"${val.comps.implied_pe:.2f}")
                    with col2:
                        if val.comps.implied_ps:
                            st.metric("Implied (Peer P/S)", f"${val.comps.implied_ps:.2f}")
                    with col3:
                        if val.comps.median_implied_price:
                            st.metric("Median Implied", f"${val.comps.median_implied_price:.2f}")

        except Exception as e:
            st.error(f"Valuation error: {e}")
            st.exception(e)


# ══════════════════════════════════════════════
# Tab 3: Investment Report
# ══════════════════════════════════════════════

with tab_report:

    st.subheader("📝 Investment Research Report")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Generates a comprehensive report for {ticker} using your sidebar parameters.")
    with col2:
        generate_btn = st.button("🔄 Generate Report", type="primary", use_container_width=True)

    if generate_btn:
        with st.spinner(f"Generating investment report for {ticker}..."):
            try:
                from src.analysis.investment_report import generate_investment_report

                report_md = generate_investment_report(
                    ticker,
                    revenue_growth=rev_growth,
                    wacc=wacc_param,
                    save=True,
                )

                st.session_state[f"report_{ticker}"] = report_md
                st.success(f"Report generated! ({len(report_md):,} characters)")
            except Exception as e:
                st.error(f"Report generation failed: {e}")
                st.exception(e)

    # Check for previously generated or cached report
    report_md = st.session_state.get(f"report_{ticker}")

    if not report_md:
        # Try loading from file
        from pathlib import Path

        report_path = Path("data/reports") / ticker / "investment_report.md"
        if report_path.exists():
            report_md = report_path.read_text()
            st.session_state[f"report_{ticker}"] = report_md
            st.info("Loaded previously generated report. Click 'Generate Report' to refresh.")

    if report_md:
        # Download buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                "⬇️ Download Report (.md)",
                data=report_md,
                file_name=f"{ticker}_investment_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col2:
            # Also offer tearsheet download
            try:
                tearsheet_md = generate_tearsheet(ticker)
                st.download_button(
                    "⬇️ Tearsheet (.md)",
                    data=tearsheet_md,
                    file_name=f"{ticker}_tearsheet.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            except Exception:
                pass

        st.markdown("---")

        # Render the full report
        st.markdown(report_md)

    else:
        st.info("Click **Generate Report** to create an investment research report.")
        st.markdown("""
        The report includes:
        - 🎯 Investment Rating (BUY / HOLD / SELL)
        - 📊 Financial Performance (Revenue, Income, EPS trends)
        - 🏦 Balance Sheet Highlights
        - 💰 Cash Flow Analysis
        - 📐 DCF Valuation with Sensitivity Table
        - 📊 Bull / Base / Bear Scenarios
        - ⚠️ Risks & Catalysts
        - 🎬 Action Plan with Position Sizing
        """)
