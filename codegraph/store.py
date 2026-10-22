"""Stage 3: write the resolved graph into LadybugDB (bulk COPY from CSV)."""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from typing import Any

import ladybug as lb

from . import SCHEMA_VERSION, __version__

DDL = [
    "CREATE NODE TABLE File(path STRING, lang STRING, loc INT64, parsed BOOLEAN, package STRING, PRIMARY KEY(path))",
    "CREATE NODE TABLE Symbol(id STRING, name STRING, qualname STRING, kind STRING, lang STRING, file STRING, "
    "line INT64, end_line INT64, arity_min INT64, arity_max INT64, visibility STRING, is_static BOOLEAN, "
    "annotations STRING, parent_id STRING, entry_reason STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Meta(key STRING, value STRING, PRIMARY KEY(key))",
    "CREATE REL TABLE DEFINES(FROM File TO Symbol)",
    "CREATE REL TABLE CONTAINS(FROM Symbol TO Symbol)",
    "CREATE REL TABLE CALLS(FROM Symbol TO Symbol, file STRING, line INT64, col INT64, confidence STRING, reason STRING)",
    "CREATE REL TABLE REFERENCES(FROM Symbol TO Symbol, file STRING, line INT64, col INT64, confidence STRING, reason STRING)",
    "CREATE REL TABLE INHERITS(FROM Symbol TO Symbol, file STRING, line INT64, kind STRING, confidence STRING)",
    "CREATE REL TABLE IMPORTS(FROM File TO File, line INT64, name STRING, confidence STRING)",
]


def _b(v):
    return "true" if v else "false"


def write(graph, db_path: str, meta: dict):
    if os.path.exists(db_path):
        if os.path.isdir(db_path):
            shutil.rmtree(db_path)
        else:
            os.remove(db_path)
        for suffix in (".wal", ".shadow"):
            if os.path.exists(db_path + suffix):
                os.remove(db_path + suffix)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="codegraph-")
    try:

        def dump(name, rows, header=None):
            p = os.path.join(tmp, name + ".csv")
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                if header:
                    w.writerow(header)
                w.writerows(rows)
            return p

        files = [
            (fi.path, fi.lang, fi.loc, _b(fi.parsed), fi.package) for fi in graph.files.values()
        ]
        syms = [
            (
                s.id,
                s.name,
                s.qualname,
                s.kind,
                s.lang,
                s.file,
                s.line,
                s.end_line,
                s.arity_min,
                s.arity_max,
                s.visibility,
                _b(s.is_static),
                ",".join(s.annotations),
                s.parent_id or "",
                s.entry_reason,
            )
            for s in graph.symbols.values()
        ]
        defines = [
            (s.file, s.id)
            for s in graph.symbols.values()
            if s.file and s.kind != "module" or (s.kind == "module")
        ]
        defines = [(f, i) for f, i in defines if f]
        contains = [(s.parent_id, s.id) for s in graph.symbols.values() if s.parent_id]
        calls = [(e.src, e.dst, e.file, e.line, e.col, e.confidence, e.reason) for e in graph.calls]
        refs = [(e.src, e.dst, e.file, e.line, e.col, e.confidence, e.reason) for e in graph.refs]
        inh = [(e.src, e.dst, e.file, e.line, e.kind, e.confidence) for e in graph.inherits]
        imps = sorted(set(graph.imports))
        meta_rows = [(k, v if isinstance(v, str) else json.dumps(v)) for k, v in meta.items()]
        meta_rows += [("schema_version", str(SCHEMA_VERSION)), ("codegraph_version", __version__)]

        db = lb.Database(db_path, buffer_pool_size=64 * 1024 * 1024, max_num_threads=2)
        conn = lb.Connection(db)
        for stmt in DDL:
            conn.execute(stmt)
        for table, rows in (
            ("File", files),
            ("Symbol", syms),
            ("Meta", meta_rows),
            ("DEFINES", defines),
            ("CONTAINS", contains),
            ("CALLS", calls),
            ("REFERENCES", refs),
            ("INHERITS", inh),
            ("IMPORTS", imps),
        ):
            if rows:
                p = dump(table, rows)
                # Explicit dialect: auto-detection samples early rows and turns quoting off
                # when none of them is quoted, which splits a later quoted field.
                conn.execute(
                    f"COPY {table} FROM '{p}' "
                    "(HEADER=false, AUTO_DETECT=false, DELIM=',', QUOTE='\"', ESCAPE='\"')"
                )
        conn.close() if hasattr(conn, "close") else None
        db.close() if hasattr(db, "close") else None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def connect(db_path: str, read_only: bool = True) -> tuple[Any, Any]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    db = lb.Database(
        db_path, read_only=read_only, buffer_pool_size=64 * 1024 * 1024, max_num_threads=2
    )
    return db, lb.Connection(db)
