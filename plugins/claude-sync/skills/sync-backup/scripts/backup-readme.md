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
- `plugins.json` — Plugin list, marketplaces, and plugin config key names (extracted from settings.json; config values masked)
- `sync-metadata.json` — Per-file modification timestamps (for conflict detection)
- `mcp-servers.json` — MCP server configs from `~/.claude.json` (user scope), merged per server name
- `bootstrap.sh` — Restore script for new devices

### About `mcp-servers.json`

Values under `headers` and `env` are stored as `<REDACTED>`; the key names are kept so a restore knows what to ask for. **Secrets passed through `args` or a URL query string are not masked** — keep this repository private. When you restore, `/sync-restore` prompts for each masked value; skipping a prompt leaves that server unregistered rather than creating one with broken auth.

This file is merged **per server name**, so backing up from one machine will not drop servers that only exist on another. `plugins.json` is merged the same way, key by key, across its three sections.

The file is written in schema v2 (`{"version": 2, "scope": "user", "servers": {...}}`) by claude-sync v3.0.0 and later. **A machine still running claude-sync v2.x will overwrite this file with the old array format and drop servers whose command contains spaces** — upgrade every machine before backing up from any of them.

### About `plugins.json`

Not synced:

- Marketplace **auto-update settings** (`autoUpdate`) — the CLI has no option to set them
- **Marketplaces registered from a local directory, and the plugins that belong to them** — another machine has no source to register them from
- **Plugins installed automatically as dependencies** — restoring the parent brings them along
- **Plugins that a marketplace installs through a command** — they cannot be installed inside a session, so your own terminal is needed
- **The values of version constraints (arrays/objects)** — such a plugin is installed, but the constraint itself is not reproduced on this machine. The repo value is preserved; to give it up, choose "unify on this machine's value" during a restore. **That comes first if you want it gone**
- **Plugin config values** — they are stored masked and re-entered during a restore. You may skip them
- **Hold decisions** (`~/.claude/.sync-state/plugins-held.json`) — they stay on this machine and never spread to another. Delete the file and you are asked again
