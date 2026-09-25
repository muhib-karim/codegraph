# codegraph v0.1 - design

codegraph turns a source repo into a code graph stored in an embedded graph
database (LadybugDB), then answers four questions with exact graph lookups and
a `file:line` citation on every answer. There is no LLM anywhere in the answer
path. This document was written before the code, from first principles, and is
the spec the implementation follows.

## 1. Pipeline

```
repo files -> [0 discover] -> [1 definitions] -> [2 references] -> [3 load] -> graph.lbug
                                                                     |
                                   callers / inherits / dead-code / blast (Cypher)
```

0. **Discover.** Walk the repo (skip `.git`, `node_modules`, `build`, `.codegraph`,
   venvs). Every file becomes a `File` node with a language tag. Only Python
   (`.py`) and Java (`.java`) are parsed at v0.1; every other file is recorded
   with `parsed=false` so coverage gaps are visible, never hidden.
1. **Pass 1 - definitions.** Parse each file with Tree-sitter and record, per file:
   module/package, imports, classes (incl. nested, interfaces, enums, records,
   Java anonymous classes), functions, methods, constructors, each with name,
   qualified name, line span, arity (min/max; varargs = open max), visibility,
   static flag and decorators/annotations. Also recorded, but not yet resolved:
   base-class names, call sites (callee name, receiver shape, argument count,
   splat flag), non-call references to names, and simple type facts
   (Java declared types of params/locals/fields; Python `x = Cls(...)` and
   `self.x = Cls(...)`).
2. **Pass 2 - resolution.** With the whole repo's definitions indexed, resolve
   bases first (so inherited-method lookup works), then every call site and
   reference, by **name + arity + import/scope context**. Each resolved edge
   gets a confidence tag:
   - `exact` - the target is bound by language scoping: same scope/enclosing
     scope, same file, explicit import, `self`/`this`/`super`/`cls`, a receiver
     whose declared or constructed type is a repo class, or `Type.m()` static
     access. Arity must be compatible (Java: equal, or >= n-1 for varargs;
     Python: min <= args <= max, open when `*args`/`**kwargs` or splat at site).
   - `heuristic` - receiver type unknown and exactly one repo method of that
     name with compatible arity exists in the same language; or an
     exact-scope bind whose arity does not match; or several same-arity Java
     overloads (one edge to each). The `reason` field says which.
   - Calls into the standard library / third-party code (receiver or name bound
     to an import that is not a repo file, or a receiver typed as a non-repo
     class) are **not** edges; they are counted in stats as `external`.
   - A call with an unknown receiver and zero or 2+ name candidates is dropped
     and counted as `unresolved` / `ambiguous`. No guessing beyond this.
3. **Load.** Write nodes/edges to CSV and bulk `COPY` into LadybugDB at
   `<repo>/.codegraph/graph.lbug` (or `--db`). Re-indexing rebuilds from scratch.

Callers are always a symbol: the enclosing function/method; module-level
Python code uses a per-file `module` pseudo-symbol; Java field initialisers and
static blocks use the class symbol.

## 2. Graph schema (LadybugDB DDL)

```
NODE File(path STRING PK, lang STRING, loc INT64, parsed BOOLEAN, package STRING)
NODE Symbol(id STRING PK, name STRING, qualname STRING, kind STRING, lang STRING,
            file STRING, line INT64, end_line INT64, arity_min INT64, arity_max INT64,
            visibility STRING, is_static BOOLEAN, annotations STRING,
            parent_id STRING, entry_reason STRING)
NODE Meta(key STRING PK, value STRING)
REL DEFINES   (File -> Symbol)
REL CONTAINS  (Symbol -> Symbol)                  parent class/function -> member
REL CALLS     (Symbol -> Symbol, file STRING, line INT64, col INT64, confidence STRING, reason STRING)
REL REFERENCES(Symbol -> Symbol, file STRING, line INT64, col INT64, confidence STRING, reason STRING)
                                                  non-call uses: reads of fields/variables, functions
                                                  passed as values, Java method references
REL INHERITS  (Symbol -> Symbol, file STRING, line INT64, kind STRING, confidence STRING)   child -> parent
REL IMPORTS   (File -> File, line INT64, name STRING, confidence STRING)
```

- `Symbol.kind`: `module | class | interface | enum | record | function | method |
  constructor | field | variable | external`. `field` = Java field or enum
  constant; `variable` = Python module-level name (first binding). `external` = a base class outside the repo
  (e.g. `Exception`); id `external::<name>`, file `''`, line 0.
- `Symbol.id`: `<path>::<qualname>`; `/<arity_min>` appended for functions,
  methods and constructors; `@<line>` appended on any remaining collision.
  Constructors: qualname `Class.<init>`. Java anonymous classes:
  `Outer.method.$anon@<line>`. Module pseudo-symbol: `<path>::<module>`.
- `arity_max = -1` means unbounded. Python methods exclude `self`/`cls`.
- `visibility`: `public | protected | package | private` (Python: `private` if
  the name starts with `_` and is not a dunder, else `public`).
- `entry_reason` (non-empty = entry point, never dead): `main`, `dunder`,
  `override`, `test`, `init-private` (private no-arg Java constructor idiom),
  `abstract`, `script` (Python `if __name__ == "__main__"` module).
