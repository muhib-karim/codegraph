# Contributing

Use Python 3.11 or 3.12. Run `make install` to create `.venv` and install the
editable package with development and optional MCP dependencies. The core
package must remain usable without the MCP SDK. No API keys or model calls
are needed.

Before a change is ready for review:

```sh
make lint typecheck test eval
```

Ruff checks lint and formatting across project code and tests. Fixtures are
excluded from autoformatting because their line numbers are evaluation data.
Mypy runs in strict mode on `service.py`, `mcp_server.py` and `evaluation.py`;
the older parser/resolver/explorer modules are not yet fully typed. Add new
modules to the strict check. Pytest measures the entire package, including CLI
subprocesses, with an 85% minimum. Do not lower the gate or exclude difficult
code to make a change pass.

Browser tests skip if the optional browser package or executable is unavailable.
To run them, install `.[browser]` and a local Chromium browser using
`.venv/bin/playwright install chromium`. CI needs neither. Protocol tests call
all MCP tools through the official client session in memory, plus a real stdio
round trip using the README configuration.

When changing retrieval behavior, update source-based labels only for a
reviewed semantic correction; do not copy retriever output into expected
answers. See `eval/README.md`. Regenerate and commit both reports and any README
results-table changes. Include observed regressions as well as improvements.

Use small conventional commits (`feat:`, `fix:`, `test:`, `docs:`). Explain the
problem, behavior change, validation and remaining limitations in the change
request. Keep file:line evidence and confidence semantics stable, or document
and version a contract change. Keep dependencies and memory requirements small.
The MIT license applies to contributions.
