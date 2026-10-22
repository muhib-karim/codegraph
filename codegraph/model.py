"""Plain data records produced by pass 1 and consumed by pass 2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Symbol:
    id: str
    name: str
    qualname: str
    kind: str
    lang: str
    file: str
    line: int
    end_line: int
    arity_min: int = 0
    arity_max: int = 0  # -1 = unbounded
    visibility: str = "public"
    is_static: bool = False
    annotations: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    entry_reason: str = ""


@dataclass
class CallSite:
    caller: str  # Symbol id of enclosing scope
    line: int
    col: int
    name: str  # callee simple name ("<init>" for constructors via new)
    recv_kind: str  # none | self | super | name | attr_self | expr | new | ctor_this | ctor_super
    recv: str = ""  # receiver identifier / type text
    argc: int = 0
    splat: bool = False


@dataclass
class Ref:
    owner: str  # Symbol id of enclosing scope
    line: int
    col: int
    name: str
    recv_kind: str = "none"  # none | self | type (Java Type::m) | this | super
    recv: str = ""


@dataclass
class Import:
    line: int
    module: str  # python: dotted module (with leading dots if relative); java: full name
    name: str = ""  # python from-import name; "" for plain import
    alias: str = ""
    kind: str = "module"  # module | from | star | java | java_star | java_static | java_static_star


@dataclass
class BaseDecl:
    cls: str  # Symbol id
    text: str  # base expression text (generics stripped)
    line: int
    kind: str = "extends"  # extends | implements


@dataclass
class FileInfo:
    path: str
    lang: str
    loc: int
    parsed: bool
    content_hash: str = ""
    package: str = ""
    symbols: list[Symbol] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    bases: list[BaseDecl] = field(default_factory=list)
    # scope-id -> {var: type-text}; for classes this holds field / self.attr types
    var_types: dict[str, dict[str, str]] = field(default_factory=dict)
    is_script: bool = False
    # scope-id -> names bound locally in that function scope (params, assignments, loop vars)
    locals: dict[str, set[str]] = field(default_factory=dict)
    # scope-id -> names declared `global` in that function
    globals_decl: dict[str, set[str]] = field(default_factory=dict)
    # JS/TS: exported name -> local name ("default" for the default export)
    exports: dict[str, str] = field(default_factory=dict)
