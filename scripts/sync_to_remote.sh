#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# sync_to_remote.sh — ETL locally, sync data to DMIT server
#
# Short-term strategy for low-resource remote server:
#   1. Run ETL on local Mac (PostgreSQL)
#   2. Export PG → temporary SQLite
#   3. rsync raw data + artifacts + SQLite to remote
#   4. Restart remote services
#
# Usage:
#   ./scripts/sync_to_remote.sh                     # sync all existing data
#   ./scripts/sync_to_remote.sh ingest NVDA         # ETL one ticker, then sync
#   ./scripts/sync_to_remote.sh ingest NVDA,AAPL    # ETL multiple, then sync
#   ./scripts/sync_to_remote.sh sync-only           # skip ETL, just sync
#   ./scripts/sync_to_remote.sh sync-prices         # sync prices, then sync
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ──────────────────────────────────────────
REMOTE_HOST="${REMOTE_HOST:-dmitserver}"
REMOTE_PFS_DIR="${REMOTE_PFS_DIR:-/opt/pfs}"
LOCAL_PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

LOCAL_PG_URL="${DATABASE_URL:-postgresql://pfs:pfs_dev_2024@localhost:5432/personal_finance}"
LOCAL_SQLITE_TEMP="${LOCAL_PROJECT_DIR}/data/personal_finance_sync.db"
REMOTE_SQLITE_PATH="${REMOTE_PFS_DIR}/data/personal_finance.db"

# Directories to sync
LOCAL_RAW_DIR="${LOCAL_PROJECT_DIR}/data/raw"
LOCAL_ARTIFACTS_DIR="${LOCAL_PROJECT_DIR}/data/artifacts"
REMOTE_DATA_DIR="${REMOTE_PFS_DIR}/data"

# ── Helpers ────────────────────────────────────────────────
info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
err()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

cleanup() {
    if [[ -f "$LOCAL_SQLITE_TEMP" ]]; then
        rm -f "$LOCAL_SQLITE_TEMP"
        info "Cleaned up temp SQLite: $LOCAL_SQLITE_TEMP"
    fi
}
trap cleanup EXIT

check_prereqs() {
    command -v uv    >/dev/null 2>&1 || { err "uv not found"; exit 1; }
    command -v rsync >/dev/null 2>&1 || { err "rsync not found"; exit 1; }
    command -v ssh   >/dev/null 2>&1 || { err "ssh not found"; exit 1; }

    # Verify remote is reachable
    if ! ssh -o ConnectTimeout=5 "$REMOTE_HOST" true 2>/dev/null; then
        err "Cannot reach remote host: $REMOTE_HOST"
        exit 1
    fi
    ok "Remote host reachable: $REMOTE_HOST"
}

# ── Step 1: Run ETL locally ───────────────────────────────
run_etl() {
    local mode="$1"
    shift

    case "$mode" in
        ingest)
            local tickers="$1"
            local years="${2:-5}"
            if [[ "$tickers" == *","* ]]; then
                info "ETL: batch ingest [$tickers] (${years} years)"
                cd "$LOCAL_PROJECT_DIR"
                uv run python -m pfs.etl.pipeline ingest-batch "$tickers" --years "$years"
            else
                info "ETL: ingest [$tickers] (${years} years)"
                cd "$LOCAL_PROJECT_DIR"
                uv run python -m pfs.etl.pipeline ingest "$tickers" --years "$years"
            fi
            ok "ETL complete"
            ;;
        sync-prices)
            local tickers="${1:-}"
            info "ETL: syncing prices"
            cd "$LOCAL_PROJECT_DIR"
            if [[ -n "$tickers" ]]; then
                uv run python -m pfs.etl.pipeline sync-prices --tickers "$tickers"
            else
                uv run python -m pfs.etl.pipeline sync-prices
            fi
            ok "Price sync complete"
            ;;
        sync-only)
            info "Skipping ETL — sync-only mode"
            ;;
        *)
            err "Unknown mode: $mode"
            echo "Usage: $0 [ingest TICKER(S)|sync-prices|sync-only]"
            exit 1
            ;;
    esac
}

# ── Step 2: Export PostgreSQL → temp SQLite ────────────────
export_pg_to_sqlite() {
    info "Exporting PostgreSQL → temporary SQLite..."
    rm -f "$LOCAL_SQLITE_TEMP"

    cd "$LOCAL_PROJECT_DIR"
    # Initialize SQLite schema, then copy data
    DATABASE_URL="sqlite:///${LOCAL_SQLITE_TEMP}" \
        uv run python scripts/init_db.py

    uv run python scripts/migrate_postgres_to_sqlite.py \
        --source-url "$LOCAL_PG_URL" \
        --target-url "sqlite:///${LOCAL_SQLITE_TEMP}"

    local size
    size=$(du -sh "$LOCAL_SQLITE_TEMP" | cut -f1)
    ok "SQLite export done: $LOCAL_SQLITE_TEMP ($size)"
}

