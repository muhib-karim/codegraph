"""Build the static GitHub Pages site into an output directory.

    python scripts/build_site.py --out _site

Everything on the page comes from real runs at build time:
- the graph demo reads `data/graph.json`, exported from an index of `tests/fixtures`;
- the quickstart terminal shows the actual CLI output on the `web` fixture;
- the benchmark table is rendered from `bench/results/latest.json`, a copied CI run.
No backend: the page is plain HTML, CSS and one script.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codegraph import __version__  # noqa: E402
from codegraph.cli import main as cli  # noqa: E402
from codegraph.indexer import index  # noqa: E402
from codegraph.service import GraphService  # noqa: E402

SAMPLE = ROOT / "tests" / "fixtures"
MARKER = ".codegraph-site"  # written into every build so a rebuild may replace it
SESSION = [
    ["callers", "make"],
    ["callees", "main"],
    ["impact", "src/util.ts", "--depth", "2"],
    ["search", "area", "--kind", "method"],
]


def export_graph(db: Path) -> dict[str, Any]:
    with GraphService(str(db)) as graph:
        rows = graph.conn.execute(
            "MATCH (s:Symbol) WHERE s.kind <> 'external' "
            "RETURN s.id, s.name, s.qualname, s.kind, s.lang, s.file, s.line ORDER BY s.id"
        ).get_all()
        edges: list[dict[str, Any]] = []
        for rel, kind in (("CALLS", "call"), ("REFERENCES", "ref"), ("INHERITS", "inherits")):
            for src, dst, f, ln, conf in graph.conn.execute(
                f"MATCH (a:Symbol)-[r:{rel}]->(b:Symbol) WHERE b.kind <> 'external' "
                "RETURN a.id, b.id, r.file, r.line, r.confidence ORDER BY r.file, r.line, b.id"
            ).get_all():
                edges.append(
                    {
                        "source": src,
                        "target": dst,
                        "type": kind,
                        "file": f,
                        "line": ln,
                        "confidence": conf,
                    }
                )
        meta = graph.meta
    linked = {e["source"] for e in edges} | {e["target"] for e in edges}
    nodes = [
        {
            "id": sid,
            "name": name if kind != "module" else Path(f).name,
            "qualname": qn if kind != "module" else f"{Path(f).name} (module)",
            "kind": kind,
            "lang": lang,
            "file": f,
            "line": ln,
            "group": f.split("/", 1)[0],
        }
        for sid, name, qn, kind, lang, f, ln in rows
        if kind != "module" or sid in linked
    ]
    stats = json.loads(meta["stats"])
    return {
        "version": __version__,
        "sample": "tests/fixtures",
        "indexed_at": meta["indexed_at"],
        "parsed_by_lang": stats["parsed_by_lang"],
        "nodes": nodes,
        "edges": edges,
    }


def cli_session() -> str:
    """Real output of the quickstart commands on the `web` fixture."""
    tmp = Path(tempfile.mkdtemp(prefix="cg-site-"))
    try:
        repo = tmp / "web"
        shutil.copytree(SAMPLE / "web", repo)
        index(str(repo), str(repo / ".codegraph" / "graph.lbug"))
        out = []
        for argv in SESSION:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                cli([*argv, "--repo", str(repo)])
            out.append("$ codegraph " + " ".join(argv) + "\n" + buf.getvalue())
        return "".join(out).rstrip("\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def bench_table(report: dict[str, Any]) -> str:
    r = report["runner"]
    rows = []
    for repo in report["repos"]:
        q = repo["queries"]
        cells = "".join(
            f"<td>{q[k]['median_ms']:.2f}</td>" if k in q else "<td>n/a</td>"
            for k in ("callers", "callees", "impact", "search")
        )
        rows.append(
            f'<tr><th scope="row">{html.escape(repo["name"])}'
            f"<span>{html.escape(repo['language'])} · <code>{html.escape(repo['ref'])}</code>"
            f"</span></th><td>{repo['parsed_files']:,}</td><td>{repo['parsed_loc']:,}</td>"
            f"<td>{repo['symbols']:,}</td><td>{repo['edges']:,}</td>"
            f"<td>{repo['index_seconds']:.2f}</td><td>{repo['peak_rss_mb']:.0f}</td>{cells}</tr>"
        )
    label = (
        f"{r['ci']} runner, {r['image']}, {r['os']}, {r['arch']}, {r['cpus']} CPUs, "
        f"Python {r['python']}; {report['date']}; codegraph {report['version']}"
        + (
            f", commit <code>{html.escape(r['commit'])}</code>, run {r['run_id']}"
            if r["run_id"]
            else ""
        )
    )
    return (
        '<div class="table-wrap" tabindex="0" role="region" aria-label="Benchmark results">'
        '<table><thead><tr><th scope="col">Repository</th><th scope="col">Files</th>'
        '<th scope="col">Lines</th><th scope="col">Symbols</th><th scope="col">Edges</th>'
        '<th scope="col">Index s</th><th scope="col">Peak MB</th>'
        '<th scope="col">callers ms</th><th scope="col">callees ms</th>'
        '<th scope="col">impact ms</th><th scope="col">search ms</th></tr></thead><tbody>'
        + "".join(rows)
        + f'</tbody></table></div><p class="fine">Measured on: {label}. Query times are '
        f"medians of {report['runs_per_query']} runs after a warm-up.</p>"
    )


def check_out(out: Path) -> None:
    """Refuse output paths whose replacement would delete anything but an earlier build."""
    target = out.resolve()
    root = ROOT.resolve()
    if target == root or target in root.parents:
        raise SystemExit(f"refusing to replace {out}: it contains the source checkout")
    if target.is_relative_to(root) and not target.is_relative_to(root / "_site"):
        raise SystemExit(
            f"refusing to replace {out}: use _site/ or a directory outside the checkout"
        )
    if target.exists() and any(target.iterdir()) and not (target / MARKER).exists():
        raise SystemExit(f"refusing to replace {out}: not empty and not an earlier site build")


def build(out: Path, bench: Path) -> None:
    check_out(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    tmp = Path(tempfile.mkdtemp(prefix="cg-site-"))
    try:
        db = tmp / "graph.lbug"
        index(str(SAMPLE), str(db))
        graph = export_graph(db)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    (out / "data").mkdir(exist_ok=True)
    (out / "data" / "graph.json").write_text(json.dumps(graph, separators=(",", ":")))
    report = json.loads(bench.read_text())
    page = (out / "index.html").read_text()
    page = page.replace("{{VERSION}}", __version__)
    page = page.replace("{{CLI_SESSION}}", html.escape(cli_session()))
    page = page.replace("{{BENCH_TABLE}}", bench_table(report))
    page = page.replace(
        "{{SAMPLE_COUNTS}}",
        html.escape(f"{len(graph['nodes'])} symbols and {len(graph['edges'])} edges"),
    )
    assert "{{" not in page, "unfilled placeholder"
    (out / "index.html").write_text(page)
    (out / MARKER).write_text("generated by scripts/build_site.py; safe to delete\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the static Pages site.")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--bench", default=str(ROOT / "bench" / "results" / "latest.json"))
    args = ap.parse_args(argv)
    build(Path(args.out), Path(args.bench))
    print(f"site written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
