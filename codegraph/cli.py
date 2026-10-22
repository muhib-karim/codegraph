"""codegraph command line."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import SCHEMA_VERSION, __version__, queries, store

DEFAULT_DB = os.path.join(".codegraph", "graph.lbug")


def find_db(args):
    if getattr(args, "db", None):
        return args.db
    if getattr(args, "repo", None):
        return os.path.join(args.repo, DEFAULT_DB)
    d = os.getcwd()
    while True:
        p = os.path.join(d, DEFAULT_DB)
        if os.path.exists(p):
            return p
        nd = os.path.dirname(d)
        if nd == d:
            return os.path.join(os.getcwd(), DEFAULT_DB)
        d = nd


def emit(args, command, query, resolved, results, db, extra=None, error=None):
    answers, seen = [], set()
    for r in results:
        k = (r["file"], r["line"])
        if k not in seen:
            seen.add(k)
            answers.append({"file": r["file"], "line": r["line"], "symbol": r.get("qualname", "")})
    if args.json:
        out = {
            "command": command,
            "query": query,
            "db": db,
            "schema_version": SCHEMA_VERSION,
            "resolved": resolved,
            "results": results,
            "count": len(results),
            "answers": answers,
        }
        if extra:
            out.update(extra)
        if error:
            out["error"] = error
        print(json.dumps(out, indent=None if args.compact else 2, ensure_ascii=False))
        return
    if error:
        print(f"error: {error}", file=sys.stderr)
        return
    for r in results:
        cols = [
            r["citation"],
            r.get("qualname", ""),
            r.get("kind", ""),
            r.get("dead_confidence", r.get("confidence", "")),
        ]
        if "depth" in r and command in ("callers", "blast", "impact", "inherits"):
            cols.append(str(r["depth"]))
        if "via" in r:
            cols.append(r.get("def", r["via"]))
        elif command == "callees":
            cols.append(r["def"])
        print("\t".join(str(c) for c in cols))
    if not results:
        print(f"# no results ({command} {query})", file=sys.stderr)


def cmd_index(args):
    from .indexer import index

    repo = os.path.abspath(args.path)
    db = args.db or os.path.join(repo, DEFAULT_DB)
    stats = index(repo, db)
    if args.json:
        print(json.dumps({"db": db, **stats}, indent=2))
    else:
        r = stats["resolution"]
        print(
            f"indexed {stats['files']} files ({stats['parsed_by_lang']}) in {stats['seconds']}s -> {db}"
        )
        print(f"symbols: {stats['symbols_by_kind']}")
        print(
            f"edges: calls={stats['calls']} references={stats['references']} inherits={stats['inherits']} "
            f"imports={stats['imports_internal']}"
        )
        print(
            f"call sites: exact={r.get('call_exact', 0)} heuristic={r.get('call_heuristic', 0)} "
            f"external={r.get('call_external', 0)} ambiguous={r.get('call_ambiguous', 0)} "
            f"unresolved={r.get('call_unresolved', 0)}"
        )
        if stats["unparsed_code_files"]:
            print(
                f"not parsed at v0.1 (no symbols/edges): {len(stats['unparsed_code_files'])} code files, e.g. "
                + ", ".join(stats["unparsed_code_files"][:5])
            )
        if stats["parse_errors"]:
            print("parse errors: " + "; ".join(stats["parse_errors"]))
    return 0


def run_query(args, command, fn, query):
    db = find_db(args)
    try:
        _db, conn = store.connect(db)
    except FileNotFoundError:
        print(f"error: no graph at {db}; run `codegraph index <repo>` first", file=sys.stderr)
        return 1
    try:
        resolved, results = fn(conn)
    except queries.NotFound as e:
        emit(args, command, query, [], [], db, error=f"not found: {e}")
        return 2
    emit(args, command, query, resolved, results, db)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="codegraph",
        description="Codebase knowledge graph: index a repo, then ask "
        "callers / inherits / dead-code / blast questions with file:line citations.",
    )
    ap.add_argument("--version", action="version", version=f"codegraph {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--db", help=f"graph path (default: nearest {DEFAULT_DB})")
        p.add_argument("--repo", help="repo root whose graph to use")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--compact", action="store_true", help="single-line JSON")
        p.add_argument("--scope", default="", help="only report results under this path prefix")

    p = sub.add_parser("index", help="build the graph for a repo")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--db")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("callers", help="who calls / references a symbol")
    p.add_argument("symbol")
    p.add_argument(
        "--in", dest="in_file", default="", help="only match the symbol defined in this file"
    )
    p.add_argument("--depth", type=int, default=1)
    common(p)

    p = sub.add_parser("callees", help="what a symbol calls directly")
    p.add_argument("symbol")
    p.add_argument("--in", dest="in_file", default="")
    common(p)

    p = sub.add_parser("search", help="find symbols by name substring")
    p.add_argument("query")
    p.add_argument("--kind", default="", help="comma list of symbol kinds")
    common(p)

    p = sub.add_parser("inherits", help="subclasses (or ancestors) of a class")
    p.add_argument("symbol")
    p.add_argument("--in", dest="in_file", default="")
    p.add_argument("--ancestors", action="store_true", help="walk up instead of down")
    p.add_argument("--depth", type=int, default=0, help="0 = transitive (default)")
    common(p)

    p = sub.add_parser("dead-code", help="symbols nothing in the indexed code uses")
    p.add_argument(
        "--kind",
        default="",
        help="comma list: function,method,constructor,class,field,variable,...",
    )
    p.add_argument("--confidence", choices=["all", "likely", "possible"], default="all")
    common(p)

    p = sub.add_parser(
        "blast", aliases=["impact"], help="what can break if a file or symbol changes"
    )
    p.add_argument("target")
    p.add_argument("--in", dest="in_file", default="")
    p.add_argument("--depth", type=int, default=3, help="0 = unbounded")
    common(p)

    p = sub.add_parser("stats", help="index metadata and coverage")
    p.add_argument("--db")
    p.add_argument("--repo")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("explore", help="serve the read-only graph explorer on loopback")
    p.add_argument("--repo", help="repo root whose graph to view")
    p.add_argument("--db", help="graph path")
    p.add_argument("--port", type=int, default=8765)

    p = sub.add_parser("mcp", help="serve read-only graph tools over stdio (requires [mcp])")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--repo")
    group.add_argument("--db")

    p = sub.add_parser("eval", help="evaluate graph and text retrieval on labelled fixtures")
    p.add_argument("--questions", default="eval/questions.jsonl")
    p.add_argument("--fixtures", default="tests/fixtures")
    p.add_argument("--output", default="eval/reports")
    p.add_argument("--k", type=int, default=5)

    args = ap.parse_args(argv)
    if args.cmd == "mcp":
        try:
            from .mcp_server import serve as serve_mcp
        except ImportError:
            print("error: MCP requires pip install 'codegraph[mcp]'", file=sys.stderr)
            return 1
        try:
            serve_mcp(find_db(args))
        except (FileNotFoundError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "eval":
        import shlex

        from .evaluation import run

        try:
            report = run(
                args.questions,
                args.fixtures,
                args.output,
                args.k,
                shlex.join(["codegraph", *(sys.argv[1:] if argv is None else argv)]),
            )
        except (ValueError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(json.dumps(report["overall"], indent=2))
        return 0

    if args.cmd == "explore":
        from .explorer_server import serve

        try:
            serve(find_db(args), args.port)
        except (FileNotFoundError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "index":
        return cmd_index(args)
    if args.cmd == "callers":
        return run_query(
            args,
            "callers",
            lambda c: queries.callers(c, args.symbol, args.in_file, args.depth, args.scope),
            args.symbol,
        )
    if args.cmd == "callees":
        return run_query(
            args,
            "callees",
            lambda c: queries.callees(c, args.symbol, args.in_file, args.scope),
            args.symbol,
        )
    if args.cmd == "search":
        kinds = [k for k in args.kind.split(",") if k] or None
        return run_query(
            args,
            "search",
            lambda c: ([], queries.search(c, args.query, kinds, args.scope)),
            args.query,
        )
    if args.cmd == "inherits":
        return run_query(
            args,
            "inherits",
            lambda c: queries.inherits(
                c, args.symbol, args.in_file, args.ancestors, args.depth, args.scope
            ),
            args.symbol,
        )
    if args.cmd == "dead-code":
        kinds = [k for k in args.kind.split(",") if k] or None
        return run_query(
            args,
            "dead-code",
            lambda c: ([], queries.dead_code(c, args.scope, kinds, args.confidence)),
            args.scope,
        )
    if args.cmd in ("blast", "impact"):
        return run_query(
            args,
            args.cmd,
            lambda c: queries.blast(c, args.target, args.in_file, args.depth, args.scope),
            args.target,
        )
    if args.cmd == "stats":
        db = find_db(args)
        try:
            _db, conn = store.connect(db)
        except FileNotFoundError:
            print(f"error: no graph at {db}", file=sys.stderr)
            return 1
        m = queries.meta(conn)
        if "stats" in m:
            m["stats"] = json.loads(m["stats"])
        print(json.dumps(m, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
