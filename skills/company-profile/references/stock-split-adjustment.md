# Stock Split Adjustment

SEC XBRL filings report EPS and other per-share figures **as-filed at the time of the original filing** — they are NOT retroactively restated for subsequent stock splits. This causes historical per-share metrics to appear inflated relative to post-split values (e.g., NVDA reported FY2024 EPS of \$11.93 pre-split, which should be \$1.19 after the 10:1 split in June 2024).

## Mandatory Adjustment Rule

All per-share metrics displayed in the report and Streamlit app **must be split-adjusted to the current share basis** so that multi-year trends are comparable. This applies to:
- EPS (basic and diluted)
- Dividends per share
- Book value per share
- Any custom per-share ratios

## How to Detect and Apply Splits

1. **Query yfinance for split history**: `yf.Ticker(ticker).splits` returns a series of split dates and ratios
2. **Compute cumulative split factor**: For each historical fiscal year, multiply all split ratios that occurred *after* that fiscal year's end date up to the present
3. **Adjust**: `adjusted_eps = reported_eps / cumulative_split_factor`
4. **Store the split history** in `data/processed/{TICKER}/stock_splits.json` for auditability

### Example: NVDA (10:1 split on 2024-06-10)

```python
import yfinance as yf

splits = yf.Ticker("NVDA").splits  # e.g., {2024-06-10: 10.0, 2021-07-20: 4.0}

# For FY2024 (ended Jan 2024, before the June 2024 split):
# cumulative_factor = 10.0 (one split after FY-end)
# adjusted_eps = 11.93 / 10.0 = 1.193 ≈ $1.19

# For FY2021 (ended Jan 2021, before both splits):
# cumulative_factor = 4.0 * 10.0 = 40.0
# adjusted_eps = reported_eps / 40.0
```

> **Important**: Shares outstanding (`shares_diluted`) from XBRL are also as-reported. When computing per-share metrics from raw financials (e.g., `net_income / shares_diluted`), either adjust both numerator consistency or use the already-adjusted EPS. The safest approach is to adjust shares outstanding upward by the same cumulative split factor and recompute derived metrics.

### `stock_splits.json` Format

```json
{
  "ticker": "NVDA",
  "splits": [
    { "date": "2024-06-10", "ratio": 10, "description": "10-for-1 stock split" },
    { "date": "2021-07-20", "ratio": 4, "description": "4-for-1 stock split" }
  ],
  "source": "yfinance",
  "current_basis_date": "2026-03-09"
}
```

### Ingestion Code

After data ingestion (Task 1), query yfinance for split history and save:

```python
import yfinance as yf, json
from pathlib import Path

splits = yf.Ticker(ticker).splits
if not splits.empty:
    split_data = {
        "ticker": ticker,
        "splits": [
            {"date": str(d.date()), "ratio": float(r)}
            for d, r in splits.items()
        ],
        "source": "yfinance"
    }
    out = Path(f"data/processed/{ticker}/stock_splits.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(split_data, indent=2))
```

This file is consumed by `generate_report.py` to split-adjust all per-share metrics.
