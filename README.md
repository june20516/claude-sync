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
- `~/.claude/settings.json` -> `plugins.json` — Plugin/marketplace list (sensitive data excluded)
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
- **`plugins.json` is still overwritten wholesale.** It is not part of the per-file reconcile, so the last machine to back up wins for the plugin list. This is a known limitation.

## Safety

- **Conflict detection**: Files changed on both sides since the last known base are flagged as conflicts; local copies are never silently overwritten.
- **Sensitive data protection**: The raw `settings.json` is never pushed — only the plugin list is extracted. MCP server configs are pushed with `headers`/`env` values masked as `<REDACTED>`
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
