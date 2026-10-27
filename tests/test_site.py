"""The static Pages build: bundled graph, real CLI session and the labelled benchmark."""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_site_build(tmp_path):
    out = tmp_path / "site"
    load().main(["--out", str(out)])
    page = (out / "index.html").read_text()
    assert "{{" not in page
    # The quickstart terminal is real CLI output on the web fixture, HTML-escaped.
    assert "$ codegraph callers make\nsrc/app.ts:11\tmain\tfunction\texact" in page
    # The benchmark table carries its runner label and only the committed CI numbers.
    bench = json.loads((ROOT / "bench/results/latest.json").read_text())
    assert bench["runner"]["ci"] == "GitHub Actions" and bench["runner"]["run_id"]
    assert f"run {bench['runner']['run_id']}" in page and bench["date"] in page
    for repo in bench["repos"]:
        assert f"<td>{repo['index_seconds']:.2f}</td>" in page
    # Static only: no third-party origins in scripts, styles or fetches.
    assert not re.search(r'(src|href)="https?://(?!github\.com/muhib-karim/codegraph)', page)
    graph = json.loads((out / "data" / "graph.json").read_text())
    ids = {n["id"] for n in graph["nodes"]}
    assert graph["parsed_by_lang"] == {"python": 10, "java": 7, "typescript": 13, "javascript": 11}
    assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])
    assert {n["group"] for n in graph["nodes"]} == {
        "mini",
        "workflow",
        "workflow_ts",
        "web",
        "webjs",
    }
    assert "web/src/util.ts::scale/1" in ids  # the demo's default selection
    js = (out / "demo.js").read_text()
    assert "innerHTML" not in js and "fetch('data/graph.json')" in js


def test_output_directory_guard_refuses_source_paths(tmp_path):
    """Only the pure check runs here: a missing guard must fail the test, never delete files."""
    import pytest

    check = load().check_out
    for target in (ROOT, ROOT / "site", ROOT / "codegraph", ROOT / "site" / "data", ROOT.parent):
        with pytest.raises(SystemExit):
            check(target)
    check(tmp_path / "out")  # a fresh directory elsewhere is fine
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").write_text("keep me")
    with pytest.raises(SystemExit):
        check(tmp_path / "docs")  # existing content that no build wrote
    check(ROOT / "_site")  # the conventional build output inside the checkout is fine
