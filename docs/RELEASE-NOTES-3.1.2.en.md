# claude-sync 3.1.2

Fixes **two false sentences** found while finishing 3.1.0's real-device smoke test. Behaviour is
unchanged — this is about what the tool says to you, and one source comment.

## What was false

**When a repo document had broken syntax, the scripts still told you to fix it by hand.**
3.1.0 removed that instruction from six lines across the three `SKILL.md` files — but the same
sentence also lived in the `reason` produced by the core (`lib/keyed_sync.py`):

> `…이 문서를 건너뛴다. 파일을 정상 JSON으로 고친 뒤 다시 실행한다`
> ("…skipping this document. Restore the file to valid JSON and run again.")

All three `SKILL.md` files instruct the agent to **show `reason` verbatim**, so fixing the prose
did not stop that instruction from reaching you through the script message. Observed in the real
output during the 2026-09-02 smoke test.

The core now states **only what happened**. The remedy belongs to the skill — recovery is
`/sync-backup` step 4.5 finding the last healthy version in git history and asking whether to roll
back, and the core does not know which skill is running. The neighbouring `UnknownBackupSchema`
was already shaped that way (it states the fact; "update the plugin" lives in `SKILL.md`);
`broken_syntax` was the odd one out.

**A comment in step 10 claimed "runs on all three shells".** It was added in 3.1.1 when `mapfile`
became a `while read` loop, but POSIX `sh` has no process substitution (`< <(…)`), so the claim is
false. What actually runs is bash and zsh — which is exactly what the test parametrizes over. Only
the comment was out of step.

## Preventing a repeat

Both cases come from **a claim that was not tied to a measurement** — the same shape as the
`mapfile` miss.

- A guard now checks that the core's `reason` does not prescribe a manual repair. The banned-phrase
  list carries a **count assertion** so the list cannot silently shrink.
- A guard now checks that the shells named in the step-10 comment match the shells the test suite
  actually parametrizes over.

## Impact

The backup file format does not change. `SCHEMA_VERSION` (2) and `MIN_READER_VERSION` (3.0.0) are
unchanged, so this mixes freely with any 3.0.0+ machine with no ordering constraint.

## Upgrading from 3.1.1

```
claude plugin marketplace update claude-sync && claude plugin update claude-sync
```

Restart and you are done — nothing else to do, since no data is affected.
