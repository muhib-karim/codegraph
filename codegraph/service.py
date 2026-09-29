"""Typed, read-only graph boundary shared by MCP and the evaluation runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from . import SCHEMA_VERSION, queries, store
from .discover import discover

Record = dict[str, Any]


class GraphService:
    def __init__(self, db_path: str) -> None:
        self.db, self.conn = store.connect(db_path)
        self.meta = queries.meta(self.conn)
        if self.meta.get("schema_version") != str(SCHEMA_VERSION):
            self.close()
            raise ValueError("Unsupported graph schema; rebuild the index")
        self.root = Path(self.meta["repo_root"]).resolve()
        self.files: dict[str, Record] = {
            p: {
                "file": p,
                "line": 1,
                "citation": f"{p}:1",
                "language": lang,
                "parsed": parsed,
                "loc": loc,
                "confidence": "not_applicable",
            }
            for p, lang, parsed, loc in self.conn.execute(
                "MATCH (f:File) RETURN f.path, f.lang, f.parsed, f.loc ORDER BY f.path"
            ).get_all()
        }

    def close(self) -> None:
        self.conn.close()
        self.db.close()

    def __enter__(self) -> GraphService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def path(self, value: str, *, prefix: bool = False) -> None:
        """Reject traversal, absolute paths, unindexed paths and symlink escapes."""
        if not value:
            return
        parts = PurePosixPath(value).parts
        if (
            len(value) > 512
            or value.startswith("/")
            or "\\" in value
            or ":" in value
            or ".." in parts
            or ".git" in parts
            or "\x00" in value
        ):
            raise ValueError("Use a path inside the indexed repository")
        normalized = value.rstrip("/")
        if not (self.root / normalized).resolve().is_relative_to(self.root):
            raise ValueError("Path escapes the indexed repository")
        if normalized not in self.files and not (
            prefix and any(p.startswith(normalized + "/") for p in self.files)
        ):
            raise ValueError("Path is not in the indexed repository")

    @staticmethod
    def page(rows: list[Record], limit: int, offset: int) -> Record:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be nonnegative")
        more = offset + limit < len(rows)
        return {
            "results": rows[offset : offset + limit],
            "total": len(rows),
            "next_offset": offset + limit if more else None,
            "truncated": more,
        }

    def query(
        self,
        kind: str,
        target: str = "",
        *,
        in_file: str = "",
        scope: str = "",
        depth: int = 1,
        ancestors: bool = False,
        kinds: list[str] | None = None,
        confidence: str = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> Record:
        self.path(in_file)
        self.path(scope, prefix=True)
        if not 1 <= depth <= 10:
            raise ValueError("depth must be 1..10")
        if not 0 < len(target) <= 512 and kind != "dead-code":
            raise ValueError("A target of 1..512 characters is required")
        if "::" in target:
            self.path(target.split("::", 1)[0])
        elif "/" in target or "\\" in target or target.startswith(".") or ":" in target:
            self.path(target)
        if kinds and any(k not in queries.CODE_KINDS for k in kinds):
            raise ValueError("Unknown symbol kind")
        if confidence not in ("all", "likely", "possible"):
            raise ValueError("Unknown dead-code confidence")
        resolved: list[Record]
        results: list[Record]
        if kind == "find":
            resolved = [queries._sym(r) for r in queries.resolve_symbol(self.conn, target, in_file)]
            results = [
                {
                    **r,
                    "symbol": r["id"],
                    "citation": f"{r['file']}:{r['line']}",
                    "confidence": "exact",
                    "reason": "definition",
                }
                for r in resolved
                if not scope
                or r["file"] == scope.rstrip("/")
                or r["file"].startswith(scope.rstrip("/") + "/")
            ]
        elif kind == "callers":
            resolved, results = queries.callers(self.conn, target, in_file, depth, scope)
        elif kind == "callees":
            resolved, results = self.callees(target, in_file, scope)
        elif kind == "inherits":
            resolved, results = queries.inherits(
                self.conn, target, in_file, ancestors, depth, scope
            )
        elif kind == "blast":
            resolved, results = queries.blast(self.conn, target, in_file, depth, scope)
        elif kind == "dead-code":
            resolved, results = [], queries.dead_code(self.conn, scope, kinds, confidence)
        else:
            raise ValueError("Unknown query kind")
        # Guard stored paths as well as selectors, including post-index symlink replacement.
        for row in results:
            self.path(row["file"])
        return {
            "schema_version": SCHEMA_VERSION,
            "command": kind,
            "resolved": resolved,
            "depth": depth,
            **self.page(results, limit, offset),
        }

    def callees(self, target: str, in_file: str, scope: str) -> tuple[list[Record], list[Record]]:
        resolved = [queries._sym(r) for r in queries.resolve_symbol(self.conn, target, in_file)]
        rows = self.conn.execute(
            "MATCH (s:Symbol)-[r:CALLS]->(t:Symbol) WHERE s.id IN $ids "
            "RETURN t.id, t.qualname, t.kind, t.file, t.line, r.file, r.line, "
            "r.confidence, r.reason, s.id ORDER BY r.file, r.line, t.id",
            {"ids": [r["id"] for r in resolved]},
        ).get_all()
        results = [
            {
                "symbol": sid,
                "qualname": qn,
                "kind": kind,
                "file": f,
                "line": ln,
                "citation": f"{f}:{ln}",
                "def": f"{df}:{dl}",
                "confidence": conf,
                "reason": reason,
                "caller": caller,
                "edge": "call",
            }
            for sid, qn, kind, df, dl, f, ln, conf, reason, caller in rows
            if not scope or f == scope.rstrip("/") or f.startswith(scope.rstrip("/") + "/")
        ]
        return resolved, results

    def status(self, limit: int = 100, offset: int = 0) -> Record:
        hashes: dict[str, str] = json.loads(self.meta.get("file_hashes", "{}"))
        changed: list[str] = []
        for name, digest in hashes.items():
            try:
                self.path(name)
                if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != digest:
                    changed.append(name)
            except (OSError, ValueError):
                changed.append(name)
        current = {p for p, _ in discover(str(self.root))}
        added = sorted(current - self.files.keys())
        missing = sorted(self.files.keys() - current)
        stale = bool(changed or added or missing) if hashes else None
        results = [
            {**r, "changed": r["file"] in changed, "missing": r["file"] in missing}
            for r in self.files.values()
        ]
        stats = json.loads(self.meta.get("stats", "{}"))
        return {
            "schema_version": SCHEMA_VERSION,
            "indexed_at": self.meta.get("indexed_at"),
            "stats": stats,
            "snapshot_stale": stale,
            "staleness_method": "sha256" if hashes else "unknown (reindex to enable hashes)",
            "changed_files": sorted(changed),
            "added_files": added,
            "missing_files": missing,
            "parsed_files": sum(bool(r["parsed"]) for r in results),
            "indexed_files": len(results),
            **self.page(results, limit, offset),
        }
