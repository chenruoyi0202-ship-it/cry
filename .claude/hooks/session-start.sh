#!/bin/bash
# Install dependencies for the skills in .claude/skills/:
#   - webapp-testing: playwright (Python)
#   - agent-browser: npm CLI + AGENT_BROWSER_EXECUTABLE_PATH env var
# Only runs in Claude Code on the web (remote) environments.
set -euo pipefail

# Only run in remote environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "[session-start] installing skill dependencies..." >&2

# 1. Playwright Python (pinned to match preinstalled browsers in /opt/pw-browsers)
if ! python3 -c "import playwright" 2>/dev/null; then
  pip install --quiet 'playwright==1.56.0' >&2
fi

# 2. agent-browser CLI
if ! command -v agent-browser >/dev/null 2>&1; then
  npm install -g --silent agent-browser >&2
fi

# 3. Point agent-browser at the preinstalled chromium (skip Chrome download)
CHROME_BIN=""
if [ -x /opt/pw-browsers/chromium-1194/chrome-linux/chrome ]; then
  CHROME_BIN=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
else
  # Fall back to any chromium under PLAYWRIGHT_BROWSERS_PATH
  CHROME_BIN=$(find "${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}" -type f -name chrome 2>/dev/null | head -n1 || true)
fi

if [ -n "$CHROME_BIN" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export AGENT_BROWSER_EXECUTABLE_PATH=$CHROME_BIN" >> "$CLAUDE_ENV_FILE"
fi

echo "[session-start] done." >&2
