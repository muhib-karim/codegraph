# v1.0.0 interface addendum

The original graph schema remains version 1. Existing CLI query rows, including
call-site versus declaration citations, are retained. Package version and
question/report schema versions are independent.

`codegraph mcp --repo PATH | --db PATH` adds an optional official MCP SDK stdio
server. `GraphService` owns and closes a read-only database connection; no
client operation can rebuild, edit or select another database. Function-based
tools use typed SDK schemas, read-only annotations and structured results.
Selectors are parameterized. Repository paths must be indexed, relative and
contained after realpath resolution. Result paths are checked too.

`find_symbol` returns exact declaration evidence using the existing resolver.
`callees` queries direct CALLS edges, preserving target IDs and call sites.
The other relationship tools delegate to the existing query functions, with
bounded depth 1..10 and pages of 1..100 rows. `next_offset` is null at the end.
Pagination bounds output, not query execution cost. Tool errors are SDK error
results rather than fabricated empty answers.

MCP result rows retain relationship confidence. Definition confidence `exact`
means parsed declaration identity, with reason `definition`. `index_status`
returns file-start anchors and `not_applicable` confidence for file metadata,
plus parsed counts and full index statistics. A file anchor may identify an
empty/missing file; it does not claim a live source line exists.

Index metadata now includes hashes of the bytes used in discovery/parsing.
Status compares indexed paths and hashes with current files, and reports
additions and deletions. A pre-v1 index without hashes has unknown freshness.
The explorer keeps its existing coarse Git status display. Rebuilds are still
in place, so the MCP server and the explorer must be stopped before indexing. Connection buffers are capped
at 64 MiB and two workers; parser objects and query result materialization also
consume memory.

The evaluation runner lives in `codegraph/evaluation.py`; labels and source
fixtures remain reviewable in `eval/` and `tests/fixtures/`. Each fixture is
indexed in a temporary directory. Retrieval sees only kind/arguments, never
labels. The text baseline shares declaration spans for identity normalization,
not resolved relationships. Reports preserve every answer and all metric
inputs. See `eval/README.md` for the versioned scoring and label policy.

Strict typing currently covers the service, MCP server and evaluation runner.
Older modules retain their existing dynamic APIs. CI enforces this boundary
and package-wide statement coverage of at least 85%, including subprocesses.
