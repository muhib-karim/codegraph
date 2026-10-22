"""Pass 1 for TypeScript and JavaScript: definitions, imports, exports, bases, calls, references.

The records mirror the Python extractor so the resolver can bind names lexically:
ES/CommonJS imports become `from` / `module` imports with a relative module specifier,
and module-level declarations that are not exported are private to their file.
"""

from __future__ import annotations

import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

from .extract_common import IdAllocator, end_line, line, module_symbol, text
from .model import BaseDecl, CallSite, FileInfo, Import, Ref, Symbol

TS = Language(tsts.language_typescript())
TSX = Language(tsts.language_tsx())  # a superset of JavaScript, including JSX

# extension -> (language tag, grammar)
GRAMMARS: dict[str, tuple[str, Language]] = {
    ".ts": ("typescript", TS),
    ".mts": ("typescript", TS),
    ".cts": ("typescript", TS),
    ".tsx": ("typescript", TSX),
    ".js": ("javascript", TSX),
    ".jsx": ("javascript", TSX),
    ".mjs": ("javascript", TSX),
    ".cjs": ("javascript", TSX),
}

_FUNCTION_VALUES = {
    "arrow_function",
    "function_expression",
    "function",
    "generator_function",
}
_CLASS_DECLS = {"class_declaration", "abstract_class_declaration", "class"}
_TYPE_ONLY = {
    "type_annotation",
    "type_arguments",
    "type_parameters",
    "type_alias_declaration",
    "ambient_declaration",
    "function_signature",
    "comment",
}
_PATTERN_LEAVES = {"identifier", "shorthand_property_identifier_pattern"}


def _grammar(path: str) -> tuple[str, Language]:
    for ext, entry in GRAMMARS.items():
        if path.endswith(ext):
            return entry
    raise ValueError(f"not a TypeScript/JavaScript file: {path}")


def _string(node: Node | None) -> str:
    """The value of a string literal node, without quotes."""
    if node is None:
        return ""
    return "".join(text(c) for c in node.named_children if c.type == "string_fragment")


def _type_name(annotation: Node | None) -> str:
    """A class-like name from a type annotation (`Foo`, `ns.Foo`, `Foo<T>`), else ""."""
    if annotation is None:
        return ""
    node = annotation.named_children[0] if annotation.type == "type_annotation" else annotation
    if node is None:
        return ""
    if node.type == "generic_type":
        node = node.child_by_field_name("name") or node
    if node.type in ("type_identifier", "identifier", "nested_type_identifier"):
        return text(node).replace(" ", "")
    return ""


def _require(node: Node | None) -> str | None:
    """Module specifier of `require('x')`, else None."""
    if node is None or node.type != "call_expression":
        return None
    fn = node.child_by_field_name("function")
    args = node.child_by_field_name("arguments")
    if fn is None or text(fn) != "require" or args is None:
        return None
    first = args.named_children[0] if args.named_children else None
    return _string(first) if first is not None and first.type == "string" else None


def _is_dotted(node: Node) -> bool:
    if node.type == "identifier":
        return True
    if node.type != "member_expression":
        return False
    obj = node.child_by_field_name("object")
    prop = node.child_by_field_name("property")
    return (
        obj is not None
        and prop is not None
        and prop.type == "property_identifier"
        and node.child_by_field_name("optional_chain") is None
        and _is_dotted(obj)
    )


def _exports_target(node: Node | None) -> str | None:
    """'' for `module.exports`, the name for `exports.x` / `module.exports.x`, else None."""
    if node is None or node.type != "member_expression":
        return None
    dotted = text(node).replace(" ", "")
    if dotted == "module.exports":
        return ""
    for prefix in ("module.exports.", "exports."):
        rest = dotted[len(prefix) :]
        if dotted.startswith(prefix) and rest.isidentifier():
            return rest
    return None