- Paths are repo-relative POSIX; lines are 1-based.
- Empty strings load as NULL in LadybugDB (`entry_reason`, `parent_id`,
  `package`, `annotations`, `reason`): compare with `coalesce(x, '') = ''`.
- CALLS/REFERENCES `file`,`line`,`col` = the call/use site (col 0-based).
  INHERITS `line` = line of the base-type expression.
- Python constructor calls `Cls(...)` produce two CALLS edges at the same site:
  to the class and to its `__init__` (if any). Java `new T(...)` targets the
  arity-matching constructor(s) plus the class; implicit constructors = class only.

## 3. Query commands (v0.1)

All four accept `--db PATH`, `--repo DIR`, `--json` (`--compact` for one line)
and `--scope PREFIX` (filter results by path). `callers`/`inherits`/`blast`
accept `--in FILE` to pick the definition in one file. `dead-code` accepts
`--kind a,b` and `--confidence likely|possible|all`. Symbol arguments accept
`path::qualname`, a qualified name (`Class.method`) or a bare name; a name that
matches several symbols answers for all matches and lists them in `resolved`.

| command | answers | one citation per result = |
|---|---|---|
| `callers <symbol> [--depth N]` | who calls/references the symbol (N=1 default, transitive up to N) | the **call site** `file:line` |
| `inherits <class> [--ancestors]` | subclasses/implementors, direct and transitive (or ancestors) | the **class declaration** `file:line` |
| `dead-code [--kind K] [--confidence C]` | symbols with no incoming CALLS/REFERENCES/INHERITS and no entry reason | the **definition** `file:line` |
| `blast <file-or-symbol> [--depth N]` | everything that can break if the target changes: reverse CALLS + REFERENCES + INHERITS, BFS to N (default 3; class targets include their members) | the **use site** `file:line` inside the impacted symbol; `def` = its definition |

dead-code confidence: `likely` (private, or nested function) vs `possible`
(non-private: could be reached from code v0.1 cannot see - other languages,
reflection, frameworks). Default output shows both, sorted likely first.

## 4. Output contract (for harnesses)

Text mode: one result per line, tab-separated, sorted by (file, line, name):
`<file>:<line>\t<qualname>\t<kind>\t<confidence>[\t<depth>\t<via>]`.

JSON mode (`--json`), stable key order, same sort:
```json
{"command": "callers", "query": "Foo.bar", "db": "...", "schema_version": 1,
 "resolved": [{"id": "...", "qualname": "Foo.bar", "kind": "method", "file": "a.py", "line": 10}],
 "results": [{"citation": "b.py:42", "file": "b.py", "line": 42,
              "symbol": "b.py::main", "qualname": "main", "kind": "function",
              "confidence": "exact", "reason": "import", "depth": 1, "via": "b.py:42"}],
 "count": 1}
```
`answers` is the harness-ready projection of `results`: one `{file, line,
symbol}` per distinct `file:line`, same order - an eval adapter can pass it
through unchanged. Per command, `citation` is as in the table above. Result
fields by command: callers/blast add `edge` (call|ref|inherits), `target`
(matched symbol id), `via`, `def`; inherits adds `relation`
(extends|implements) and `parent` / `declared_by`; dead-code adds
`dead_confidence` (likely|possible) and `visibility`. Exit codes:
0 = answered (including zero results), 2 = symbol/class/file not found
(JSON still printed with `"error"`), 1 = usage/DB error.

## 5. Known limits (v0.1, stated not faked)

- Languages: Python and Java only. Kotlin, Shell, Smali and all others are
  File nodes with `parsed=false`; no symbols, no edges.
- No cross-language edges (e.g. Smali/Kotlin patches calling Java extension
  code). Such targets show up as `possible` dead code.
- No reflection / string-based dispatch, no dynamic attribute resolution,
  no dataflow beyond single-assignment constructor typing, no generics
  reasoning, overloads resolved by arity only.
- No string/data-contract coupling (a method name embedded in a string,
  shared dict keys) and no shell-script invocations.
- Heuristic edges are only ever single-candidate name matches (or same-arity
  overload fan-out) and are always tagged.

## 6. Open convention items (must be versioned before gold changes or rescoring)

- **inherits citation line for Smali (open).** The v0.1 contract cites the
  declaring class line for `inherits`. For Python/Java the class header and
  the base-type expression are usually the same line. In Smali they are not:
  `.class` is line 1 and `.super` is line 2. The interim eval gold
  (inherits-002) cites the `.super` line for all six fixture classes. If
  Smali support is added, the proposed convention is that inherits cites the
  base-type expression line (`INHERITS.line`; the graph also stores the class
  line as `Symbol.line`). Decide it explicitly, bump
  `schema_version`/the output contract version, and only then change gold or
  rescore.

## 7. Revision history

- v0 (2026-09-25 14:45 AEST, before the eval harness was received or run):
  verbatim copy in `docs/DESIGN-v0-predeclared-2026-09-25T1445.md`.
- v0.1 (2026-09-25 14:54 AEST, after the first eval run at 14:52): added
  `field`/`variable` symbol kinds and field/variable reads in REFERENCES; blast
  citation changed from definition line to use site; `answers` key and CLI
  flags documented; explicit limit line for string/data-contract coupling and
  shell invocations; NULL/edge notes for query writers.
- 2026-09-25 14:58 AEST: section 6 (open convention items) added.
