"""Pass 1 for Java: definitions, imports, bases, call sites, references, declared types."""
from __future__ import annotations

import tree_sitter_java as tsj
from tree_sitter import Language, Parser

from .extract_common import IdAllocator, end_line, line, module_symbol, text
from .model import BaseDecl, CallSite, FileInfo, Import, Ref, Symbol

JAVA = Language(tsj.language())

_CLASS_KINDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "interface",
}


def type_name(node) -> str:
    """Simple (possibly dotted) type name with generics/arrays stripped."""
    if node is None:
        return ""
    t = node.type
    if t == "generic_type":
        for c in node.named_children:
            if c.type in ("type_identifier", "scoped_type_identifier"):
                return type_name(c)
    if t == "array_type":
        return type_name(node.child_by_field_name("element")) + "[]"
    if t == "scoped_type_identifier":
        return ".".join(type_name(c) for c in node.named_children if c.type in ("type_identifier", "scoped_type_identifier", "generic_type"))
    return text(node)


def _modifiers(node):
    vis, static, annos, abstract = "package", False, [], False
    for c in node.children:
        if c.type == "modifiers":
            for m in c.children:
                s = text(m)
                if s in ("public", "private", "protected"):
                    vis = s
                elif s == "static":
                    static = True
                elif s == "abstract":
                    abstract = True
                elif m.type in ("marker_annotation", "annotation"):
                    annos.append(text(m.child_by_field_name("name")).split(".")[-1])
    return vis, static, annos, abstract


def _arity(params):
    n, var = 0, False
    if params is None:
        return 0, 0
    for p in params.named_children:
        if p.type == "formal_parameter":
            n += 1
        elif p.type == "spread_parameter":
            var = True
    return n, (-1 if var else n)


def _argc(args):
    if args is None:
        return 0
    return sum(1 for a in args.named_children if a.type not in ("comment", "line_comment", "block_comment"))


