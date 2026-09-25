#!/usr/bin/env python3
"""Adapter for the codegraph-eval harness (interim v0 contract).

Reads one question on stdin, maps command+arguments onto the codegraph CLI,
prints {"answers": [...]} (codegraph --json already emits that key).
Never reads `expected`. The graph is built once per repo into
$CODEGRAPH_EVAL_DB (default /tmp/codegraph-eval/graph.lbug).
"""
import json
import os
import subprocess
import sys

q = json.load(sys.stdin)
repo = os.environ["CODEGRAPH_EVAL_REPO"]
db = os.environ.get("CODEGRAPH_EVAL_DB", "/tmp/codegraph-eval/graph.lbug")
cg = [sys.executable, "-m", "codegraph"]
env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.path.exists(db):
    subprocess.run(cg + ["index", repo, "--db", db], check=True, env=env, stdout=subprocess.DEVNULL)

a = q.get("arguments", {})
cmd = q["command"]
in_file = (a.get("defined_in") or {}).get("file", "")
common = ["--db", db, "--json", "--compact"]
scope = a.get("scope", "")
if scope and scope != "non-defining-file":
    common += ["--scope", scope]

if cmd == "callers":
    argv = ["callers", a["symbol"], "--depth", "1"] + (["--in", in_file] if in_file else [])
elif cmd == "inherits":
    mode = a.get("mode", "subclasses_of")
    if mode == "explicit_extends_in_scope":
        argv = None  # no single-target form; answered below from the graph
    else:
        argv = ["inherits", a["symbol"], "--depth", "1"] + (["--in", in_file] if in_file else [])
        if mode == "superclass_of":
            argv.append("--ancestors")
elif cmd == "dead-code":
    kind = {"module_level_name": "variable,function,class", "module_level_function": "function",
            "static_field": "field"}.get(a.get("kind", ""), "")
    argv = ["dead-code"] + (["--kind", kind] if kind else [])
elif cmd in ("blast-radius", "blast"):
    # gold blast questions ask for DIRECT consumers: pin depth 1 and keep only depth-1 results
    argv = ["blast", a["symbol"], "--depth", "1"] + (["--in", in_file] if in_file else [])
else:
    argv = None

answers = []
if argv is not None:
    p = subprocess.run(cg + argv + common, capture_output=True, text=True, env=env)
    if p.returncode not in (0, 2):
        sys.stderr.write(p.stderr)
        sys.exit(1)
    out = json.loads(p.stdout)
    results = out.get("results", [])
    if cmd in ("blast-radius", "blast", "callers"):
        results = [r for r in results if r.get("depth", 1) == 1]
    if cmd == "dead-code" and a.get("enclosing_class"):
        pfx = a["enclosing_class"] + "."
        results = [r for r in results if r["qualname"].startswith(pfx) and "." not in r["qualname"][len(pfx):]]
    if cmd == "dead-code" and a.get("kind", "").startswith("module_level"):
        results = [r for r in results if "." not in r["qualname"]]
    if scope == "non-defining-file" and in_file:
        results = [r for r in results if r["file"] != in_file]
    seen = set()
    for r in results:
        k = (r["file"], r["line"])
        if k not in seen:
            seen.add(k)
            answers.append({"file": r["file"], "line": r["line"], "symbol": r.get("qualname", "")})
print(json.dumps({"answers": answers}))
