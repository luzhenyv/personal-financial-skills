"""Search the knowledge base index.

Placeholder implementation — full redesign planned.
"""

import argparse
import json
import sys
from pathlib import Path

INDEX_PATH = Path("data/artifacts/_knowledge/index.json")
SOURCES_DIR = Path("data/artifacts/_knowledge/sources")


def load_index() -> dict:
    if not INDEX_PATH.exists():
        print("Knowledge base is empty. Ingest documents first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(INDEX_PATH.read_text())


def search(query: str | None = None, sector: str | None = None, ticker: str | None = None) -> list[dict]:
    index = load_index()
    results = index["sources"]

    if sector:
        sector_lower = sector.lower()
        results = [s for s in results if any(sector_lower in sec.lower() for sec in s.get("sectors", []))]

    if ticker:
        ticker_upper = ticker.upper()
        results = [s for s in results if ticker_upper in s.get("tickers_mentioned", [])]

    if query:
        query_lower = query.lower()
        results = [
            s for s in results
            if query_lower in s.get("title", "").lower()
            or any(query_lower in t.lower() for t in s.get("tags", []))
        ]

    return results


def main():
    parser = argparse.ArgumentParser(description="Search the knowledge base")
    parser.add_argument("--query", help="Free-text search query")
    parser.add_argument("--sector", help="Filter by sector")
    parser.add_argument("--ticker", help="Filter by ticker")
    args = parser.parse_args()

    if not any([args.query, args.sector, args.ticker]):
        # List all
        index = load_index()
        results = index["sources"]
    else:
        results = search(query=args.query, sector=args.sector, ticker=args.ticker)

    if not results:
        print("No matching sources found.")
        return

    print(f"Found {len(results)} source(s):\n")
    for s in results:
        print(f"  [{s['id']}] {s['title']}")
        print(f"    Type: {s['type']} | Ingested: {s.get('ingested_at', 'unknown')}")
        if s.get("sectors"):
            print(f"    Sectors: {', '.join(s['sectors'])}")
        if s.get("tickers_mentioned"):
            print(f"    Tickers: {', '.join(s['tickers_mentioned'])}")
        print()


if __name__ == "__main__":
    main()
