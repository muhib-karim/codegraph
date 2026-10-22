"""TypeScript and JavaScript indexing on the committed `web` (TS/TSX) and `webjs` (JS) fixtures."""

from pathlib import Path

import pytest

from codegraph.extract_ts import extract
from codegraph.indexer import index
from codegraph.service import GraphService

FIXTURES = Path(__file__).parent / "fixtures"


def symbols(path):
    fi = extract(path, (FIXTURES / "web" / path).read_bytes())
    return {s.qualname: s for s in fi.symbols}, fi


@pytest.fixture(scope="module")
def web(tmp_path_factory):
    db = tmp_path_factory.mktemp("web") / "graph.lbug"
    stats = index(str(FIXTURES / "web"), str(db))
    with GraphService(str(db)) as graph:
        yield graph, stats


@pytest.fixture(scope="module")
def webjs(tmp_path_factory):
    db = tmp_path_factory.mktemp("webjs") / "graph.lbug"
    stats = index(str(FIXTURES / "webjs"), str(db))
    with GraphService(str(db)) as graph:
        yield graph, stats


def sites(graph, kind, target, **kw):
    return [(r["citation"], r["confidence"]) for r in graph.query(kind, target, **kw)["results"]]


def test_typescript_declarations():
    syms, fi = symbols("src/shapes.ts")
    assert fi.lang == "typescript"
    kinds = {q: (s.kind, s.line, s.visibility) for q, s in syms.items()}
    assert kinds["Shape"] == ("interface", 1, "public")
    assert kinds["Shape.area"] == ("method", 2, "public")
    assert kinds["Base"] == ("class", 5, "public")
    assert kinds["Circle.constructor"] == ("constructor", 14, "public")
    assert kinds["Circle.area"] == ("method", 18, "public")
    assert kinds["Color"] == ("enum", 25, "public")
    assert kinds["orphan"] == ("function", 30, "private")
    assert [(b.text, b.kind) for b in fi.bases] == [
        ("Shape", "implements"),
        ("Base", "extends"),
        ("Circle", "extends"),
    ]
    # TS parameter properties become typed fields of the class.
    assert kinds["Circle.radius"] == ("field", 14, "private")


def test_arrow_functions_and_variables():
    syms, _ = symbols("src/util.ts")
    assert syms["double"].kind == "function"
    assert syms["SCALE"].kind == "variable"
    assert (syms["scale"].arity_min, syms["scale"].arity_max) == (1, 1)


def test_imports_and_reexports():
    _, app = symbols("src/app.ts")
    assert [(i.module, i.name, i.alias, i.kind) for i in app.imports] == [
        ("./index", "Circle", "", "from"),
        ("./index", "Ring", "", "from"),
        ("./index", "resize", "", "from"),
        ("./util", "", "util", "module"),
        ("./registry", "default", "Registry", "from"),
    ]
    _, barrel = symbols("src/index.ts")
    assert [(i.module, i.name, i.alias, i.kind) for i in barrel.imports] == [
        ("./shapes", "", "", "reexport_star"),
        ("./util", "scale", "resize", "reexport"),
    ]


def test_syntax_error_keeps_recovered_symbols():
    syms, fi = symbols("src/broken.ts")
    assert fi.parsed and "survives" in syms


def test_index_stats_count_typescript(web):
    _, stats = web
    assert stats["parsed_by_lang"] == {"typescript": 7}
    assert stats["unparsed_code_files"] == []
    assert stats["parse_errors"] == []


def test_typescript_callers_skip_shadowing_param_and_comments(web):
    graph, _ = web
    assert sites(graph, "callers", "make") == [
        ("src/app.ts:11", "exact"),
        ("src/view.tsx:4", "exact"),
    ]


def test_reexport_alias_and_arrow_scope(web):
    graph, _ = web
    rows = graph.query("callers", "scale")["results"]
    assert [(r["citation"], r["def"]) for r in rows] == [
        ("src/app.ts:7", "src/app.ts:6"),
        ("src/util.ts:7", "src/util.ts:7"),
    ]


def test_typescript_callees(web):
    graph, _ = web
    got = sites(graph, "callees", "main")
    assert ("src/app.ts:11", "exact") in got  # make
    assert ("src/app.ts:12", "exact") in got  # default-imported class
    rows = graph.query("callees", "main")["results"]
    by_name = {(r["qualname"], r["line"]): r["confidence"] for r in rows}
    assert by_name[("Registry.add", 13)] == "exact"  # typed local from `new`
    assert by_name[("Circle.area", 15)] == "exact"  # inherited through Ring
    assert by_name[("double", 14)] == "exact"  # namespace import
    assert by_name[("Base.describe", 15)] == "heuristic"  # untyped receiver


