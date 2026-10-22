# Handoff: codegraph v1.1.0

Branch `upgrade/v1.1.0`, cut from `main` at `e0940ae`. Not merged and no PR opened;
the coordinator reviews and merges.

## What shipped

| Definition of Done item | Where |
|---|---|
| 1. TypeScript/JavaScript indexing, same query surface, fixture tests per language | `codegraph/extract_ts.py`, JS binding in `codegraph/resolve.py`; fixtures `tests/fixtures/web` (TS/TSX) and `tests/fixtures/webjs` (JS); `tests/test_typescript.py` |
| 2. MCP server with callers/callees/impact/search, protocol-level test, Claude Code/Codex docs | `codegraph/mcp_server.py` (`search`, `impact` added; existing tools kept); `tests/test_mcp.py` (in-memory SDK session and a real stdio subprocess); `docs/MCP.md` and the README MCP section |
| 3. Benchmark on public repos, in CI on Linux, labelled runner + date | `bench/run.py`, `bench/repos.json` (requests, zod, gson at pinned tags), `benchmark` job in `.github/workflows/ci.yml`; committed numbers in `bench/results/` copied unchanged from a CI artifact |
| 4. Pages site: interactive graph demo from a bundled index, benchmark table, quickstart; homepage set; 200 verified | `site/`, `scripts/build_site.py`, `.github/workflows/pages.yml`; https://muhib-karim.github.io/codegraph/ returns 200 for the page, `data/graph.json`, `demo.js` and `style.css`; repo homepage set to that URL |
| 5. CI gates | ruff + format, mypy strict over `codegraph/`, `bench/`, `scripts/`, coverage >= 85% (about 89.5%), Python 3.11 + 3.12, gitleaks job, CodeQL workflow (Python, JS/TS, Actions), `.github/dependabot.yml` (pip, Actions, Docker) |
| 6. README, CHANGELOG `[1.1.0] - 2026-10-22`, version bump, SKILLS_USED.md, TASKS.md, HANDOFF.md | all at the repo root; version 1.1.0 in `pyproject.toml`, `codegraph/__init__.py`, `CITATION.cff`, Docker tag in CI |

The coordinator's note set the CHANGELOG date to 2026-10-22; the frozen brief said
2026-10-21.

Also fixed along the way: the database bulk load silently truncated or rejected quoted
CSV fields after many unquoted rows (LadybugDB dialect sniffing). Indexing psf/requests
failed before this fix.

## Repository settings changed (outside git)

- GitHub Pages enabled with build type "GitHub Actions".
- The `github-pages` environment allows deployments from `main` (default) and
  `upgrade/v1.1.0` (added so the site could be verified before merge). Remove the
  `upgrade/v1.1.0` policy after merging if you want deployments from `main` only.
- Repository homepage set to https://muhib-karim.github.io/codegraph/.

## After merge

1. The Pages workflow runs on `main` too and redeploys the same site.
2. Tag the merge commit `v1.1.0` and create the release from the CHANGELOG entry
   (the README release badge already says v1.1.0).
3. Dependabot will start opening weekly update PRs; CodeQL runs weekly as well.

## Code review

One reviewer subagent on `e0940ae..15e39b9`. No critical findings. All of the
following were fixed test-first in `d1f2623`:

- Important: cyclic `export *` chains made resolution exponential (23 s for 50 call
  sites); now each (file, name) is visited once per lookup and results are cached.
- Important: functions declared inside callbacks or module-level blocks became
  module-level symbols and took over outer names (wrong `exact` edges, wrong dead
  code); they now stay local.
- Important: `console.log`, `JSON.stringify` and other unbound JS receivers matched
  repo methods by unique name; they now count as external calls.
- Minor: syntax-error recovery is reported (`files_with_syntax_errors`); `search`
  accepts any name fragment; the CLI validates `search`; `export { foo as bar }` no
  longer exports `foo`; `build_site.py` refuses output paths that would delete
  sources; `bench/run.py` removes its temporary clones.

Not changed, by design: methods in object literals and anonymous callbacks have no
symbol of their own (calls inside them are attributed to the enclosing symbol), and
tsconfig path aliases and package imports are treated as external.

## Incident during this session

While writing the red test for the `build_site.py` output guard, the first version of
that test called the real build with the repository root as `--out`. The unguarded
`rmtree` deleted the local working copy, including one unpushed commit and some
uncommitted edits. Nothing on GitHub was affected and sibling directories were
untouched. The checkout was re-cloned from `origin/upgrade/v1.1.0` (`98b37c3`), the
repo-local git identity was re-applied unchanged, and the lost work was redone from
the session record and recommitted (`cf0b8c1`). The rewritten test exercises only the
pure `check_out()` guard, never a deleting build against a real path.

## Known limitations (also in the README)

- No labelled TS/JS questions in the evaluation suite yet; TS/JS correctness is
  covered by query-level tests, not by the 50-question evaluation.
- Receivers typed by a call result or a library are matched heuristically or not at
  all; JavaScript calls are not arity-checked.
- The explorer's `app.js` is minified, so CodeQL skips it; `site/demo.js` is the JS
  that CodeQL analyses.

## Verify locally

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,mcp]'
make lint typecheck test eval
git diff --exit-code eval/reports
.venv/bin/python bench/run.py --local tests/fixtures/web --out /tmp/bench
.venv/bin/python scripts/build_site.py --out _site
```
