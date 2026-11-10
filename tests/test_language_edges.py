"""Language regression scenarios exercise binding, shadowing and confidence semantics."""

from textwrap import dedent

from codegraph.indexer import build


def build_sources(tmp_path, sources):
    for name, source in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(source).lstrip())
    graph, errors = build(str(tmp_path))
    assert not errors
    return graph


def edges(graph, attribute="calls"):
    return {
        (graph.symbols[e.src].qualname, graph.symbols[e.dst].qualname, e.confidence)
        for e in getattr(graph, attribute)
    }


def test_python_scope_imports_fields_and_dynamic_receivers(tmp_path):
    graph = build_sources(
        tmp_path,
        {
            "lib/__init__.py": "",
            "lib/base.py": """
            TOKEN = 1
            callback = lambda x: x
            class Engine:
                def run(self, amount=1): return amount
                @staticmethod
                def create(*args, **kwargs): return Engine()
            def variadic(x: int = 1, /, *args: int, **kwargs): return x
            def bounded(x, y=2): return x
        """,
            "lib/client.py": """
            from .base import Engine as Motor, variadic, bounded, TOKEN, callback
            from . import base
            from .base import *
            import lib.base as module
            import os as external
            from absent import missing
            __all__ = ["run"]
            class Wrapper:
                def __init__(self): self.engine = Motor()
                def use(self):
                    self.engine.run()
                    return self.use
                @classmethod
                def construct(cls, x=0): return cls.use
            class Child(Wrapper):
                def use(self): return super().use()
            class Foreign(Exception):
                def go(self): self.unknown()
            class TestClient: pass
            def test_entry(): pass
            def outer():
                def nested(): return TOKEN
                def inner(): return nested()
                return inner()
            def run(obj, *args, **kwargs):
                global TOKEN
                TOKEN += 1
                x, y = (1, 2)
                for x, y in [(1, 2)]: pass
                with open("ignored") as stream: data = stream.read()
                try: missing()
                except Exception as error: print(error)
                lam = lambda TOKEN: TOKEN
                callback(1)
                variadic(*args, **kwargs)
                bounded(1, 2, 3)
                bounded(y=TOKEN, x=1)
                module.variadic(1)
                base.Engine.create()
                module.callback(1)
                module.missing()
                external.path.exists("x")
                Motor.create()
                Motor.missing()
                e = Motor()
                e.run()
                obj.create()
                obj.unknown()
                Motor().run()
                return [nested for nested in args]
            def shadow(bounded): return bounded()
        """,
        },
    )
    calls = edges(graph)
    assert ("run", "bounded", "heuristic") in calls
    assert ("run", "bounded", "exact") in calls
    assert ("run", "variadic", "exact") in calls
    assert ("Wrapper.use", "Engine.run", "exact") in calls
    assert ("Child.use", "Wrapper.use", "exact") in calls
    assert ("outer.inner", "outer.nested", "exact") in calls
    assert not any(src == "shadow" for src, _, _ in calls)
    assert ("Wrapper.use", "Wrapper.use", "exact") in edges(graph, "refs")
    assert graph.stats["call_external"] > 0 and graph.stats["call_unresolved"] > 0
    assert graph.symbols["lib/client.py::test_entry/0"].entry_reason == "test"
    assert graph.symbols["lib/client.py::__all__"].entry_reason == "dunder"


