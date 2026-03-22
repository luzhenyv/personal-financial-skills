#!/usr/bin/env bash
# setup-openclaw.sh — Configure OpenClaw workspace for Mini Bloomberg skills
# Run once after initial deployment on Agent Server
set -euo pipefail

PROJECT_DIR="/opt/pfs"
OC_WORKSPACE="/root/.openclaw/workspace"
OC_SKILLS="$OC_WORKSPACE/skills"

echo "=== Setting up OpenClaw workspace for Mini Bloomberg ==="

# 1. Remove old test skills (user confirmed these can be deleted)
echo "Removing old test skills..."
rm -rf "$OC_SKILLS/daily-schedule-parser"
rm -rf "$OC_SKILLS/english-expression-helper"
rm -rf "$OC_SKILLS/investment-assistant"

# 2. Symlink project skills into OpenClaw workspace
echo "Symlinking project skills..."
mkdir -p "$OC_SKILLS"
ln -sfn "$PROJECT_DIR/skills/company-profile" "$OC_SKILLS/company-profile"
ln -sfn "$PROJECT_DIR/skills/thesis-tracker"  "$OC_SKILLS/thesis-tracker"
ln -sfn "$PROJECT_DIR/skills/etl-coverage"    "$OC_SKILLS/etl-coverage"

# 3. Install CLAUDE.md (agent persona)
echo "Installing CLAUDE.md..."
cp "$PROJECT_DIR/agents/openclaw/CLAUDE.md" "$OC_WORKSPACE/CLAUDE.md"

# 4. Create flags directory for event-driven triggers
mkdir -p "$PROJECT_DIR/data/artifacts/_flags"

# 5. Configure MCP HTTP endpoint (from .env)
if [[ -f "$PROJECT_DIR/.env" ]]; then
    source "$PROJECT_DIR/.env"
fi
MCP_URL="${PFS_MCP_URL:-http://127.0.0.1:8001/mcp}"
echo "MCP HTTP endpoint: $MCP_URL"

# 6. Ensure artifact git repo has GitHub remote
ARTIFACTS_DIR="$PROJECT_DIR/data/artifacts"
if [[ -d "$ARTIFACTS_DIR/.git" ]]; then
    if ! git -C "$ARTIFACTS_DIR" remote get-url origin &>/dev/null; then
        echo "NOTE: artifacts repo has no remote. Set one with:"
        echo "  git -C $ARTIFACTS_DIR remote add origin <github-url>"
    else
        echo "Artifacts remote: $(git -C "$ARTIFACTS_DIR" remote get-url origin)"
    fi
fi

# 7. Verify
echo ""
echo "=== Verification ==="
echo "Skills installed:"
ls -la "$OC_SKILLS/"
echo ""
echo "CLAUDE.md:"
head -5 "$OC_WORKSPACE/CLAUDE.md"
echo ""
echo "=== OpenClaw workspace setup complete ==="
echo ""
echo "Next: run setup-cron.sh to configure scheduled jobs"
