# Benchmark

`bench/run.py` measures how long codegraph takes to index real repositories and how
fast the MCP query paths answer on them. CI runs it on every push (job `benchmark`)
and publishes `latest.md` in the job summary and `latest.json` as an artifact.

| Repository | Language | Pinned ref |
|---|---|---|
| [psf/requests](https://github.com/psf/requests) | Python | `v2.32.3` |
| [colinhacks/zod](https://github.com/colinhacks/zod) | TypeScript | `v3.23.8` |
| [google/gson](https://github.com/google/gson) | Java | `gson-parent-2.11.0` |

What is measured, per repository:

- **Index time**: wall-clock time of `codegraph index` work (discover, parse, resolve,
  write the database), in a fresh process.
- **Peak RSS** of that process.
- **Query latency**: median and p95 of 20 timed runs after one warm-up for
  `callers`, `callees`, `impact` (depth 3) and `search`, through `GraphService`,
  the layer the MCP server calls. Targets come from the graph itself: the most-called
  function or method (callers, impact, and its first three letters for search) and the
  function with the most outgoing calls (callees).

The committed numbers in [`results/latest.md`](results/latest.md) are copied unchanged
from a CI run; the file names the runner image, date, commit and run id. Numbers from
other machines are not comparable.

Run it yourself:

```sh
pip install .
python bench/run.py --out /tmp/bench                      # clones the three repositories
python bench/run.py --local path/to/repo --out /tmp/bench # any local checkout, no network
```

Repositories are cloned shallowly at the pinned tag and only parsed, never executed.
