# Project brain: codegraph

Handoff note for the next session. Keep it short.

## What this is

Code graph for Python, Java and (from 1.1.0) TypeScript/JavaScript: index a repository
into an embedded graph database, then answer callers / callees / impact / search queries
with `file:line` citations from the CLI, an MCP server or a loopback explorer.

## Status

v1.1.0 in progress on `upgrade/v1.1.0` (plan: `TASKS.md`). TS/JS indexing done: `extract_ts.py` + JS binding in `resolve.py`, fixtures `web` and `webjs`.

## Next step

Task 5 in `TASKS.md` (Pages site). Tasks 1-4 and 6 committed; benchmark numbers still to be copied from a CI run after the version bump.

## Gotchas

- Run pytest with `-x -q -p no:cacheprovider`, one process at a time (small machine).
- `eval/reports/latest.*` are checked in CI with `git diff --exit-code`; regenerate with `codegraph eval`.
- Indexing rebuilds the database in place; close explorer/MCP readers first.

## Session log

