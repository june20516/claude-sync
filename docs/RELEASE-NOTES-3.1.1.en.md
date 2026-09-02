# claude-sync 3.1.1

Fixes one portability defect that 3.1.0's real-device smoke test caught. **Upgrade if you are on
3.1.0** — on that version file baselines are silently never written.

## What was wrong

Step 10 of `/sync-backup` collected the base-update list with `mapfile`. That is a bash 4+
builtin, and it exists **neither in macOS's stock bash (3.2) nor in zsh**. On those shells the
line dies with `command not found`, the array stays empty, and the next gate reads it as zero —
so `update_base.py` is **never called at all**.

No error, no warning, no report. The exit code is 0 and the backup looks like it succeeded.
Only the outcome regresses to the very defect 3.1.0 set out to fix (②): a machine that only ever
backs up never grows file baselines, so every run keeps calling those files "no base — neither
side can be called newer".

## What changed

- `mapfile` is now a `while read` loop. It runs on both bash 3.2 and zsh.
- **A guard that actually executes that block was added.** The previous guard only compared the
  block's **text**, which is why this slipped through. Step 4's `.syncignore` block already had
  an executing guard; step 10 did not — that gap is now closed.
- The release-notes guard derives its filenames from the version instead of hardcoding them.
- The real-device checklist now states that "8 file baselines unchanged" in step 3-3 does **not**
  measure ② — those eight already exist from the previous run, so the assertion is vacuous.

## Impact

The backup file format does not change. `SCHEMA_VERSION` (2) and `MIN_READER_VERSION` (3.0.0) are
unchanged, so machines on 3.0.0, 3.1.0 and 3.1.1 mix freely with no ordering constraint.

If a machine already ran a backup on 3.1.0, the repo and your local settings are fine — the only
thing missing is **that machine's file baselines**. Upgrade and run `/sync-backup` once more and
they get written.

## Upgrading from 3.1.0

```
claude plugin marketplace update claude-sync && claude plugin update claude-sync
```

Restart, then run `/sync-backup` once. Check that per-file baselines now exist under
`~/.claude/.sync-state/base/`.
