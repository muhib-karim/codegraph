import json
from pathlib import Path

import pytest

from codegraph.evaluation import aggregate, load_questions, run, score


def answer(symbol, line=1):
    return {"symbol": symbol, "file": "a.py", "line": line}


def test_metrics_detect_wrong_citations_duplicates_and_ranks():
    gold = [answer("a"), answer("b")]
    predictions = [answer("decoy"), answer("a", 2), answer("a", 2)]
    result = score(gold, predictions, 1)
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
    assert result["mrr"] == 0.5
    assert result["hit_at_k"] == result["citation_accuracy"] == 0
    assert score(gold, predictions, 2)["hit_at_k"] == 1
    assert score([], [], 5)["f1"] == 1
    assert score([], [], 5)["mrr"] is None
    assert score([], predictions, 5)["precision"] == 0
    assert score(gold, [], 5)["recall"] == 0
    assert aggregate([score([], [], 1)])["mrr"] is None


def test_full_fixture_evaluation(tmp_path):
    report = run("eval/questions.jsonl", "tests/fixtures", str(tmp_path), 5, "codegraph eval")
    assert report["questions"] >= 40
    assert set(report["by_kind"]) == {"callers", "inherits", "dead-code", "blast", "find"}
    assert {"graph/exact", "graph/heuristic", "graph/likely", "graph/possible", "text/text"} <= set(
        report["by_confidence"]
    )
    for tag in report["by_confidence"].values():
        # Tag precision is averaged only where the tag produced predictions.
        assert 1 <= tag["tagged_questions"] <= report["questions"]
        assert tag["precision"] is not None
    # Keep failures visible. This is a semantic canary, not an expected aggregate score.
    row = next(r for r in report["results"] if r["id"] == "callers-010")
    assert row["expected"] and not row["predictions"]["graph"]
    assert row["scores"]["graph"]["recall"] == 0
    assert json.loads((tmp_path / "latest.json").read_text())["overall"] == report["overall"]
    assert "Command: `codegraph eval`" in (tmp_path / "latest.md").read_text()


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"kind": "sql"},
        {"difficulty": "unknown"},
        {"repo": "../mini"},
        {"repo": "missing"},
        {"arguments": {"evil": 1}},
        {"arguments": {"target": "make", "depth": True}},
        {"arguments": {}},
        {"expected": "invalid"},
        {"expected": [{"symbol": "make"}]},
        {"expected": [{"symbol": "make", "file": "app.py", "line": 1}]},
        {"expected": [{"symbol": "x::y", "file": "../outside", "line": 1}]},
        {"expected": [{"symbol": "x::y", "file": "app.py", "line": 999}]},
    ],
)
def test_invalid_label_sets(tmp_path, change):
    original = json.loads(Path("eval/questions.jsonl").read_text().splitlines()[0])
    original.update(change)
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(original))
    with pytest.raises(ValueError):
        load_questions(path, Path("tests/fixtures"))


def test_empty_duplicate_and_invalid_k(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_questions(path, Path("tests/fixtures"))
    original = Path("eval/questions.jsonl").read_text().splitlines()[0]
    path.write_text(original + "\n" + original)
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(path, Path("tests/fixtures"))
    with pytest.raises(ValueError, match="positive"):
        run(str(path), "tests/fixtures", str(tmp_path), 0, "invalid")
