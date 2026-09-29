# Retrieval evaluation

Command: `codegraph eval`

codegraph 1.0.0; question schema 1; 50 questions; k=5.

Questions SHA-256: `4a27330ebf72d3c336b182e61874a0ea3d8dcce94b8ab51e5cc04aaf68c9c987`

Metrics are macro averages over questions. Ranking excludes empty-gold questions.
Citation accuracy is the share of distinct returned (symbol id, file, line) tuples
that match a labelled tuple.

| Kind | Retriever | P | R | F1 | MRR | hit@k | Citation accuracy |
|---|---|---:|---:|---:|---:|---:|---:|
| overall | graph | 0.9200 | 0.9200 | 0.9067 | 0.9362 | 0.9362 | 0.9200 |
| overall | text | 0.7867 | 0.9067 | 0.7967 | 0.8546 | 1.0000 | 0.7933 |
| blast | graph | 0.9000 | 0.9000 | 0.9000 | 0.8889 | 0.8889 | 0.9000 |
| blast | text | 0.6667 | 0.8333 | 0.7200 | 0.7222 | 1.0000 | 0.6833 |
| callers | graph | 0.7500 | 0.8333 | 0.7500 | 0.8182 | 0.8182 | 0.7500 |
| callers | text | 0.5139 | 1.0000 | 0.6361 | 0.6970 | 1.0000 | 0.5278 |
| dead-code | graph | 1.0000 | 0.9375 | 0.9583 | 1.0000 | 1.0000 | 1.0000 |
| dead-code | text | 1.0000 | 0.8750 | 0.9167 | 1.0000 | 1.0000 | 1.0000 |
| find | graph | 1.0000 | 0.9583 | 0.9722 | 1.0000 | 1.0000 | 1.0000 |
| find | text | 0.8750 | 1.0000 | 0.9167 | 0.9091 | 1.0000 | 0.8750 |
| inherits | graph | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| inherits | text | 1.0000 | 0.7500 | 0.8333 | 1.0000 | 1.0000 | 1.0000 |

## Confidence breakdown

Each row keeps only the predictions carrying that tag. P, F1 and citation accuracy
average over the questions where the tag produced at least one prediction (column Q).
R, MRR and hit@k average over all questions with non-empty gold, so R is the share
of gold symbols the tag covers. Tags are not ground-truth labels. `likely`/`possible`
additionally filter dead-code candidates, so rows overlap.

| Retriever / tag | Q | P | R | F1 | MRR | hit@k | Citation accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| graph/exact | 44 | 1.0000 | 0.9149 | 0.9848 | 0.9362 | 0.9362 | 1.0000 |
| graph/heuristic | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| graph/likely | 6 | 1.0000 | 0.1170 | 0.9444 | 0.1277 | 0.1277 | 1.0000 |
| graph/possible | 2 | 1.0000 | 0.0426 | 1.0000 | 0.0426 | 0.0426 | 1.0000 |
| text/text | 48 | 0.7778 | 0.9007 | 0.7882 | 0.8546 | 1.0000 | 0.7847 |

## Cases with graph errors

- `blast-009`: F1 0.0000, citation accuracy 0.0000.
- `callers-010`: F1 0.0000, citation accuracy 0.0000.
- `callers-011`: F1 0.0000, citation accuracy 0.0000.
- `callers-012`: F1 0.0000, citation accuracy 0.0000.
- `dead-code-007`: F1 0.6667, citation accuracy 1.0000.
- `find-007`: F1 0.6667, citation accuracy 1.0000.

See ../README.md for label policy, baseline details, empty-set conventions and limits.
