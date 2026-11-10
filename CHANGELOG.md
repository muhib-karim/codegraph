# Changelog

## [Unreleased]

### Added

- Labelled TypeScript/JavaScript evaluation questions: a new `workflow_ts`
  fixture (an order/receipt pipeline in `.ts`, `.tsx`, ESM `.js`, `.mjs` and
  CommonJS `.cjs`, with TS<->JS imports and runtime-dispatch cases the graph is
  expected to miss) and 24 questions across all five kinds, 12 TypeScript and
  12 JavaScript. The suite now has 74 questions.
- An optional `language` field per question (`python`, `java`, `typescript`,
  `javascript`), validated when present and set on every shipped row. The
  report has a `by_language` JSON section and a "By language" table with graph
  and text rows per language.
- `make check` (lint, typecheck and test in one target) and `make eval-drift`
  (run the evaluation and fail when the committed `eval/reports` no longer
  match).

### Changed

- `eval/reports/` and the README evaluation table were regenerated. Scores of
  the 50 existing questions are unchanged; the overall numbers move because of
  the new questions. The site's graph demo now also includes the `workflow_ts`
  fixture.
- `make install` upgrades pip, setuptools and wheel in the new virtual
  environment before installing the package.
- CI bootstraps with `make install` and runs `make check` and
  `make eval-drift`. A new push to a pull request cancels the run it
  supersedes; runs for pushes are never cancelled.
- The README "Development and container" section is now "Development", with
  the container commands under their own heading.

### Fixed

The resolver fixes below remove wrong `exact` edges and add missing ones. The
evaluation reports are unchanged, because the labelled fixtures do not contain
these patterns.

- A parameter or other untyped local no longer takes the type of an outer
  variable or class field it shadows. `x = Foo()` at module level followed by
  `def go(x): x.run()` stored an `exact` call to `Foo.run`; the same happened
  for a parameter named like a `self.x = Foo()` attribute or a TS/JS class
  field of known type. Such calls now use the unique-name heuristic.
- The type of an inherited field is resolved in the file that declares the
  field. In Python a same-named class in the subclass's module received the
  `exact` edge. In Java, calls, field reads and method references through a
  field inherited from another package were counted as external and stored
  no edge.
- Python: a bare-name default parameter value (`def run(cb=helper)`) is a
  reference to that name. Before, `helper` could be listed as dead code. A
  typed `*args` parameter no longer records its own name as a reference.
- Python: a lambda parameter shadows a function or variable of the same name
  when it is called or used as a receiver, not only when it is read.
- Python: reading `self.name` or `cls.name` is a reference to the method or
  property `name` in any position, including the right side of an assignment
  and inside operators and comparisons. Assigning to `self.name` is not.
- TypeScript/JavaScript: a named function declared inside a callback of a
  function keeps its call and reference edges. Before, it had none and was
  listed as likely dead code.
- Java: a record's compact canonical constructor has the arity of the record
  components, so `new Pair(1, "a")` is an `exact` call. Its symbol ID changes
  from `Pair.<init>/0` to `Pair.<init>/2` for a two-component record.
- `codegraph index` on a path that is not a directory prints an error and
  exits with 1. Before, a mistyped path was created and "indexed" as an empty
  repository, and a file path ended in a traceback. `indexer.index` raises
  `NotADirectoryError`.

## [1.1.0] - 2026-10-22

### Added

- TypeScript and JavaScript indexing (`.ts`, `.tsx`, `.mts`, `.cts`, `.js`,
  `.jsx`, `.mjs`, `.cjs`) with the same query surface as Python and Java: ES
  imports, CommonJS `require`/`module.exports`, default exports, re-export
  barrels, classes, interfaces, enums, TS parameter properties, typed and
  constructed locals and JSX component use. New `web` (TS/TSX) and `webjs` (JS)
  fixture repositories with query-level tests.
- MCP tools `search` (ranked name search) and `impact` (the documented name for
  blast radius; `blast_radius` remains). CLI commands `callees`, `search` and
  `impact` (alias of `blast`).
- `docs/MCP.md` with Claude Code and Codex CLI setup, kept in sync with the
  tested README configuration by a test.
- `bench/run.py` and a `benchmark` CI job: index time, peak RSS and query
  latency on pinned requests, zod and gson checkouts. Results in
  `bench/results/` are copied unchanged from CI run 39707970318.
- GitHub Pages site (`site/`, `scripts/build_site.py`, Pages workflow) with a
  static graph demo built from a bundled index of the test fixtures, the real
  CLI session and the benchmark table.
- CI: gitleaks, CodeQL (Python, JavaScript/TypeScript, Actions) and Dependabot
  (pip, Actions, Docker).

### Changed

- mypy strict now covers the whole package, `bench/` and `scripts/` (previously
  three modules).
- Callee lookup moved into `queries.py` so the CLI and MCP server share it.
- The MCP server instructions mention all four languages and the `search` tool.

### Fixed

- Indexing failed or silently truncated symbol annotations when the first
  quoted CSV field appeared after many unquoted rows (for example a function
  with two decorators late in a large file): LadybugDB's CSV dialect sniffing
  turned quoting off. The bulk load now passes an explicit dialect. Found by
  indexing psf/requests in the new benchmark.
- Index statistics list `files_with_syntax_errors`: files the parser recovered
  from, where some declarations may be missing.

The graph schema is unchanged; 1.0.0 indexes remain readable, but rebuild them
to pick up TypeScript and JavaScript files.

## 1.0.0

- Add an optional official-SDK MCP server over stdio with read-only symbol,
  caller, callee, inheritance, unused-candidate, impact and status tools.
- Reject MCP path arguments outside the indexed repository, bound response
  sizes and keep the stored confidence tag on every result.
- Store SHA-256 content hashes at index time so `index_status` can report
  stale, added and deleted files. Snapshots built before 1.0.0 report unknown
  freshness.
- Replace `eval/codegraph_adapter.py`, which required an external harness,
  with the in-repository `codegraph eval` suite: 50 labelled Python/Java fixture
  questions, a lexical baseline, per-kind/confidence metrics and JSON/Markdown
  evidence. These scores are not comparable with the old harness.
- Release version 1.0.0 with Python 3.11/3.12 CI, lint/format checks, strict
  typing for new modules, package coverage gating, Docker, development commands
  and contributor/security documentation. Cap the database buffer pool at
  64 MiB and database workers at two for small local workloads.
- Preserve existing CLI query output and explorer behavior. Extend parser and
  resolver regression coverage; retain fixture failures for runtime dispatch,
  same-arity overloads and bare-name lookup precedence.

## 0.2.0

- Add a read-only loopback explorer, packaged static assets, graph neighborhoods,
  source previews, path guards, pagination and snapshot notices.
- Add URL state restoration, keyboard/status affordances and tests for local
  assets, query parity and source containment in follow-up explorer work.

## 0.1.0

- Introduce clean-room Python and Java extraction with Tree-sitter, two-pass
  resolution and embedded graph storage.
- Add callers, inheritance, unused candidates and blast-radius CLI queries,
  confidence tags and file:line citations.
- Record unsupported-language coverage and publish the original design contract.
