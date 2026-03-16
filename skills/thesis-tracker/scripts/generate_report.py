"""Generate the thesis markdown report from JSON artifacts.

Reads all JSON files from data/artifacts/{TICKER}/thesis/ and assembles
a human-readable thesis_{TICKER}.md report.

After the report is written, the agent should call MCP save_analysis_report
to persist the report in the database.

Usage:
    uv run python skills/thesis-tracker/scripts/generate_report.py NVDA
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def main():
    parser = argparse.ArgumentParser(description="Generate thesis markdown report")
    parser.add_argument("ticker", type=str, help="Ticker symbol (e.g. NVDA)")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    from src.analysis.thesis_tracker import generate_thesis_markdown

    md = generate_thesis_markdown(ticker)
    if not md:
        print(f"❌ No thesis found for {ticker}")
        print(f"   Create one first: uv run python skills/thesis-tracker/scripts/create_thesis.py {ticker} -i")
        sys.exit(1)

    md_path = Path(f"data/artifacts/{ticker}/thesis/thesis_{ticker}.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md)

    print(f"✅ Report generated → {md_path}")


if __name__ == "__main__":
    main()
