-- ============================================
-- Personal Financial Skills - Database Schema
-- Mini Bloomberg for Personal Investors
-- ============================================

-- ============================================
-- CORE: Companies
-- ============================================
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) UNIQUE NOT NULL,
    ticker VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    sic_code VARCHAR(10),
    exchange VARCHAR(20),
    fiscal_year_end VARCHAR(5),
    market_cap BIGINT,
    description TEXT,
    website VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- FINANCIAL STATEMENTS
-- ============================================

CREATE TABLE income_statements (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT,
    filing_type VARCHAR(10),
    filing_date DATE,
    -- Revenue & Cost
    revenue BIGINT,
    cost_of_revenue BIGINT,
    gross_profit BIGINT,
    -- Operating
    research_and_development BIGINT,
    selling_general_admin BIGINT,
    operating_expenses BIGINT,
    operating_income BIGINT,
    -- Below the line
    interest_expense BIGINT,
    interest_income BIGINT,
    other_income BIGINT,
    pretax_income BIGINT,
    income_tax BIGINT,
    net_income BIGINT,
    -- Per share
    eps_basic NUMERIC(10,4),
    eps_diluted NUMERIC(10,4),
    shares_basic BIGINT,
    shares_diluted BIGINT,
    -- Source tracking
    source VARCHAR(50) DEFAULT 'sec_xbrl',
    raw_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, fiscal_quarter)
);

CREATE TABLE balance_sheets (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT,
    filing_type VARCHAR(10),
    filing_date DATE,
    -- Assets
    cash_and_equivalents BIGINT,
    short_term_investments BIGINT,
    accounts_receivable BIGINT,
    inventory BIGINT,
    total_current_assets BIGINT,
    property_plant_equipment BIGINT,
    goodwill BIGINT,
    intangible_assets BIGINT,
    total_assets BIGINT,
    -- Liabilities
    accounts_payable BIGINT,
    short_term_debt BIGINT,
    total_current_liabilities BIGINT,
    long_term_debt BIGINT,
    total_liabilities BIGINT,
    -- Equity
    common_stock BIGINT,
    retained_earnings BIGINT,
    total_stockholders_equity BIGINT,
    -- Source
    source VARCHAR(50) DEFAULT 'sec_xbrl',
    raw_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, fiscal_quarter)
);

CREATE TABLE cash_flow_statements (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT,
    filing_type VARCHAR(10),
    filing_date DATE,
    -- Operating
    net_income BIGINT,
    depreciation_amortization BIGINT,
    stock_based_compensation BIGINT,
    change_in_working_capital BIGINT,
    cash_from_operations BIGINT,
    -- Investing
    capital_expenditure BIGINT,
    acquisitions BIGINT,
    purchases_of_investments BIGINT,
    sales_of_investments BIGINT,
    cash_from_investing BIGINT,
    -- Financing
    debt_issuance BIGINT,
    debt_repayment BIGINT,
    share_repurchase BIGINT,
    dividends_paid BIGINT,
    cash_from_financing BIGINT,
    -- Summary
    net_change_in_cash BIGINT,
    free_cash_flow BIGINT,
    -- Source
    source VARCHAR(50) DEFAULT 'sec_xbrl',
    raw_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, fiscal_quarter)
);

-- ============================================
-- DERIVED METRICS
-- ============================================

CREATE TABLE financial_metrics (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    fiscal_year INT NOT NULL,
    fiscal_quarter INT,
    -- Margins
    gross_margin NUMERIC(8,4),
    operating_margin NUMERIC(8,4),
    net_margin NUMERIC(8,4),
    fcf_margin NUMERIC(8,4),
    -- Growth (YoY)
    revenue_growth NUMERIC(8,4),
    operating_income_growth NUMERIC(8,4),
    net_income_growth NUMERIC(8,4),
    eps_growth NUMERIC(8,4),
    -- Returns
    roe NUMERIC(8,4),
    roa NUMERIC(8,4),
    roic NUMERIC(8,4),
    -- Leverage
    debt_to_equity NUMERIC(8,4),
    current_ratio NUMERIC(8,4),
    quick_ratio NUMERIC(8,4),
    -- Valuation (requires price data)
    pe_ratio NUMERIC(8,2),
    ps_ratio NUMERIC(8,2),
    pb_ratio NUMERIC(8,2),
    ev_to_ebitda NUMERIC(8,2),
    fcf_yield NUMERIC(8,4),
    --
    calculated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, fiscal_quarter)
);

-- ============================================
-- PRICE DATA
-- ============================================

CREATE TABLE daily_prices (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    date DATE NOT NULL,
    open_price NUMERIC(12,4),
    high_price NUMERIC(12,4),
    low_price NUMERIC(12,4),
    close_price NUMERIC(12,4),
    adjusted_close NUMERIC(12,4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, date)
);

-- ============================================
-- PORTFOLIO
-- ============================================

CREATE TABLE portfolio_holdings (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    shares NUMERIC(12,4) NOT NULL,
    avg_cost_basis NUMERIC(12,4) NOT NULL,
    purchase_date DATE,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE portfolio_transactions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    action VARCHAR(10) NOT NULL,
    shares NUMERIC(12,4) NOT NULL,
    price NUMERIC(12,4) NOT NULL,
    date DATE NOT NULL,
    fees NUMERIC(8,2) DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- ANALYSIS REPORTS
-- ============================================

CREATE TABLE analysis_reports (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    report_type VARCHAR(50) NOT NULL,
    title VARCHAR(255),
    content_md TEXT,
    parameters JSONB,
    generated_by VARCHAR(50),
    file_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- SEC FILINGS TRACKING
-- ============================================

CREATE TABLE sec_filings (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    cik VARCHAR(10),
    accession_number VARCHAR(30) UNIQUE NOT NULL,
    filing_type VARCHAR(10),
    filing_date DATE,
    reporting_date DATE,
    primary_doc_url TEXT,
    xbrl_url TEXT,
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- WATCHLIST
-- ============================================

CREATE TABLE watchlist (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES companies(ticker),
    category VARCHAR(50),
    thesis TEXT,
    target_price NUMERIC(12,4),
    added_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_income_ticker_year ON income_statements(ticker, fiscal_year);
CREATE INDEX idx_balance_ticker_year ON balance_sheets(ticker, fiscal_year);
CREATE INDEX idx_cashflow_ticker_year ON cash_flow_statements(ticker, fiscal_year);
CREATE INDEX idx_metrics_ticker_year ON financial_metrics(ticker, fiscal_year);
CREATE INDEX idx_prices_ticker_date ON daily_prices(ticker, date);
CREATE INDEX idx_reports_ticker_type ON analysis_reports(ticker, report_type);
CREATE INDEX idx_filings_ticker ON sec_filings(ticker, filing_type);
