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
