"""Pass 1 for Python: definitions, imports, bases, call sites, references, type facts."""
from __future__ import annotations

import tree_sitter_python as tsp
from tree_sitter import Language, Parser

from .extract_common import IdAllocator, end_line, line, module_symbol, text
from .model import BaseDecl, CallSite, FileInfo, Import, Ref, Symbol

PY = Language(tsp.language())

# Parent node types in which a bare identifier is a value use (a reference).
_VALUE_PARENTS = {
    "argument_list", "list", "tuple", "set", "pair", "return_statement",
    "expression_list", "conditional_expression", "boolean_operator", "lambda",
    "parenthesized_expression", "subscript", "yield",
}


def _params(params_node, is_method: bool, is_static: bool):
    """Return (min, max) positional arity; max -1 = unbounded."""
    req = opt = 0
    unbounded = False
    names = []
    if params_node is None:
        return 0, 0
    for p in params_node.named_children:
        t = p.type
        s = text(p)
        if t in ("list_splat_pattern",) or (t in ("typed_parameter",) and s.startswith("*") and not s.startswith("**")):
            unbounded = True
            continue
        if t == "dictionary_splat_pattern" or s.startswith("**"):
            unbounded = True
            continue
        if t in ("keyword_separator", "positional_separator"):
            continue
        if t in ("identifier", "typed_parameter"):
            names.append(s.split(":")[0].strip())
            req += 1
        elif t in ("default_parameter", "typed_default_parameter"):
            names.append(s.split("=")[0].split(":")[0].strip())
            opt += 1
    if is_method and not is_static and names:
        # the first positional parameter is the bound receiver (self / cls)
        if req > 0:
            req -= 1
        elif opt > 0:
            opt -= 1
    return req, (-1 if unbounded else req + opt)


def _argc(args_node):
    if args_node is None:
        return 0, False
    if args_node.type == "generator_expression":
        return 1, False
    n = 0
    splat = False
    for a in args_node.named_children:
        if a.type == "comment":
            continue
        if a.type in ("list_splat", "dictionary_splat"):
            splat = True
            continue
        n += 1
    return n, splat


def _identifiers(node):
    if node is None:
        return []
    if node.type == "identifier":
        return [node]
    out = []
    for c in node.named_children:
        out.extend(_identifiers(c))
    return out


