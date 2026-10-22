# codegraph v1.1.0 Implementation Plan

> Execution: native (one session, task by task, TDD), then one whole-branch review.
> Steps use checkbox syntax; tick them as they land.

**Goal:** Ship v1.1.0: TypeScript/JavaScript indexing, MCP `search` and `impact` tools,
a CI benchmark on public repositories, a GitHub Pages site with a static graph demo,
and stricter CI gates.

**Architecture:** A new Tree-sitter extractor (`extract_ts.py`) emits the same
`FileInfo` records as the Python extractor. JS/TS imports are expressed as the same
`from`/`module` import records, so the resolver binds JS/TS names through the
lexical path already used for Python, with a JS module-path resolver. The storage
schema does not change (`SCHEMA_VERSION` stays 1).

**Tech stack:** Python 3.11/3.12, tree-sitter 0.23+ (`tree-sitter-typescript` for
`.ts` and the TSX grammar for `.tsx/.js/.jsx/.mjs/.cjs`), LadybugDB, MCP SDK, vanilla
JS + SVG for the Pages demo, GitHub Actions.

**Spec:** the frozen task brief (Definition of Done items 1-7), summarised under
Global Constraints.

## Global Constraints

- Branch `upgrade/v1.1.0`; push only through the gated push script; never push to main, never open the PR.
- CHANGELOG heading `## [1.1.0] - 2026-10-22`; version 1.1.0 everywhere.
- CI: ruff, mypy strict, coverage >= 85%, Python 3.11 + 3.12, gitleaks, Dependabot, CodeQL; all green.
- Benchmark numbers come only from real CI runs, labelled with runner and date.
- No storage-format change without asking first.
- No environment URLs, hostnames, tokens or keys in the repository.

## Review Focus

1. A JS file importing `./util` where both `util.ts` and `util/index.ts` exist: the file wins, like Node/TS resolution.
2. `export default` and re-export barrels (`export * from './x'`, `export { a as b } from './x'`) resolve to the real declaration.
3. Locals (`const x`, parameters, destructuring) shadow module-level names; no edge to the shadowed symbol.
4. A syntax error in one `.ts` file keeps the rest of the index (parser recovery, no crash).
5. MCP `search` with an empty or 512+ character query, or `limit` > 100, returns a tool error, not a crash.

---

### Task 1: TypeScript/JavaScript extractor
**Files:** create `codegraph/extract_ts.py`; modify `discover.py`, `indexer.py`, `model.py`; fixtures `tests/fixtures/web/` (TS) and `tests/fixtures/webjs/` (JS); test `tests/test_typescript.py`.
- [ ] Failing tests: symbols (class, interface, enum, function, arrow const, method, constructor, field), imports, bases.
- [ ] Implement `extract(path: str, src: bytes) -> FileInfo` (lang `typescript` or `javascript`).
- [ ] Tests pass; commit.

### Task 2: Resolver support
**Files:** modify `codegraph/resolve.py`; test `tests/test_typescript.py`.
- [ ] Failing query tests: `callers`, `callees`, `inherits`, `blast`, `dead-code` on both fixtures, with exact citations.
- [ ] Implement `js_module_file`, `js_bind`, re-export and default-export following; reuse the Python call/ref paths.
- [ ] Tests pass, eval report unchanged; commit.

### Task 3: MCP `search` and `impact`
**Files:** modify `service.py`, `mcp_server.py`, `tests/test_mcp.py`, README MCP section.
- [ ] `search(query, kinds, scope, limit, offset)`: case-insensitive substring over names and qualified names, exact matches first.
- [ ] `impact` = documented name for blast radius (`blast_radius` kept for compatibility).
- [ ] Protocol-level stdio test lists and calls both tools; Claude Code and Codex config documented and tested.

### Task 4: Benchmark
**Files:** create `bench/run.py`, `bench/repos.json`, `bench/README.md`, `bench/results/`; CI job `benchmark`.
- [ ] Pinned public repositories of increasing size; index time and median query latency per tool.
- [ ] CI uploads JSON + Markdown; commit numbers from a real CI run with runner, date and run id.

### Task 5: Pages site
**Files:** create `site/` (HTML, CSS, JS), `scripts/build_site.py`, `.github/workflows/pages.yml`.
- [ ] Static graph demo from a bundled sample index (JSON exported at build time), benchmark table, quickstart.
- [ ] Deploy via Pages workflow, set repo homepage, verify HTTP 200.

### Task 6: CI gates
- [ ] mypy strict over the whole package; gitleaks job; `.github/dependabot.yml`; CodeQL workflow.

### Task 7: Docs, version, release notes
- [ ] README refresh (banner, badges, demo screenshot, install, usage, MCP, mermaid architecture, roadmap).
- [ ] CHANGELOG, version bump, SKILLS_USED.md, HANDOFF.md.
- [ ] Push, CI green on head.

## Blockers

None so far.
