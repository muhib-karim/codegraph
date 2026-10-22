"""CLI commands added in 1.1.0: callees, search and impact (alias of blast)."""

from pathlib import Path

import pytest

from codegraph.cli import main
from codegraph.indexer import index

WEB = Path(__file__).parent / "fixtures" / "web"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("cli") / "graph.lbug"
    index(str(WEB), str(path))
    return str(path)


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out.splitlines(), out.err


def test_callees_lists_call_sites_with_targets(db, capsys):
    code, lines, _ = run(capsys, "callees", "make", "--db", db)
    assert code == 0
    assert lines == [
        "src/app.ts:7\tCircle\tclass\texact\tsrc/shapes.ts:13",
        "src/app.ts:7\tCircle.constructor\tconstructor\texact\tsrc/shapes.ts:14",
        "src/app.ts:7\tscale\tfunction\texact\tsrc/util.ts:3",
    ]


def test_search_ranks_exact_then_prefix_then_substring(db, capsys):
    code, lines, _ = run(capsys, "search", "re", "--db", db)
    assert code == 0
    names = [line.split("\t")[1] for line in lines]
    assert names[0] == "Registry"  # prefix match before substring matches
    assert "Registry.size" not in names  # only names and qualified names that contain "re"
    code, lines, _ = run(capsys, "search", "scale", "--db", db, "--kind", "function")
    assert [line.split("\t")[:3] for line in lines] == [["src/util.ts:3", "scale", "function"]]


def test_search_without_match_is_empty_not_error(db, capsys):
    code, lines, err = run(capsys, "search", "zzz", "--db", db)
    assert (code, lines) == (0, [])
    assert "no results" in err


def test_impact_is_blast(db, capsys):
    assert run(capsys, "impact", "src/util.ts", "--db", db) == run(
        capsys, "blast", "src/util.ts", "--db", db
    )


def test_search_validates_kind_and_query(db, capsys):
    code, _, err = run(capsys, "search", "re", "--db", db, "--kind", "bogus")
    assert code == 1 and "unknown symbol kind" in err
    code, _, err = run(capsys, "search", "", "--db", db)
    assert code == 1 and "1..512" in err
