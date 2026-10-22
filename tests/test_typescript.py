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