class _Extractor:
    def __init__(self, path: str, src: bytes) -> None:
        self.path = path
        self.lang, grammar = _grammar(path)
        self.tree = Parser(grammar).parse(src)
        loc = src.count(b"\n") + (0 if src.endswith(b"\n") or not src else 1)
        self.fi = FileInfo(path=path, lang=self.lang, loc=loc, parsed=True)
        self.ids = IdAllocator()
        self.mod = module_symbol(self.ids, path, self.lang, loc, path.rsplit(".", 1)[0])
        self.fi.symbols.append(self.mod)
        self.shadow: list[set[str]] = []  # parameters/locals of anonymous functions
        self.module_names: dict[str, Symbol] = {}
        self.exported: set[str] = set()  # local names visible to importers

    # ---------- helpers ----------
    def symbol(
        self,
        node: Node,
        name: str,
        kind: str,
        scope: Symbol,
        qual: str,
        arity: tuple[int, int] | None = None,
        visibility: str = "public",
        is_static: bool = False,
    ) -> Symbol:
        qn = f"{qual}.{name}" if qual else name
        amin, amax = arity or (0, 0)
        sym = Symbol(
            id=self.ids.make(self.path, qn, amin if arity else None, line(node)),
            name=name,
            qualname=qn,
            kind=kind,
            lang=self.lang,
            file=self.path,
            line=line(node),
            end_line=end_line(node),
            arity_min=amin if self.lang == "typescript" else 0,
            arity_max=amax if self.lang == "typescript" else -1,
            visibility="private" if scope.kind == "module" else visibility,
            is_static=is_static,
            parent_id=scope.id,
        )
        self.fi.symbols.append(sym)
        if scope.kind == "module":
            self.module_names.setdefault(name, sym)
        return sym

    def bind_local(self, scope: Symbol, name: str) -> None:
        if self.shadow:
            self.shadow[-1].add(name)
        elif scope.kind in ("function", "method", "constructor"):
            self.fi.locals.setdefault(scope.id, set()).add(name)

    def pattern_names(self, node: Node | None, scope: Symbol, qual: str) -> list[Node]:
        """Identifier nodes bound by a declaration/parameter pattern; default values are visited."""
        if node is None:
            return []
        if node.type in _PATTERN_LEAVES:
            return [node]
        if node.type in ("required_parameter", "optional_parameter"):
            value = node.child_by_field_name("value")
            if value is not None:
                self.visit(value, scope, qual)
            return self.pattern_names(node.child_by_field_name("pattern"), scope, qual)
        if node.type in ("assignment_pattern", "object_assignment_pattern"):
            right = node.child_by_field_name("right")
            if right is not None:
                self.visit(right, scope, qual)
            return self.pattern_names(node.child_by_field_name("left"), scope, qual)
        if node.type == "pair_pattern":
            return self.pattern_names(node.child_by_field_name("value"), scope, qual)
        out: list[Node] = []
        if node.type in ("object_pattern", "array_pattern", "rest_pattern"):
            for c in node.named_children:
                out.extend(self.pattern_names(c, scope, qual))
        return out

    def params(self, node: Node | None) -> tuple[int, int]:
        """(min, max) declared arity; max -1 = rest parameter."""
        req = opt = 0
        rest = False
        if node is None:
            return 0, 0
        if node.type == "identifier":  # `x => ...`
            return 1, 1
        for p in node.named_children:
            pattern = p.child_by_field_name("pattern")
            if p.type == "comment" or (pattern is not None and pattern.type == "this"):
                continue
            if pattern is not None and pattern.type == "rest_pattern":
                rest = True
            elif p.type == "optional_parameter" or p.child_by_field_name("value") is not None:
                opt += 1
            else:
                req += 1
        return req, -1 if rest else req + opt

    def function(
        self,
        node: Node,
        name: str,
        kind: str,
        scope: Symbol,
        qual: str,
        visibility: str = "public",
        is_static: bool = False,
    ) -> Symbol:
        """Declare a function-like symbol and visit its parameters and body in its own scope."""
        params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
        sym = self.symbol(node, name, kind, scope, qual, self.params(params), visibility, is_static)
        self.fi.locals.setdefault(sym.id, set())
        if params is not None:
            plist = [params] if params.type == "identifier" else params.named_children
            for p in plist:
                for n in self.pattern_names(p, scope, qual):
                    self.fi.locals[sym.id].add(text(n))
                type_name = _type_name(p.child_by_field_name("type"))
                pattern = p.child_by_field_name("pattern")
                if type_name and pattern is not None and pattern.type == "identifier":
                    self.fi.var_types.setdefault(sym.id, {})[text(pattern)] = type_name
        body = node.child_by_field_name("body")
        if body is not None:
            saved, self.shadow = self.shadow, []
            self.visit(body, sym, sym.qualname)
            self.shadow = saved
        return sym

    def anonymous(self, node: Node, scope: Symbol, qual: str) -> None:
        """Callbacks and object-literal methods: no symbol; their names shadow outer ones."""
        params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
        names: set[str] = set()
        if params is not None:
            plist = [params] if params.type == "identifier" else params.named_children
            for p in plist:
                names.update(text(n) for n in self.pattern_names(p, scope, qual))
        self.shadow.append(names)
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit(body, scope, qual)
        self.shadow.pop()

    def call(
        self, node: Node, fn: Node | None, args: Node | None, scope: Symbol, qual: str
    ) -> None:
        argc, splat = 0, False
        if args is not None:
            for a in args.named_children:
                if a.type == "comment":
                    continue
                if a.type == "spread_element":
                    splat = True
                else:
                    argc += 1
        site = None
        if fn is None:
            pass
        elif fn.type == "identifier":
            site = CallSite(
                scope.id, line(fn), fn.start_point[1], text(fn), "none", "", argc, splat
            )
        elif fn.type == "super":
            site = CallSite(scope.id, line(fn), fn.start_point[1], "<init>", "ctor_super", "", argc)
        elif fn.type == "member_expression":
            obj = fn.child_by_field_name("object")
            prop = fn.child_by_field_name("property")
            if obj is not None and prop is not None:
                rk, rv = "expr", ""
                if obj.type == "this":
                    rk = "self"
                elif obj.type == "super":
                    rk = "super"
                elif obj.type == "identifier":
                    rk, rv = "name", text(obj)
                    if not self.shadowed(rv):
                        self.fi.refs.append(Ref(scope.id, line(obj), obj.start_point[1], rv))
                elif (
                    obj.type == "member_expression"
                    and text(obj.child_by_field_name("object")) == "this"
                ):
                    rk, rv = "attr_self", text(obj.child_by_field_name("property"))
                    self.visit(obj, scope, qual)
                elif _is_dotted(obj):
                    rk, rv = "dotted", text(obj).replace(" ", "")
                    self.visit(obj, scope, qual)
                else:
                    self.visit(obj, scope, qual)
                if rk == "name" and self.shadowed(rv):
                    rk, rv = "expr", ""
                site = CallSite(
                    scope.id, line(prop), prop.start_point[1], text(prop), rk, rv, argc, splat
                )
        else:
            self.visit(fn, scope, qual)
        if site is not None and not (site.recv_kind == "none" and self.shadowed(site.name)):
            self.fi.calls.append(site)
        if args is not None:
            self.visit(args, scope, qual)

    def shadowed(self, name: str) -> bool:
        return any(name in s for s in self.shadow)

    def record_type(
        self, scope: Symbol, name: str, value: Node | None, annotation: Node | None
    ) -> None:
        type_name = _type_name(annotation)
        if not type_name and value is not None:
            ctor = value.child_by_field_name(
                "constructor" if value.type == "new_expression" else "function"
            )
            if value.type in ("new_expression", "call_expression") and ctor is not None:
                if _is_dotted(ctor):
                    type_name = text(ctor).replace(" ", "")
        if type_name:
            self.fi.var_types.setdefault(scope.id, {})[name] = type_name

    # ---------- declarations ----------
    def declarators(self, node: Node, scope: Symbol, qual: str, exported: bool) -> None:
        for decl in node.named_children:
            if decl.type != "variable_declarator":
                continue
            name_node = decl.child_by_field_name("name")
            value = decl.child_by_field_name("value")
            spec = _require(value)
            if name_node is None:
                continue
            if spec is not None:
                self.require(name_node, spec, scope)
                continue
            if name_node.type == "identifier":
                name = text(name_node)
                if exported:
                    self.exported.add(name)
                if value is not None and value.type in _FUNCTION_VALUES:
                    if scope.kind in ("module", "function", "method", "constructor"):
                        self.function(value, name, "function", scope, qual)
                        if scope.kind != "module":
                            self.bind_local(scope, name)
                        continue
                if value is not None and value.type == "class":
                    self.klass(value, name, scope, qual)
                    continue
                if scope.kind == "module" and not self.shadow:
                    if name not in self.module_names:
                        self.symbol(name_node, name, "variable", scope, qual)
                else:
                    self.bind_local(scope, name)
                self.record_type(scope, name, value, decl.child_by_field_name("type"))
            else:
                for n in self.pattern_names(name_node, scope, qual):
                    if scope.kind == "module" and not self.shadow:
                        self.symbol(n, text(n), "variable", scope, qual)
                    else:
                        self.bind_local(scope, text(n))
            if value is not None:
                self.visit(value, scope, qual)

    def require(self, name_node: Node, spec: str, scope: Symbol) -> None:
        ln = line(name_node)
        if name_node.type == "identifier":
            self.fi.imports.append(Import(ln, spec, "default", text(name_node), "from"))
        elif name_node.type == "object_pattern":
            for c in name_node.named_children:
                if c.type == "shorthand_property_identifier_pattern":
                    self.fi.imports.append(Import(ln, spec, text(c), "", "from"))
                elif c.type == "pair_pattern":
                    key, val = c.child_by_field_name("key"), c.child_by_field_name("value")
                    if key is not None and val is not None and val.type == "identifier":
                        self.fi.imports.append(Import(ln, spec, text(key), text(val), "from"))
        if scope.kind != "module":
            for n in self.pattern_names(name_node, scope, ""):
                self.bind_local(scope, text(n))

    def klass(self, node: Node, name: str, scope: Symbol, qual: str, kind: str = "class") -> Symbol:
        sym = self.symbol(node, name, kind, scope, qual)
        for c in node.named_children:
            if c.type == "class_heritage":
                for clause in c.named_children:
                    self.heritage(clause, sym, scope, qual)
            elif c.type == "extends_type_clause":  # interface Foo extends Bar, Baz
                self.heritage(c, sym, scope, qual)
            elif c.type == "decorator":
                self.visit(c, scope, qual)
        body = node.child_by_field_name("body")
        if body is not None:
            for member in body.named_children:
                self.member(member, sym)
        return sym

    def heritage(self, clause: Node, cls: Symbol, scope: Symbol, qual: str) -> None:
        kind = "implements" if clause.type == "implements_clause" else "extends"
        for b in clause.named_children:
            if b.type == "generic_type":
                b = b.child_by_field_name("name") or b
            if b.type in ("identifier", "type_identifier", "nested_type_identifier") or (
                b.type == "member_expression" and _is_dotted(b)
            ):
                self.fi.bases.append(BaseDecl(cls.id, text(b).replace(" ", ""), line(b), kind))
            elif b.type not in ("type_arguments", "comment"):
                self.visit(b, scope, qual)  # mixin calls and other expressions

    def member(self, node: Node, cls: Symbol) -> None:
        t = node.type
        if t not in (
            "method_definition",
            "abstract_method_signature",
            "public_field_definition",
            "field_definition",
        ) and not (t == "method_signature" and cls.kind == "interface"):
            if t not in ("method_signature", "property_signature", "index_signature", "comment"):
                self.visit(node, cls, cls.qualname)
            return
        name_node = node.child_by_field_name("name") or node.child_by_field_name("property")
        if name_node is None:
            return
        name = text(name_node)
        mods = {c.type for c in node.children} | {
            text(c) for c in node.children if c.type == "accessibility_modifier"
        }
        private = "private" in mods or name_node.type == "private_property_identifier"
        visibility = "private" if private else "protected" if "protected" in mods else "public"
        is_static = "static" in mods
        if t in ("public_field_definition", "field_definition"):
            value = node.child_by_field_name("value")
            if value is not None and value.type in _FUNCTION_VALUES:
                self.function(value, name, "method", cls, cls.qualname, visibility, is_static)
                return
            self.symbol(name_node, name, "field", cls, cls.qualname, None, visibility, is_static)
            self.record_type(cls, name, value, node.child_by_field_name("type"))
            if value is not None:
                self.visit(value, cls, cls.qualname)
            return
        kind = "constructor" if name == "constructor" and t == "method_definition" else "method"
        sym = self.function(node, name, kind, cls, cls.qualname, visibility, is_static)
        if kind == "constructor":
            self.parameter_properties(node, cls, sym)

    def parameter_properties(self, ctor: Node, cls: Symbol, sym: Symbol) -> None:
        """`constructor(private repo: Repo)` declares a typed field."""
        params = ctor.child_by_field_name("parameters")
        for p in params.named_children if params is not None else []:
            pattern = p.child_by_field_name("pattern")
            mods = [c for c in p.children if c.type in ("accessibility_modifier", "readonly")]
            if not mods or pattern is None or pattern.type != "identifier":
                continue
            vis = text(mods[0]) if mods[0].type == "accessibility_modifier" else "public"
            name = text(pattern)
            self.symbol(pattern, name, "field", cls, cls.qualname, None, vis)
            self.record_type(cls, name, None, p.child_by_field_name("type"))

    # ---------- statements and expressions ----------
    def import_statement(self, node: Node) -> None:
        spec = _string(node.child_by_field_name("source"))
        ln = line(node)
        clause = next((c for c in node.named_children if c.type == "import_clause"), None)
        if clause is None:
            req = next((c for c in node.named_children if c.type == "import_require_clause"), None)
            if req is not None:  # import x = require('y')
                ident = next((c for c in req.named_children if c.type == "identifier"), None)
                src = _string(req.child_by_field_name("source"))
                if ident is not None:
                    self.fi.imports.append(Import(ln, src, "default", text(ident), "from"))
            elif spec:
                self.fi.imports.append(Import(ln, spec, "", "", "side_effect"))
            return
        for c in clause.named_children:
            if c.type == "identifier":
                self.fi.imports.append(Import(ln, spec, "default", text(c), "from"))
            elif c.type == "namespace_import":
                ident = next((i for i in c.named_children if i.type == "identifier"), None)
                if ident is not None:
                    self.fi.imports.append(Import(ln, spec, "", text(ident), "module"))
            elif c.type == "named_imports":
                for s in c.named_children:
                    if s.type != "import_specifier":
                        continue
                    name = s.child_by_field_name("name")
                    alias = s.child_by_field_name("alias")
                    self.fi.imports.append(Import(ln, spec, text(name), text(alias), "from"))

    def export_statement(self, node: Node, scope: Symbol, qual: str) -> None:
        source = node.child_by_field_name("source")
        spec = _string(source) if source is not None else ""
        decl = node.child_by_field_name("declaration")
        value = node.child_by_field_name("value")
        is_default = any(c.type == "default" for c in node.children)
        ln = line(node)
        if decl is not None:
            before = len(self.fi.symbols)
            self.visit(decl, scope, qual, exported=True)
            for s in self.fi.symbols[before:]:
                if s.parent_id == scope.id:
                    self.exported.add(s.name)
                    if is_default:
                        self.fi.exports["default"] = s.name
                        break
            return
        if value is not None:
            name = text(value.child_by_field_name("name")) or "default"
            if value.type == "identifier":
                self.fi.exports["default"] = text(value)
                self.exported.add(text(value))
            elif value.type in _FUNCTION_VALUES:
                self.function(value, name, "function", scope, qual)
                self.fi.exports["default"] = name
                self.exported.add(name)
            elif value.type in _CLASS_DECLS:
                self.klass(value, name, scope, qual)
                self.fi.exports["default"] = name
                self.exported.add(name)
            else:
                self.visit(value, scope, qual)
            return
        clause = next((c for c in node.named_children if c.type == "export_clause"), None)
        ns = next((c for c in node.named_children if c.type == "namespace_export"), None)
        if clause is not None:
            for item in clause.named_children:
                if item.type != "export_specifier":
                    continue
                name = text(item.child_by_field_name("name"))
                alias = text(item.child_by_field_name("alias"))
                if spec:
                    self.fi.imports.append(Import(ln, spec, name, alias, "reexport"))
                else:
                    self.fi.exports[alias or name] = name
                    self.exported.add(name)
        elif ns is not None and spec:
            ident = next((i for i in ns.named_children if i.type == "identifier"), None)
            self.fi.imports.append(Import(ln, spec, "*", text(ident), "reexport_ns"))
        elif spec:
            self.fi.imports.append(Import(ln, spec, "", "", "reexport_star"))

    def commonjs_export(self, target: str, right: Node, scope: Symbol, qual: str) -> None:
        if right.type == "identifier":
            self.fi.exports[target or "default"] = text(right)
            self.exported.add(text(right))
            return
        if target == "" and right.type == "object":
            for c in right.named_children:
                if c.type == "shorthand_property_identifier":
                    self.fi.exports[text(c)] = text(c)
                    self.exported.add(text(c))
                elif c.type == "pair":
                    key, val = c.child_by_field_name("key"), c.child_by_field_name("value")
                    if key is not None and val is not None and val.type == "identifier":
                        self.fi.exports[text(key)] = text(val)
                        self.exported.add(text(val))
                    elif val is not None:
                        self.visit(val, scope, qual)
                else:
                    self.visit(c, scope, qual)
            return
        if target and right.type in _FUNCTION_VALUES and scope.kind == "module":
            self.function(right, target, "function", scope, qual)
            self.fi.exports[target] = target
            self.exported.add(target)
            return
        self.visit(right, scope, qual)

    def visit(self, node: Node, scope: Symbol, qual: str, exported: bool = False) -> None:
        t = node.type
        if t in _TYPE_ONLY:
            return
        if t == "import_statement":
            self.import_statement(node)
            return
        if t == "export_statement":
            self.export_statement(node, scope, qual)
            return
        if t in ("function_declaration", "generator_function_declaration"):
            name = text(node.child_by_field_name("name"))
            self.function(node, name, "function", scope, qual)
            if scope.kind != "module":
                self.bind_local(scope, name)
            return
        if t in _CLASS_DECLS and node.child_by_field_name("name") is not None:
            self.klass(node, text(node.child_by_field_name("name")), scope, qual)
            return
        if t == "interface_declaration":
            self.klass(node, text(node.child_by_field_name("name")), scope, qual, "interface")
            return
        if t == "enum_declaration":
            self.symbol(node, text(node.child_by_field_name("name")), "enum", scope, qual)
            return
        if t in ("lexical_declaration", "variable_declaration"):
            self.declarators(node, scope, qual, exported)
            return
        if t in _FUNCTION_VALUES or t == "method_definition" or t in _CLASS_DECLS:
            self.anonymous(node, scope, qual)
            return
        if t == "call_expression":
            if _require(node) is not None:
                return
            self.call(
                node,
                node.child_by_field_name("function"),
                node.child_by_field_name("arguments"),
                scope,
                qual,
            )
            return
        if t == "new_expression":
            self.call(
                node,
                node.child_by_field_name("constructor"),
                node.child_by_field_name("arguments"),
                scope,
                qual,
            )
            return
        if t in ("jsx_opening_element", "jsx_self_closing_element"):
            tag = node.child_by_field_name("name")
            if tag is not None and tag.type == "identifier" and text(tag)[:1].isupper():
                self.fi.calls.append(
                    CallSite(scope.id, line(tag), tag.start_point[1], text(tag), "none", "", 1)
                )
            elif tag is not None and tag.type == "member_expression":
                self.call(node, tag, None, scope, qual)
            for c in node.named_children:
                if c is not tag:
                    self.visit(c, scope, qual)
            return
        if t == "jsx_closing_element":
            return
        if t == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            target = _exports_target(left)
            if target is not None and right is not None and scope.kind == "module":
                self.commonjs_export(target, right, scope, qual)
                return
            if (
                left is not None
                and left.type == "member_expression"
                and text(left.child_by_field_name("object")) == "this"
                and scope.kind in ("method", "constructor")
                and scope.parent_id
            ):
                cls = next(s for s in self.fi.symbols if s.id == scope.parent_id)
                self.record_type(cls, text(left.child_by_field_name("property")), right, None)
        if t in ("for_in_statement", "for_statement") and scope.kind != "module":
            left = node.child_by_field_name("left")
            for n in self.pattern_names(left, scope, qual) if left is not None else []:
                self.bind_local(scope, text(n))
        if t == "catch_clause":
            param = node.child_by_field_name("parameter")
            for n in self.pattern_names(param, scope, qual) if param is not None else []:
                self.bind_local(scope, text(n))
            body = node.child_by_field_name("body")
            if body is not None:
                self.visit(body, scope, qual)
            return
        if t in ("identifier", "shorthand_property_identifier"):
            name = text(node)
            if not self.shadowed(name) and name not in ("undefined", "require"):
                self.fi.refs.append(Ref(scope.id, line(node), node.start_point[1], name))
            return
        if t == "member_expression":
            obj = node.child_by_field_name("object")
            prop = node.child_by_field_name("property")
            if obj is not None and obj.type == "this" and prop is not None:
                self.fi.refs.append(
                    Ref(scope.id, line(prop), prop.start_point[1], text(prop), "self")
                )
                return
            if obj is not None:
                self.visit(obj, scope, qual)
            return
        if t in ("pair", "property_signature"):
            value = node.child_by_field_name("value")
            if value is not None:
                self.visit(value, scope, qual)
            return
        for c in node.named_children:
            self.visit(c, scope, qual)

    def run(self) -> FileInfo:
        for c in self.tree.root_node.named_children:
            self.visit(c, self.mod, "")
        for name in self.exported:
            sym = self.module_names.get(name)
            if sym is not None:
                sym.visibility = "public"
        return self.fi


def extract(path: str, src: bytes) -> FileInfo:
    return _Extractor(path, src).run()