def extract(path: str, src: bytes) -> FileInfo:
    tree = Parser(JAVA).parse(src)
    loc = src.count(b"\n") + (0 if src.endswith(b"\n") or not src else 1)
    fi = FileInfo(path=path, lang="java", loc=loc, parsed=True)
    ids = IdAllocator()
    mod = module_symbol(ids, path, "java", loc, path.rsplit("/", 1)[-1][:-5])
    fi.symbols.append(mod)

    lam_shadow = []

    def shadowed(name):
        return any(name in sh for sh in lam_shadow)

    def vt(scope_id):
        return fi.var_types.setdefault(scope_id, {})

    def add_class(node, scope, qual, kind, name, iface_default=False):
        qn = f"{qual}.{name}" if qual else name
        vis, static, annos, abstract = _modifiers(node)
        if iface_default and vis == "package":
            vis = "public"
        sym = Symbol(id=ids.make(path, qn, None, line(node)), name=name, qualname=qn, kind=kind, lang="java",
                     file=path, line=line(node), end_line=end_line(node), visibility=vis, is_static=static,
                     annotations=annos, parent_id=scope.id)
        fi.symbols.append(sym)
        return sym, qn

    def class_body(body, sym, qn):
        if body is None:
            return
        for c in body.children:
            if c.type == "enum_body_declarations":
                for d in c.children:
                    visit(d, sym, qn)
            elif c.type == "enum_constant":
                cname = text(c.child_by_field_name("name"))
                fi.symbols.append(Symbol(id=ids.make(path, f"{qn}.{cname}", None, line(c)), name=cname,
                                         qualname=f"{qn}.{cname}", kind="field", lang="java", file=path,
                                         line=line(c), end_line=end_line(c), visibility="public",
                                         is_static=True, parent_id=sym.id))
                vt(sym.id)[cname] = sym.name
                args = c.child_by_field_name("arguments")
                cb = c.child_by_field_name("body")
                if args is not None:
                    fi.calls.append(CallSite(sym.id, line(c), c.start_point[1], "<init>", "new", sym.name, _argc(args)))
                    visit(args, sym, qn)
                if cb is not None:
                    anon, aqn = add_class(c, sym, qn, "class", "$anon@%d" % line(c))
                    fi.bases.append(BaseDecl(anon.id, sym.name, line(c), "extends"))
                    class_body(cb, anon, aqn)
            else:
                visit(c, sym, qn)

    def visit(node, scope: Symbol, qual: str):
        t = node.type
        if t == "package_declaration":
            for c in node.named_children:
                if c.type in ("scoped_identifier", "identifier"):
                    fi.package = text(c)
            return
        if t == "import_declaration":
            static = any(c.type == "static" for c in node.children)
            star = any(c.type == "asterisk" for c in node.children)
            name = next((text(c) for c in node.named_children if c.type in ("scoped_identifier", "identifier")), "")
            kind = "java_static" if static else "java"
            if star:
                kind += "_star"
            fi.imports.append(Import(line=line(node), module=name, kind=kind))
            return
        if t in _CLASS_KINDS:
            name = text(node.child_by_field_name("name"))
            in_iface = scope.kind == "interface"
            sym, qn = add_class(node, scope, qual, _CLASS_KINDS[t], name, iface_default=in_iface)
            sup = node.child_by_field_name("superclass")
            if sup is not None:
                for c in sup.named_children:
                    fi.bases.append(BaseDecl(sym.id, type_name(c), line(c), "extends"))
            for c in node.children:
                if c.type in ("super_interfaces", "extends_interfaces"):
                    kind = "implements" if c.type == "super_interfaces" else "extends"
                    for tl in c.named_children:
                        for ty in (tl.named_children if tl.type == "type_list" else [tl]):
                            fi.bases.append(BaseDecl(sym.id, type_name(ty), line(ty), kind))
            if t == "record_declaration":
                params = node.child_by_field_name("parameters")
                if params is not None:
                    for p in params.named_children:
                        if p.type == "formal_parameter":
                            vt(sym.id)[text(p.child_by_field_name("name"))] = type_name(p.child_by_field_name("type"))
            class_body(node.child_by_field_name("body"), sym, qn)
            return
        if t in ("method_declaration", "constructor_declaration", "compact_constructor_declaration"):
            is_ctor = t != "method_declaration"
            name = text(node.child_by_field_name("name")) if not is_ctor else scope.name
            qn = f"{qual}.<init>" if is_ctor else (f"{qual}.{name}" if qual else name)
            params = node.child_by_field_name("parameters")
            amin, amax = _arity(params)
            vis, static, annos, abstract = _modifiers(node)
            body = node.child_by_field_name("body")
            if scope.kind == "interface":
                if vis == "package":
                    vis = "public"
                if body is None:
                    abstract = True
            sym = Symbol(id=ids.make(path, qn, amin, line(node)), name=name, qualname=qn,
                         kind="constructor" if is_ctor else "method", lang="java", file=path,
                         line=line(node), end_line=end_line(node), arity_min=amin, arity_max=amax,
                         visibility=vis, is_static=static, annotations=annos, parent_id=scope.id)
            if abstract:
                sym.entry_reason = "abstract"
            fi.symbols.append(sym)
            if params is not None:
                for p in params.named_children:
                    if p.type in ("formal_parameter", "spread_parameter"):
                        ty = p.child_by_field_name("type")
                        if ty is None:
                            ty = next((c for c in p.named_children if c.type not in ("modifiers", "variable_declarator", "identifier")), None)
                        nm = p.child_by_field_name("name")
                        if nm is None:
                            d = next((c for c in p.named_children if c.type == "variable_declarator"), None)
                            nm = d.child_by_field_name("name") if d is not None else None
                        if nm is not None:
                            vt(sym.id)[text(nm)] = type_name(ty) + ("[]" if p.type == "spread_parameter" else "")
            if body is not None:
                for c in body.children:
                    visit(c, sym, qn)
            return
        if t == "field_declaration" or t == "constant_declaration":
            ty = type_name(node.child_by_field_name("type"))
            vis, static, annos, _ = _modifiers(node)
            if scope.kind == "interface":
                vis, static = "public", True
            for d in node.children_by_field_name("declarator"):
                nm = d.child_by_field_name("name")
                vt(scope.id)[text(nm)] = ty
                fname = text(nm)
                fi.symbols.append(Symbol(id=ids.make(path, f"{qual}.{fname}", None, line(nm)), name=fname,
                                         qualname=f"{qual}.{fname}", kind="field", lang="java", file=path,
                                         line=line(nm), end_line=end_line(d), visibility=vis, is_static=static,
                                         annotations=annos, parent_id=scope.id))
                v = d.child_by_field_name("value")
                if v is not None:
                    visit(v, scope, qual)
            return
        if t in ("local_variable_declaration",):
            ty = type_name(node.child_by_field_name("type"))
            for d in node.children_by_field_name("declarator"):
                v = d.child_by_field_name("value")
                vty = ty
                if ty == "var" and v is not None and v.type == "object_creation_expression":
                    vty = type_name(v.child_by_field_name("type"))
                vt(scope.id)[text(d.child_by_field_name("name"))] = vty
                if v is not None:
                    visit(v, scope, qual)
            return
        if t in ("enhanced_for_statement",):
            ty = node.child_by_field_name("type")
            nm = node.child_by_field_name("name")
            if ty is not None and nm is not None:
                vt(scope.id)[text(nm)] = type_name(ty)
        if t == "catch_formal_parameter":
            nm = node.child_by_field_name("name")
            ct = next((c for c in node.named_children if c.type == "catch_type"), None)
            if nm is not None and ct is not None and ct.named_children:
                vt(scope.id)[text(nm)] = type_name(ct.named_children[0])
            return
        if t == "method_invocation":
            nm = node.child_by_field_name("name")
            obj = node.child_by_field_name("object")
            args = node.child_by_field_name("arguments")
            if obj is None:
                rk, rv = "none", ""
            elif obj.type == "this":
                rk, rv = "self", "this"
            elif obj.type == "super":
                rk, rv = "super", ""
            elif obj.type == "identifier":
                rk, rv = "name", text(obj)
                if not shadowed(rv):
                    fi.refs.append(Ref(scope.id, line(obj), obj.start_point[1], rv, "none"))
            elif obj.type == "field_access" and text(obj.child_by_field_name("object")) == "this":
                rk, rv = "attr_self", text(obj.child_by_field_name("field"))
                f = obj.child_by_field_name("field")
                fi.refs.append(Ref(scope.id, line(f), f.start_point[1], rv, "field", "this"))
            elif obj.type in ("field_access", "scoped_identifier"):
                rk, rv = "dotted", text(obj).replace(" ", "")
            else:
                rk, rv = "expr", ""
            fi.calls.append(CallSite(scope.id, line(nm), nm.start_point[1], text(nm), rk, rv, _argc(args)))
            if obj is not None and rk in ("expr", "dotted"):
                visit(obj, scope, qual)
            if args is not None:
                visit(args, scope, qual)
            return
        if t == "object_creation_expression":
            ty = node.child_by_field_name("type")
            args = node.child_by_field_name("arguments")
            tname = type_name(ty)
            fi.calls.append(CallSite(scope.id, line(node), node.start_point[1], "<init>", "new", tname, _argc(args)))
            if args is not None:
                visit(args, scope, qual)
            body = next((c for c in node.children if c.type == "class_body"), None)
            if body is not None:
                anon, aqn = add_class(node, scope, qual, "class", "$anon@%d" % line(node))
                fi.bases.append(BaseDecl(anon.id, tname, line(node), "extends"))
                class_body(body, anon, aqn)
            return
        if t == "explicit_constructor_invocation":
            ctor = node.child_by_field_name("constructor")
            args = node.child_by_field_name("arguments")
            rk = "ctor_super" if ctor is not None and ctor.type == "super" else "ctor_this"
            fi.calls.append(CallSite(scope.id, line(node), node.start_point[1], "<init>", rk, "", _argc(args)))
            if args is not None:
                visit(args, scope, qual)
            return
        if t == "method_reference":
            kids = [c for c in node.children]
            try:
                i = [c.type for c in kids].index("::")
            except ValueError:
                i = -1
            if i > 0:
                lhs = kids[0]
                rhs = kids[i + 1] if i + 1 < len(kids) else None
                name = "<init>" if rhs is not None and rhs.type == "new" else text(rhs)
                if lhs.type == "this":
                    rk, rv = "this", ""
                elif lhs.type == "super":
                    rk, rv = "super", ""
                else:
                    rk, rv = "type", type_name(lhs) if lhs.type != "identifier" else text(lhs)
                fi.refs.append(Ref(scope.id, line(node), node.start_point[1], name, rk, rv))
            return
        if t == "assignment_expression":
            left = node.child_by_field_name("left")
            op = next((c for c in node.children if not c.is_named), None)
            is_plain = op is not None and text(op) == "="
            for c in node.children:
                if c == left and is_plain:
                    if left.type == "field_access":
                        visit(left.child_by_field_name("object"), scope, qual)  # object is read, field is written
                    elif left.type != "identifier":
                        visit(left, scope, qual)
                    continue
                visit(c, scope, qual)
            return
        if t == "lambda_expression":
            params = node.child_by_field_name("parameters")
            names = set()
            if params is not None:
                stack = [params]
                while stack:
                    n = stack.pop()
                    if n.type == "identifier":
                        names.add(text(n))
                    stack.extend(n.named_children)
            lam_shadow.append(names)
            body = node.child_by_field_name("body")
            if body is not None:
                visit(body, scope, qual)
            lam_shadow.pop()
            return
        if t == "field_access":
            obj = node.child_by_field_name("object")
            f = node.child_by_field_name("field")
            if obj is not None and f is not None:
                if obj.type == "this":
                    rv = "this"
                elif obj.type == "super":
                    rv = "super"
                else:
                    rv = text(obj).replace(" ", "")
                    visit(obj, scope, qual)
                fi.refs.append(Ref(scope.id, line(f), f.start_point[1], text(f), "field", rv))
            return
        if t == "identifier":
            nm = text(node)
            par = node.parent.type if node.parent is not None else ""
            if par not in ("labeled_statement", "break_statement", "continue_statement", "marker_annotation",
                           "annotation", "element_value_pair", "scoped_identifier") and not shadowed(nm):
                fi.refs.append(Ref(scope.id, line(node), node.start_point[1], nm, "none"))
            return
        for c in node.children:
            visit(c, scope, qual)

    for c in tree.root_node.children:
        visit(c, mod, "")
    return fi
