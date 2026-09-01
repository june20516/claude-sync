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
- `plugins.json` — Plugin list, marketplaces, and plugin config key names (extracted from settings.json; config values masked), merged key by key
- `sync-metadata.json` — Version markers plus a per-file content hash of what this backup contained. Those hashes are a record, not an input: conflict detection compares against each machine's own `.sync-state/` base, not this file. What does get read back is `min_reader_version` — it blocks a machine too old to understand this backup.
- `mcp-servers.json` — MCP server configs from `~/.claude.json` (user scope), merged per server name
- `bootstrap.sh` — Restore script for new devices
- `.gitignore` — One line, `*.tmp`, so a half-written temp file left by a hard kill is never committed. Created by `bootstrap.sh`, so a repository whose machines all upgraded in place will not have it yet.

### Before backing up: every machine must be on v3.0.0

> **Do not run `/sync-backup` on a machine still running claude-sync v2.x** — this holds even if that machine uses no MCP servers at all. v2 rebuilds *both* backed-up documents from that machine alone, without reading what is in this repository, so a single run undoes the repo copy of each:
>
> - `mcp-servers.json` — rebuilt in the old array format from that machine's `claude mcp list` output alone, so servers that exist **only on another machine** are erased from the repo, and servers whose command contains spaces are erased **including that machine's own**.
> - `plugins.json` — rebuilt from that machine's `settings.json`, of which v2 copies only `enabledPlugins` and `extraKnownMarketplaces`. Entries that exist **only on another machine** are erased from the repo, and `pluginConfigs` and `additionalMarketplaces` are erased **including that machine's own**, because v2 does not know those keys at all.
>
> The `min_reader_version` marker in `sync-metadata.json` is there to block a machine too old to understand this backup. **A v2.x machine is exactly that machine — and it has no code that reads the marker**, because the guard first shipped in v3.0.0. Upgrade order is therefore the only thing that prevents this. Recovering afterwards means restoring those files from this repository's git history.

**Then: one machine backs up, every other machine restores first.** A machine that has never reconciled this repo has no shared base, so `/sync-restore` reports every entry present on both sides as changed on both sides and asks about each one. Answer once and the base is written. Running `/sync-backup` first on such a machine does not ask — the merge falls back to a union and **the local value silently replaces the repo value for every shared entry, with no conflict reported.**


### About `mcp-servers.json`

Values under `headers` and `env` are stored as `<REDACTED>`; the key names are kept so a restore knows what to ask for. **Secrets passed through `args` or a URL query string are not masked** — keep this repository private. When you restore, `/sync-restore` prompts for each masked value; skipping a prompt leaves that server unregistered rather than creating one with broken auth.

This file is merged **per server name**, so backing up from one machine will not drop servers that only exist on another — **as long as every machine is on v3.0.0 or later**.

The file is written in schema v2 (`{"version": 2, "scope": "user", "servers": {...}}`) by claude-sync v3.0.0 and later. **A machine still running claude-sync v2.x overwrites this file with the array it builds from its own `claude mcp list`** — see *Before backing up: every machine must be on v3.0.0* above, which covers `plugins.json` as well.

### About `plugins.json`

`plugins.json` is merged the same way, key by key, across its three sections — plugin entries, marketplaces, and plugin config keys are each reconciled individually, so backing up from one machine will not drop entries that only exist on another — **as long as every machine is on v3.0.0 or later**.

**A machine still running claude-sync v2.x does not do this merge** — it rebuilds the file from its own `settings.json`, so see *Before backing up: every machine must be on v3.0.0* above before you back up from anywhere.

Not synced:

- Marketplace **auto-update settings** (`autoUpdate`) — the CLI has no option to set them; edit `~/.claude/settings.json` on each machine if you need them
- **Marketplaces registered from a local directory, and the plugins that belong to them** — another machine has no source to register them from; run `claude plugin marketplace add` there yourself
- **Plugins installed automatically as dependencies** — restoring the parent brings them along
- **Plugins that a marketplace installs through a command** — they cannot be installed inside a session, so your own terminal is needed
- **The values of version constraints (arrays/objects)** — such a plugin is installed, but the constraint itself is not reproduced on this machine. The repo value is preserved; to give it up, choose "unify on this machine's value" during a restore. **That comes first if you want it gone**
- **Plugin config values** — they are stored masked and re-entered during a restore. You may skip them
- **Hold decisions** (`~/.claude/.sync-state/plugins-held.json`) — they stay on this machine and never spread to another. Delete the file and you are asked again
