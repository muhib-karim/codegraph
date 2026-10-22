# Changelog

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
  `bench/results/` are copied unchanged from CI run 39705868795.
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
