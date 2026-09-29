# Offline retrieval evaluation, schema 1

Run `codegraph eval` from the checkout root. Optional flags are `--questions`,
`--fixtures`, `--output`, and `--k` (default 5). The suite ships as a CLI module;
fixture data and labels live in the source checkout, not the installed wheel.
All fixture repositories were written for this project. No external harness is
required. Expected answers are never passed into either retriever.

`questions.jsonl` has one object per line: `schema_version`, unique `id`, `repo`
(a directory directly under the fixtures root), `kind`, `arguments`, `expected`,
and `difficulty` (`easy`, `medium`, `hard`). Arguments match `GraphService.query`:
`target`, `in_file`, `scope`, `depth` (1..10), `ancestors`, `kinds`, `confidence`.
An omitted `depth` means 1, the `GraphService.query` default.
Every expected answer has `symbol`, `file`, `line`. The loader checks schema,
paths, citation ranges and duplicates; the runner verifies IDs against the
parsed declaration inventory. Those checks do not establish semantic truth.

## Label policy

Labels were authored from source before the first retrieval run, using the
existing symbol-ID and citation conventions. Reading the declaration inventory
was used to verify IDs, including annotation-start lines and overload suffixes;
retriever output was not used to generate expected answers.

- `find`: intended name matches; qualified names/IDs disambiguate. Bare names
  should include same-named methods and functions. The existing resolver's
  preference for exact qualified names fails `find-007`; that behavior remains
  measured rather than relabelled as success.
- `callers`: direct call and non-call value-reference sites, unless an explicit
  depth requests reverse traversal. IDs identify the enclosing caller.
- `inherits`: descendants or ancestors up to the specified depth. Evidence is
  the declaration of the child that states the relationship, including for
  ancestor queries; the returned ID can therefore belong to another file.
- `blast`: reverse calls, references and inheritance, up to the specified
  depth. IDs identify impacted symbols, citations their use sites.
- `dead-code`: candidates with no uses in the fixture after accounting for the
  fixture's intended dispatch and overload selection. This is not a global
  reachability analysis. Selected questions scope to functions, variables,
  methods or fields, with explicit candidate filters.

The workflow fixture is a small order/receipt pipeline in Python, plus a Java
processor hierarchy. In its closed fixture context `dispatch` receives a
`MailSink`; `Runner.execute` receives a `CardProcessor`. Those runtime targets
are gold even though graph resolution misses them. `convert(3)` selects the
integer overload; the String overload is unused. The graph's arity-only
fan-out causes both a false caller and a missed unused candidate. Decoys in
comments, strings and unrelated classes are intentional retrieval negatives.

`mini` keeps its original files/line numbers; `decoys.py` extends it. The set
has 12 callers, 8 inheritance, 8 dead-code, 10 blast and 12 find questions.
The 50 questions are curated coverage examples, not a random sample of developer
questions; multiple questions reuse the same relationships. Difficulty is a
human tag, not a measured score.

## Scoring and baseline

Each question is scored independently; overall and per-kind scores are macro
averages. Retrieval precision/recall/F1 compare unique symbol IDs. Repeated
sites for the same symbol do not inflate these metrics. MRR is the reciprocal
rank of the first relevant distinct ID; hit@k is whether any relevant ID occurs
among the first k. Returned order is deterministic, not a semantic ranking.

Citation accuracy is the fraction of distinct returned `(symbol, file, line)`
tuples that occur in gold. It measures correctness of returned evidence, not
citation completeness. The JSON preserves all rows so missing sites can be
inspected. Neither a correct ID at the wrong line nor a decoy ID at a correct
line earns citation credit.

With no predictions: precision and citation accuracy are 1 only if gold is
also empty, otherwise 0. Empty gold has recall 1; F1 is the harmonic mean.
Empty-gold questions do not contribute to MRR/hit@k (JSON `null`). Thus a
correct empty answer earns full set/evidence credit without inventing a rank.

Confidence breakdowns keep only the predictions carrying one tag. Precision,
F1 and citation accuracy for a tag are averaged over the questions where that
tag produced at least one prediction; the report shows that count as `Q`.
Recall, MRR and hit@k are averaged over all questions with non-empty gold, so
a tag's recall is the share of gold symbols it covers. It is not conditional
recall within a labelled confidence stratum. `exact` and `heuristic` are graph
evidence tags. `likely` and `possible` additionally select unused candidates,
so these rows overlap. Text results use the tag `text`.

The lexical baseline shares only declaration IDs/spans/names/kinds/visibility
for output normalization; it never reads graph relationships or labels. It
matches whole words, maps each hit to the narrowest enclosing declaration,
skips imports and declaration lines for callers/blast, matches direct class
headers for inheritance, and treats declarations with no other word occurrences
as unused. Find matches simple declaration names. It honors scope, in-file
find filters, kind and dead-code confidence; it does not resolve overload IDs,
imports, runtime types or transitive depth. Comments and strings count as hits.
It is a deliberately simple grep-style comparison, not a tuned search engine.

## Reproduction and changes

Reports record the exact command, package version, question SHA-256, each fixture
file's SHA-256, every prediction and per-question scores. Temporary databases
are deleted after each run; checked-in sources are not modified. There are no
timing or scale claims. Reports omit timestamps and absolute temporary paths
so an unchanged run produces identical artifacts.

When changing a fixture, review labels against source rather than copying new
retriever output. Change the schema version for semantic/scoring contract
changes, document label corrections, regenerate both reports and the README
table, and include any lower scores. The old external-harness adapter was
removed in 1.0.0; its historical scores are not comparable to this dataset.
