# Using codegraph as an MCP server

`codegraph mcp` serves a read-only graph over stdio using the official MCP SDK.
Install the extra and index the repository first:

```sh
pip install 'codegraph[mcp]'        # or: pip install -e '.[mcp]' in a checkout
codegraph index /absolute/path/to/repo
```

Replace the two absolute paths below with your own. `command` must point at the
`codegraph` executable of the environment where the `mcp` extra is installed.

## Claude Code

Add it for the current project from the command line:

```sh
claude mcp add codegraph -- /absolute/path/to/codegraph/.venv/bin/codegraph mcp --repo /absolute/path/to/repo
```

Or commit a project-scoped `.mcp.json` at the repository root:

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "/absolute/path/to/codegraph/.venv/bin/codegraph",
      "args": ["mcp", "--repo", "/absolute/path/to/repo"]
    }
  }
}
```

Run `/mcp` inside Claude Code to check that the server is connected.

## Codex CLI

Add a server table to `~/.codex/config.toml`:

```toml
[mcp_servers.codegraph]
command = "/absolute/path/to/codegraph/.venv/bin/codegraph"
args = ["mcp", "--repo", "/absolute/path/to/repo"]
```

or run `codex mcp add codegraph -- /absolute/path/to/codegraph/.venv/bin/codegraph mcp --repo /absolute/path/to/repo`.

## Other clients

Any client that launches stdio servers accepts the same command and arguments.
For a database in a custom location use `mcp --db /absolute/path/to/graph.lbug`
instead of `--repo`. In a container, run `docker run -i` without a TTY.

## Tools

| Tool | Answers | Defaults |
|---|---|---|
| `index_status` | Coverage and staleness of the snapshot; call it first | |
| `search` | Symbols whose name contains the query (qualified name if it has a dot) | limit 20 |
| `find_symbol` | Definitions for a bare or qualified name or full symbol id | |
| `callers` | Incoming calls and value references | depth 1 |
| `callees` | Direct outgoing calls with target definitions | |
| `impact` | Reverse calls, references and inheritance from a symbol or file | depth 3 |
| `blast_radius` | Same as `impact` (kept for 1.0 clients) | depth 3 |
| `inherits` | Descendants or ancestors of a class or interface | depth 3 |
| `dead_code` | Symbols without incoming edges, tagged `likely` or `possible` | |

Every result row has `file`, `line`, `citation` (`file:line`) and `confidence`.
Responses are paged with `limit` (1 to 100) and `offset`; pass `next_offset` back
for the next page. The server opens the database read-only, offers no raw query
language and rejects paths outside the indexed repository.