def test_java_nested_types_imports_fields_varargs_and_references(tmp_path):
    graph = build_sources(
        tmp_path,
        {
            "p/Support.java": """
            package p;
            public class Support {
                public static int FLAG = 1;
                public static void log(String... values) {}
                public static class Nested { public void ping() {} }
                public void work() {}
            }
        """,
            "p/Types.java": """
            package p;
            interface Root { void act(); }
            interface Extended extends Root { int VALUE = 1; class Inner {} }
            enum Mode {
                FAST(1) { public void act() {} }, SLOW(2);
                Mode(int code) {}
                public void act() {}
            }
            record Pair(int x, String name) { Pair { } }
            abstract class Parent {
                protected Support support = new Support();
                protected int count = 1;
                public void inherited() {}
                static class Member { void ping() {} }
            }
        """,
            "p/Client.java": """
            package p;
            import p.Support;
            import p.Support.Nested;
            import static p.Support.FLAG;
            import static p.Support.log;
            import java.util.List;
            class Client extends Parent implements Extended {
                private static final long serialVersionUID = 1;
                Client() { this(1); }
                Client(int n) { super(); }
                @Override public void act() { super.inherited(); }
                @Test public void testCase() {}
                public void use(List<Support> values, Support[] array) {
                    var local = new Support();
                    local.work();
                    this.support.work();
                    support.work();
                    this.count = FLAG;
                    this.count += 1;
                    int x = super.count;
                    x += local.FLAG;
                    x += Support.FLAG;
                    log("one", "two");
                    Nested n = new Nested();
                    n.ping();
                    Member m = new Member();
                    m.ping();
                    p.Support.log();
                    System.out.println("external");
                    for (Support item : values) { item.work(); }
                    Runnable one = this::inherited;
                    Runnable two = super::inherited;
                    java.util.function.Supplier<Support> ctor = Support::new;
                    java.util.function.Function<Integer, Integer> f = count -> count;
                    try { throw new RuntimeException(); } catch (RuntimeException err) { err.printStackTrace(); }
                    new Root() { public void act() {} };
                }
            }
            class Utility { private Utility() {} }
        """,
            "p/Wildcard.java": """
            package q;
            import p.*;
            import static p.Support.*;
            class Wildcard {
                void go() {
                    log();
                    Support s = new Support();
                    s.work();
                    Support.Nested n = new Support.Nested();
                    n.ping();
                }
            }
        """,
        },
    )
    calls = edges(graph)
    assert ("Client.use", "Support.work", "exact") in calls
    assert ("Client.use", "Support.log", "exact") in calls
    assert ("Wildcard.go", "Support.log", "exact") in calls
    assert ("Wildcard.go", "Support.Nested.ping", "exact") in calls
    assert ("Client.act", "Parent.inherited", "exact") in calls
    refs = edges(graph, "refs")
    assert ("Client.use", "Support.FLAG", "exact") in refs
    assert ("Client.use", "Parent.count", "exact") in refs
    assert ("Client.use", "Parent.inherited", "exact") in refs
    assert graph.symbols["p/Client.java::Client.serialVersionUID"].entry_reason == "serial"
    assert graph.symbols["p/Client.java::Utility.<init>/0"].entry_reason == "init-private"
    assert graph.symbols["p/Client.java::Client.testCase/0"].entry_reason == "test"
    assert graph.symbols["p/Types.java::Mode.FAST"].kind == "field"
    assert graph.symbols["p/Types.java::Pair"].kind == "record"
    assert any(
        "$anon" in s.qualname and s.entry_reason == "override" for s in graph.symbols.values()
    )


def test_unknown_dynamic_dispatch_is_not_an_exact_edge(tmp_path):
    graph = build_sources(
        tmp_path,
        {
            "dispatch.py": """
            class A:
                def common(self): pass
                def unique(self): pass
            class B:
                def common(self): pass
            def route(obj):
                obj.common()
                obj.unique()
                obj.missing()
        """,
        },
    )
    calls = edges(graph)
    assert calls == {("route", "A.unique", "heuristic")}
    assert graph.stats["call_ambiguous"] == 1
    assert graph.stats["call_unresolved"] == 1


def test_bulk_load_keeps_quoted_fields_after_many_plain_rows(tmp_path):
    """The database must not sniff the CSV dialect from early rows: a symbol with two
    decorators (a quoted, comma-joined field) late in the file broke indexing of real repos."""
    from codegraph.indexer import index
    from codegraph.service import GraphService

    plain = "".join(f"def f{i}():\n    pass\n" for i in range(1500))
    late = "@first\n@second(1)\ndef decorated():\n    pass\n"
    (tmp_path / "a.py").write_text(plain + late)
    db = tmp_path / "g.lbug"
    index(str(tmp_path), str(db))
    with GraphService(str(db)) as graph:
        rows = graph.conn.execute(
            "MATCH (s:Symbol {name: 'decorated'}) RETURN s.annotations"
        ).get_all()
    assert rows == [["first,second"]]


