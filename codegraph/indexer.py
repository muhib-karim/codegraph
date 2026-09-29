"""Orchestrates stages 0-3."""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import subprocess
import time
from collections import Counter
from typing import Any

from . import extract_java, extract_python, store
from .discover import PARSED_LANGS, discover
from .model import FileInfo
from .resolve import Resolver

EXTRACTORS = {"python": extract_python.extract, "java": extract_java.extract}


def build(root: str):
    files = {}
    errors = []
    for rel, lang in discover(root):
        full = os.path.join(root, rel)
        with open(full, "rb") as f:
            src = f.read()
        if lang in PARSED_LANGS:
            try:
                files[rel] = EXTRACTORS[lang](rel, src)
                files[rel].content_hash = hashlib.sha256(src).hexdigest()
                continue
            except Exception as e:  # keep indexing; record the failure
                errors.append(f"{rel}: {type(e).__name__}: {e}")
        loc = src.count(b"\n") + (0 if src.endswith(b"\n") or not src else 1)
        files[rel] = FileInfo(
            path=rel, lang=lang, loc=loc, parsed=False, content_hash=hashlib.sha256(src).hexdigest()
        )
    graph = Resolver(files).run()
    return graph, errors


def git_head(root):
    try:
        return subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return ""


def index(root: str, db_path: str) -> dict[str, Any]:
    t0 = time.time()
    root = os.path.abspath(root)
    graph, errors = build(root)
    langs = Counter(fi.lang for fi in graph.files.values())
    parsed = Counter(fi.lang for fi in graph.files.values() if fi.parsed)
    kinds = Counter(s.kind for s in graph.symbols.values())
    stats = {
        "files": len(graph.files),
        "files_by_lang": dict(langs),
        "parsed_by_lang": dict(parsed),
        "unparsed_code_files": sorted(
            p
            for p, fi in graph.files.items()
            if not fi.parsed
            and fi.lang
            in ("kotlin", "shell", "smali", "javascript", "typescript", "go", "rust", "c", "cpp")
        ),
        "symbols_by_kind": dict(kinds),
        "calls": len(graph.calls),
        "references": len(graph.refs),
        "inherits": len(graph.inherits),
        "imports_internal": len(set(graph.imports)),
        "resolution": dict(graph.stats),
        "parse_errors": errors,
    }
    meta = {
        "repo_root": root,
        "repo_commit": git_head(root),
        "indexed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "file_hashes": {p: fi.content_hash for p, fi in graph.files.items()},
    }
    store.write(graph, db_path, meta)
    stats["seconds"] = round(time.time() - t0, 2)
    return stats
