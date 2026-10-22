# Skills used

Which agent skill drove which change. Only skills that were actually loaded and
followed are listed under "Used"; the rest are named with the reason they were not.

## v1.1.0

### Used

| Skill | What it drove |
|---|---|
| writing-plans | `TASKS.md`: plan header, global constraints copied from the brief, a Review Focus list of five risk inputs (module resolution order, default exports and barrels, local shadowing, syntax-error recovery, MCP input validation) and right-sized tasks with checkboxes. |
| test-driven-development | Failing tests first for the TS/JS extractor and resolver (`tests/test_typescript.py`: collection error, then a failing `callers` query), MCP `search`/`impact` and CLI `callees`/`search`/`impact` (six failing tests before the code), the CSV bulk-load regression (the red run showed a silently truncated `"first` annotation) and every code-review fix. Exception, disclosed: `bench/run.py` was written before `tests/test_bench.py`. |
| impeccable | The Pages site. The context loader found no product brief, so the page extends the established visual world of the explorer and banner (navy ground, teal accent, amber for heuristic) instead of inventing one. Craft-floor checks applied: no eyebrow labels, gradient text or card grids; tabular numerals in the benchmark table; themed selection, scrollbar and focus rings; one authored motion (the impact ripple) that respects reduced motion. Two batched screenshot rounds at 1440 px and 390 px found and fixed a cramped force layout, a demo below the first viewport, a legend overlapping the inspector on phones and broken quickstart steps. |
| requesting-code-review | One reviewer subagent on `e0940ae..15e39b9`. No critical findings; three important ones (exponential time on cyclic `export *`, declarations inside callbacks and module-level blocks leaking to module scope, JS globals such as `console.log` matching repo methods by unique name) and six minor ones, all fixed with tests. See `HANDOFF.md`. |
| verification-before-completion | Final gate: ruff, mypy strict, pytest with coverage, evaluation drift check, CI and CodeQL green on the pushed head, Pages URL returning 200, before declaring done. |

### Not used, and why

- ui-ux-pro-max: not loaded; impeccable covered the page and the incumbent design language already fixed palette and type.
- understand-anything, graphify, archify: not loaded. The architecture diagram in the README was written from the module layout in `codegraph/`; it is a Mermaid flowchart so GitHub renders it without generated assets.
- brainstorming: the brief was frozen and the continuation rule ruled out interactive questions.
- systematic-debugging: not loaded as a skill. The CSV and CodeQL failures were investigated root-cause first (read the error, reproduce minimally, then fix), which is that skill's method, but the credit goes to the method, not the skill file.
- Android, Compose, design-asset, document and messaging skills: outside this project's scope.