def test_untyped_local_shadows_outer_variable_and_field_types(tmp_path):
    """A parameter is a different variable from the module-level or `self.` name it shadows,
    so the outer name's constructed type must not produce an exact edge."""
    graph = build_sources(
        tmp_path,
        {
            "shadow.py": """
            class Foo:
                def run(self): return 1
            class Bar:
                def run(self): return 2
            x = Foo()
            def param(x):
                x.run()
            def uses_global():
                x.run()
            def closure():
                y = Foo()
                def inner(): return y.run()
                def rebinds(y): return y.run()
                return inner, rebinds
            class Holder:
                def __init__(self): self.x = Foo()
                def go(self, x): x.run()
        """,
            "shadow.ts": """
            class Foo { run(): number { return 1; } }
            class Bar { run(): number { return 2; } }
            export class Holder {
              x = new Foo();
              go(x: any): number { return x.run(); }
              typed(x: Bar): number { return x.run(); }
            }
        """,
        },
    )
    calls = edges(graph)
    assert ("uses_global", "Foo.run", "exact") in calls
    assert ("closure.inner", "Foo.run", "exact") in calls
    assert ("Holder.typed", "Bar.run", "exact") in calls
    for caller in ("param", "closure.rebinds", "Holder.go"):
        assert not any(src == caller for src, _, _ in calls), caller


def test_inherited_field_type_resolves_in_the_declaring_file(tmp_path):
    """A field's type name is written against the imports of the class that declares it,
    not those of the subclass that uses the field."""
    graph = build_sources(
        tmp_path,
        {
            "helpers.py": """
            class Helper:
                def run(self): return 1
        """,
            "base.py": """
            from helpers import Helper
            class Base:
                def __init__(self): self.helper = Helper()
        """,
            "child.py": """
            from base import Base
            class Helper:
                def run(self): return 2
            class Child(Base):
                def go(self): return self.helper.run()
        """,
            "b/Helper.java": """
            package b;
            public class Helper {
                public int count;
                public void run() {}
            }
        """,
            "a/Base.java": """
            package a;
            import b.Helper;
            public class Base { protected Helper helper = new Helper(); }
        """,
            "c/Child.java": """
            package c;
            import a.Base;
            public class Child extends Base {
                void viaName() { helper.run(); }
                void viaThis() { this.helper.run(); }
                int viaField() { return helper.count; }
                Runnable viaReference() { return helper::run; }
            }
        """,
        },
    )
    calls = {(e.src, e.dst, e.confidence) for e in graph.calls}
    refs = {(e.src, e.dst, e.confidence) for e in graph.refs}
    assert ("child.py::Child.go/0", "helpers.py::Helper.run/0", "exact") in calls
    assert not any(dst == "child.py::Helper.run/0" for _, dst, _ in calls)
    run = "b/Helper.java::Helper.run/0"
    assert ("c/Child.java::Child.viaName/0", run, "exact") in calls
    assert ("c/Child.java::Child.viaThis/0", run, "exact") in calls
    assert ("c/Child.java::Child.viaField/0", "b/Helper.java::Helper.count", "exact") in refs
    assert ("c/Child.java::Child.viaReference/0", run, "exact") in refs


def test_python_parameter_defaults_and_annotations_are_references(tmp_path):
    """`def run(cb=helper)` uses helper: a bare-name default is a value reference made in
    the enclosing scope, and a parameter name itself is never one."""
    graph = build_sources(
        tmp_path,
        {
            "defaults.py": """
            def helper(): return 1
            LIMIT = 3
            args = ()
            class Kind: pass
            def run(cb=helper, n: int = LIMIT, *args: Kind, **kwargs):
                return cb()
        """,
        },
    )
    refs = edges(graph, "refs")
    assert ("<module>", "helper", "exact") in refs
    assert ("<module>", "LIMIT", "exact") in refs
    assert ("<module>", "Kind", "exact") in refs
    assert not any(dst == "args" for _, dst, _ in refs)