def test_typescript_inherits_and_super(web):
    graph, _ = web
    assert sites(graph, "inherits", "Base", depth=3) == [
        ("src/shapes.ts:13", "exact"),
        ("src/shapes.ts:23", "exact"),
    ]
    assert [r["qualname"] for r in graph.query("inherits", "Shape", depth=3)["results"]] == [
        "Base",
        "Circle",
        "Ring",
    ]
    assert ("src/shapes.ts:15", "exact") in sites(graph, "callers", "Base")
    assert ("src/shapes.ts:9", "exact") in sites(graph, "callers", "Base.area")


def test_typescript_blast_and_dead_code(web):
    graph, _ = web
    blast = {r["citation"] for r in graph.query("blast", "src/util.ts", depth=2)["results"]}
    assert {"src/app.ts:7", "src/app.ts:14", "src/view.tsx:4"} <= blast
    dead = {r["qualname"]: r["dead_confidence"] for r in graph.query("dead-code")["results"]}
    assert dead["orphan"] == "likely"
    assert dead["label"] == "likely"
    assert "make" not in dead and "Circle.area" not in dead


def test_javascript_commonjs_and_esm(webjs):
    graph, stats = webjs
    assert stats["parsed_by_lang"] == {"javascript": 5}
    assert sites(graph, "callers", "add") == [("app.mjs:6", "exact"), ("main.js:7", "exact")]
    assert sites(graph, "callers", "Counter.increment") == [("main.js:6", "exact")]
    assert sites(graph, "callers", "add1") == [("lib/counter.js:9", "exact")]
    assert sites(graph, "callers", "Emitter.emit") == [("lib/events.mjs:14", "exact")]
    assert sites(graph, "callers", "Bus.emit") == [("app.mjs:7", "exact")]
    dead = {r["qualname"]: r["dead_confidence"] for r in graph.query("dead-code")["results"]}
    # Exported but never called inside the repository: a candidate, not proof.
    assert dead == {"unusedHelper": "likely", "start": "possible"}


def test_module_resolution_prefers_file_and_maps_js_extension(tmp_path):
    (tmp_path / "util").mkdir()
    (tmp_path / "util.ts").write_text("export function pick() {}\n")
    (tmp_path / "util" / "index.ts").write_text("export function pick() {}\n")
    (tmp_path / "esm.ts").write_text("export function other() {}\n")
    (tmp_path / "main.ts").write_text(
        "import { pick } from './util';\nimport { other } from './esm.js';\n"
        "export function run() {\n  pick();\n  other();\n}\n"
    )
    db = tmp_path / "g.lbug"
    index(str(tmp_path), str(db))
    with GraphService(str(db)) as graph:
        rows = graph.query("callees", "run")["results"]
        assert [(r["def"], r["confidence"]) for r in rows] == [
            ("util.ts:1", "exact"),
            ("esm.ts:1", "exact"),
        ]


def test_jsx_components_and_typed_parameters_bind_calls(tmp_path):
    (tmp_path / "ui.tsx").write_text(
        "export class Store {\n  load(): number {\n    return 1;\n  }\n}\n"
        "export function Panel(props: { n: number }) {\n  return <b>{props.n}</b>;\n}\n"
        "export function App(store: Store) {\n  store.load();\n  return <Panel n={1} />;\n}\n"
    )
    db = tmp_path / "g.lbug"
    index(str(tmp_path), str(db))
    with GraphService(str(db)) as graph:
        rows = graph.query("callees", "App")["results"]
        assert [(r["qualname"], r["citation"], r["confidence"]) for r in rows] == [
            ("Store.load", "ui.tsx:10", "exact"),
            ("Panel", "ui.tsx:11", "exact"),
        ]


def build_repo(tmp_path, files):
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body)
    db = tmp_path / "g.lbug"
    stats = index(str(tmp_path), str(db))
    return db, stats


def test_cyclic_star_reexports_terminate_quickly(tmp_path):
    import time

    files = {
        f"{a}.ts": "".join(f"export * from './{b}';\n" for b in "abcd" if b != a) for a in "abcd"
    }
    files["app.ts"] = (
        "import { missing } from './a';\nexport function run() {\n"
        + "".join(f"  missing({i});\n" for i in range(50))
        + "}\n"
    )
    t0 = time.perf_counter()
    build_repo(tmp_path, files)
    assert time.perf_counter() - t0 < 5


