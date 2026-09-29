import json
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MINI = os.path.join(HERE, "fixtures", "mini")


def cg(*args, db):
    p = subprocess.run(
        [sys.executable, "-m", "codegraph", *args, "--db", db, "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert p.returncode in (0, 2), p.stderr
    return json.loads(p.stdout)


@pytest.fixture(scope="module")
def db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "g.lbug")
    subprocess.run(
        [sys.executable, "-m", "codegraph", "index", MINI, "--db", path],
        check=True,
        cwd=ROOT,
        capture_output=True,
    )
    return path


def sites(out):
    return sorted((a["file"], a["line"]) for a in out["answers"])


def test_python_callers_across_import_and_module_attr(db):
    out = cg("callers", "make", db=db)
    assert sites(out) == [("app.py", 6), ("app.py", 10)]
    assert all(r["confidence"] == "exact" for r in out["results"])


def test_nested_function_and_constructor(db):
    assert sites(cg("callers", "make.inner", db=db)) == [("pkg/shapes.py", 35)]
    assert ("pkg/shapes.py", 34) in sites(cg("callers", "Circle", db=db))


def test_super_and_typed_local(db):
    out = cg("callers", "Circle.area", db=db)
    assert sites(out) == [("pkg/shapes.py", 25)]
    assert ("app.py", 9) in sites(cg("callers", "Ring.area", db=db))


def test_python_inherits(db):
    assert sites(cg("inherits", "Shape", db=db)) == [("pkg/shapes.py", 15), ("pkg/shapes.py", 23)]
    anc = cg("inherits", "Ring", "--ancestors", db=db)
    assert {r["qualname"] for r in anc["results"]} == {"Circle", "Shape"}


def test_java_inherits_and_overloads(db):
    assert sites(cg("inherits", "Animal", db=db)) == [("src/demo/Dog.java", 3)]
    assert sites(cg("inherits", "demo.Base", db=db)) == [("src/demo/Dog.java", 3)]
    out = cg("callers", "Dog.bark", db=db)
    assert sites(out) == [("src/demo/Dog.java", 10)]
    assert {r["target"] for r in out["results"]} == {"src/demo/Dog.java::Dog.bark/1"}


def test_java_ctor_typed_var_method_ref(db):
    assert ("src/demo/Dog.java", 19) in sites(cg("callers", "Dog.<init>", db=db))
    assert sites(cg("callers", "Dog.sound", db=db)) == [("src/demo/Dog.java", 20)]
    assert sites(cg("callers", "Dog.helper", db=db)) == [("src/demo/Dog.java", 21)]
    assert sites(cg("callers", "Base.<init>", db=db)) == [("src/demo/Dog.java", 7)]


def test_dead_code(db):
    out = cg("dead-code", db=db)
    names = {r["qualname"]: r["dead_confidence"] for r in out["results"]}
    assert names.get("_orphan") == "likely"
    assert names.get("UNUSED_CONST") == "possible"
    assert names.get("Dog.neverCalled") == "likely"
    assert names.get("Dog.unusedField") == "likely"
    ids = {r["symbol"] for r in out["results"]}
    assert "src/demo/Dog.java::Dog.bark/2" in ids  # the unused overload
    assert "src/demo/Dog.java::Dog.bark/1" not in ids
    assert "main" not in names and "Dog.sound" not in names
    assert "SCALE" not in names and "Shape.describe" not in names


def test_blast(db):
    out = cg("blast", "pkg/shapes.py", "--depth", "2", db=db)
    assert ("app.py", 6) in sites(out)
    one = cg("blast", "SCALE", "--depth", "1", db=db)
    assert sites(one) == [("pkg/shapes.py", 20)]


def test_not_found_exit_code(db):
    p = subprocess.run(
        [sys.executable, "-m", "codegraph", "callers", "nope_zzz", "--db", db, "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert p.returncode == 2 and "error" in json.loads(p.stdout)
