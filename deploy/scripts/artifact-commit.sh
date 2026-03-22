#!/usr/bin/env bash
# artifact-commit.sh — Auto-commit artifact changes to git
# Called by pfs-artifact-commit.timer daily at 23:55
set -euo pipefail

ARTIFACTS_DIR="/opt/pfs/data/artifacts"
cd "$ARTIFACTS_DIR"

# Ensure this is a git repo
if [[ ! -d .git ]]; then
    echo "ERROR: $ARTIFACTS_DIR is not a git repository"
    exit 1
fi

git add --all

if git diff --cached --quiet; then
    echo "No artifact changes — skipping commit"
    exit 0
fi

changed=$(git diff --cached --name-only | wc -l | tr -d ' ')
now=$(date '+%Y-%m-%d %H:%M %Z')
git commit -m "Auto-sync: ${changed} artifact(s) updated [${now}]" --quiet

echo "Committed ${changed} artifact change(s)"

# Push to remote if configured
if git remote get-url origin &>/dev/null; then
    git push --quiet 2>&1 || echo "WARN: push to remote failed"
fi
