"""The `language` label field, per-language aggregation and the workflow_ts TS/JS questions."""

import json
from pathlib import Path

import pytest

from codegraph.evaluation import by_language, load_questions, run, score
from codegraph.indexer import index
from codegraph.service import GraphService

FIXTURES = Path("tests/fixtures")
QUESTIONS = Path("eval/questions.jsonl")


def ts_rows():
    return [
        r for r in map(json.loads, QUESTIONS.read_text().splitlines()) if r["repo"] == "workflow_ts"
    ]


def write(tmp_path, rows):
    path = tmp_path / "questions.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_language_is_validated_when_present_and_optional(tmp_path):
    row = json.loads(QUESTIONS.read_text().splitlines()[0])
    assert row["language"] == "python"
    with pytest.raises(ValueError, match="invalid language"):
        load_questions(write(tmp_path, [{**row, "language": "rust"}]), FIXTURES)
    with pytest.raises(ValueError, match="invalid language"):
        load_questions(write(tmp_path, [{**row, "language": None}]), FIXTURES)
    legacy = {k: v for k, v in row.items() if k != "language"}
    assert load_questions(write(tmp_path, [legacy]), FIXTURES) == [legacy]


def test_every_question_carries_a_language():
    rows = load_questions(QUESTIONS, FIXTURES)
    assert all(r["language"] in ("python", "java", "typescript", "javascript") for r in rows)


def test_by_language_macro_averages_per_language():
    def result(language, expected, predicted):
        expected = [{"symbol": s, "file": "a.ts", "line": 1} for s in expected]
        predicted = [{"symbol": s, "file": "a.ts", "line": 1} for s in predicted]
        scores = {"graph": score(expected, predicted, 5), "text": score(expected, [], 5)}
        return {"scores": scores} | ({"language": language} if language else {})

    groups = by_language(
        [
            result("javascript", ["a"], ["a"]),
            result("typescript", ["a", "b"], ["a"]),
            result("typescript", ["a"], ["x"]),
            result(None, [], []),
        ]
    )
    assert list(groups) == ["typescript", "javascript", "unspecified"]
    ts = groups["typescript"]["graph"]
    assert ts["questions"] == 2
    assert ts["precision"] == 0.5  # mean of 1.0 and 0.0
    assert ts["recall"] == 0.25  # mean of 0.5 and 0.0
    assert ts["mrr"] == 0.5 and ts["hit_at_k"] == 0.5
    assert groups["javascript"]["graph"]["f1"] == 1
    assert groups["javascript"]["text"]["recall"] == 0
    assert groups["unspecified"]["graph"]["mrr"] is None  # empty gold has no rank


def test_workflow_ts_labels_cover_all_kinds_and_name_indexed_symbols(tmp_path):
    rows = ts_rows()
    assert {r["kind"] for r in rows} == {"callers", "inherits", "dead-code", "blast", "find"}
    assert {r["language"] for r in rows} == {"typescript", "javascript"}
    load_questions(write(tmp_path, rows), FIXTURES)
    db = tmp_path / "g.lbug"
    index(str(FIXTURES / "workflow_ts"), str(db))
    with GraphService(str(db)) as graph:
        known = {
            r[0]
            for r in graph.conn.execute(
                "MATCH (s:Symbol) WHERE s.kind <> 'external' RETURN s.id"
            ).get_all()
        }
    expected = {a["symbol"] for r in rows for a in r["expected"]}
    assert expected and expected <= known


def test_workflow_ts_smoke_run_reports_by_language(tmp_path):
    path = write(tmp_path, ts_rows())
    report = run(str(path), str(FIXTURES), str(tmp_path / "out"), 5, "codegraph eval")
    assert set(report["by_language"]) == {"typescript", "javascript"}
    for group in report["by_language"].values():
        assert group["graph"]["questions"] == 12
    assert list(report["fixture_hashes"]) == ["workflow_ts"]
    # Runtime dispatch stays a visible graph miss.
    row = next(r for r in report["results"] if r["id"] == "callers-016")
    assert row["expected"] and not row["predictions"]["graph"]
    md = (tmp_path / "out" / "latest.md").read_text()
    assert "## By language" in md and "| typescript | graph | 12 |" in md
