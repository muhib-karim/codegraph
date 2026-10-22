"""Pass 2: resolve bases, calls and references into typed, confidence-tagged edges."""

from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .model import CallSite, FileInfo, Ref, Symbol

# (kind, value, reason): kind is sym | module | local | external | None; value is a
# list of Symbols for sym, a file path for module, else None.
Binding = tuple[str | None, Any, str]

CALLABLE = {"function", "method", "constructor"}
CLASSLIKE = {"class", "interface", "enum", "record"}
JS = {"javascript", "typescript"}
# Candidate files for a relative JS/TS module specifier, in Node/TypeScript lookup order.
JS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")


def family(lang: str) -> str:
    """Languages that can call each other by name: JS and TS share one namespace."""
    return "js" if lang in JS else lang


@dataclass
class Edge:
    src: str
    dst: str
    file: str
    line: int
    col: int = 0
    confidence: str = "exact"
    reason: str = ""
    kind: str = ""


@dataclass
class Graph:
    files: dict[str, FileInfo]
    symbols: dict[str, Symbol]
    calls: list[Edge] = field(default_factory=list)
    refs: list[Edge] = field(default_factory=list)
    inherits: list[Edge] = field(default_factory=list)
    # (src_file, dst_file, line, name, confidence)
    imports: list[tuple[str, str, int, str, str]] = field(default_factory=list)
    stats: Counter[str] = field(default_factory=Counter)


def _source(c: CallSite | Ref) -> str:
    """Symbol id of the scope that contains a call site or reference."""
    return c.caller if isinstance(c, CallSite) else c.owner


def arity_ok(sym: Symbol, argc: int, splat: bool = False) -> bool:
    if splat:
        return argc <= sym.arity_max or sym.arity_max == -1
    if sym.arity_max == -1:
        return argc >= sym.arity_min
    return sym.arity_min <= argc <= sym.arity_max


