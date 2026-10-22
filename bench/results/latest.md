# codegraph benchmark

Runner: GitHub Actions · ubuntu24 20261012.334.1 · Linux 6.17.0-1022-azure · x86_64 · 4 CPUs · Python 3.12.15. Date (UTC): 2026-10-22. codegraph 1.1.0, commit e803967b31b6, run 39705868795.

| Repository | Ref | Parsed files | Parsed LOC | Symbols | Edges | Index (s) | Peak RSS (MB) | callers | callees | impact | search |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| requests (Python) | `v2.32.3` | 36 | 11209 | 928 | 946 | 0.92 | 110.1 | 3.57 ms | 3.12 ms | 11.28 ms | 1.97 ms |
| zod (TypeScript) | `v3.23.8` | 170 | 30994 | 1915 | 7473 | 1.48 | 128.1 | 5.96 ms | 5.79 ms | 10.11 ms | 1.54 ms |
| gson (Java) | `gson-parent-2.11.0` | 249 | 53021 | 5757 | 27395 | 2.43 | 142.2 | 89.61 ms | 16.16 ms | 137.99 ms | 5.4 ms |

Query cells are the median of 20 timed runs after one warm-up, through the same service the MCP server uses (limit 100). Index time includes parsing, resolution and writing the database. Targets are picked from the graph: the most-called function or method for callers, impact (depth 3) and search (its first three letters), and the function with the most outgoing calls for callees.
