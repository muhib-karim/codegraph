"""Offline, schema-versioned retrieval evaluation. Labels never enter a retriever."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from statistics import mean

from . import __version__, queries
from .indexer import index
from .service import GraphService, Record

KINDS = {"callers", "inherits", "dead-code", "blast", "find"}
ARGUMENTS = {"target", "in_file", "scope", "depth", "ancestors", "kinds", "confidence"}
# Language of the code under test; optional per row. Report order follows this tuple.
LANGUAGES = ("python", "java", "typescript", "javascript")


def load_questions(path: Path, fixtures: Path) -> list[Record]:
    rows = []
    ids: set[str] = set()
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or row.get("schema_version") != 1:
            raise ValueError(f"Question {number}: unsupported schema")
        if not isinstance(row.get("id"), str) or row["id"] in ids:
            raise ValueError(f"Question {number}: missing or duplicate id")
        ids.add(row["id"])
        if row.get("kind") not in KINDS or row.get("difficulty") not in {"easy", "medium", "hard"}:
            raise ValueError(f"Question {number}: invalid kind or difficulty")
        if "language" in row and row["language"] not in LANGUAGES:
            raise ValueError(f"Question {number}: invalid language")
        repo = row.get("repo", "")
        if not isinstance(repo, str) or not repo or Path(repo).name != repo:
            raise ValueError(f"Question {number}: invalid repo")
        root = (fixtures / repo).resolve()
        if not root.is_relative_to(fixtures.resolve()) or not root.is_dir():
            raise ValueError(f"Question {number}: fixture outside root or missing")
        args = row.get("arguments")
        if not isinstance(args, dict) or args.keys() - ARGUMENTS:
            raise ValueError(f"Question {number}: invalid arguments")
        for key, value in args.items():
            if key == "depth":
                valid = type(value) is int and 1 <= value <= 10
            elif key == "ancestors":
                valid = type(value) is bool
            elif key == "kinds":
                valid = isinstance(value, list) and all(v in queries.CODE_KINDS for v in value)
            else:
                valid = isinstance(value, str)
            if not valid:
                raise ValueError(f"Question {number}: invalid {key}")
        if row["kind"] != "dead-code" and not args.get("target"):
            raise ValueError(f"Question {number}: target required")
        if not isinstance(row.get("expected"), list):
            raise ValueError(f"Question {number}: expected must be a list")
        seen = set()
        for answer in row["expected"]:
            if not isinstance(answer, dict) or set(answer) != {"symbol", "file", "line"}:
                raise ValueError(f"Question {number}: invalid answer")
            if not isinstance(answer["symbol"], str) or "::" not in answer["symbol"]:
                raise ValueError(f"Question {number}: symbol id required")
            if not isinstance(answer["file"], str):
                raise ValueError(f"Question {number}: file required")
            source = (root / answer["file"]).resolve()
            if not source.is_relative_to(root) or not source.is_file():
                raise ValueError(f"Question {number}: invalid citation path")
            if type(answer["line"]) is not int or not 1 <= answer["line"] <= len(
                source.read_text().splitlines()
            ):
                raise ValueError(f"Question {number}: invalid citation line")
            key = (answer["symbol"], answer["file"], answer["line"])
            if key in seen:
                raise ValueError(f"Question {number}: duplicate expected answer")
            seen.add(key)
        rows.append(row)
    if not rows:
        raise ValueError("Question set is empty")
    return rows


def score(expected: list[Record], predicted: list[Record], k: int) -> Record:
    """Retrieval uses unique symbol ids. Citation accuracy uses distinct evidence tuples."""
    gold = {r["symbol"] for r in expected}
    ranked = list(dict.fromkeys(r["symbol"] for r in predicted))
    found = set(ranked)
    tp = len(gold & found)
    precision = tp / len(found) if found else float(not gold)
    recall = tp / len(gold) if gold else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    citations = {(r["symbol"], r["file"], r["line"]) for r in predicted}
    evidence = {(r["symbol"], r["file"], r["line"]) for r in expected}
    rr = next((1 / n for n, sid in enumerate(ranked, 1) if sid in gold), 0.0)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mrr": rr if gold else None,
        "hit_at_k": float(bool(gold & set(ranked[:k]))) if gold else None,
        "citation_accuracy": len(citations & evidence) / len(citations)
        if citations
        else float(not evidence),
        "true_positives": tp,
        "predicted_symbols": len(found),
        "expected_symbols": len(gold),
    }


def by_language(results: list[Record]) -> Record:
    """Macro averages per question language, like by_kind; rows without one are "unspecified"."""
    groups: dict[str, list[Record]] = {}
    for r in results:
        groups.setdefault(r.get("language", "unspecified"), []).append(r)
    return {
        lang: {
            name: aggregate([r["scores"][name] for r in groups[lang]]) for name in ("graph", "text")
        }
        for lang in (*LANGUAGES, "unspecified")
        if lang in groups
    }


def aggregate(scores: list[Record]) -> Record:
    result: Record = {"questions": len(scores)}
    for key in ("precision", "recall", "f1", "mrr", "hit_at_k", "citation_accuracy"):
        values = [s[key] for s in scores if s[key] is not None]
        result[key] = mean(values) if values else None
    return result


class TextRetriever:
    """Word search only; shared definition spans attach stable ids, never graph edges."""

    def __init__(self, graph: GraphService) -> None:
        self.root = graph.root
        self.symbols: list[Record] = [
            dict(
                zip(
                    ("id", "name", "qualname", "kind", "file", "line", "end_line", "visibility"),
                    r,
                    strict=True,
                )
            )
            for r in graph.conn.execute(
                "MATCH (s:Symbol) WHERE s.kind <> 'external' RETURN s.id, s.name, s.qualname, "
                "s.kind, s.file, s.line, s.end_line, s.visibility ORDER BY s.file, s.line, s.id"
            ).get_all()
        ]
        self.lines = {
            p: (self.root / p).read_text().splitlines()
            for p, row in graph.files.items()
            if row["parsed"]
        }

    @staticmethod
    def result(sym: Record, file: str, line: int) -> Record:
        return {
            "symbol": sym["id"],
            "file": file,
            "line": line,
            "citation": f"{file}:{line}",
            "confidence": "text",
        }

    def retrieve(self, kind: str, args: Record) -> list[Record]:
        target = args.get("target", "")
        term = target.split("::")[-1].split("/")[0].split(".")[-1]
        scope = args.get("scope", "").rstrip("/")

        def scoped(file: str) -> bool:
            return not scope or file == scope or file.startswith(scope + "/")

        if kind == "find":
            return [
                self.result(s, s["file"], s["line"])
                for s in self.symbols
                if s["name"] == term
                and scoped(s["file"])
                and (not args.get("in_file") or s["file"] == args["in_file"])
            ]
        if kind == "dead-code":
            results = []
            for s in self.symbols:
                if s["kind"] not in args.get("kinds", queries.CODE_KINDS) or not scoped(s["file"]):
                    continue
                likely = s["visibility"] == "private" or (
                    s["kind"] == "function" and "." in s["qualname"]
                )
                if args.get("confidence", "all") not in ("all", "likely" if likely else "possible"):
                    continue
                pattern = re.compile(r"\b" + re.escape(s["name"]) + r"\b")
                uses = [
                    (f, n)
                    for f, lines in self.lines.items()
                    for n, line in enumerate(lines, 1)
                    if pattern.search(line) and (f, n) != (s["file"], s["line"])
                ]
                if not uses:
                    results.append(self.result(s, s["file"], s["line"]))
            return results
        pattern = re.compile(r"\b" + re.escape(term) + r"\b")
        results = []
        for file, lines in sorted(self.lines.items()):
            for number, line in enumerate(lines, 1):
                if not pattern.search(line) or not scoped(file):
                    continue
                owners = [
                    s
                    for s in self.symbols
                    if s["file"] == file and s["line"] <= number <= s["end_line"]
                ]
                if not owners:
                    continue
                owner = min(owners, key=lambda s: (s["end_line"] - s["line"], -s["line"]))
                if kind == "inherits":
                    if not re.search(r"\b(class|interface)\b", line):
                        continue
                    if args.get("ancestors"):
                        for parent in self.symbols:
                            if (
                                parent["kind"] in ("class", "interface")
                                and parent["name"] != term
                                and re.search(r"\b" + re.escape(parent["name"]) + r"\b", line)
                            ):
                                results.append(self.result(parent, file, number))
                        continue
                    if owner["name"] == term:
                        continue
                elif number == owner["line"] or re.match(r"\s*(from|import|package)\b", line):
                    continue
                results.append(self.result(owner, file, number))
        return results


def retrieve_graph(graph: GraphService, kind: str, args: Record) -> list[Record]:
    result: list[Record] = []
    offset = 0
    while True:
        try:
            page = graph.query(kind, **args, offset=offset)
        except queries.NotFound:
            return []
        result.extend(page["results"])
        if page["next_offset"] is None:
            return result
        offset = page["next_offset"]


def render(report: Record) -> str:
    lines = [
        "# Retrieval evaluation",
        "",
        f"Command: `{report['command']}`",
        "",
        f"codegraph {report['codegraph_version']}; question schema 1; "
        f"{report['questions']} questions; k={report['k']}.",
        "",
        f"Questions SHA-256: `{report['questions_sha256']}`",
        "",
        "Metrics are macro averages over questions. Ranking excludes empty-gold questions.",
        "Citation accuracy is the share of distinct returned (symbol id, file, line) tuples",
        "that match a labelled tuple.",
        "",
        "| Kind | Retriever | P | R | F1 | MRR | hit@k | Citation accuracy |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for kind, group in [("overall", report["overall"]), *report["by_kind"].items()]:
        for retriever, metrics in group.items():
            values = [
                "n/a" if metrics[k] is None else f"{metrics[k]:.4f}"
                for k in ("precision", "recall", "f1", "mrr", "hit_at_k", "citation_accuracy")
            ]
            lines.append(f"| {kind} | {retriever} | " + " | ".join(values) + " |")
    lines += [
        "",
        "## By language",
        "",
        "Language of the code under test, as labelled per question. Same macro averages.",
        "",
        "| Language | Retriever | Q | P | R | F1 | MRR | hit@k | Citation accuracy |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lang, group in report["by_language"].items():
        for retriever, metrics in group.items():
            values = [
                "n/a" if metrics[k] is None else f"{metrics[k]:.4f}"
                for k in ("precision", "recall", "f1", "mrr", "hit_at_k", "citation_accuracy")
            ]
            lines.append(
                f"| {lang} | {retriever} | {metrics['questions']} | " + " | ".join(values) + " |"
            )
    lines += [
        "",
        "## Confidence breakdown",
        "",
        "Each row keeps only the predictions carrying that tag. P, F1 and citation accuracy",
        "average over the questions where the tag produced at least one prediction (column Q).",
        "R, MRR and hit@k average over all questions with non-empty gold, so R is the share",
        "of gold symbols the tag covers. Tags are not ground-truth labels. `likely`/`possible`",
        "additionally filter dead-code candidates, so rows overlap.",
        "",
        "| Retriever / tag | Q | P | R | F1 | MRR | hit@k | Citation accuracy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in report["by_confidence"].items():
        values = [
            "n/a" if metrics[k] is None else f"{metrics[k]:.4f}"
            for k in ("precision", "recall", "f1", "mrr", "hit_at_k", "citation_accuracy")
        ]
        lines.append(f"| {name} | {metrics['tagged_questions']} | " + " | ".join(values) + " |")
    lines += ["", "## Cases with graph errors", ""]
    for row in report["results"]:
        metrics = row["scores"]["graph"]
        if metrics["f1"] < 1 or metrics["citation_accuracy"] < 1:
            lines.append(
                f"- `{row['id']}`: F1 {metrics['f1']:.4f}, citation accuracy {metrics['citation_accuracy']:.4f}."
            )
    lines += [
        "",
        "See ../README.md for label policy, baseline details, empty-set conventions and limits.",
        "",
    ]
    return "\n".join(lines)


def run(questions: str, fixtures: str, output: str, k: int, command: str) -> Record:
    if k < 1:
        raise ValueError("k must be positive")
    path = Path(questions)
    labels = load_questions(path, Path(fixtures))
    results = []
    fixture_hashes = {}
    with tempfile.TemporaryDirectory(prefix="codegraph-eval-") as tmp:
        for repo in sorted({row["repo"] for row in labels}):
            db = str(Path(tmp) / f"{repo}.lbug")
            index(str(Path(fixtures) / repo), db)
            with GraphService(db) as graph:
                fixture_hashes[repo] = json.loads(graph.meta["file_hashes"])
                text = TextRetriever(graph)
                # Check symbol identity independently of retrieval; evidence lines are human labels.
                known = {s["id"] for s in text.symbols}
                for question in (row for row in labels if row["repo"] == repo):
                    if any(a["symbol"] not in known for a in question["expected"]):
                        raise ValueError(f"Unknown gold symbol in {question['id']}")
                    predictions = {
                        "graph": retrieve_graph(graph, question["kind"], question["arguments"]),
                        "text": text.retrieve(question["kind"], question["arguments"]),
                    }
                    results.append(
                        {
                            **question,
                            "predictions": predictions,
                            "scores": {
                                name: score(question["expected"], pred, k)
                                for name, pred in predictions.items()
                            },
                        }
                    )
    results.sort(key=lambda r: r["id"])
    overall = {name: aggregate([r["scores"][name] for r in results]) for name in ("graph", "text")}
    by_kind = {
        kind: {
            name: aggregate([r["scores"][name] for r in results if r["kind"] == kind])
            for name in ("graph", "text")
        }
        for kind in sorted(KINDS)
    }
    by_confidence: Record = {}
    for name in ("graph", "text"):
        tags = {p["confidence"] for r in results for p in r["predictions"][name]}
        tags |= {
            p["dead_confidence"]
            for r in results
            for p in r["predictions"][name]
            if "dead_confidence" in p
        }
        for tag in sorted(tags):
            tag_scores = []
            for r in results:
                tagged = [
                    p
                    for p in r["predictions"][name]
                    if p["confidence"] == tag or p.get("dead_confidence") == tag
                ]
                s = score(r["expected"], tagged, k)
                if not tagged:
                    # Precision is undefined for a question where the tag predicted nothing.
                    s.update(precision=None, f1=None, citation_accuracy=None)
                if not r["expected"]:
                    # Empty gold has nothing for a tag to cover; skip it, as MRR/hit@k do.
                    s["recall"] = None
                tag_scores.append(s)
            by_confidence[f"{name}/{tag}"] = {
                **aggregate(tag_scores),
                "tagged_questions": sum(s["precision"] is not None for s in tag_scores),
            }
    report = {
        "schema_version": 1,
        "codegraph_version": __version__,
        "command": command,
        "questions": len(labels),
        "k": k,
        "questions_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "fixture_hashes": fixture_hashes,
        "overall": overall,
        "by_kind": by_kind,
        "by_language": by_language(results),
        "by_confidence": by_confidence,
        "results": results,
    }
    dest = Path(output)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "latest.json").write_text(json.dumps(report, indent=2) + "\n")
    (dest / "latest.md").write_text(render(report))
    return report
