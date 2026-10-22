# codegraph benchmark

Runner: GitHub Actions · ubuntu24 20261018.339.1 · Linux 7.0.0-1017-azure · x86_64 · 4 CPUs · Python 3.12.15. Date (UTC): 2026-10-22. codegraph 1.1.0, commit b3daafac4283, run 39707970318.

| Repository | Ref | Parsed files | Parsed LOC | Symbols | Edges | Index (s) | Peak RSS (MB) | callers | callees | impact | search |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| requests (Python) | `v2.32.3` | 36 | 11209 | 928 | 946 | 0.41 | 123.7 | 4.91 ms | 4.12 ms | 15.28 ms | 2.83 ms |
| zod (TypeScript) | `v3.23.8` | 170 | 30994 | 1717 | 7275 | 0.87 | 127.0 | 8.32 ms | 8.06 ms | 14.01 ms | 2.14 ms |
| gson (Java) | `gson-parent-2.11.0` | 249 | 53021 | 5757 | 27395 | 1.51 | 156.4 | 116.26 ms | 21.23 ms | 181.14 ms | 6.98 ms |

Query cells are the median of 20 timed runs after one warm-up, through the same service the MCP server uses (limit 100). Index time includes parsing, resolution and writing the database. Targets are picked from the graph: the most-called function or method for callers, impact (depth 3) and search (its first three letters), and the function with the most outgoing calls for callees.
