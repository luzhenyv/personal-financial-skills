---
name: knowledge-base
description: Ingest and index external research documents (PDFs, reports, articles) into a queryable knowledge store. Supports "ingest report [file/url]", "search knowledge [query]", "list sources". This is a placeholder skill — full design coming later.
---

# Knowledge Base

Ingest external research into a structured, queryable knowledge store. Other skills can query this during thesis creation, earnings analysis, and morning briefings.

> **⚠️ Placeholder skill** — minimal implementation. Full redesign planned.

## When to Use

- "Ingest this Morningstar report"
- "Search knowledge base for semiconductor supply chain"
- "List all ingested sources"
- "Summarize what we know about {sector/theme}"

## Artifacts

Output goes to `data/artifacts/_knowledge/`:

```
data/artifacts/_knowledge/
  index.json                    # Master index of all ingested documents
  sources/
    {source_id}.json            # Structured extraction per document
    {source_id}_summary.md      # Key takeaways
```

Every JSON artifact includes `"schema_version": "1.0"`.

### index.json Schema

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-04-01T12:00:00Z",
  "sources": [
    {
      "id": "morningstar_oil_2025",
      "title": "Morningstar Oil & Gas Outlook 2025",
      "type": "report",
      "sectors": ["Energy"],
      "tickers_mentioned": ["XOM", "CVX"],
      "ingested_at": "2026-04-01T12:00:00Z",
      "tags": ["oil", "energy", "outlook"]
    }
  ]
}
```

## Workflow (2 Tasks)

### Task 1: Ingest Document (Script + AI)

```bash
uv run python skills/knowledge-base/scripts/ingest.py --file path/to/report.pdf
uv run python skills/knowledge-base/scripts/ingest.py --url https://example.com/report
```

**What the script does:**
1. Reads the document (PDF text extraction or web fetch)
2. AI extracts: title, sectors, tickers mentioned, key findings, tags
3. Writes `{source_id}.json` + `{source_id}_summary.md` to `data/artifacts/_knowledge/sources/`
4. Updates `index.json` with new entry

### Task 2: Search Knowledge (Script)

```bash
uv run python skills/knowledge-base/scripts/search.py --query "semiconductor supply chain"
uv run python skills/knowledge-base/scripts/search.py --sector Technology
uv run python skills/knowledge-base/scripts/search.py --ticker NVDA
```

**What the script does:**
1. Reads `index.json`
2. Filters by query text, sector, ticker, or tag
3. Returns matching sources with summaries

## CLI Summary

```bash
uv run python skills/knowledge-base/scripts/ingest.py --file {path}   # Ingest local file
uv run python skills/knowledge-base/scripts/ingest.py --url {url}     # Ingest from URL
uv run python skills/knowledge-base/scripts/search.py --query {text}  # Search by text
uv run python skills/knowledge-base/scripts/search.py --sector {name} # Search by sector
uv run python skills/knowledge-base/scripts/search.py --ticker {tick} # Search by ticker
```

## Cross-Skill Integration (Future)

- **thesis-tracker** — query relevant research when creating/updating theses
- **morning-briefing** — surface relevant knowledge for daily digest
- **earnings-analysis** — cross-reference analyst reports during earnings review
- **fund-manager** — factor external research into decision synthesis
