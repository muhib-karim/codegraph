"""Helpers shared by the per-language extractors."""

from __future__ import annotations

from typing import Any

from .model import Symbol


def text(node: Any) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def child(node: Any, name: str) -> Any:
    """A field the grammar always provides; raises (recorded as a parse error) if absent."""
    found = node.child_by_field_name(name)
    if found is None:
        raise ValueError(f"{node.type} without {name} at line {line(node)}")
    return found


def line(node: Any) -> int:
    return int(node.start_point[0]) + 1


def end_line(node: Any) -> int:
    return int(node.end_point[0]) + 1


class IdAllocator:
    """Builds stable, unique symbol ids of the form <path>::<qualname>[/<arity>][@<line>]."""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def make(self, path: str, qualname: str, arity: int | None = None, lineno: int = 0) -> str:
        base = f"{path}::{qualname}"
        if arity is not None:
            base += f"/{arity}"
        sid = base
        if sid in self.used:
            sid = f"{base}@{lineno}"
            n = 2
            while sid in self.used:
                sid = f"{base}@{lineno}.{n}"
                n += 1
        self.used.add(sid)
        return sid


def module_symbol(ids: IdAllocator, path: str, lang: str, loc: int, name: str) -> Symbol:
    return Symbol(
        id=ids.make(path, "<module>"),
        name=name,
        qualname="<module>",
        kind="module",
        lang=lang,
        file=path,
        line=1,
        end_line=max(loc, 1),
    )
