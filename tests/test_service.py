import shutil
from pathlib import Path

import pytest

from codegraph.indexer import index
from codegraph.service import GraphService

MINI = Path(__file__).parent / "fixtures" / "mini"


@pytest.fixture
def graph(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(MINI, root)
    db = str(tmp_path / "g.lbug")
    index(str(root), db)
    with GraphService(db) as service:
        yield service


def test_status_detects_content_additions_deletions_and_symlinks(graph, tmp_path):
    assert graph.status()["snapshot_stale"] is False
    (graph.root / "app.py").write_text("# changed\n")
    (graph.root / "new.py").write_text("# new\n")
    (graph.root / "decoys.py").unlink()
    status = graph.status()
    assert status["snapshot_stale"]
    assert "app.py" in status["changed_files"]
    assert status["added_files"] == ["new.py"]
    assert status["missing_files"] == ["decoys.py"]
    outside = tmp_path / "secret"
    outside.write_text("not returned")
    (graph.root / "app.py").unlink()
    (graph.root / "app.py").symlink_to(outside)
    assert "app.py" in graph.status()["changed_files"]
    with pytest.raises(ValueError, match="escapes"):
        graph.query("find", "main")
    graph.meta.pop("file_hashes")
    assert graph.status()["snapshot_stale"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "invalid", "target": "make"},
        {"kind": "find"},
        {"kind": "dead-code", "kinds": ["bogus"]},
        {"kind": "dead-code", "confidence": "certain"},
        {"kind": "find", "target": "make", "scope": ".git/config"},
        {"kind": "find", "target": "make", "limit": 0},
    ],
)
def test_validation(graph, kwargs):
    with pytest.raises(ValueError):
        graph.query(**kwargs)


def test_callee_identity_and_scopes(graph):
    results = graph.query("callees", "make.inner", scope="pkg")["results"]
    assert {r["symbol"] for r in results} == {
        "pkg/shapes.py::Circle",
        "pkg/shapes.py::Circle.__init__/1",
    }
    assert all(r["citation"] == "pkg/shapes.py:34" for r in results)
    assert graph.query("find", "Circle", scope="app.py")["results"] == []
