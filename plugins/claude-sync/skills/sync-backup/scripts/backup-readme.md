# Claude Settings Backup

This repository is a backup of your Claude Code settings.

## How to Restore

### Option 1: bootstrap.sh (quick restore)

```bash
git clone <this-repo-url> ${TMPDIR:-/tmp}/claude-sync-repo
bash ${TMPDIR:-/tmp}/claude-sync-repo/bootstrap.sh
```

Works with just Git. If you need to install plugins afterwards, run `/sync-restore` in Claude Code.

### Option 2: claude-sync plugin

```bash
claude plugin marketplace add claude-sync --source github --repo june20516/claude-sync
claude plugin install claude-sync@claude-sync
```

Then in Claude Code:

```
/sync-restore
```

## Contents

- `agents/` — Custom agent definitions
- `skills/` — General-purpose skills
- `CLAUDE.md` — Global rules
- `plugins.json` — Plugin/marketplace list (extracted from settings.json, no sensitive data)
- `sync-metadata.json` — Per-file modification timestamps (for conflict detection)
- `mcp-servers.json` — MCP server list (name, URL, type)
- `bootstrap.sh` — Restore script for new devices