def test_declarations_inside_callbacks_and_blocks_stay_local(tmp_path):
    db, _ = build_repo(
        tmp_path,
        {
            "spec.test.js": "function setup() {}\n"
            "describe('x', () => {\n"
            "  const setup = () => 2;\n"
            "  function helper() {}\n"
            "  it('y', () => { setup(); helper(); });\n"
            "});\n",
            "util.ts": "export function helper(n: number) {\n  return n;\n}\n",
            "shadow.ts": "import { helper } from './util';\n"
            "if (true) {\n  const helper = () => 9;\n  helper();\n}\n"
            "export function f() {\n  helper(2);\n}\n",
        },
    )
    with GraphService(str(db)) as graph:
        assert graph.query("callers", "spec.test.js::setup/0")["results"] == []
        assert [r["citation"] for r in graph.query("callers", "util.ts::helper/1")["results"]] == [
            "shadow.ts:7"
        ]
        names = {(s["file"], s["qualname"]) for s in graph.query("search", "helper")["results"]}
        assert names == {("util.ts", "helper")}  # no module-level helper leaks from blocks
        dead = {(r["file"], r["qualname"]) for r in graph.query("dead-code")["results"]}
        assert ("spec.test.js", "setup") in dead  # the outer one really is unused


def test_unbound_js_globals_do_not_match_repo_methods(tmp_path):
    db, stats = build_repo(
        tmp_path,
        {
            "logger.ts": "export class Logger {\n  log(msg: string) {}\n"
            "  stringify(x: object) {}\n}\n",
            "app.ts": "export function main() {\n  console.log('x');\n  JSON.stringify({});\n"
            "  window.localStorage.getItem('k');\n}\n",
        },
    )
    with GraphService(str(db)) as graph:
        assert graph.query("callers", "Logger.log")["results"] == []
        assert graph.query("callers", "Logger.stringify")["results"] == []
    assert stats["resolution"]["call_external"] >= 3


def test_syntax_errors_are_reported(web):
    _, stats = web
    assert stats["files_with_syntax_errors"] == ["src/broken.ts"]


def test_renamed_export_hides_the_local_name(tmp_path):
    db, _ = build_repo(
        tmp_path,
        {
            "lib.ts": "function foo() {}\nexport { foo as bar };\n",
            "a.ts": "import { bar } from './lib';\nexport function useBar() {\n  bar();\n}\n",
            "b.ts": "import { foo } from './lib';\nexport function useFoo() {\n  foo();\n}\n",
        },
    )
    with GraphService(str(db)) as graph:
        assert [r["citation"] for r in graph.query("callers", "lib.ts::foo/0")["results"]] == [
            "a.ts:3"
        ]


def test_search_accepts_leading_dot_queries(web):
    graph, _ = web
    assert [r["qualname"] for r in graph.query("search", ".area")["results"]] == [
        "Shape.area",
        "Base.area",
        "Circle.area",
    ]


def test_less_common_module_syntax(tmp_path):
    db, stats = build_repo(
        tmp_path,
        {
            "cjs.js": "exports.one = function () { return 1; };\n"
            "function two() { return 2; }\n"
            "module.exports.two = two;\n"
            "module.exports = { three: two, four: () => 4 };\n",
            "anon.ts": "export default function () {\n  return 5;\n}\n",
            "klass.ts": "export default class {\n  static make() {}\n}\n",
            "legacy.ts": "import fs = require('./cjs');\nimport './side';\n"
            "export function run() {\n  fs.one();\n  try {\n    fs.two();\n  } catch (e) {\n"
            "    e.toString();\n  }\n}\n",
            "side.ts": "export const loaded = true;\n",
            "use.ts": "import anon from './anon';\nimport K from './klass';\nimport * as ns from './index';\n"
            "export function go() {\n  anon();\n  K.make();\n  ns.inner.one();\n}\n",
            "index.ts": "export * as inner from './cjs';\n",
        },
    )
    assert stats["parse_errors"] == [] and stats["files_with_syntax_errors"] == []
    with GraphService(str(db)) as graph:
        found = {r["qualname"]: r["kind"] for r in graph.query("search", "o")["results"]}
        assert found["one"] == "function" and found["two"] == "function"
        callees = {(r["qualname"], r["line"]) for r in graph.query("callees", "run")["results"]}
        assert ("one", 4) in callees and ("two", 6) in callees
        callees = {r["qualname"] for r in graph.query("callees", "go")["results"]}
        assert {"default", "default.make"} <= callees
