"""The four v0.1 queries. Every answer is an exact Cypher lookup against the stored graph."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

Rows = list[dict[str, Any]]

SYM_COLS = "s.id, s.qualname, s.kind, s.file, s.line, s.name, s.visibility, s.parent_id, s.entry_reason, s.lang"
CODE_KINDS = [
    "class",
    "interface",
    "enum",
    "record",
    "function",
    "method",
    "constructor",
    "field",
    "variable",
]


class NotFound(Exception):
    pass


def _rows(conn: Any, q: str, params: dict[str, Any] | None = None) -> list[Any]:
    rows: list[Any] = conn.execute(q, params or {}).get_all()
    return rows


def _sym(row: Any) -> dict[str, Any]:
    return {"id": row[0], "qualname": row[1], "kind": row[2], "file": row[3], "line": row[4]}


def resolve_symbol(
    conn: Any,
    query: str,
    in_file: str = "",
    allow_external: bool = False,
    kinds: list[str] | None = None,
) -> list[Any]:
    """Map a user symbol string to Symbol rows. Accepts <path>::<qualname>, qualified or bare names,
    and Java fully-qualified names."""
    kinds = kinds or CODE_KINDS + (["external"] if allow_external else [])
    base = "MATCH (s:Symbol) WHERE s.kind IN $kinds "
    tries: list[tuple[str, dict[str, Any]]] = []
    if "::" in query:
        tries.append(
            (
                base
                + "AND (s.id = $q OR s.id STARTS WITH ($q + '/') OR s.id STARTS WITH ($q + '@'))",
                {"q": query},
            )
        )
    else:
        tries.append((base + "AND s.qualname = $q", {"q": query}))
        if "." in query:
            tries.append((base + "AND ends_with(s.qualname, '.' + $q)", {"q": query}))
            # java FQN: package + qualname
            tries.append(
                (
                    base + "AND s.lang = 'java' AND EXISTS { MATCH (f:File)-[:DEFINES]->(s) "
                    "WHERE coalesce(f.package, '') <> '' AND f.package + '.' + s.qualname = $q }",
                    {"q": query},
                )
            )
        else:
            tries.append((base + "AND s.name = $q", {"q": query}))
    for q, p in tries:
        p = dict(p, kinds=kinds)
        if in_file:
            q += " AND s.file = $in_file"
            p["in_file"] = in_file
        rows = _rows(conn, q + f" RETURN {SYM_COLS} ORDER BY s.file, s.line", p)
        if rows:
            return rows
    raise NotFound(query)


def _incoming(
    conn: Any, ids: Iterable[str], rels: tuple[str, ...] = ("CALLS", "REFERENCES")
) -> list[Any]:
    out = []
    for rel in rels:
        if rel == "INHERITS":
            q = (
                "MATCH (c:Symbol)-[r:INHERITS]->(t:Symbol) WHERE t.id IN $ids "
                "RETURN c.id, c.qualname, c.kind, c.file, c.line, c.file, c.line, r.confidence, r.kind, t.id"
            )
        else:
            q = (
                f"MATCH (c:Symbol)-[r:{rel}]->(t:Symbol) WHERE t.id IN $ids "
                "RETURN c.id, c.qualname, c.kind, c.file, c.line, r.file, r.line, r.confidence, r.reason, t.id"
            )
        for row in _rows(conn, q, {"ids": list(ids)}):
            out.append((rel,) + tuple(row))
    return out


def _scoped(results: Rows, scope: str) -> Rows:
    if not scope:
        return results
    s = scope.rstrip("/")
    return [r for r in results if r["file"] == s or r["file"].startswith(s + "/")]


def _sort(results: Rows) -> Rows:
    return sorted(
        results, key=lambda r: (r["file"], r["line"], r.get("qualname", ""), r.get("depth", 0))
    )


def callers(
    conn: Any, query: str, in_file: str = "", depth: int = 1, scope: str = ""
) -> tuple[Rows, Rows]:
    targets = resolve_symbol(conn, query, in_file)
    frontier = {t[0] for t in targets}
    # a Python class and its __init__ are both constructor-call targets; treat them as one
    seen_sites = set()
    results, visited = [], set(frontier)
    for d in range(1, max(depth, 1) + 1):
        nxt = set()
        for rel, cid, cq, ck, cf, cl, sf, sl, conf, reason, tid in _incoming(conn, frontier):
            key = (cid, sf, sl)
            if key in seen_sites:
                continue
            seen_sites.add(key)
            results.append(
                {
                    "citation": f"{sf}:{sl}",
                    "file": sf,
                    "line": sl,
                    "symbol": cid,
                    "qualname": cq,
                    "kind": ck,
                    "edge": "call" if rel == "CALLS" else "ref",
                    "confidence": conf,
                    "reason": reason,
                    "depth": d,
                    "via": f"{sf}:{sl}",
                    "target": tid,
                    "def": f"{cf}:{cl}",
                }
            )
            if cid not in visited:
                visited.add(cid)
                nxt.add(cid)
        frontier = nxt
        if not frontier:
            break
    return [_sym(t) for t in targets], _sort(_scoped(results, scope))


def inherits(
    conn: Any,
    query: str,
    in_file: str = "",
    ancestors: bool = False,
    depth: int = 0,
    scope: str = "",
) -> tuple[Rows, Rows]:
    kinds = ["class", "interface", "enum", "record", "external"]
    targets = resolve_symbol(conn, query, in_file, allow_external=True, kinds=kinds)
    frontier = {t[0] for t in targets}
    results, visited, d = [], set(frontier), 0
    while frontier and (depth <= 0 or d < depth):
        d += 1
        if ancestors:
            q = (
                "MATCH (c:Symbol)-[r:INHERITS]->(p:Symbol) WHERE c.id IN $ids "
                "RETURN p.id, p.qualname, p.kind, p.file, p.line, c.file, c.line, r.kind, r.confidence, c.qualname"
            )
        else:
            q = (
                "MATCH (c:Symbol)-[r:INHERITS]->(p:Symbol) WHERE p.id IN $ids "
                "RETURN c.id, c.qualname, c.kind, c.file, c.line, c.file, c.line, r.kind, r.confidence, p.qualname"
            )
        nxt = set()
        for sid, sq, sk, sf, sl, cf, cl, rk, conf, other in _rows(conn, q, {"ids": list(frontier)}):
            # citation: the declaration line of the class that declares the edge
            results.append(
                {
                    "citation": f"{cf}:{cl}",
                    "file": cf,
                    "line": cl,
                    "symbol": sid,
                    "qualname": sq,
                    "kind": sk,
                    "relation": rk,
                    "confidence": conf,
                    "depth": d,
                    "declared_by" if ancestors else "parent": other,
                }
            )
            if sid not in visited:
                visited.add(sid)
                nxt.add(sid)
        frontier = nxt
    return [_sym(t) for t in targets], _sort(_scoped(results, scope))


def dead_code(
    conn: Any, scope: str = "", kinds: list[str] | None = None, confidence: str = "all"
) -> Rows:
    kinds = kinds or CODE_KINDS
    q = (
        "MATCH (s:Symbol) WHERE s.kind IN $kinds AND coalesce(s.entry_reason, '') = '' AND NOT s.qualname CONTAINS '$anon' "
        "AND NOT EXISTS { MATCH (x:Symbol)-[:CALLS]->(s) WHERE x.id <> s.id } "
        "AND NOT EXISTS { MATCH (x:Symbol)-[:REFERENCES]->(s) WHERE x.id <> s.id } "
        "AND NOT EXISTS { MATCH (:Symbol)-[:INHERITS]->(s) } "
        f"RETURN {SYM_COLS}"
    )
    cands = _rows(conn, q, {"kinds": list(kinds)})
    results = []
    classlike = {"class", "interface", "enum", "record"}
    for row in cands:
        sid, qn, kind, f, ln, name, vis, parent, _, lang = row
        if kind in classlike:
            # a class is live if anything outside it touches it or any member nested in it
            outside = _rows(
                conn,
                "MATCH (x:Symbol)-[r:CALLS|REFERENCES]->(m:Symbol) "
                "WHERE (m.id = $id OR starts_with(m.id, $pfx)) AND NOT (x.id = $id OR starts_with(x.id, $pfx)) "
                "RETURN count(*)",
                {"id": sid, "pfx": f"{f}::{qn}."},
            )
            if outside and outside[0][0] > 0:
                continue
            entry = _rows(
                conn,
                "MATCH (m:Symbol) WHERE starts_with(m.id, $pfx) AND coalesce(m.entry_reason, '') <> '' "
                "AND m.entry_reason <> 'init-private' RETURN count(*)",
                {"pfx": f"{f}::{qn}."},
            )
            if entry and entry[0][0] > 0:
                continue  # holds an entry point (main, test, override...)
        parent_kind = ""
        if parent:
            pk = _rows(conn, "MATCH (p:Symbol {id: $id}) RETURN p.kind", {"id": parent})
            parent_kind = pk[0][0] if pk else ""
        likely = vis == "private" or parent_kind in ("function", "method")
        dc = "likely" if likely else "possible"
        if confidence != "all" and dc != confidence:
            continue
        results.append(
            {
                "citation": f"{f}:{ln}",
                "file": f,
                "line": ln,
                "symbol": sid,
                "qualname": qn,
                "kind": kind,
                "confidence": "exact",
                "dead_confidence": dc,
                "visibility": vis,
            }
        )
    results = _scoped(results, scope)
    return sorted(
        results,
        key=lambda r: (r["dead_confidence"] != "likely", r["file"], r["line"], r["qualname"]),
    )


def blast(
    conn: Any, target: str, in_file: str = "", depth: int = 3, scope: str = ""
) -> tuple[Rows, Rows]:
    files = _rows(
        conn, "MATCH (f:File {path: $p}) RETURN f.path, f.parsed", {"p": target.rstrip("/")}
    )
    if files:
        rows = _rows(
            conn,
            f"MATCH (s:Symbol) WHERE s.file = $p AND s.kind <> 'module' RETURN {SYM_COLS}",
            {"p": files[0][0]},
        )
        if not rows and not files[0][1]:
            raise NotFound(f"{target} (file not parsed at v0.1)")
        targets = rows
    else:
        targets = resolve_symbol(conn, target, in_file)
        # a class change reaches everything nested in it
        extra = []
        for t in targets:
            if t[2] in ("class", "interface", "enum", "record"):
                extra += _rows(
                    conn,
                    f"MATCH (s:Symbol) WHERE starts_with(s.id, $pfx) RETURN {SYM_COLS}",
                    {"pfx": f"{t[3]}::{t[1]}."},
                )
        targets = targets + extra
    start = {t[0] for t in targets}
    frontier = {sid: "exact" for sid in start}
    visited = set(start)
    results, seen = [], set()
    d = 0
    while frontier and (depth <= 0 or d < depth):
        d += 1
        nxt = {}
        for rel, cid, cq, ck, cf, cl, sf, sl, conf, reason, tid in _incoming(
            conn, frontier.keys(), ("CALLS", "REFERENCES", "INHERITS")
        ):
            if cid in start:
                continue
            path_conf = (
                "heuristic" if (conf == "heuristic" or frontier[tid] == "heuristic") else "exact"
            )
            key = (cid, sf, sl)
            if key not in seen:
                seen.add(key)
                results.append(
                    {
                        "citation": f"{sf}:{sl}",
                        "file": sf,
                        "line": sl,
                        "symbol": cid,
                        "qualname": cq,
                        "kind": ck,
                        "edge": {"CALLS": "call", "REFERENCES": "ref", "INHERITS": "inherits"}[rel],
                        "confidence": path_conf,
                        "depth": d,
                        "via": f"{sf}:{sl}",
                        "target": tid,
                        "def": f"{cf}:{cl}",
                    }
                )
            if cid not in visited:
                visited.add(cid)
                nxt[cid] = path_conf
        frontier = nxt
    results = _scoped(results, scope)
    return [_sym(t) for t in targets], _sort(results)


def callees(conn: Any, target: str, in_file: str = "", scope: str = "") -> tuple[Rows, Rows]:
    """Direct outgoing calls: one row per (call site, target definition)."""
    resolved = [_sym(r) for r in resolve_symbol(conn, target, in_file)]
    rows = _rows(
        conn,
        "MATCH (s:Symbol)-[r:CALLS]->(t:Symbol) WHERE s.id IN $ids "
        "RETURN t.id, t.qualname, t.kind, t.file, t.line, r.file, r.line, "
        "r.confidence, r.reason, s.id ORDER BY r.file, r.line, t.id",
        {"ids": [r["id"] for r in resolved]},
    )
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
    ]
    return resolved, _scoped(results, scope)


def search(conn: Any, query: str, kinds: list[str] | None = None, scope: str = "") -> Rows:
    """Case-insensitive substring search over symbol names (qualified names when the query
    contains a dot). Exact matches rank first, then prefixes, then other substrings."""
    q = query.lower()
    field = "s.qualname" if "." in q else "s.name"
    rows = _rows(
        conn,
        f"MATCH (s:Symbol) WHERE s.kind IN $kinds AND lower({field}) CONTAINS $q RETURN {SYM_COLS}",
        {"q": q, "kinds": kinds or CODE_KINDS},
    )
    results = [
        {
            **_sym(r),
            "symbol": r[0],
            "name": r[5],
            "lang": r[9],
            "citation": f"{r[3]}:{r[4]}",
            "confidence": "exact",
            "reason": "name-match",
        }
        for r in rows
    ]

    def rank(r: dict[str, Any]) -> tuple[int, str, int, str]:
        key = (r["qualname"] if "." in q else r["name"]).lower()
        return (0 if key == q else 1 if key.startswith(q) else 2, r["file"], r["line"], r["id"])

    return sorted(_scoped(results, scope), key=rank)


def meta(conn: Any) -> dict[str, str]:
    return {k: v for k, v in _rows(conn, "MATCH (m:Meta) RETURN m.key, m.value")}
