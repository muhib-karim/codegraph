"""The benchmark script runs offline on a local fixture and labels its numbers."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("bench_run", ROOT / "bench" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_benchmark_writes_labelled_json_and_table(tmp_path, capsys):
    bench = load()
    assert (
        bench.main(
            ["--local", str(ROOT / "tests/fixtures/webjs"), "--runs", "2", "--out", str(tmp_path)]
        )
        == 0
    )
    report = json.loads((tmp_path / "latest.json").read_text())
    assert report["runner"]["ci"] in ("local", "GitHub Actions")
    assert report["date"] and report["version"]
    [repo] = report["repos"]
    assert repo["parsed_by_lang"] == {"javascript": 5}
    assert set(repo["queries"]) == {"callers", "callees", "impact", "search"}
    for q in repo["queries"].values():
        assert q["median_ms"] >= 0 and q["p95_ms"] >= q["median_ms"] and q["results"] > 0
    table = (tmp_path / "latest.md").read_text()
    assert "Runner:" in table and "| webjs (mixed) | `local` | 5 |" in table


def test_pinned_repositories_grow_and_use_tags():
    repos = json.loads((ROOT / "bench" / "repos.json").read_text())
    assert [r["name"] for r in repos] == ["requests", "zod", "gson"]
    assert all(r["url"].startswith("https://github.com/") and r["ref"] for r in repos)