def _module_name(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def extract(path: str, src: bytes) -> FileInfo:
    tree = Parser(PY).parse(src)
    loc = src.count(b"\n") + (0 if src.endswith(b"\n") or not src else 1)
    fi = FileInfo(path=path, lang="python", loc=loc, parsed=True)
    ids = IdAllocator()
    mod = module_symbol(ids, path, "python", loc, _module_name(path))
    fi.symbols.append(mod)

    shadow = []  # lambda parameter name sets currently in scope
    module_vars = {}

    def _bind_local(scope, name):
        if scope.kind in ("function", "method"):
            fi.locals.setdefault(scope.id, set()).add(name)

    def bind_targets(left, scope, qual, assign_node):
        """Record names bound by an assignment/loop target; visit sub-expressions that are reads."""
        if left.type == "identifier":
            name = text(left)
            if scope.kind == "module" and assign_node is not None:
                if name not in module_vars:
                    sym = Symbol(id=ids.make(path, name, None, line(left)), name=name, qualname=name,
                                 kind="variable", lang="python", file=path, line=line(left),
                                 end_line=end_line(assign_node), visibility=_vis(name), parent_id=scope.id)
                    fi.symbols.append(sym)
                    module_vars[name] = sym
            else:
                _bind_local(scope, name)
            return
        if left.type in ("pattern_list", "tuple_pattern", "list_pattern", "tuple", "list", "list_splat_pattern", "parenthesized_expression"):
            for c in left.named_children:
                bind_targets(c, scope, qual, assign_node)
            return
        visit(left, scope, qual)  # attribute / subscript targets: object is read

    def visit(node, scope: Symbol, qual: str, decorators=()):
        t = node.type
        if t == "decorated_definition":
            decs = [text(d).lstrip("@").split("(")[0].strip() for d in node.named_children if d.type == "decorator"]
            for d in node.named_children:
                if d.type == "decorator":
                    visit(d, scope, qual)
            defn = node.child_by_field_name("definition")
            if defn is not None:
                visit(defn, scope, qual, decorators=decs)
            return
        if t == "class_definition":
            name = text(node.child_by_field_name("name"))
            qn = f"{qual}.{name}" if qual else name
            sym = Symbol(id=ids.make(path, qn, None, line(node)), name=name, qualname=qn, kind="class",
                         lang="python", file=path, line=line(node), end_line=end_line(node),
                         visibility=_vis(name), annotations=list(decorators), parent_id=scope.id)
            fi.symbols.append(sym)
            sup = node.child_by_field_name("superclasses")
            if sup is not None:
                for b in sup.named_children:
                    if b.type in ("identifier", "attribute"):
                        fi.bases.append(BaseDecl(cls=sym.id, text=text(b), line=line(b)))
                    elif b.type in ("keyword_argument", "comment"):
                        continue
                    else:
                        visit(b, scope, qual)
            body = node.child_by_field_name("body")
            if body is not None:
                for c in body.children:
                    visit(c, sym, qn)
            return
        if t == "function_definition":
            name = text(node.child_by_field_name("name"))
            qn = f"{qual}.{name}" if qual else name
            is_method = scope.kind == "class"
            is_static = "staticmethod" in decorators
            amin, amax = _params(node.child_by_field_name("parameters"), is_method, is_static)
            kind = "method" if is_method else "function"
            sym = Symbol(id=ids.make(path, qn, amin, line(node)), name=name, qualname=qn, kind=kind,
                         lang="python", file=path, line=line(node), end_line=end_line(node),
                         arity_min=amin, arity_max=amax, visibility=_vis(name), is_static=is_static,
                         annotations=list(decorators), parent_id=scope.id)
            fi.symbols.append(sym)
            params = node.child_by_field_name("parameters")
            loc_names = fi.locals.setdefault(sym.id, set())
            if params is not None:
                for p in params.named_children:
                    nm = p if p.type == "identifier" else (p.child_by_field_name("name") or next((c for c in p.named_children if c.type == "identifier"), None))
                    if nm is not None:
                        loc_names.add(text(nm))
                    for c in p.named_children:
                        if c.type not in ("identifier",):
                            visit(c, scope, qual)  # default values evaluate in enclosing scope
            body = node.child_by_field_name("body")
            if body is not None:
                for c in body.children:
                    visit(c, sym, qn)
            return
        if t == "import_statement":
            for n in node.named_children:
                if n.type == "dotted_name":
                    fi.imports.append(Import(line=line(node), module=text(n), kind="module"))
                elif n.type == "aliased_import":
                    fi.imports.append(Import(line=line(node), module=text(n.child_by_field_name("name")),
                                             alias=text(n.child_by_field_name("alias")), kind="module"))
            return
        if t == "import_from_statement":
            modn = node.child_by_field_name("module_name")
            modtxt = text(modn).replace(" ", "")
            star = any(c.type == "wildcard_import" for c in node.named_children)
            if star:
                fi.imports.append(Import(line=line(node), module=modtxt, kind="star"))
            for n in node.children_by_field_name("name"):
                if n.type == "dotted_name":
                    fi.imports.append(Import(line=line(node), module=modtxt, name=text(n), kind="from"))
                elif n.type == "aliased_import":
                    fi.imports.append(Import(line=line(node), module=modtxt,
                                             name=text(n.child_by_field_name("name")),
                                             alias=text(n.child_by_field_name("alias")), kind="from"))
            return
        if t == "if_statement" and scope.kind == "module":
            cond = text(node.child_by_field_name("condition")).replace("'", '"').replace(" ", "")
            if cond in ('__name__=="__main__"', '"__main__"==__name__'):
                fi.is_script = True
        if t == "call":
            fn = node.child_by_field_name("function")
            argc, splat = _argc(node.child_by_field_name("arguments"))
            if fn is not None and fn.type == "identifier":
                fi.calls.append(CallSite(scope.id, line(node), node.start_point[1], text(fn), "none", "", argc, splat))
            elif fn is not None and fn.type == "attribute":
                obj = fn.child_by_field_name("object")
                attr = text(fn.child_by_field_name("attribute"))
                if obj.type == "identifier" and text(obj) in ("self", "cls"):
                    rk, rv = "self", text(obj)
                elif obj.type == "call" and text(obj.child_by_field_name("function")) == "super":
                    rk, rv = "super", ""
                elif obj.type == "identifier":
                    rk, rv = "name", text(obj)
                    fi.refs.append(Ref(scope.id, line(obj), obj.start_point[1], rv, "recv"))
                elif obj.type == "attribute" and text(obj.child_by_field_name("object")) in ("self", "cls"):
                    rk, rv = "attr_self", text(obj.child_by_field_name("attribute"))
                elif obj.type == "attribute":
                    rk, rv = "dotted", text(obj).replace(" ", "")
                else:
                    rk, rv = "expr", ""
                fi.calls.append(CallSite(scope.id, line(fn.child_by_field_name("attribute")),
                                         fn.child_by_field_name("attribute").start_point[1],
                                         attr, rk, rv, argc, splat))
                if rk in ("expr", "dotted", "attr_self"):
                    visit(obj, scope, qual)
            elif fn is not None:
                visit(fn, scope, qual)
            args = node.child_by_field_name("arguments")
            if args is not None:
                for c in args.children:
                    visit(c, scope, qual)
            return
        if t in ("assignment", "augmented_assignment"):
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if t == "assignment" and right is not None and right.type == "call" and left is not None:
                fn = right.child_by_field_name("function")
                if fn is not None and fn.type in ("identifier", "attribute"):
                    tname = text(fn).replace(" ", "")
                    if left.type == "identifier":
                        fi.var_types.setdefault(scope.id, {})[text(left)] = tname
                    elif left.type == "attribute" and text(left.child_by_field_name("object")) == "self":
                        cls_id = scope.parent_id if scope.kind == "method" else None
                        if cls_id:
                            fi.var_types.setdefault(cls_id, {})[text(left.child_by_field_name("attribute"))] = tname
            if t == "assignment" and left is not None:
                bind_targets(left, scope, qual, node)
            elif left is not None and left.type != "identifier":
                visit(left, scope, qual)
            elif left is not None:
                # augmented assignment reads the name too
                fi.refs.append(Ref(scope.id, line(left), left.start_point[1], text(left)))
            for c in node.children:
                if c == left:
                    continue
                visit(c, scope, qual)
            return
        if t in ("for_statement", "for_in_clause"):
            left = node.child_by_field_name("left")
            if left is not None:
                bind_targets(left, scope, qual, None)
            for c in node.children:
                if c != left:
                    visit(c, scope, qual)
            return
        if t == "as_pattern":
            alias = node.child_by_field_name("alias")
            for c in node.children:
                if c == alias:
                    for n in _identifiers(c):
                        _bind_local(scope, text(n))
                else:
                    visit(c, scope, qual)
            return
        if t in ("global_statement", "nonlocal_statement"):
            for n in node.named_children:
                if n.type == "identifier" and t == "global_statement":
                    fi.globals_decl.setdefault(scope.id, set()).add(text(n))
            return
        if t == "lambda":
            params = node.child_by_field_name("parameters")
            body = node.child_by_field_name("body")
            names = {text(n) for n in _identifiers(params)} if params is not None else set()
            shadow.append(names)
            if body is not None:
                visit(body, scope, qual)
            shadow.pop()
            return
        if t == "keyword_argument":
            v = node.child_by_field_name("value")
            if v is not None:
                if v.type == "identifier":
                    fi.refs.append(Ref(scope.id, line(v), v.start_point[1], text(v)))
                else:
                    visit(v, scope, qual)
            return
        if t == "identifier":
            nm = text(node)
            if not any(nm in sh for sh in shadow):
                fi.refs.append(Ref(scope.id, line(node), node.start_point[1], nm))
            return
        if t == "attribute":
            obj = node.child_by_field_name("object")
            par = node.parent
            if obj is not None and text(obj) in ("self", "cls") and par is not None and par.type in _VALUE_PARENTS | {"keyword_argument"}:
                a = node.child_by_field_name("attribute")
                fi.refs.append(Ref(scope.id, line(a), a.start_point[1], text(a), "self"))
                return
            if obj is not None:
                visit(obj, scope, qual)
            return
        for c in node.children:
            visit(c, scope, qual)

    for c in tree.root_node.children:
        visit(c, mod, "")
    if fi.is_script:
        mod.entry_reason = "script"
    return fi


def _vis(name: str) -> str:
    if name.startswith("__") and name.endswith("__"):
        return "public"
    return "private" if name.startswith("_") else "public"
