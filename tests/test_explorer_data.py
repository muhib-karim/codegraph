import os
import tempfile

import pytest

from codegraph import indexer, queries
from codegraph.explorer_data import BadRequest, Explorer

MINI = os.path.join(os.path.dirname(__file__), "fixtures", "mini")


@pytest.fixture(scope="module")
def view():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "g.lbug")
        indexer.index(MINI, db)
        yield Explorer(db)


def test_browse_and_citations(view):
    assert view.status()["schema_version"] == "1"
    page = view.files("pkg/", limit=1)
    assert len(page["items"]) == 1 and page["next"]
    f = view.file("pkg/shapes.py")
    assert f["file"]["parsed"]
    sym = view.symbols("Circle")["items"][0]
    detail = view.symbol(sym["id"])
    assert detail["citation"] == f"{sym['file']}:{sym['line']}"
    graph = view.neighborhood(sym["id"])
    assert any(e["type"] == "INHERITS" for e in graph["edges"])
    assert all(e["source"] in {n["id"] for n in graph["nodes"]} for e in graph["edges"])
    assert view.source(sym["file"], sym["line"], sym["line"])["lines"][0]["line"] == sym["line"]


def test_query_parity(view):
    raw_resolved, raw_results = queries.callers(view.conn, "make")
    result = view.query("callers", "make")
    assert result["resolved"] == raw_resolved
    exact = view.query("callers", "pkg/shapes.py::Circle")
    assert exact["resolved"][0]["id"] == "pkg/shapes.py::Circle"
    assert result["results"]["items"] == raw_results
    assert view.query("dead-code")["results"]["items"] == queries.dead_code(view.conn)


def test_guards(view):
    with pytest.raises(BadRequest):
        view.files(limit=10000)
    with pytest.raises(BadRequest):
        view.query("blast", "make", depth=100)
    with pytest.raises(BadRequest):
        view.neighborhood("pkg/shapes.py::Circle", relations="CALLS|DELETE")
    with pytest.raises(BadRequest):
        view.source("../README.md", 1, 2)
    with pytest.raises(queries.NotFound):
        view.source("not-indexed.py", 1, 2)
    with pytest.raises(queries.NotFound):
        view.symbol("nonexistent")


def test_indexed_symlink_escape_is_rejected(tmp_path, view):
    # Existing indexed path is replaced with an escaping symlink in a disposable copy.
    # This exercises realpath containment after the indexed-file membership check.
    import shutil

    from codegraph import indexer

    repo = tmp_path / "fixture"
    shutil.copytree(MINI, repo)
    outside = tmp_path / "outside.txt"
    outside.write_text("UNIQUE_DISPOSABLE_SENTINEL")
    db = str(tmp_path / "symlink.lbug")
    indexer.index(str(repo), db)
    victim = repo / "app.py"
    victim.unlink()
    victim.symlink_to(outside)
    indexed = Explorer(db)
    assert indexed.file("app.py")["file"]["path"] == "app.py"
    assert (repo / "app.py").is_symlink()
    assert not (repo / "app.py").resolve().is_relative_to(repo.resolve())
    with pytest.raises(queries.NotFound):
        indexed.source("app.py", 1, 1)
