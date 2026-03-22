"""Quick smoke-test for data_fallback module."""
from pfs.etl.data_fallback import fill_statement_gaps, _recompute_derived


def test_derived_fields():
    inc = {"revenue": 100000, "cost_of_revenue": 40000, "gross_profit": None,
           "operating_income": 30000, "operating_expenses": None}
    bal = {"total_assets": 200000, "total_stockholders_equity": 80000,
           "total_liabilities": None}
    cf = {"cash_from_operations": 50000, "capital_expenditure": 10000,
          "free_cash_flow": None}
    _recompute_derived(inc, bal, cf)
    assert inc["gross_profit"] == 60000
    assert inc["operating_expenses"] == 30000
    assert bal["total_liabilities"] == 120000
    assert cf["free_cash_flow"] == 40000
    print("PASSED: derived fields recomputed correctly")


def test_no_fallback():
    inc = {"revenue": 50000, "net_income": 10000, "gross_profit": None,
           "cost_of_revenue": 20000, "operating_income": 15000,
           "eps_diluted": 2.5, "shares_diluted": 4000}
    bal = {"total_assets": 100000, "total_stockholders_equity": 50000,
           "cash_and_equivalents": 20000, "total_liabilities": None}
    cf = {"cash_from_operations": 15000, "capital_expenditure": 5000,
          "free_cash_flow": None}
    inc, bal, cf, sources = fill_statement_gaps("TEST", 2024, None, inc, bal, cf)
    assert cf["free_cash_flow"] == 10000
    assert bal["total_liabilities"] == 50000
    assert inc["gross_profit"] == 30000
    assert sources == {"yfinance": [], "alpha_vantage": []}
    print("PASSED: no fallback needed, derived fields ok")


def test_quarterly_skips_fallback():
    inc = {"revenue": None, "net_income": None}
    bal = {"total_assets": None}
    cf = {"cash_from_operations": None}
    inc, bal, cf, sources = fill_statement_gaps("TEST", 2024, 1, inc, bal, cf)
    assert sources == {}
    print("PASSED: quarterly skips fallback")


if __name__ == "__main__":
    test_derived_fields()
    test_no_fallback()
    test_quarterly_skips_fallback()
    print("\nAll tests PASSED")
