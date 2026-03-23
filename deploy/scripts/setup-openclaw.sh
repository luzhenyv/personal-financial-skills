#!/usr/bin/env bash
# setup-openclaw.sh — Configure OpenClaw workspace for Mini Bloomberg skills
# Run once after initial deployment on Agent Server
set -euo pipefail

PROJECT_DIR="/opt/pfs"
OC_WORKSPACE="/root/.openclaw/workspace"
OC_SKILLS="$OC_WORKSPACE/skills"

echo "=== Setting up OpenClaw workspace for Mini Bloomberg ==="

# 1. Copy project skills into OpenClaw workspace
# NOTE: OpenClaw rejects symlinks that resolve outside the workspace root,
# so we copy instead of symlink. Re-run this script (or deploy.sh) to sync.
echo "Copying project skills..."
mkdir -p "$OC_SKILLS"
for skill in company-profile thesis-tracker etl-coverage; do
    rm -rf "${OC_SKILLS:?}/$skill"
    cp -r "$PROJECT_DIR/skills/$skill" "$OC_SKILLS/$skill"
done

# 2. Ensure uv is in system PATH for OpenClaw exec
if [[ -x "$HOME/.local/bin/uv" ]] && [[ ! -x "/usr/local/bin/uv" ]]; then
    ln -sf "$HOME/.local/bin/uv" /usr/local/bin/uv
    echo "Symlinked uv to /usr/local/bin/uv"
fi

# 3. Install CLAUDE.md (agent persona)
echo "Installing CLAUDE.md..."
cp "$PROJECT_DIR/agents/openclaw/CLAUDE.md" "$OC_WORKSPACE/CLAUDE.md"

# 4. Create flags directory for event-driven triggers
mkdir -p "$PROJECT_DIR/data/artifacts/_flags"

# 5. Verify setup
if [[ -f "$PROJECT_DIR/.env" ]]; then
    source "$PROJECT_DIR/.env"
fi
echo "API endpoint: ${PFS_API_URL:-http://127.0.0.1:8000}"

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
