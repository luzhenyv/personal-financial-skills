"""SQLAlchemy ORM models matching schema.sql."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from pfs.db.compat import CompatibleJSON


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    cik = Column(String(10), unique=True, nullable=False)
    ticker = Column(String(10), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    sector = Column(String(100))
    industry = Column(String(100))
    sic_code = Column(String(10))
    exchange = Column(String(20))
    fiscal_year_end = Column(String(5))
    market_cap = Column(BigInteger)
    employee_count = Column(Integer)
    headquarters = Column(String(255))
    description = Column(Text)
    website = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    income_statements = relationship("IncomeStatement", back_populates="company")
    balance_sheets = relationship("BalanceSheet", back_populates="company")
    cash_flow_statements = relationship("CashFlowStatement", back_populates="company")
    revenue_segments = relationship("RevenueSegment", back_populates="company")
    financial_metrics = relationship("FinancialMetric", back_populates="company")
    daily_prices = relationship("DailyPrice", back_populates="company")
    sec_filings = relationship("SecFiling", back_populates="company")
    analysis_reports = relationship("AnalysisReport", back_populates="company")
    stock_splits = relationship("StockSplit", back_populates="company", order_by="StockSplit.split_date")
    portfolio_positions = relationship("Position", back_populates="company")



class IncomeStatement(Base):
    __tablename__ = "income_statements"
    __table_args__ = (UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Integer)
    filing_type = Column(String(10))
    filing_date = Column(Date)
    # Revenue & Cost
    revenue = Column(BigInteger)
    cost_of_revenue = Column(BigInteger)
    gross_profit = Column(BigInteger)
    # Operating
    research_and_development = Column(BigInteger)
    selling_general_admin = Column(BigInteger)
    depreciation_amortization = Column(BigInteger)
    operating_expenses = Column(BigInteger)
    operating_income = Column(BigInteger)
    # Below the line
    interest_expense = Column(BigInteger)
    interest_income = Column(BigInteger)
    other_income = Column(BigInteger)
    pretax_income = Column(BigInteger)
    income_tax = Column(BigInteger)
    net_income = Column(BigInteger)
    # Per share
    eps_basic = Column(Numeric(10, 4))
    eps_diluted = Column(Numeric(10, 4))
    shares_basic = Column(BigInteger)
    shares_diluted = Column(BigInteger)
    # Source
    source = Column(String(50), default="sec_xbrl")
    raw_json = Column(CompatibleJSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="income_statements")


class BalanceSheet(Base):
    __tablename__ = "balance_sheets"
    __table_args__ = (UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Integer)
    filing_type = Column(String(10))
    filing_date = Column(Date)
    # Assets
    cash_and_equivalents = Column(BigInteger)
    short_term_investments = Column(BigInteger)
    accounts_receivable = Column(BigInteger)
    inventory = Column(BigInteger)
    total_current_assets = Column(BigInteger)
    property_plant_equipment = Column(BigInteger)
    goodwill = Column(BigInteger)
    intangible_assets = Column(BigInteger)
    total_assets = Column(BigInteger)
    # Liabilities
    accounts_payable = Column(BigInteger)
    deferred_revenue = Column(BigInteger)
    short_term_debt = Column(BigInteger)
    total_current_liabilities = Column(BigInteger)
    long_term_debt = Column(BigInteger)
    total_liabilities = Column(BigInteger)
    # Equity
    common_stock = Column(BigInteger)
    retained_earnings = Column(BigInteger)
    total_stockholders_equity = Column(BigInteger)
    # Source
    source = Column(String(50), default="sec_xbrl")
    raw_json = Column(CompatibleJSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="balance_sheets")


class CashFlowStatement(Base):
    __tablename__ = "cash_flow_statements"
    __table_args__ = (UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Integer)
    filing_type = Column(String(10))
    filing_date = Column(Date)
    # Operating
    net_income = Column(BigInteger)
    depreciation_amortization = Column(BigInteger)
    stock_based_compensation = Column(BigInteger)
    change_in_working_capital = Column(BigInteger)
    cash_from_operations = Column(BigInteger)
    # Investing
    capital_expenditure = Column(BigInteger)
    acquisitions = Column(BigInteger)
    purchases_of_investments = Column(BigInteger)
    sales_of_investments = Column(BigInteger)
    cash_from_investing = Column(BigInteger)
    # Financing
    debt_issuance = Column(BigInteger)
    debt_repayment = Column(BigInteger)
    share_repurchase = Column(BigInteger)
    dividends_paid = Column(BigInteger)
    cash_from_financing = Column(BigInteger)
    # Summary
    net_change_in_cash = Column(BigInteger)
    free_cash_flow = Column(BigInteger)
    # Source
    source = Column(String(50), default="sec_xbrl")
    raw_json = Column(CompatibleJSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="cash_flow_statements")


class RevenueSegment(Base):
    __tablename__ = "revenue_segments"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "fiscal_year", "fiscal_quarter", "segment_type", "segment_name"
        ),
    )

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Integer)
    segment_type = Column(String(20), nullable=False)  # 'product', 'geography', 'channel'
    segment_name = Column(String(255), nullable=False)
    revenue = Column(BigInteger)
    pct_of_total = Column(Numeric(8, 4))
    source = Column(String(50), default="sec_xbrl")
    raw_json = Column(CompatibleJSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="revenue_segments")


class FinancialMetric(Base):
    __tablename__ = "financial_metrics"
    __table_args__ = (UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Integer)
    # Margins
    gross_margin = Column(Numeric(8, 4))
    operating_margin = Column(Numeric(8, 4))
    ebitda_margin = Column(Numeric(8, 4))
    net_margin = Column(Numeric(8, 4))
    fcf_margin = Column(Numeric(8, 4))
    # Growth
    revenue_growth = Column(Numeric(8, 4))
    operating_income_growth = Column(Numeric(8, 4))
    net_income_growth = Column(Numeric(8, 4))
    eps_growth = Column(Numeric(8, 4))
    # Returns
    roe = Column(Numeric(8, 4))
    roa = Column(Numeric(8, 4))
    roic = Column(Numeric(8, 4))
    # Leverage
    debt_to_equity = Column(Numeric(8, 4))
    current_ratio = Column(Numeric(8, 4))
    quick_ratio = Column(Numeric(8, 4))
    # Efficiency
    dso = Column(Numeric(8, 2))
    dio = Column(Numeric(8, 2))
    dpo = Column(Numeric(8, 2))
    # Valuation
    ebitda = Column(BigInteger)
    pe_ratio = Column(Numeric(8, 2))
    ps_ratio = Column(Numeric(8, 2))
    pb_ratio = Column(Numeric(8, 2))
    ev_to_ebitda = Column(Numeric(8, 2))
    fcf_yield = Column(Numeric(8, 4))
    calculated_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="financial_metrics")


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("ticker", "date"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    date = Column(Date, nullable=False)
    open_price = Column(Numeric(12, 4))
    high_price = Column(Numeric(12, 4))
    low_price = Column(Numeric(12, 4))
    close_price = Column(Numeric(12, 4))
    adjusted_close = Column(Numeric(12, 4))
    volume = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="daily_prices")


class SecFiling(Base):
    __tablename__ = "sec_filings"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    cik = Column(String(10))
    accession_number = Column(String(30), unique=True, nullable=False)
    filing_type = Column(String(10))
    filing_date = Column(Date)
    reporting_date = Column(Date)
    primary_doc_url = Column(Text)
    xbrl_url = Column(Text)
    is_processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="sec_filings")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    report_type = Column(String(50), nullable=False)
    title = Column(String(255))
    content_md = Column(Text)
    parameters = Column(CompatibleJSON)
    generated_by = Column(String(50))
    file_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="analysis_reports")


class StockSplit(Base):
    __tablename__ = "stock_splits"
    __table_args__ = (UniqueConstraint("ticker", "split_date"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    split_date = Column(Date, nullable=False)
    ratio = Column(Numeric(10, 4), nullable=False)
    source = Column(String(50), default="yfinance")
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="stock_splits")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    category = Column(String(50))
    thesis = Column(Text)
    target_price = Column(Numeric(12, 4))
    added_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)




# ──────────────────────────────────────────────
# ETL AUDIT
# ──────────────────────────────────────────────


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    run_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)
    income_statements = Column(Integer, default=0)
    balance_sheets = Column(Integer, default=0)
    cash_flow_statements = Column(Integer, default=0)
    financial_metrics = Column(Integer, default=0)
    revenue_segments = Column(Integer, default=0)
    daily_prices = Column(Integer, default=0)
    sec_filings = Column(Integer, default=0)
    filings_downloaded = Column(Integer, default=0)
    stock_splits = Column(Integer, default=0)
    errors = Column(CompatibleJSON, default=list)
    run_metadata = Column("metadata", CompatibleJSON, default=dict)


# ──────────────────────────────────────────────
# PORTFOLIO (Mini PORT)
# ──────────────────────────────────────────────


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, default="default")
    cash = Column(Numeric(14, 2), nullable=False, default=100_000)
    inception_date = Column(Date, nullable=False)
    benchmark = Column(String(10), default="SPY")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="portfolio")
    positions = relationship("Position", back_populates="portfolio")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    date = Column(Date, nullable=False)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    action = Column(String(10), nullable=False)  # buy, sell, dividend
    shares = Column(Numeric(12, 4), nullable=False)
    price = Column(Numeric(12, 4), nullable=False)
    fees = Column(Numeric(8, 2), default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="transactions")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "ticker"),)

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String(10), ForeignKey("companies.ticker"), nullable=False)
    shares = Column(Numeric(12, 4), nullable=False)
    avg_cost = Column(Numeric(12, 4), nullable=False)
    conviction = Column(String(10))  # high, medium, low
    position_type = Column(String(10), default="long")  # long, short
    opened_at = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="positions")
    company = relationship("Company", back_populates="portfolio_positions")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("portfolio_id", "date"),)

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    date = Column(Date, nullable=False)
    total_market_value = Column(Numeric(14, 2))
    total_cost_basis = Column(Numeric(14, 2))
    cash = Column(Numeric(14, 2))
    unrealized_pnl = Column(Numeric(14, 2))
    realized_pnl = Column(Numeric(14, 2))
    positions_json = Column(CompatibleJSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="snapshots")
