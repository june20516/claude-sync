#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "=== Claude Settings Restore (bootstrap) ==="

# Create ~/.claude directory
mkdir -p "$CLAUDE_DIR"

# Restore agents
if [ -d "$SCRIPT_DIR/agents" ]; then
  mkdir -p "$CLAUDE_DIR/agents"
  cp -r "$SCRIPT_DIR/agents/" "$CLAUDE_DIR/agents/"
  echo "* agents restored"
fi

# Restore skills
if [ -d "$SCRIPT_DIR/skills" ]; then
  mkdir -p "$CLAUDE_DIR/skills"
  cp -r "$SCRIPT_DIR/skills/" "$CLAUDE_DIR/skills/"
  echo "* skills restored"
fi

# Restore CLAUDE.md
if [ -f "$SCRIPT_DIR/CLAUDE.md" ]; then
  cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
  echo "* CLAUDE.md restored"
fi

# Create sync-config.json (auto-detect repo URL)
REPO_URL=$(cd "$SCRIPT_DIR" && git remote get-url origin 2>/dev/null || echo "")
if [ -n "$REPO_URL" ] && [ ! -f "$CLAUDE_DIR/sync-config.json" ]; then
  cat > "$CLAUDE_DIR/sync-config.json" << EOF
{
  "repo_url": "$REPO_URL"
}
EOF
  echo "* sync-config.json created (repo: $REPO_URL)"
fi

# Plugin and MCP server restore guide
if [ -f "$SCRIPT_DIR/plugins.json" ] || [ -f "$SCRIPT_DIR/mcp-servers.json" ]; then
  echo ""
  echo "=== Plugins & MCP Servers ==="
  echo "To install items listed in plugins.json and mcp-servers.json,"
  echo "run /sync-restore in Claude Code."
fi

echo ""
echo "=== Done ==="
echo "Restored settings will take effect when you start Claude Code."
