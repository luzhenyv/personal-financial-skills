"""Quick check of NVDA data in the database."""
from src.db.session import get_session
from src.db.models import (
    Company, IncomeStatement, BalanceSheet, CashFlowStatement, FinancialMetric
)

s = get_session()

c = s.query(Company).filter_by(ticker="NVDA").first()
print(f"Company: {c.name} (CIK: {c.cik})")

incs = s.query(IncomeStatement).filter_by(ticker="NVDA").order_by(IncomeStatement.fiscal_year).all()
for i in incs:
    rev = f"{i.revenue/1e9:.1f}B" if i.revenue else "N/A"
    ni = f"{i.net_income/1e9:.1f}B" if i.net_income else "N/A"
    print(f"  IS FY{i.fiscal_year}: revenue={rev}, net_income={ni}")

bss = s.query(BalanceSheet).filter_by(ticker="NVDA").order_by(BalanceSheet.fiscal_year).all()
for b in bss:
    ta = f"{b.total_assets/1e9:.1f}B" if b.total_assets else "N/A"
    eq = f"{b.total_stockholders_equity/1e9:.1f}B" if b.total_stockholders_equity else "N/A"
    print(f"  BS FY{b.fiscal_year}: assets={ta}, equity={eq}")

cfs = s.query(CashFlowStatement).filter_by(ticker="NVDA").order_by(CashFlowStatement.fiscal_year).all()
for cf in cfs:
    cfo = f"{cf.cash_from_operations/1e9:.1f}B" if cf.cash_from_operations else "N/A"
    fcf = f"{cf.free_cash_flow/1e9:.1f}B" if cf.free_cash_flow else "N/A"
    print(f"  CF FY{cf.fiscal_year}: CFO={cfo}, FCF={fcf}")

ms = s.query(FinancialMetric).filter_by(ticker="NVDA").order_by(FinancialMetric.fiscal_year).all()
for m in ms:
    print(f"  Metrics FY{m.fiscal_year}: gm={m.gross_margin}, om={m.operating_margin}, roe={m.roe}")

s.close()
