# claude-sync

A Claude Code plugin that syncs your settings across devices via a Git repository.

## Installation

```bash
claude plugin marketplace add claude-sync --source github --repo june20516/claude-sync
claude plugin install claude-sync@claude-sync
```

## Skills

| Command | Description |
|---------|-------------|
| `/sync-backup` | Back up local settings to a Git repo and push |
| `/sync-restore` | Restore settings from a Git repo (aborts safely on conflicts) |
| `/sync-status` | Show differences between local and repo (dry-run) |

## What Gets Synced

- `~/.claude/agents/` — Custom agents
- `~/.claude/skills/` — General-purpose skills
- `~/.claude/CLAUDE.md` — Global rules
- `~/.claude/settings.json` -> `plugins.json` — Plugin list, marketplaces, and plugin config **key names** (config values are masked)
- `~/.claude.json` (user scope) -> `mcp-servers.json` — MCP server configs, with secret values masked

Only the top-level `mcpServers` object in `~/.claude.json` (the *user* scope) is synced. Account-level connectors (`claude.ai *`), plugin-provided servers (`plugin:*`), and project/local scope servers (`.mcp.json`, `projects[*].mcpServers`) are not in that object, so they are excluded automatically. Values under `headers` and `env` are replaced with `<REDACTED>` while the key names are preserved, so a restore knows which credentials to ask for. Keys passed through `args` or a URL query string are **not** masked.

## Usage

### Back up from an existing device

```
/sync-backup
```

On first run, you'll be prompted for a backup Git repo URL. It will be reused automatically after that.

### Restore on a new device

**Option 1: Install the plugin first, then restore**

```bash
claude plugin marketplace add claude-sync --source github --repo june20516/claude-sync
claude plugin install claude-sync@claude-sync
```

Then in Claude Code:

```
/sync-restore
```

If a server was deleted or changed on another machine, `/sync-restore` asks about it one server at a time (remove / keep / later, or adopt repo value / keep local / later).

**Option 2: bootstrap.sh (works without Claude Code)**

```bash
git clone <backup-repo-url> /tmp/claude-sync-repo
bash /tmp/claude-sync-repo/bootstrap.sh
```

### Check before applying changes

```
/sync-status
```

## Upgrading to v3.0.0 (read this first)

v3.0.0 changes the `mcp-servers.json` schema and **is not backward compatible**.

> **While any machine is still on v2.x, do not run `/sync-backup` on it.** The v2 backup step regenerates `mcp-servers.json` wholesale without reading the repo copy, so a single run rewrites the v3 file back to the old array format — and servers whose command contains spaces are dropped entirely. A v2 `/sync-status` will also abort with a `TypeError`.

Upgrade every machine first, then back up:

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync    # restart required to apply
```

From v3.0.0 on, a machine that meets a backup it cannot recognize skips the MCP step, leaves the repo file untouched, and tells you to update the plugin — so this class of damage cannot repeat in later upgrades.

## Sync Behavior Model (v3.0.0+)

claude-sync uses a **content-hash, git-like 3-way reconcile** — modification timestamps are never used.

- **Restore is pull-only.** `/sync-restore` never auto-pushes local changes to the repo.
- **New files are always added.** Files that exist only in the repo (new agents, skills, plugins, MCP entries) are always applied to the local machine, independent of any conflicts in other files.
- **Conflicts arise only when both sides diverged from the last shared base.** In that case the tool attempts a `git merge-file` 3-way merge. If the changes do not overlap, the result is committed automatically (`auto_merge`). If the same lines were changed on both sides, the file is listed as a `conflict` and the local copy is left untouched. You then choose one of: keep local / adopt backup / merge manually / defer.
- **`pull_only` machines never back up.** Machines designated as read-only consumers will never push their state to the repo.
- **MCP servers merge per server name.** `mcp-servers.json` is reconciled key by key, so a backup from one machine never drops servers that only exist on another. Deletions do propagate, and `/sync-restore` asks per server before removing anything locally.
- **`plugins.json` merges key by key.** Plugin entries, marketplaces, and plugin config keys are reconciled individually, so a backup from one machine never drops entries that only exist on another. Deletions propagate, and `/sync-restore` asks before removing anything locally.

Not synced:

- Marketplace **auto-update settings** (`autoUpdate`) — the CLI has no option to set them; edit `~/.claude/settings.json` on each machine if you need them
- **Marketplaces registered from a local directory, and the plugins that belong to them** — another machine has no source to register them from; run `claude plugin marketplace add` there yourself
- **Plugins installed automatically as dependencies** — restoring the parent brings them along
- **Plugins that a marketplace installs through a command** — they cannot be installed inside a session, so your own terminal is needed
- **The values of version constraints (arrays/objects)** — such a plugin is installed, but the constraint itself is not reproduced on this machine. The repo value is preserved; to give it up, choose "unify on this machine's value" during a restore. **That comes first if you want it gone**
- **Plugin config values** — they are stored masked and re-entered during a restore. You may skip them
- **Hold decisions** (`~/.claude/.sync-state/plugins-held.json`) — they stay on this machine and never spread to another. Delete the file and you are asked again

## Safety

- **Conflict detection**: Files changed on both sides since the last known base are flagged as conflicts; local copies are never silently overwritten.
- **Sensitive data protection**: The raw `settings.json` is never pushed — three fields are extracted and `pluginConfigs` values are masked as `<REDACTED>` (key names are kept so a restore knows what to ask for). MCP server configs are pushed with `headers`/`env` values masked the same way
- **Metadata tracking**: Each backup records a content-hash base snapshot for accurate 3-way conflict detection

## Security

Your `CLAUDE.md` or agent files may contain sensitive information such as internal URLs or company-specific rules. **It is strongly recommended to keep your backup repo private.**

To exclude specific files from backup, create `~/.claude/.syncignore` (gitignore format):

```
# Exclude internal agents
agents/internal-*.md

# Exclude specific skills
skills/secret-tool/
```

When sharing your settings with others, use `.syncignore` to filter out sensitive files before backing up.
