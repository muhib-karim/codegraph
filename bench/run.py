"""Index-time and query-latency benchmark on pinned public repositories.

    python bench/run.py --out bench-out                # clone, index and query every repo
    python bench/run.py --local tests/fixtures/web     # one local directory, no network

Each repository is indexed in a fresh subprocess so peak RSS belongs to that repository.
Query targets are chosen from the graph itself (most-called symbol, symbol with most
outgoing calls), so nothing is hand-picked. Numbers are only meaningful together with
the runner label written next to them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QUERIES = ("callers", "callees", "impact", "search")


def clone(repo: dict[str, str], work: Path) -> Path:
    dest = work / repo["name"]
    if not dest.exists():
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", repo["ref"], repo["url"], dest],
            check=True,
        )
    return dest


def timed(fn: Any, runs: int) -> tuple[float, float, int]:
    """(median ms, p95 ms, result count) after one warm-up call."""
    total = fn()["total"]
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    p95 = samples[min(len(samples) - 1, round(0.95 * (len(samples) - 1)))]
    return round(statistics.median(samples), 2), round(p95, 2), total


def measure(path: Path, runs: int) -> dict[str, Any]:
    """Index one directory and time queries; runs inside its own process."""
    from codegraph.indexer import index
    from codegraph.service import GraphService

    tmp = Path(tempfile.mkdtemp(prefix="cg-bench-"))
    db = tmp / "graph.lbug"
    try:
        t0 = time.perf_counter()
        stats = index(str(path), str(db))
        seconds = time.perf_counter() - t0
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        db_bytes = sum(f.stat().st_size for f in tmp.rglob("*") if f.is_file())
        with GraphService(str(db)) as graph:
            loc = sum(int(r["loc"] or 0) for r in graph.files.values() if r["parsed"])
            conn = graph.conn
            hub = conn.execute(
                "MATCH (s:Symbol)<-[c:CALLS]-(:Symbol) WHERE s.kind IN ['function','method'] "
                "RETURN s.id, s.name, count(c) AS n ORDER BY n DESC, s.id LIMIT 1"
            ).get_all()
            caller = conn.execute(
                "MATCH (s:Symbol)-[c:CALLS]->(:Symbol) WHERE s.kind IN ['function','method'] "
                "RETURN s.id, count(c) AS n ORDER BY n DESC, s.id LIMIT 1"
            ).get_all()
            queries: dict[str, Any] = {}
            if hub and caller:
                hub_id, hub_name = hub[0][0], hub[0][1]
                plan = {
                    "callers": ("callers", hub_id, {}),
                    "callees": ("callees", caller[0][0], {}),
                    "impact": ("impact", hub_id, {"depth": 3}),
                    "search": ("search", hub_name[:3] or hub_name, {}),
                }
                for label, (kind, target, extra) in plan.items():
                    median, p95, total = timed(
                        lambda k=kind, t=target, e=extra: graph.query(k, t, limit=100, **e), runs
                    )
                    queries[label] = {
                        "target": target,
                        "median_ms": median,
                        "p95_ms": p95,
                        "results": total,
                    }
        return {
            "files": stats["files"],
            "parsed_files": sum(stats["parsed_by_lang"].values()),
            "parsed_by_lang": stats["parsed_by_lang"],
            "parsed_loc": loc,
            "symbols": sum(stats["symbols_by_kind"].values()),
            "edges": stats["calls"] + stats["references"] + stats["inherits"],
            "index_seconds": round(seconds, 2),
            "peak_rss_mb": round(peak_mb, 1),
            "db_mb": round(db_bytes / 2**20, 1),
            "queries": queries,
            "runs_per_query": runs,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def runner_label() -> dict[str, str]:
    env = os.environ
    return {
        "os": f"{platform.system()} {platform.release()}",
        "image": " ".join(filter(None, [env.get("ImageOS", ""), env.get("ImageVersion", "")]))
        or "local",
        "arch": platform.machine(),
        "cpus": str(os.cpu_count()),
        "python": platform.python_version(),
        "ci": "GitHub Actions" if env.get("GITHUB_ACTIONS") == "true" else "local",
        "run_id": env.get("GITHUB_RUN_ID", ""),
        "commit": env.get("GITHUB_SHA", "")[:12],
    }


def render(report: dict[str, Any]) -> str:
    r = report["runner"]
    lines = [
        "# codegraph benchmark",
        "",
        f"Runner: {r['ci']} · {r['image']} · {r['os']} · {r['arch']} · {r['cpus']} CPUs · "
        f"Python {r['python']}. Date (UTC): {report['date']}. codegraph {report['version']}"
        + (f", commit {r['commit']}, run {r['run_id']}" if r["run_id"] else "")
        + ".",
        "",
        "| Repository | Ref | Parsed files | Parsed LOC | Symbols | Edges | Index (s) "
        "| Peak RSS (MB) | callers | callees | impact | search |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for repo in report["repos"]:
        q = repo["queries"]
        cells = [f"{q[k]['median_ms']} ms" if k in q else "n/a" for k in QUERIES]
        lines.append(
            f"| {repo['name']} ({repo['language']}) | `{repo['ref']}` | {repo['parsed_files']} "
            f"| {repo['parsed_loc']} | {repo['symbols']} | {repo['edges']} "
            f"| {repo['index_seconds']} | {repo['peak_rss_mb']} | " + " | ".join(cells) + " |"
        )
    lines += [
        "",
        f"Query cells are the median of {report['runs_per_query']} timed runs after one warm-up, "
        "through the same service the MCP server uses (limit 100). Index time includes parsing, "
        "resolution and writing the database. Targets are picked from the graph: the most-called "
        "function or method for callers, impact (depth 3) and search (its first three letters), "
        "and the function with the most outgoing calls for callees.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repos", default=str(HERE / "repos.json"))
    ap.add_argument("--work", default="", help="clone directory (default: a temp dir)")
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--only", default="", help="comma list of repository names")
    ap.add_argument("--local", default="", help="benchmark one local directory instead")
    ap.add_argument("--measure", default="", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.measure:  # child process: print one JSON object
        print(json.dumps(measure(Path(args.measure), args.runs)))
        return 0
    from codegraph import __version__

    if args.local:
        repos = [{"name": Path(args.local).name, "url": "", "ref": "local", "language": "mixed"}]
    else:
        repos = json.loads(Path(args.repos).read_text())
        if args.only:
            keep = set(args.only.split(","))
            repos = [r for r in repos if r["name"] in keep]
    work = Path(args.work or tempfile.mkdtemp(prefix="cg-bench-src-"))
    results = []
    for repo in repos:
        path = Path(args.local) if args.local else clone(repo, work)
        commit = ""
        if not args.local:
            commit = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        child = subprocess.run(
            [sys.executable, __file__, "--measure", str(path), "--runs", str(args.runs)],
            capture_output=True,
            text=True,
            check=True,
        )
        row = {**repo, "commit": commit, **json.loads(child.stdout)}
        results.append(row)
        print(f"{repo['name']}: {row['index_seconds']}s, {row['symbols']} symbols", file=sys.stderr)
    report = {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "version": __version__,
        "runner": runner_label(),
        "runs_per_query": args.runs,
        "repos": sorted(results, key=lambda r: r["parsed_loc"]),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "latest.md").write_text(render(report))
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