# ── Step 3: Sync files to remote ──────────────────────────
sync_to_remote() {
    info "Syncing data to $REMOTE_HOST:$REMOTE_DATA_DIR ..."

    # 3a. Sync raw SEC filings (incremental, compressed)
    info "  Syncing raw data..."
    rsync -avz --progress \
        --exclude='*.tmp' \
        "$LOCAL_RAW_DIR/" \
        "$REMOTE_HOST:$REMOTE_DATA_DIR/raw/"
    ok "  Raw data synced"

    # 3b. Sync artifacts (incremental, compressed)
    info "  Syncing artifacts..."
    rsync -avz --progress \
        --exclude='.git' \
        "$LOCAL_ARTIFACTS_DIR/" \
        "$REMOTE_HOST:$REMOTE_DATA_DIR/artifacts/"
    ok "  Artifacts synced"

    # 3c. Transfer SQLite database (atomic replace)
    info "  Transferring SQLite database..."
    # Upload to temp location first, then swap atomically
    scp -q "$LOCAL_SQLITE_TEMP" "$REMOTE_HOST:${REMOTE_SQLITE_PATH}.new"
    ssh "$REMOTE_HOST" "mv -f '${REMOTE_SQLITE_PATH}.new' '${REMOTE_SQLITE_PATH}'"
    ok "  SQLite database transferred"
}

# ── Step 4: Restart remote services ───────────────────────
restart_remote_services() {
    info "Restarting remote services..."

    # Use nohup + disown so the restart survives SSH disconnect
    ssh -o ServerAliveInterval=5 -o ServerAliveCountMax=3 "$REMOTE_HOST" \
        'for svc in pfs-api pfs-streamlit pfs-mcp; do
            if systemctl is-active --quiet "$svc" 2>/dev/null; then
                sudo systemctl restart "$svc" && echo "  Restarted $svc"
            fi
        done' || warn "SSH disconnected during restart (services may still restart OK)"

    ok "Remote services restarted"
}

# ── Step 5: Verify remote data ────────────────────────────
verify_remote() {
    info "Verifying remote data..."

    ssh "$REMOTE_HOST" bash -s <<REMOTE_SCRIPT
        set -euo pipefail
        echo "  SQLite size: \$(du -sh '${REMOTE_SQLITE_PATH}' | cut -f1)"
        echo "  Raw data:    \$(du -sh '${REMOTE_DATA_DIR}/raw/' | cut -f1)"
        echo "  Artifacts:   \$(du -sh '${REMOTE_DATA_DIR}/artifacts/' | cut -f1)"
        echo "  Disk free:   \$(df -h '${REMOTE_PFS_DIR}' | awk 'NR==2{print \$4}')"

        # Quick table row counts via Python (sqlite3 CLI may not be installed)
        echo "  ── Table row counts ──"
        python3 -c "
import sqlite3
conn = sqlite3.connect('${REMOTE_SQLITE_PATH}')
for tbl in ['companies','income_statements','balance_sheets','cash_flow_statements',
            'financial_metrics','daily_prices','sec_filings','stock_splits']:
    try:
        n = conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
        print(f'  {tbl:<25} {n} rows')
    except Exception as e:
        print(f'  {tbl:<25} ERROR: {e}')
conn.close()
" 2>/dev/null || echo "  (could not query SQLite)"
REMOTE_SCRIPT

    ok "Verification complete"
}

# ── Main ──────────────────────────────────────────────────
main() {
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   Mini Bloomberg — Sync to Remote        ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    check_prereqs

    local mode="${1:-sync-only}"

    # Run ETL if requested
    case "$mode" in
        ingest)
            run_etl ingest "${2:-}" "${3:-5}"
            ;;
        sync-prices)
            run_etl sync-prices "${2:-}"
            ;;
        sync-only)
            run_etl sync-only
            ;;
        *)
            run_etl ingest "$mode" "${2:-5}"
            ;;
    esac

    export_pg_to_sqlite
    sync_to_remote
    restart_remote_services
    verify_remote

    echo ""
    ok "All done! Remote server is up to date."
    echo ""
}

main "$@"
