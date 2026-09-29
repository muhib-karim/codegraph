# Changelog

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