def test_python_lambda_parameters_shadow_calls_and_receivers(tmp_path):
    """A lambda parameter hides the module-level function or typed variable of the same
    name when it is called or used as a receiver, just as it does when it is read."""
    graph = build_sources(
        tmp_path,
        {
            "lam.py": """
            class Foo:
                def run(self): return 1
            class Bar:
                def run(self): return 2
            def make(value): return value
            shape = Foo()
            def calls_parameter(items):
                return map(lambda make: make(2), items)
            def receiver_parameter(items):
                return map(lambda shape: shape.run(), items)
            def unshadowed(items):
                return map(lambda item: (make(item), shape.run()), items)
        """,
        },
    )
    calls = edges(graph)
    assert ("unshadowed", "make", "exact") in calls
    assert ("unshadowed", "Foo.run", "exact") in calls
    assert not any(src in ("calls_parameter", "receiver_parameter") for src, _, _ in calls)
    refs = edges(graph, "refs")
    assert ("unshadowed", "shape", "exact") in refs
    assert not any(src == "receiver_parameter" for src, _, _ in refs)


def test_python_self_attribute_reads_are_references_in_any_position(tmp_path):
    """Reading `self.name` uses the method or property `name` wherever the read appears;
    assigning to `self.name` does not."""
    graph = build_sources(
        tmp_path,
        {
            "reads.py": """
            class Shape:
                @property
                def area(self): return 1
                @property
                def label(self): return "s"
                def handler(self): return 2
                def listed(self): return 3
                def replaced(self): return 4
                def swapped(self): return 5
                def use(self):
                    callback = self.handler
                    total = self.area * 2
                    if self.area > 1:
                        total += 1
                    self.replaced = None
                    self.swapped, other = None, total
                    return [self.listed], callback, self.label.upper()
        """,
        },
    )
    refs = edges(graph, "refs")
    for name in ("handler", "area", "listed", "label"):
        assert ("Shape.use", f"Shape.{name}", "exact") in refs, name
    assert not any(dst in ("Shape.replaced", "Shape.swapped") for _, dst, _ in refs)


def test_ts_function_declared_in_a_callback_is_callable(tmp_path):
    """A named function declared inside a callback of a function is that function's
    nested symbol; the callback must not hide it from its own call sites."""
    graph = build_sources(
        tmp_path,
        {
            "nested.ts": """
            export function outer(items: number[], apply: (n: number) => number): void {
              items.forEach((item) => {
                const helper = (n: number) => n + 1;
                function other(n: number) { return n; }
                helper(item);
                other(item);
                items.map(other);
                apply(item);
              });
            }
        """,
            "nested.js": """
            export function wrap(items) {
              items.forEach(function (item) {
                const local = () => item;
                local();
              });
            }
        """,
        },
    )
    calls = edges(graph)
    assert ("outer", "outer.helper", "exact") in calls
    assert ("outer", "outer.other", "exact") in calls
    assert ("wrap", "wrap.local", "exact") in calls
    assert ("outer", "outer.other", "exact") in edges(graph, "refs")
    assert {dst for src, dst, _ in calls if src == "outer"} == {"outer.helper", "outer.other"}


def test_java_record_compact_constructor_takes_the_record_components(tmp_path):
    """`Pair { ... }` is the canonical constructor: its arity is the component count."""
    graph = build_sources(
        tmp_path,
        {
            "p/Pair.java": """
            package p;
            record Pair(int x, String name) {
                Pair { if (x < 0) throw new IllegalArgumentException(name); }
                static Pair of() { return new Pair(1, "a"); }
            }
        """,
        },
    )
    ctor = graph.symbols["p/Pair.java::Pair.<init>/2"]
    assert (ctor.kind, ctor.arity_min, ctor.arity_max) == ("constructor", 2, 2)
    calls = {(e.src, e.dst, e.confidence, e.reason) for e in graph.calls}
    assert ("p/Pair.java::Pair.of/0", ctor.id, "exact", "new") in calls
    assert ("p/Pair.java::Pair.of/0", "p/Pair.java::Pair", "exact", "new") in calls
