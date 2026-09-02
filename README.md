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
| `/sync-restore` | Restore settings from a Git repo (conflicting files are left untouched and resolved interactively) |
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

If an entry was deleted or changed on another machine, `/sync-restore` asks about it one at a time (remove / keep / later, or adopt repo value / keep local / later). The same three choices apply to MCP servers, plugins, marketplaces, and plugin config keys.

**Option 2: bootstrap.sh (works without Claude Code)**

```bash
git clone <backup-repo-url> /tmp/claude-sync-repo
bash /tmp/claude-sync-repo/bootstrap.sh
```

### Check before applying changes

```
/sync-status
```

## Configuration

`~/.claude/sync-config.json` is created on the first run and holds these keys:

| Key | Required | Meaning |
|---|---|---|
| `repo_url` | yes | Git URL of the backup repo |
| `git_user_name` / `git_user_email` | no | Local git identity for the backup clone. The clone lives in a temp dir, so `includeIf` rules may not apply |
| `pull_only` | no | `true` makes this machine restore-only — `/sync-backup` refuses to run |
| `language` | no | Language for everything the skills say to you, e.g. `"en"`. Prose is translated at output time; commands, JSON keys, paths and names are never translated. Absent means Korean |

## Upgrading to v3.0.0 (read this first)

v3.0.0 changes the `mcp-servers.json` and `plugins.json` schemas and **is not backward compatible**.

> **While any machine is still on v2.x, do not run `/sync-backup` on it — this holds even if you use no MCP servers at all.** The v2 backup step rebuilds *both* backed-up documents from that machine alone, without reading the repo copy, so a single run undoes the repo copy of each:
>
> - `mcp-servers.json` — rebuilt in the old array format from that machine's `claude mcp list` output alone, so servers that exist **only on another machine** are erased from the repo, and servers whose command contains spaces are erased **including that machine's own**.
> - `plugins.json` — rebuilt from that machine's `settings.json`, of which v2 copies only `enabledPlugins` and `extraKnownMarketplaces`. Entries that exist **only on another machine** are erased from the repo, and `pluginConfigs` and `additionalMarketplaces` are erased **including that machine's own**, because v2 does not know those keys at all.
>
> A v2 `/sync-status` will also abort with a `TypeError`. And nothing stops the v2.x machine itself: the `min_reader_version` marker v3.0.0 writes only blocks a reader **older than** the version it names, and **v2.x has no code that reads the marker** — that guard first shipped in v3.0.0. Upgrade order is the only thing that prevents this.

Upgrade every machine first:

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync    # restart required to apply
```

Then run the two commands in this order. **Do not run `/sync-backup` on every machine.**

1. **One machine backs up.** A single `/sync-backup` migrates the repo to the new format.
2. **Every other machine restores first.** Run `/sync-restore` before that machine's first `/sync-backup`. It has no shared base yet, so entries present on both sides are all reported as changed on both sides and it asks about each one — that is the mechanism that keeps your choices, not a defect. Answer once and the base is written; later runs are quiet.

Backing up first on a machine with no base does **not** ask: the merge falls back to a union and **the local value silently overwrites the repo value for every shared entry, with no conflict reported.** Entries this machine does not have are kept, so nothing is deleted — but a value you set elsewhere can be replaced without a word.

From v3.0.0 on, a machine that meets a backup it cannot recognize skips that step — the MCP step and the plugin step both follow this rule — leaves the repo file untouched, and tells you to update the plugin, so this class of damage cannot repeat in later upgrades.

## Sync Behavior Model (v3.0.0+)

claude-sync uses a **content-hash, git-like 3-way reconcile** — modification timestamps are never used.

- **Restore is pull-only.** `/sync-restore` never auto-pushes local changes to the repo.
- **New files are always added.** Files that exist only in the repo (new agents, skills) are always applied to the local machine, independent of any conflicts in other files. Plugins and MCP entries follow the same intent but are not unconditional: a plugin whose marketplace fails to register is reported as blocked, an entry this machine cannot reproduce is reported as unrestorable, and an MCP server whose secret you skip is not registered.
- **Conflicts arise only when both sides diverged from the last shared base.** In that case the tool attempts a `git merge-file` 3-way merge. If the changes do not overlap, the result is committed automatically (`auto_merge`). If the same lines were changed on both sides, the file is listed as a `conflict` and the local copy is left untouched. You then choose one of: keep local / adopt backup / merge manually / defer.
- **`pull_only` machines never back up.** Machines designated as read-only consumers will never push their state to the repo.
- **MCP servers merge per server name.** `mcp-servers.json` is reconciled key by key, so a backup from one machine never drops servers that only exist on another — **as long as every machine is on v3.0.0 or later** (a v2.x backup erases them; see *Upgrading to v3.0.0* above). Deletions do propagate, and `/sync-restore` asks per server before removing anything locally.
- **`plugins.json` merges key by key.** Plugin entries, marketplaces, and plugin config keys are reconciled individually, so a backup from one machine never drops entries that only exist on another — **as long as every machine is on v3.0.0 or later** (a v2.x backup erases them; see *Upgrading to v3.0.0* above). Deletions propagate, and `/sync-restore` asks before removing anything locally.

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
- **Metadata tracking**: `sync-metadata.json` lists a content hash of every file this backup contains. It is a record, not an input — conflict detection compares against each machine's own `.sync-state/` base, never against this file

## Security

Your `CLAUDE.md` or agent files may contain sensitive information such as internal URLs or company-specific rules. **It is strongly recommended to keep your backup repo private.**

To exclude specific files from backup, create `~/.claude/.syncignore` — **glob patterns, one per line**, matched against the path relative to the repo root (`#` starts a comment). This is not gitignore syntax: there is no negation (`!`) and a trailing slash matches nothing, so name a directory without one.

```
# Exclude internal agents
agents/internal-*.md

# Exclude specific skills (no trailing slash)
skills/secret-tool
```

When sharing your settings with others, use `.syncignore` to filter out sensitive files before backing up.

**`.syncignore` means one thing — "do not upload" — and it applies to the backup direction only.**

- **Backup removes the path from the repo.** It is not merely skipped: `/sync-backup` deletes every match from the repo working tree and commits that deletion. **A copy another machine had already pushed at the same path is deleted too**, for everyone.
- **Restore ignores `.syncignore`.** `/sync-restore` never reads the file, so a repo file at an excluded path is reconciled exactly like any other — added if it is new, overwritten if the repo is ahead, merged if both sides changed. This is deliberate: honouring the list on the way in would mean never receiving a file another machine pushed at that path. **Excluding a path does not protect the local file from being overwritten** — it only keeps your copy out of the repo.
- **`/sync-status` reports the two cases differently.** An excluded file that is not in the repo is not listed at all. One that is still in the repo is listed on its own line — "excluded but still in the repo (backup will delete it there)" — because calling it a pending push would be false and staying silent about it would be false too.
- **It cannot exclude `plugins.json` or `mcp-servers.json`.** Both are regenerated by later steps than the one that applies the exclusions, so a pattern for them has no effect. Their sensitive values are masked instead; the key names are kept.
