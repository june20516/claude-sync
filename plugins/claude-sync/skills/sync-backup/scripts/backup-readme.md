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
- `mcp-servers.json` — MCP server configs from `~/.claude.json` (user scope), merged per server name
- `bootstrap.sh` — Restore script for new devices

### About `mcp-servers.json`

Values under `headers` and `env` are stored as `<REDACTED>`; the key names are kept so a restore knows what to ask for. **Secrets passed through `args` or a URL query string are not masked** — keep this repository private. When you restore, `/sync-restore` prompts for each masked value; skipping a prompt leaves that server unregistered rather than creating one with broken auth.

This file is merged **per server name**, so backing up from one machine will not drop servers that only exist on another. `plugins.json`, in contrast, is regenerated and overwritten on every backup.

The file is written in schema v2 (`{"version": 2, "scope": "user", "servers": {...}}`) by claude-sync v3.0.0 and later. **A machine still running claude-sync v2.x will overwrite this file with the old array format and drop servers whose command contains spaces** — upgrade every machine before backing up from any of them.
