# Project brain: codegraph

Handoff note for the next session. Keep it short.

## What this is

Code graph for Python, Java and (from 1.1.0) TypeScript/JavaScript: index a repository
into an embedded graph database, then answer callers / callees / impact / search queries
with `file:line` citations from the CLI, an MCP server or a loopback explorer.

## Status

v1.1.0 implemented on `upgrade/v1.1.0`: TS/JS indexing, MCP search/impact, CI
benchmark, Pages site (live, homepage set), mypy strict package-wide,
gitleaks/CodeQL/Dependabot. Code review done and all findings fixed.

## Next step

Refresh the benchmark table from the CI run on the final code, confirm CI +
CodeQL + Pages green on the pushed head. Coordinator: merge, then tag v1.1.0.

## Gotchas

- Run pytest with `-x -q -p no:cacheprovider`, one process at a time (small machine).
- `eval/reports/latest.*` are checked in CI with `git diff --exit-code`; regenerate with `codegraph eval`.
- Indexing rebuilds the database in place; close explorer/MCP readers first.
- LadybugDB CSV COPY must pass an explicit dialect (auto-detect drops quoting).
- CodeQL skips minified JS; keep `site/demo.js` readable.
- Never point a test at a real path for anything that deletes: `build_site.py`
  output is guarded by `check_out()`; test the guard, not the deletion.

## Session log
2026-10-22 01:58Z Claude Code/Opus 5.5: v1.1.0 features, review fixes, docs; next: bench refresh from CI, final push, PU_DONE.
