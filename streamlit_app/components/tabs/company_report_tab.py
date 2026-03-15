"""Report tab — full markdown report display, generate, and download."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from streamlit_app.components.loaders.company import CompanyPageData


def render_report_tab(d: CompanyPageData, rev_growth: float, wacc: float) -> None:
    """Render the Report tab content.

    Args:
        d: Populated :class:`~streamlit_app.components.data_loader.CompanyPageData`.
        rev_growth: Revenue growth rate used for report generation.
        wacc: WACC used for report generation.
    """
    from src.analysis.company_profile import generate_tearsheet

    ticker = d.company["ticker"]

    st.markdown('<div class="section-header">📝 Company Profile Report</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Full research report for {ticker}, sourced from SEC filings and analysis.")
    with col2:
        generate_btn = st.button("🔄 Generate Report", type="primary", width="stretch")

    if generate_btn:
        with st.spinner(f"Generating investment report for {ticker}..."):
            try:
                from src.analysis.investment_report import generate_investment_report

                new_md = generate_investment_report(
                    ticker,
                    revenue_growth=rev_growth,
                    wacc=wacc,
                    save=True,
                )
                st.session_state[f"report_{ticker}"] = new_md
                st.success(f"Report generated! ({len(new_md):,} characters)")
            except Exception as e:
                st.error(f"Report generation failed: {e}")
                st.exception(e)

    # Resolve which markdown to display (session → saved investment report → company profile)
    display_report: str | None = st.session_state.get(f"report_{ticker}")

    if not display_report:
        inv_profile = Path("data/artifacts") / ticker / "profile" / "investment_report.md"
        inv_legacy = Path("data/reports") / ticker / "investment_report.md"
        inv_path = inv_profile if inv_profile.exists() else inv_legacy
        if inv_path.exists():
            display_report = inv_path.read_text(encoding="utf-8")
            st.session_state[f"report_{ticker}"] = display_report

    if not display_report:
        display_report = d.report_md

    if display_report:
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            st.download_button(
                "⬇️ Download Report (.md)",
                data=display_report,
                file_name=f"{ticker}_company_profile.md",
                mime="text/markdown",
                width="stretch",
            )
        with col2:
            try:
                tearsheet_md = generate_tearsheet(ticker)
                st.download_button(
                    "⬇️ Tearsheet (.md)",
                    data=tearsheet_md,
                    file_name=f"{ticker}_tearsheet.md",
                    mime="text/markdown",
                    width="stretch",
                )
            except Exception:
                pass

        st.markdown("---")
        st.markdown(display_report)

    else:
        st.info("No report found. Click **Generate Report** to create one, or run the company-profile skill first.")
        st.markdown("""
The company profile report includes:
- 📄 Business Summary (from 10-K Item 1)
- 👥 Management Team
- 📊 Key Financial Metrics (5-year)
- 📈 Margin & Returns Analysis
- 🏦 Balance Sheet Snapshot
- 💰 Valuation Multiples
- 📊 Comparable Company Analysis
- 🏟️ Competitive Landscape
- 📈 Investment Thesis (Bull Case)
- ⚠️ Key Risks
- 🚀 Opportunities & Catalysts
        """)
