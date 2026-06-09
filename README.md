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
- `claude mcp list` -> `mcp-servers.json` — MCP server list (name, URL, type)

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

**Option 2: bootstrap.sh (works without Claude Code)**

```bash
git clone <backup-repo-url> /tmp/claude-sync-repo
bash /tmp/claude-sync-repo/bootstrap.sh
```

### Check before applying changes

```
/sync-status
```

## Sync Behavior Model (v2.0.0+)

claude-sync uses a **content-hash, git-like 3-way reconcile** — modification timestamps are never used.

- **Restore is pull-only.** `/sync-restore` never auto-pushes local changes to the repo.
- **New files are always added.** Files that exist only in the repo (new agents, skills, plugins, MCP entries) are always applied to the local machine, independent of any conflicts in other files.
- **Conflicts arise only when both sides diverged from the last shared base.** In that case the tool attempts a `git merge-file` 3-way merge. If the changes do not overlap, the result is committed automatically (`auto_merge`). If the same lines were changed on both sides, the file is listed as a `conflict` and the local copy is left untouched. You then choose one of: keep local / adopt backup / merge manually / defer.
- **`pull_only` machines never back up.** Machines designated as read-only consumers will never push their state to the repo.

## Safety

- **Conflict detection**: Files changed on both sides since the last known base are flagged as conflicts; local copies are never silently overwritten.
- **Sensitive data protection**: The raw `settings.json` is never pushed to the repo — only plugin and MCP server lists are extracted
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
