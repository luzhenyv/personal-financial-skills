"""Company Profile page — comprehensive interactive tearsheet.

Layout (5 tabs):
  1. Overview   — Business summary, segments, geography, management
  2. Financials — Revenue, profitability, margins, balance sheet, cash flow
  3. Valuation  — DCF, sensitivity, scenarios, peer comps
  4. Research   — Competitive landscape, investment thesis, risks, opportunities
  5. Report     — Full markdown report rendered + download

All heavy rendering is delegated to the tab modules in
``streamlit_app/components/tabs/``. Re-usable helpers live in
``streamlit_app/components/``.
"""

import os
import sys

import streamlit as st

# Add project root to path for src.* imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import httpx

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

from streamlit_app.components.styles import inject_css
from streamlit_app.components.loaders.company import load_company_page_data
from streamlit_app.components.tabs.company_overview_tab import render_overview_tab
from streamlit_app.components.tabs.company_financials_tab import render_financials_tab
from streamlit_app.components.tabs.company_valuation_tab import render_valuation_tab
from streamlit_app.components.tabs.company_research_tab import render_research_tab
from streamlit_app.components.tabs.company_report_tab import render_report_tab

# ──────────────────────────────────────────────
# Page config & global styles
# ──────────────────────────────────────────────

st.set_page_config(page_title="Company Profile", page_icon="🏢", layout="wide")
inject_css()

# ──────────────────────────────────────────────
# Sidebar — company selection & valuation params
# ──────────────────────────────────────────────

st.title("🏢 Company Profile")

with st.sidebar:
    st.header("Company Selection")

    try:
        resp = httpx.get(f"{API_BASE_URL}/api/companies/", timeout=10)
        resp.raise_for_status()
        companies = resp.json()
    except Exception:
        companies = []

    ticker_options = [f"{c['ticker']} — {c['name']}" for c in companies]

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
                try:
                    resp = httpx.post(
                        f"{API_BASE_URL}/api/etl/ingest",
                        json={"ticker": new_ticker, "years": years},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    st.success(
                        f"✅ Ingestion started for {new_ticker.upper()} "
                        f"(ETL run #{result.get('etl_run_id', '?')})"
                    )
                except Exception as e:
                    st.error(f"Failed to trigger ingestion: {e}")
                st.rerun()

    st.markdown("---")
    st.subheader("Valuation Parameters")
    rev_growth = st.slider(
        "Revenue Growth (%)", 0, 80, 12,
        help=(
            "**Revenue Growth** is the projected annual rate at which the company's "
            "top-line revenue will expand over the DCF forecast period. "
            "Higher growth assumptions increase intrinsic value estimates. "
            "Typical ranges: mature companies 2–8%, high-growth companies 15–40%+."
        ),
    ) / 100.0
    wacc_param = st.slider(
        "WACC (%)", 5, 20, 10,
        help=(
            "**Weighted Average Cost of Capital (WACC)** is the blended rate used to "
            "discount future free cash flows back to present value. It reflects the "
            "required return of both equity and debt holders, weighted by their share "
            "of total capital. A higher WACC lowers the DCF valuation. "
            "Typical ranges: large-cap 7–10%, small/high-risk companies 12–18%+."
        ),
    ) / 100.0
    st.caption("Used for DCF & investment report")

# ──────────────────────────────────────────────
# Guard — no company selected
# ──────────────────────────────────────────────

if not ticker:
    st.info("👈 Select or add a company from the sidebar to get started.")
    st.stop()

# ──────────────────────────────────────────────
# Load all data
# ──────────────────────────────────────────────

d = load_company_page_data(ticker)
if d is None:
    st.error(f"Could not load data for **{ticker}**. Check the database.")
    st.stop()

# ──────────────────────────────────────────────
# Header — company banner + KPI row
# ──────────────────────────────────────────────

sector = d.yf_info.get("sector") or d.company.get("sector") or "N/A"
industry = d.yf_info.get("industry") or d.company.get("industry") or "N/A"
mkt_cap = d.yf_info.get("market_cap") or d.company.get("market_cap")
source_info = d.overview.get("source", "") if d.overview else ""

price_str = f"${d.current_price:,.2f}" if d.current_price else "N/A"
mktcap_str = f"${mkt_cap / 1e9:,.0f}B" if mkt_cap else "N/A"

st.markdown(
    f"""
    <div class="company-header">
        <h1>{d.company['name']} ({d.company['ticker']})</h1>
        <div class="subtitle">{sector} · {industry} · {source_info}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# KPI row
latest_rev = d.incomes[-1].get("revenue") if d.incomes else None
latest_gm = d.metrics[-1].get("gross_margin") if d.metrics else None
latest_rev_g = d.metrics[-1].get("revenue_growth") if d.metrics else None
pe_fwd = d.yf_info.get("pe_forward")
latest_ni = d.incomes[-1].get("net_income") if d.incomes else None

kpi_items = [
    ("Price", price_str),
    ("Market Cap", mktcap_str),
    ("Revenue (LTM)", f"${latest_rev / 1e9:,.1f}B" if latest_rev else "N/A"),
    ("Gross Margin", f"{latest_gm * 100:.1f}%" if latest_gm else "N/A"),
    ("Rev Growth", f"{latest_rev_g * 100:+.1f}%" if latest_rev_g else "N/A"),
    ("P/E Forward", f"{pe_fwd:.1f}x" if pe_fwd else "N/A"),
    ("Net Income", f"${latest_ni / 1e9:,.1f}B" if latest_ni else "N/A"),
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

tab_overview, tab_financials, tab_valuation, tab_research, tab_report = st.tabs(
    ["📋 Overview", "📊 Financials", "💰 Valuation", "🔬 Research", "📝 Report"]
)

with tab_overview:
    render_overview_tab(d)

with tab_financials:
    render_financials_tab(d)

with tab_valuation:
    render_valuation_tab(d, rev_growth=rev_growth, wacc=wacc_param)

with tab_research:
    render_research_tab(d)

with tab_report:
    render_report_tab(d, rev_growth=rev_growth, wacc=wacc_param)

# ──────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────

st.markdown("---")
st.caption(
    "Data: SEC EDGAR XBRL + 10-K/Q filings · Yahoo Finance · AI analysis | "
    "Not financial advice"
)
