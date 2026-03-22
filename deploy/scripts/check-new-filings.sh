#!/usr/bin/env bash
# check-new-filings.sh — Check SEC EDGAR for new filings for tracked companies.
# Writes a flag file if new filings are detected, consumed by OpenClaw morning-brief.
set -euo pipefail

PROJECT_DIR="/opt/pfs"
FLAGS_DIR="$PROJECT_DIR/data/artifacts/_flags"
FLAG_FILE="$FLAGS_DIR/new_filings.json"

cd "$PROJECT_DIR"
mkdir -p "$FLAGS_DIR"

# Get list of tracked tickers from artifacts directory
tickers=$(ls -d data/artifacts/*/ 2>/dev/null | xargs -I{} basename {} | grep -v '^_')

if [[ -z "$tickers" ]]; then
    echo "No tracked companies found"
    exit 0
fi

new_filings="[]"
found_new=false

for ticker in $tickers; do
    # Use the ETL list_filings check — compare against what we already have in raw/
    result=$(/root/.local/bin/uv run python -c "
import json, sys
from pathlib import Path

ticker = '$ticker'
raw_dir = Path('data/raw') / ticker

# Get existing filing files
existing = set()
if raw_dir.exists():
    for f in raw_dir.glob('*.htm'):
        existing.add(f.stem)  # e.g. '10-K_2025_12'

# Check DB for filings we haven't downloaded yet
try:
    from pfs.db.session import SessionLocal
    from pfs.db.models import SecFiling
    db = SessionLocal()
    filings = db.query(SecFiling).filter(SecFiling.ticker == ticker).all()
    new = []
    for f in filings:
        key = f'{f.form_type}_{f.filed_date.year}_{f.filed_date.month:02d}'
        if key not in existing:
            new.append({'ticker': ticker, 'form_type': f.form_type, 'filed_date': str(f.filed_date), 'accession': f.accession_number})
    db.close()
    if new:
        print(json.dumps(new))
except Exception as e:
    print(f'[]', file=sys.stderr)
    print(f'Error checking {ticker}: {e}', file=sys.stderr)
" 2>/dev/null || echo "[]")

    if [[ "$result" != "[]" && -n "$result" ]]; then
        found_new=true
        new_filings=$(echo "$new_filings $result" | /root/.local/bin/uv run python -c "
import json, sys
parts = sys.stdin.read().split()
merged = []
for p in parts:
    try:
        merged.extend(json.loads(p))
    except: pass
print(json.dumps(merged))
")
    fi
done

if $found_new; then
    echo "$new_filings" > "$FLAG_FILE"
    echo "New filings detected: $new_filings"
else
    # Remove stale flag
    rm -f "$FLAG_FILE"
    echo "No new filings"
fi