class Resolver:
    def __init__(self, files: dict[str, FileInfo]) -> None:
        self.files: dict[str, FileInfo] = files
        self.sym: dict[str, Symbol] = {}
        self.children: defaultdict[str, list[Symbol]] = defaultdict(list)  # parent id -> kids
        self.by_name: defaultdict[tuple[str, str], list[Symbol]] = defaultdict(list)
        self.java_fqn: dict[str, str] = {}  # fqn -> class id
        # pkg -> {simple top-level name: class id}
        self.java_pkg: defaultdict[str, dict[str, str]] = defaultdict(dict)
        # class id -> [base class id (repo or external)]
        self.bases: defaultdict[str, list[str]] = defaultdict(list)
        self.externals: dict[str, Symbol] = {}
        self.export_cache: dict[tuple[str, str], tuple[str, Any] | None] = {}
        for fi in files.values():
            for s in fi.symbols:
                self.sym[s.id] = s
                if s.parent_id:
                    self.children[s.parent_id].append(s)
                if s.kind in CALLABLE:
                    self.by_name[(family(s.lang), s.name)].append(s)
            if fi.lang == "java":
                for s in fi.symbols:
                    if s.kind in CLASSLIKE and "$anon" not in s.qualname:
                        fqn = f"{fi.package}.{s.qualname}" if fi.package else s.qualname
                        self.java_fqn[fqn] = s.id
                        if "." not in s.qualname:
                            self.java_pkg[fi.package][s.name] = s.id
        self.g = Graph(files=files, symbols=self.sym)

    # ---------- generic helpers ----------
    def external(self, name: str, lang: str) -> str:
        sid = f"external::{name}"
        if sid not in self.sym:
            s = Symbol(
                id=sid,
                name=name.split(".")[-1],
                qualname=name,
                kind="external",
                lang=lang,
                file="",
                line=0,
                end_line=0,
            )
            self.sym[sid] = s
            self.externals[sid] = s
        return sid

    def enclosing_class(self, sid: str | None) -> Symbol | None:
        s = self.sym.get(sid or "")
        while s is not None:
            if s.kind in CLASSLIKE:
                return s
            s = self.sym.get(s.parent_id) if s.parent_id else None
        return None

    def mro(self, cls_id: str) -> list[str]:
        out, seen, stack = [], set(), [cls_id]
        while stack:
            c = stack.pop(0)
            if c in seen or c not in self.sym or self.sym[c].kind == "external":
                continue
            seen.add(c)
            out.append(c)
            stack.extend(self.bases.get(c, []))
        return out

    def has_external_ancestor(self, cls_id: str) -> bool:
        for c in self.mro(cls_id):
            if any(self.sym[b].kind == "external" for b in self.bases.get(c, []) if b in self.sym):
                return True
        return False

    def find_member(
        self,
        cls_id: str,
        name: str,
        argc: int | None = None,
        splat: bool = False,
        include_self: bool = True,
    ) -> tuple[list[Symbol], bool]:
        """Methods named `name` in cls and its repo ancestors, nearest class first.
        Returns (candidates, arity_matched)."""
        chain = self.mro(cls_id)
        if not include_self:
            chain = chain[1:]
        for c in chain:
            cands = [m for m in self.children[c] if m.name == name and m.kind in CALLABLE]
            if cands:
                if argc is None:
                    return cands, True
                ok = [m for m in cands if arity_ok(m, argc, splat)]
                return (ok, True) if ok else (cands, False)
        return [], False

    def ctor_targets(self, cls_id: str, argc: int, splat: bool = False) -> tuple[list[str], bool]:
        """Constructor edge targets: matching constructors, else the class itself."""
        cls = self.sym[cls_id]
        if cls.lang == "python":
            cands, ok = self.find_member(cls_id, "__init__", argc, splat)
            return ([cls_id] + [c.id for c in cands]), (ok or not cands)
        ctors = [m for m in self.children[cls_id] if m.kind == "constructor"]
        if not ctors:
            return [cls_id], True
        fits = [m for m in ctors if arity_ok(m, argc, splat)]
        return ([cls_id] + [m.id for m in (fits or ctors)]), bool(fits)

    # ---------- python scope resolution ----------
    def py_module_file(self, fi: FileInfo, module: str) -> str | None:
        """Resolve a python module path to a repo file, or None (external)."""
        cands = []
        if module.startswith("."):
            dots = len(module) - len(module.lstrip("."))
            rest = module.lstrip(".")
            base = posixpath.dirname(fi.path)
            for _ in range(dots - 1):
                base = posixpath.dirname(base)
            rel = rest.replace(".", "/")
            p = posixpath.join(base, rel) if rel else base
            cands += [p + ".py", posixpath.join(p, "__init__.py")]
        else:
            rel = module.replace(".", "/")
            here = posixpath.dirname(fi.path)
            cands += [
                posixpath.join(here, rel + ".py"),
                posixpath.join(here, rel, "__init__.py"),
                rel + ".py",
                posixpath.join(rel, "__init__.py"),
            ]
        for c in cands:
            c = posixpath.normpath(c)
            if c in self.files and self.files[c].lang == "python":
                return c
        return None

    def py_top(self, path: str, name: str) -> list[Symbol]:
        mod = f"{path}::<module>"
        return [
            s
            for s in self.children.get(mod, [])
            if s.name == name and (s.kind in CLASSLIKE or s.kind in ("function", "variable"))
        ]

    def py_bind(self, fi: FileInfo, scope_id: str | None, name: str) -> Binding:
        """Bind a bare python name. Returns ('sym', [Symbol], reason) | ('module', path, reason) | ('external', None, reason) | (None, None, '')."""
        # enclosing function scopes (nested defs), innermost first; class bodies are not visible
        s = self.sym.get(scope_id or "")
        while s is not None and s.kind != "module":
            if s.kind in ("function", "method"):
                loc = [
                    c
                    for c in self.children[s.id]
                    if c.name == name and (c.kind == "function" or c.kind in CLASSLIKE)
                ]
                if loc:
                    return "sym", loc, "local-scope"
                if name in fi.locals.get(s.id, ()) and name not in fi.globals_decl.get(s.id, ()):
                    return "local", None, "local-var"
            s = self.sym.get(s.parent_id) if s.parent_id else None
        top = self.py_top(fi.path, name)
        if top:
            return "sym", top, "same-file"
        for imp in fi.imports:
            if imp.kind == "from" and (imp.alias or imp.name) == name:
                path = self.py_module_file(fi, imp.module)
                if path is None:
                    # `from pkg import mod` where pkg/mod.py is a repo file
                    sub = self.py_module_file(
                        fi,
                        (imp.module + "." if not imp.module.endswith(".") else imp.module)
                        + imp.name,
                    )
                    if sub:
                        return "module", sub, "import"
                    return "external", None, "external-import"
                hit = self.py_top(path, imp.name)
                if hit:
                    return "sym", hit, "import"
                sub = self.py_module_file(
                    fi,
                    (imp.module + "." if not imp.module.endswith(".") else imp.module) + imp.name,
                )
                if sub:
                    return "module", sub, "import"
                return "external", None, "unresolved-import"
            if imp.kind == "module":
                bound = imp.alias or imp.module.split(".")[0]
                if bound == name:
                    target = imp.module if imp.alias else imp.module.split(".")[0]
                    path = self.py_module_file(fi, target)
                    return (
                        ("module", path, "import")
                        if path
                        else ("external", None, "external-import")
                    )
        for imp in fi.imports:
            if imp.kind == "star":
                path = self.py_module_file(fi, imp.module)
                if path:
                    hit = self.py_top(path, name)
                    if hit:
                        return "sym", hit, "star-import"
        return None, None, ""

    # ---------- JS/TS scope resolution ----------
    def js_module_file(self, fi: FileInfo, spec: str) -> str | None:
        """Resolve a relative import specifier to a repo JS/TS file, or None (package/external)."""
        if not spec.startswith("."):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(fi.path), spec))
        stem, ext = posixpath.splitext(base)
        cands = [base] if ext in JS_EXTS else []
        if ext in (".js", ".jsx", ".mjs", ".cjs"):  # TS sources imported by their output name
            ts = {".js": ".ts", ".jsx": ".tsx", ".mjs": ".mts", ".cjs": ".cts"}[ext]
            cands.append(stem + ts)
        cands += [base + e for e in JS_EXTS]
        cands += [posixpath.join(base, "index" + e) for e in JS_EXTS]
        for c in cands:
            if c in self.files and self.files[c].lang in JS:
                return c
        return None

    def js_export(
        self, path: str, name: str, seen: set[tuple[str, str]] | None = None
    ) -> tuple[str, Any] | None:
        """What `name` exported by `path` binds to: ('sym', [Symbol]) | ('module', path) | None.

        One lookup visits each (file, name) pair at most once, so cyclic `export *` chains
        terminate in linear time; finished top-level lookups are cached."""
        top_level = seen is None
        key = (path, name)
        if top_level and key in self.export_cache:
            return self.export_cache[key]
        visited: set[tuple[str, str]] = set() if seen is None else seen
        if key in visited:
            return None
        visited.add(key)
        result = self._js_export(path, name, visited)
        if top_level:
            self.export_cache[key] = result
        return result

    def _js_export(
        self, path: str, name: str, seen: set[tuple[str, str]]
    ) -> tuple[str, Any] | None:
        fi = self.files.get(path)
        if fi is None:
            return None
        if name in fi.exports:
            kind, val, _ = self.js_bind(fi, f"{path}::<module>", fi.exports[name], seen)
            return (kind, val) if kind in ("sym", "module") else None
        # `export { foo as bar }` exports bar only; foo itself stays private to the file.
        renamed = name in fi.exports.values()
        if name != "default" and not renamed:
            top = [s for s in self.py_top(path, name) if s.visibility == "public"]
            if top:
                return "sym", top
        for imp in fi.imports:
            target = self.js_module_file(fi, imp.module)
            if target is None:
                continue
            if imp.kind == "reexport" and (imp.alias or imp.name) == name:
                return self.js_export(target, imp.name, seen)
            if imp.kind == "reexport_ns" and imp.alias == name:
                return "module", target
        if name == "default":
            return "module", path  # CommonJS module object without a single default export
        for imp in fi.imports:
            if imp.kind == "reexport_star":
                target = self.js_module_file(fi, imp.module)
                hit = self.js_export(target, name, seen) if target else None
                if hit:
                    return hit
        return None

    def js_bind(
        self,
        fi: FileInfo,
        scope_id: str | None,
        name: str,
        seen: set[tuple[str, str]] | None = None,
    ) -> Binding:
        """Bind a bare JS/TS name; same result shape as py_bind."""
        s = self.sym.get(scope_id or "")
        while s is not None and s.kind != "module":
            if s.kind in ("function", "method", "constructor"):
                loc = [
                    c
                    for c in self.children[s.id]
                    if c.name == name and (c.kind == "function" or c.kind in CLASSLIKE)
                ]
                if loc:
                    return "sym", loc, "local-scope"
                if name in fi.locals.get(s.id, ()):
                    return "local", None, "local-var"
            s = self.sym.get(s.parent_id) if s.parent_id else None
        top = self.py_top(fi.path, name)
        if top:
            return "sym", top, "same-file"
        for imp in fi.imports:
            if imp.kind not in ("from", "module") or (imp.alias or imp.name) != name:
                continue
            path = self.js_module_file(fi, imp.module)
            if path is None:
                return "external", None, "external-import"
            if imp.kind == "module":
                return "module", path, "import"
            hit = self.js_export(path, imp.name, seen)
            if hit:
                return hit[0], hit[1], "import"
            return "external", None, "unresolved-import"
        return None, None, ""

    def bind(self, fi: FileInfo, scope_id: str | None, name: str) -> Binding:
        if fi.lang in JS:
            return self.js_bind(fi, scope_id, name)
        return self.py_bind(fi, scope_id, name)

    def module_attr(self, lang: str, path: str, name: str) -> list[Symbol]:
        """Top-level symbols reached as `<module>.<name>`."""
        if lang in JS:
            hit = self.js_export(path, name)
            return hit[1] if hit and hit[0] == "sym" else []
        return self.py_top(path, name)

    def py_var_class(self, fi: FileInfo, scope_id: str | None, var: str) -> str | None:
        """Class id for a local variable constructed as `var = Cls(...)` in this or an enclosing function."""
        s = self.sym.get(scope_id or "")
        while s is not None:
            tname = fi.var_types.get(s.id, {}).get(var)
            if tname:
                return self.py_class_from_text(fi, s.id, tname)
            if s.kind == "module":
                break
            s = self.sym.get(s.parent_id) if s.parent_id else None
        return None

    def py_class_from_text(self, fi: FileInfo, scope_id: str | None, tname: str) -> str | None:
        parts = tname.split(".")
        kind, val, _ = self.bind(fi, scope_id, parts[0])
        if kind == "sym" and len(parts) == 1:
            cl = [v for v in val if v.kind in CLASSLIKE]
            return cl[0].id if cl else None
        if kind == "module" and len(parts) == 2:
            cl = [v for v in self.module_attr(fi.lang, val, parts[1]) if v.kind in CLASSLIKE]
            return cl[0].id if cl else None
        return None

    # ---------- java type resolution ----------
    def java_type(self, fi: FileInfo, ctx_id: str | None, tname: str) -> str | None:
        """Resolve a Java type name. Returns class id, 'external:<name>' or None."""
        if not tname:
            return None
        tname = tname.replace("[]", "")
        if tname in (
            "int",
            "long",
            "short",
            "byte",
            "char",
            "boolean",
            "float",
            "double",
            "void",
            "var",
        ):
            return "external:" + tname
        first, _, rest = tname.partition(".")
        # nested / enclosing classes visible from context
        c = self.enclosing_class(ctx_id) if ctx_id else None
        while c is not None:
            for ch in self.children[c.id]:
                if ch.kind in CLASSLIKE and ch.name == first:
                    return self._java_descend(ch.id, rest)
            if c.name == first:
                return self._java_descend(c.id, rest)
            # nested classes inherited from repo supertypes
            for anc in self.mro(c.id)[1:]:
                for ch in self.children[anc]:
                    if ch.kind in CLASSLIKE and ch.name == first:
                        return self._java_descend(ch.id, rest)
            c = self.enclosing_class(c.parent_id) if c.parent_id else None
        for s in self.children.get(f"{fi.path}::<module>", []):
            if s.kind in CLASSLIKE and s.name == first:
                return self._java_descend(s.id, rest)
        for imp in fi.imports:
            if imp.kind == "java" and imp.module.split(".")[-1] == first:
                cid = self.java_fqn.get(imp.module)
                return (
                    self._java_descend(cid, rest)
                    if cid
                    else "external:" + imp.module + ("." + rest if rest else "")
                )
        if first in self.java_pkg.get(fi.package, {}):
            return self._java_descend(self.java_pkg[fi.package][first], rest)
        for imp in fi.imports:
            if imp.kind == "java_star":
                cid = self.java_fqn.get(f"{imp.module}.{first}")
                if cid:
                    return self._java_descend(cid, rest)
        if tname in self.java_fqn:
            return self.java_fqn[tname]
        if first[:1].isupper() or "." in tname:
            return "external:" + tname
        return None

    def _java_descend(self, cid: str | None, rest: str) -> str | None:
        if cid is None or not rest:
            return cid
        for part in rest.split("."):
            nxt = next(
                (c for c in self.children[cid] if c.kind in CLASSLIKE and c.name == part), None
            )
            if nxt is None:
                return None
            cid = nxt.id
        return cid

    def java_var_type(
        self, fi: FileInfo, scope_id: str | None, var: str
    ) -> tuple[str | None, str | None]:
        """Declared type of a local/param/field visible from scope."""
        s = self.sym.get(scope_id or "")
        while s is not None:
            if var in fi.var_types.get(s.id, {}):
                return fi.var_types[s.id][var], s.id
            if s.kind in CLASSLIKE:
                for anc in self.mro(s.id)[1:]:
                    afi = self.files.get(self.sym[anc].file)
                    if afi and var in afi.var_types.get(anc, {}):
                        return afi.var_types[anc][var], anc
            s = self.sym.get(s.parent_id) if s.parent_id else None
        return None, None

    # ---------- pass 2 ----------
    def run(self) -> Graph:
        self.resolve_bases()
        self.resolve_imports()
        for fi in self.files.values():
            if not fi.parsed:
                continue
            for c in fi.calls:
                self.resolve_call(fi, c)
            for r in fi.refs:
                self.resolve_ref(fi, r)
        self.mark_entries()
        self.g.symbols = self.sym
        # dedupe edges on (src,dst,line,col)
        for attr in ("calls", "refs"):
            seen, out = set(), []
            for e in getattr(self.g, attr):
                k = (e.src, e.dst, e.line, e.col)
                if k not in seen:
                    seen.add(k)
                    out.append(e)
            setattr(self.g, attr, out)
        return self.g

    def resolve_bases(self) -> None:
        for fi in self.files.values():
            for b in fi.bases:
                cls = self.sym[b.cls]
                target = None
                if fi.lang == "python" or fi.lang in JS:
                    target = self.py_class_from_text(
                        fi, cls.parent_id or f"{fi.path}::<module>", b.text
                    )
                    if target is None:
                        target = self.external(b.text, fi.lang)
                else:
                    r = self.java_type(fi, cls.parent_id, b.text)
                    if r is None or r.startswith("external:"):
                        target = self.external(r[9:] if r else b.text, "java")
                    else:
                        target = r
                if target == cls.id:
                    continue
                self.bases[cls.id].append(target)
                self.g.inherits.append(
                    Edge(cls.id, target, fi.path, b.line, 0, "exact", b.kind, b.kind)
                )

    def resolve_imports(self) -> None:
        for fi in self.files.values():
            for imp in fi.imports:
                dst = None
                if fi.lang in JS:
                    dst = self.js_module_file(fi, imp.module)
                elif fi.lang == "python":
                    if imp.kind == "from":
                        dst = self.py_module_file(fi, imp.module)
                        if dst is None:
                            m = imp.module + ("" if imp.module.endswith(".") else ".") + imp.name
                            dst = self.py_module_file(fi, m)
                    else:
                        dst = self.py_module_file(fi, imp.module)
                else:
                    if imp.kind == "java":
                        cid = self.java_fqn.get(imp.module)
                        dst = self.sym[cid].file if cid else None
                    elif imp.kind == "java_static":
                        cid = self.java_fqn.get(imp.module.rsplit(".", 1)[0])
                        dst = self.sym[cid].file if cid else None
                    elif imp.kind == "java_star":
                        cid = self.java_fqn.get(imp.module)  # static-nested wildcard not handled
                        dst = self.sym[cid].file if cid else None
                if dst and dst != fi.path:
                    self.g.imports.append((fi.path, dst, imp.line, imp.name or imp.module, "exact"))
                    self.g.stats["imports_internal"] += 1
                else:
                    self.g.stats["imports_external"] += 1

    def _emit(
        self,
        kind: str,
        src: str,
        targets: Sequence[str | Symbol],
        fi: FileInfo,
        line: int,
        col: int,
        conf: str,
        reason: str,
    ) -> None:
        lst = self.g.calls if kind == "call" else self.g.refs
        for t in targets:
            tid = t if isinstance(t, str) else t.id
            lst.append(Edge(src, tid, fi.path, line, col, conf, reason, kind))
        self.g.stats[f"{kind}_{conf}"] += len(targets)

    def _methods(
        self,
        kind: str,
        fi: FileInfo,
        c: CallSite | Ref,
        cls_id: str,
        reason: str,
        include_self: bool = True,
    ) -> bool:
        cands, ok = self.find_member(
            cls_id,
            c.name,
            c.argc if isinstance(c, CallSite) else None,
            c.splat if isinstance(c, CallSite) else False,
            include_self,
        )
        if not cands:
            return False
        if ok and len(cands) > 1 and fi.lang == "java":
            self._emit(
                kind,
                _source(c),
                cands,
                fi,
                c.line,
                c.col,
                "heuristic",
                "overload-ambiguous",
            )
        else:
            self._emit(
                kind,
                _source(c),
                cands,
                fi,
                c.line,
                c.col,
                "exact" if ok else "heuristic",
                reason if ok else "arity-mismatch",
            )
        return True

    def _by_name(self, kind: str, fi: FileInfo, c: CallSite | Ref) -> None:
        cands = [
            s
            for s in self.by_name.get((family(fi.lang), c.name), [])
            if s.kind in ("method", "function")
        ]
        if isinstance(c, CallSite):
            cands = [s for s in cands if arity_ok(s, c.argc, c.splat)]
        src = _source(c)
        if len(cands) == 1:
            self._emit(kind, src, cands, fi, c.line, c.col, "heuristic", "unique-name")
        elif len(cands) > 1:
            self.g.stats[f"{kind}_ambiguous"] += 1
        else:
            self.g.stats[f"{kind}_unresolved"] += 1

    def resolve_call(self, fi: FileInfo, c: CallSite) -> None:
        py = fi.lang == "python" or fi.lang in JS  # lexical binding, Python-style
        st = self.g.stats
        if c.recv_kind in ("new",):
            cid = self.java_type(fi, c.caller, c.recv)
            if cid and not cid.startswith("external:"):
                targets, ok = self.ctor_targets(cid, c.argc)
                self._emit(
                    "call",
                    c.caller,
                    targets,
                    fi,
                    c.line,
                    c.col,
                    "exact" if ok else "heuristic",
                    "new" if ok else "arity-mismatch",
                )
            else:
                st["call_external"] += 1
            return
        if c.recv_kind in ("ctor_this", "ctor_super"):
            cls = self.enclosing_class(c.caller)
            if cls is None:
                return
            tgt = (
                [cls.id]
                if c.recv_kind == "ctor_this"
                else [b for b in self.bases.get(cls.id, []) if self.sym[b].kind != "external"]
            )
            for t in tgt:
                targets, ok = self.ctor_targets(t, c.argc)
                targets = [x for x in targets if x != t] or [t]
                self._emit(
                    "call",
                    c.caller,
                    targets,
                    fi,
                    c.line,
                    c.col,
                    "exact" if ok else "heuristic",
                    "this()" if c.recv_kind == "ctor_this" else "super()",
                )
            if not tgt:
                st["call_external"] += 1
            return
        if c.recv_kind == "none":
            if py:
                kind, val, reason = self.bind(fi, c.caller, c.name)
                if kind == "sym" and val[0].kind == "variable":
                    self._emit(
                        "ref", c.caller, [val[0]], fi, c.line, c.col, "exact", "called-variable"
                    )
                    return
                if kind == "sym":
                    s0 = val[0]
                    if s0.kind in CLASSLIKE:
                        targets, ok = self.ctor_targets(s0.id, c.argc, c.splat)
                    else:
                        targets, ok = [s0.id], arity_ok(s0, c.argc, c.splat)
                    self._emit(
                        "call",
                        c.caller,
                        targets,
                        fi,
                        c.line,
                        c.col,
                        "exact" if ok else "heuristic",
                        reason if ok else "arity-mismatch",
                    )
                elif kind in ("external", "module"):
                    st["call_external"] += 1
                else:
                    st["call_external"] += 1  # builtins / undefined names
                return
            # java unqualified: enclosing classes (with inheritance), then static imports
            cls = self.enclosing_class(c.caller)
            while cls is not None:
                if self._methods("call", fi, c, cls.id, "same-class"):
                    return
                cls = self.enclosing_class(cls.parent_id) if cls.parent_id else None
            for imp in fi.imports:
                if imp.kind == "java_static" and imp.module.split(".")[-1] == c.name:
                    cid = self.java_fqn.get(imp.module.rsplit(".", 1)[0])
                    if cid and self._methods("call", fi, c, cid, "static-import"):
                        return
                if imp.kind == "java_static_star":
                    cid = self.java_fqn.get(imp.module)
                    if cid and self._methods("call", fi, c, cid, "static-import"):
                        return
            st["call_external"] += 1  # inherited from an external supertype, or undefined
            return
        if c.recv_kind == "self":
            cls = self.enclosing_class(c.caller)
            if cls and self._methods("call", fi, c, cls.id, "self"):
                return
            if cls and self.has_external_ancestor(cls.id):
                st["call_external"] += 1
            else:
                st["call_unresolved"] += 1
            return
        if c.recv_kind == "super":
            cls = self.enclosing_class(c.caller)
            if cls:
                for b in self.bases.get(cls.id, []):
                    if self.sym[b].kind != "external" and self._methods("call", fi, c, b, "super"):
                        return
            st["call_external"] += 1
            return
        if c.recv_kind == "attr_self":
            cls = self.enclosing_class(c.caller)
            if cls:
                if py:
                    tname = None
                    for anc in self.mro(cls.id):
                        afi = self.files[self.sym[anc].file]
                        tname = afi.var_types.get(anc, {}).get(c.recv)
                        if tname:
                            break
                    tid = self.py_class_from_text(fi, cls.parent_id, tname) if tname else None
                else:
                    tn, where = self.java_var_type(fi, cls.id, c.recv)
                    tid = self.java_type(fi, where, tn) if tn else None
                    if tid and tid.startswith("external:"):
                        st["call_external"] += 1
                        return
                if tid and self._methods("call", fi, c, tid, "typed-field"):
                    return
            self._by_name("call", fi, c)
            return
        if c.recv_kind == "name":
            if py:
                kind, val, reason = self.bind(fi, c.caller, c.recv)
                if kind is None and fi.lang in JS:  # console, JSON, window, document...
                    st["call_external"] += 1
                    return
                if kind == "module":
                    hit = self.module_attr(fi.lang, val, c.name)
                    if hit and hit[0].kind == "variable":
                        self._emit(
                            "ref", c.caller, hit[:1], fi, c.line, c.col, "exact", "module-attr"
                        )
                        self._by_name("call", fi, c)
                        return
                    if hit:
                        s0 = hit[0]
                        if s0.kind in CLASSLIKE:
                            targets, ok = self.ctor_targets(s0.id, c.argc, c.splat)
                        else:
                            targets, ok = [s0.id], arity_ok(s0, c.argc, c.splat)
                        self._emit(
                            "call",
                            c.caller,
                            targets,
                            fi,
                            c.line,
                            c.col,
                            "exact" if ok else "heuristic",
                            "module-attr" if ok else "arity-mismatch",
                        )
                    else:
                        st["call_unresolved"] += 1
                    return
                if kind == "external":
                    st["call_external"] += 1
                    return
                if kind == "local" and not self.py_var_class(fi, c.caller, c.recv):
                    self._by_name("call", fi, c)
                    return
                if kind == "sym" and val[0].kind in CLASSLIKE:
                    if self._methods("call", fi, c, val[0].id, "class-attr"):
                        return
                    st["call_unresolved"] += 1
                    return
                tid = self.py_var_class(fi, c.caller, c.recv)
                if tid and self._methods("call", fi, c, tid, "typed-local"):
                    return
                self._by_name("call", fi, c)
                return
            # java: variable with declared type, else a type name (static call)
            tn, where = self.java_var_type(fi, c.caller, c.recv)
            if tn:
                tid = self.java_type(fi, where, tn)
                if tid is None or tid.startswith("external:"):
                    st["call_external"] += 1
                    return
                if self._methods("call", fi, c, tid, "typed-var"):
                    return
                st["call_external"] += 1 if self.has_external_ancestor(tid) else 0
                st["call_unresolved"] += 0 if self.has_external_ancestor(tid) else 1
                return
            tid = self.java_type(fi, c.caller, c.recv)
            if tid and not tid.startswith("external:"):
                if self._methods("call", fi, c, tid, "static"):
                    return
                st["call_unresolved"] += 1
                return
            if tid and tid.startswith("external:"):
                st["call_external"] += 1
                return
            self._by_name("call", fi, c)
            return
        if c.recv_kind == "dotted":
            if py:
                parts = c.recv.split(".")
                kind, val, _ = self.bind(fi, c.caller, parts[0])
                if kind == "external" or (kind is None and fi.lang in JS):
                    st["call_external"] += 1
                    return
                if kind == "module" and len(parts) == 2:
                    hit = [
                        s for s in self.module_attr(fi.lang, val, parts[1]) if s.kind in CLASSLIKE
                    ]
                    if hit and self._methods("call", fi, c, hit[0].id, "module-attr"):
                        return
            else:
                tid = self.java_type(fi, c.caller, c.recv)
                if tid and not tid.startswith("external:"):
                    if self._methods("call", fi, c, tid, "static"):
                        return
                elif (
                    tid
                    and tid.startswith("external:")
                    and c.recv.split(".")[0][:1].islower() is False
                ):
                    st["call_external"] += 1
                    return
            self._by_name("call", fi, c)
            return
        # expr receiver: unknown type
        self._by_name("call", fi, c)

    def find_field(self, cls_id: str, name: str) -> Symbol | None:
        for c in self.mro(cls_id):
            for m in self.children[c]:
                if m.kind == "field" and m.name == name:
                    return m
        return None

    def _java_field_owner(self, fi: FileInfo, owner: str, recv: str) -> str | None:
        """Class id that owns a field accessed as <recv>.<field>, or None."""
        if recv == "this":
            cls = self.enclosing_class(owner)
            return cls.id if cls else None
        if recv == "super":
            cls = self.enclosing_class(owner)
            if cls:
                for b in self.bases.get(cls.id, []):
                    if self.sym[b].kind != "external":
                        return b
            return None
        if "." not in recv:
            tn, where = self.java_var_type(fi, owner, recv)
            if tn:
                tid = self.java_type(fi, where, tn)
                return tid if tid and not tid.startswith("external:") else None
        tid = self.java_type(fi, owner, recv)
        return tid if tid and not tid.startswith("external:") else None

    def resolve_ref(self, fi: FileInfo, r: Ref) -> None:
        if fi.lang == "python" or fi.lang in JS:
            if r.recv_kind == "self":
                cls = self.enclosing_class(r.owner)
                if cls:
                    cands, _ = self.find_member(cls.id, r.name)
                    if cands:
                        self._emit("ref", r.owner, cands, fi, r.line, r.col, "exact", "self")
                    elif fi.lang in JS and (f := self.find_field(cls.id, r.name)):
                        self._emit("ref", r.owner, [f], fi, r.line, r.col, "exact", "field")
                return
            kind, val, reason = self.bind(fi, r.owner, r.name)
            if kind == "sym":
                # a value use of a function, class or module-level variable
                self._emit("ref", r.owner, val[:1], fi, r.line, r.col, "exact", reason)
            return
        if r.recv_kind == "none":
            tn, where = self.java_var_type(fi, r.owner, r.name)
            if where and self.sym[where].kind in CLASSLIKE:
                f = self.find_field(where, r.name)
                if f:
                    self._emit("ref", r.owner, [f], fi, r.line, r.col, "exact", "field")
                return
            if where is None:
                for imp in fi.imports:
                    if imp.kind == "java_static" and imp.module.split(".")[-1] == r.name:
                        cid = self.java_fqn.get(imp.module.rsplit(".", 1)[0])
                        f = self.find_field(cid, r.name) if cid else None
                        if f:
                            self._emit(
                                "ref", r.owner, [f], fi, r.line, r.col, "exact", "static-import"
                            )
            return
        if r.recv_kind == "field":
            cid = self._java_field_owner(fi, r.owner, r.recv)
            if cid:
                f = self.find_field(cid, r.name)
                if f:
                    self._emit("ref", r.owner, [f], fi, r.line, r.col, "exact", "field-access")
            return
        # java method references
        if r.recv_kind in ("this", "super"):
            cls = self.enclosing_class(r.owner)
            if cls:
                self._methods(
                    "ref", fi, r, cls.id, "method-ref", include_self=(r.recv_kind == "this")
                )
            return
        if r.recv_kind == "type":
            tn, where = self.java_var_type(fi, r.owner, r.recv)
            tid = self.java_type(fi, where if tn else r.owner, tn or r.recv)
            if tid and not tid.startswith("external:"):
                if r.name == "<init>":
                    targets, _ = self.ctor_targets(tid, 0)
                    self._emit("ref", r.owner, targets, fi, r.line, r.col, "exact", "method-ref")
                else:
                    self._methods("ref", fi, r, tid, "method-ref")

    # ---------- entry points ----------
    def mark_entries(self) -> None:
        for s in self.sym.values():
            if s.kind in ("module", "external") or s.entry_reason:
                continue
            if s.kind in ("field", "variable"):
                if s.name == "serialVersionUID" or (
                    s.name.startswith("__") and s.name.endswith("__")
                ):
                    s.entry_reason = "dunder" if s.lang == "python" else "serial"
                continue
            if s.lang in JS:
                cls = self.sym.get(s.parent_id or "") if s.kind == "method" else None
                if cls and self.find_member(cls.id, s.name, include_self=False)[0]:
                    s.entry_reason = "override"
            elif s.lang == "python":
                if s.name.startswith("__") and s.name.endswith("__"):
                    s.entry_reason = "dunder"
                elif s.name.startswith("test_") or s.name.startswith("Test"):
                    s.entry_reason = "test"
                elif s.kind == "method":
                    cls = self.sym.get(s.parent_id or "")
                    if cls and self.find_member(cls.id, s.name, include_self=False)[0]:
                        s.entry_reason = "override"
            else:
                if s.kind == "method" and s.name == "main" and s.is_static and s.arity_min == 1:
                    s.entry_reason = "main"
                elif "Override" in s.annotations:
                    s.entry_reason = "override"
                elif any(
                    a
                    in (
                        "Test",
                        "Before",
                        "After",
                        "BeforeEach",
                        "AfterEach",
                        "BeforeClass",
                        "AfterClass",
                        "ParameterizedTest",
                    )
                    for a in s.annotations
                ):
                    s.entry_reason = "test"
                elif s.kind == "constructor" and s.visibility == "private" and s.arity_min == 0:
                    s.entry_reason = "init-private"
                elif s.kind == "method":
                    cls = self.sym.get(s.parent_id or "")
                    if cls and "$anon" in cls.qualname:
                        s.entry_reason = "override"  # anonymous class bodies implement a supertype
                    elif (
                        cls and self.find_member(cls.id, s.name, s.arity_min, include_self=False)[0]
                    ):
                        s.entry_reason = "override"
                elif s.kind == "enum" or (s.kind == "class" and "$anon" in s.qualname):
                    pass
