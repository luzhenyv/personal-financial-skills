"""Mini Bloomberg — Streamlit Dashboard.

Main entry point for the interactive dashboard.
Run: streamlit run streamlit_app/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Mini Bloomberg",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Mini Bloomberg")
st.markdown("*Personal Investor Toolkit — SEC EDGAR + PostgreSQL + Streamlit*")

st.markdown("---")

st.markdown(
    """
## Welcome

Personal investor toolkit for researching US public companies.
Powered by SEC EDGAR filings, Python-based valuation models, and interactive Plotly charts.

### Available Pages

| Page | Description |
|------|-------------|
| **🏢 Company Profile** | Financials, margins, valuation, and investment report — all in one page |
| **🎯 Thesis Tracker** | Investment thesis management — create, update, and health-check theses |

### 3-Tab Company Profile

The Company Profile page has three tabs:

| Tab | What It Shows |
|-----|---------------|
| **📊 Financials** | Revenue trends, profitability, margins, balance sheet, cash flow |
| **💰 Valuation** | DCF model, sensitivity heatmap, scenario analysis, peer comps |
| **📝 Investment Report** | Full research report with rating, thesis, risks, and action plan |

### Quick Start

1. **Add a company** — sidebar on Company Profile page (e.g. NVDA)
2. **Explore financials** — revenue charts, margin trends, balance sheet
3. **Run valuation** — adjust growth & WACC sliders, see DCF + scenarios
4. **Generate report** — one-click investment research report with download

### Architecture

```
SEC EDGAR XBRL → PostgreSQL → Python Analysis → Streamlit + Plotly
                                  │
                     ├── company_profile.py (tearsheet)
                     ├── valuation.py (DCF, comps, scenarios)
                     ├── investment_report.py (full report)
                     ├── thesis_tracker.py (thesis management)
                     └── yfinance_client.py (live prices)
```

### Data Sources

- **SEC EDGAR**: 10-K annual filings (income statement, balance sheet, cash flow)
- **Yahoo Finance**: Live prices, sector/industry, peer discovery
- **Computed**: Margins, returns (ROE/ROA/ROIC), growth rates, valuation ratios
"""
)

st.markdown("---")
st.caption("Data source: SEC EDGAR XBRL | Not financial advice")
