# codegraph

Index a repo into a code graph (Tree-sitter -> LadybugDB), then ask exact
questions. Every answer carries a `file:line` citation. No LLM in the answer path.

```
pip install -e .
codegraph index path/to/repo            # writes path/to/repo/.codegraph/graph.lbug
codegraph callers parse_const_string --repo path/to/repo
codegraph inherits Shape --repo path/to/repo
codegraph dead-code --repo path/to/repo --confidence likely
codegraph blast rename/axml_pool.py --repo path/to/repo --depth 2 --json
```

v0.1 parses Python and Java. Other files are recorded but not parsed (no
Kotlin, Shell or Smali yet), and there are no cross-language edges. See
[DESIGN.md](DESIGN.md) for the pipeline, schema, output contract and limits.

`eval/codegraph_adapter.py` plugs the CLI into the codegraph eval harness.

License: MIT. Clean-room implementation; no third-party code-graph source was
used.
