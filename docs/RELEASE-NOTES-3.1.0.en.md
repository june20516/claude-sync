# claude-sync 3.1.0

Closes five defects found by taking apart the output of the first real backup run on a machine
upgraded to 3.0.0, plus the two items 3.0.0 deferred. **The backup file format does not change** —
machines on 3.0.0 and 3.1.0 can be mixed, and there is no upgrade ordering constraint.

## Five sentences that were false — and what they say now

- **"The remote has newer changes."** It said that even for files with no comparison base. Following that advice and picking "take the backup" in restore throws local changes away. Now, when there is no base, it says: "There is no base to compare against, so neither side can be called newer. Picking «take the backup» discards your local changes." `/sync-status` labels the same file "no base" instead of "changed on both sides".
- **A backup-only machine never grew file baselines.** Files that already matched the repo did not get a baseline written, so the sentence above kept coming back forever. Now they do — and a later repo-only change becomes a quiet download rather than a conflict.
- **`sync-metadata.json` recorded content that was not in the repo as if it were.** It walked this machine's local tree. It now walks the repo working tree, so files pushed by other machines are listed too. No production code reads this map, and the README claim that it feeds 3-way conflict detection is fixed.
- **"Another machine added this. Restore will install it." ×7, "cannot be restored" ×7.** Account connectors that 2.x scraped out of `claude mcp list` stayed in the repo permanently and produced false sentences on every run. No machine had them locally, so merging could never remove them. Now `/sync-backup` shows the list with a reason for each and **asks whether to clean them out of the repo.** If you say yes, the plugin deletes, commits and pushes. `/sync-status` and `/sync-restore` no longer claim those entries will be installed.
- **"Restore the file to valid JSON and run again."** Five places said that when a repo document had broken syntax — the actor was the user, and in that state all three skills skip the document, so there was no way out. Now `/sync-backup` finds the last healthy version in git history and **asks whether to roll back**; if you say yes, the plugin does it. `/sync-restore` and `/sync-status` diagnose and point there.

## New

- **Cleaning up unrestorable entries** (`/sync-backup`, step 6.5). It asks once for the whole list. It states that the judgement is based on the formats *this version* knows, and that a server another machine really uses comes back through that machine's next restore, which asks first. It does not offer the cleanup at all when a downgrade is suspected.
- **Broken-syntax recovery** (`/sync-backup`, step 4.5). Same place and same shape as downgrade recovery. The manual "fix it yourself" instruction survives only where no candidate commit was found.
- **Output language** — put `"language": "en"` in `~/.claude/sync-config.json` and everything the skills say to you comes out in that language. Commands, JSON keys, paths and names are never translated. The very first setup question is asked in whatever language you are talking in. Absent means Korean.

## Other changes

- The MCP restore plan JSON now has the same two layers as the plugin plan (`sections[<section>]` for buckets, top level for execution material). Nothing changes for users.
- The READMEs gained a section listing all five configuration keys.

## Upgrading from 3.0.0

No ordering constraint. On each machine run `claude plugin marketplace update claude-sync && claude plugin update claude-sync` and restart. The first `/sync-backup` writes file baselines, and offers to clean up any unrestorable entries left in the repo.
