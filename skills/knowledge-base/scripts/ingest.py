"""Ingest external research documents into the knowledge base.

Placeholder implementation — full redesign planned.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ARTIFACTS_DIR = Path("data/artifacts/_knowledge")
SOURCES_DIR = ARTIFACTS_DIR / "sources"
INDEX_PATH = ARTIFACTS_DIR / "index.json"


def load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text())
    return {"schema_version": "1.0", "updated_at": None, "sources": []}


def save_index(index: dict) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    INDEX_PATH.write_text(json.dumps(index, indent=2))


def ingest_file(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    source_id = p.stem.lower().replace(" ", "_")
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # Placeholder: just store raw text content
    text = p.read_text(errors="replace")

    source_json = {
        "schema_version": "1.0",
        "id": source_id,
        "title": p.stem,
        "type": "file",
        "original_path": str(p),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "sectors": [],
        "tickers_mentioned": [],
        "tags": [],
        "content_preview": text[:500],
    }
    (SOURCES_DIR / f"{source_id}.json").write_text(json.dumps(source_json, indent=2))

    summary_md = f"# {p.stem}\n\n> Ingested {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
    summary_md += "## Key Takeaways\n\n*AI extraction not yet implemented — placeholder.*\n\n"
    summary_md += f"## Content Preview\n\n{text[:1000]}\n"
    (SOURCES_DIR / f"{source_id}_summary.md").write_text(summary_md)

    # Update index
    index = load_index()
    index["sources"] = [s for s in index["sources"] if s["id"] != source_id]
    index["sources"].append({
        "id": source_id,
        "title": p.stem,
        "type": "file",
        "sectors": [],
        "tickers_mentioned": [],
        "ingested_at": source_json["ingested_at"],
        "tags": [],
    })
    save_index(index)
    print(f"Ingested: {source_id} → {SOURCES_DIR / f'{source_id}.json'}")


def ingest_url(url: str) -> None:
    print(f"URL ingestion not yet implemented. URL: {url}", file=sys.stderr)
    print("This is a placeholder — full implementation planned.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to a local file to ingest")
    group.add_argument("--url", help="URL to fetch and ingest")
    args = parser.parse_args()

    if args.file:
        ingest_file(args.file)
    elif args.url:
        ingest_url(args.url)


if __name__ == "__main__":
    main()
