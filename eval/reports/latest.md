# Retrieval evaluation

Command: `codegraph eval`

codegraph 1.1.0; question schema 1; 74 questions; k=5.

Questions SHA-256: `df674dc628ea02c4a73ca4838828bc9ab08bacbad180c403cd98d4f262779d03`

Metrics are macro averages over questions. Ranking excludes empty-gold questions.
Citation accuracy is the share of distinct returned (symbol id, file, line) tuples
that match a labelled tuple.

| Kind | Retriever | P | R | F1 | MRR | hit@k | Citation accuracy |
|---|---|---:|---:|---:|---:|---:|---:|
| overall | graph | 0.9054 | 0.8959 | 0.8904 | 0.9155 | 0.9155 | 0.9054 |
| overall | text | 0.7658 | 0.8507 | 0.7588 | 0.8333 | 0.9577 | 0.7703 |
| blast | graph | 0.8571 | 0.8429 | 0.8492 | 0.8462 | 0.8462 | 0.8571 |
| blast | text | 0.6548 | 0.7405 | 0.6537 | 0.7308 | 1.0000 | 0.6667 |
| callers | graph | 0.7222 | 0.7778 | 0.7222 | 0.7647 | 0.7647 | 0.7222 |
| callers | text | 0.5370 | 0.9444 | 0.6444 | 0.7157 | 0.9412 | 0.5463 |
| dead-code | graph | 1.0000 | 0.9615 | 0.9744 | 1.0000 | 1.0000 | 1.0000 |
| dead-code | text | 0.8462 | 0.7692 | 0.7949 | 0.8462 | 0.8462 | 0.8462 |
| find | graph | 1.0000 | 0.9412 | 0.9608 | 1.0000 | 1.0000 | 1.0000 |
| find | text | 0.8725 | 1.0000 | 0.9118 | 0.9062 | 1.0000 | 0.8725 |
| inherits | graph | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| inherits | text | 1.0000 | 0.7153 | 0.7972 | 1.0000 | 1.0000 | 1.0000 |

## By language

Language of the code under test, as labelled per question. Same macro averages.

| Language | Retriever | Q | P | R | F1 | MRR | hit@k | Citation accuracy |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| python | graph | 32 | 0.9375 | 0.9219 | 0.9271 | 0.9333 | 0.9333 | 0.9375 |
| python | text | 32 | 0.7917 | 0.9167 | 0.8187 | 0.8444 | 1.0000 | 0.8021 |
| java | graph | 18 | 0.8889 | 0.9167 | 0.8704 | 0.9412 | 0.9412 | 0.8889 |
| java | text | 18 | 0.7778 | 0.8889 | 0.7574 | 0.8725 | 1.0000 | 0.7778 |
| typescript | graph | 12 | 0.9167 | 0.8583 | 0.8796 | 0.9167 | 0.9167 | 0.9167 |
| typescript | text | 12 | 0.6389 | 0.6486 | 0.5710 | 0.6667 | 0.8333 | 0.6389 |
| javascript | graph | 12 | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| javascript | text | 12 | 0.8056 | 0.8194 | 0.7889 | 0.9167 | 0.9167 | 0.8056 |

## Confidence breakdown

Each row keeps only the predictions carrying that tag. P, F1 and citation accuracy
average over the questions where the tag produced at least one prediction (column Q).
R, MRR and hit@k average over all questions with non-empty gold, so R is the share
of gold symbols the tag covers. Tags are not ground-truth labels. `likely`/`possible`
additionally filter dead-code candidates, so rows overlap.

| Retriever / tag | Q | P | R | F1 | MRR | hit@k | Citation accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| graph/exact | 65 | 1.0000 | 0.8915 | 0.9829 | 0.9155 | 0.9155 | 1.0000 |
| graph/heuristic | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| graph/likely | 10 | 1.0000 | 0.1197 | 0.9000 | 0.1408 | 0.1408 | 1.0000 |
| graph/possible | 5 | 1.0000 | 0.0563 | 0.8667 | 0.0704 | 0.0704 | 1.0000 |
| text/text | 70 | 0.7810 | 0.8444 | 0.7736 | 0.8333 | 0.9577 | 0.7857 |

## Cases with graph errors

- `blast-009`: F1 0.0000, citation accuracy 0.0000.
- `blast-012`: F1 0.8889, citation accuracy 1.0000.
- `blast-014`: F1 0.0000, citation accuracy 0.0000.
- `callers-010`: F1 0.0000, citation accuracy 0.0000.
- `callers-011`: F1 0.0000, citation accuracy 0.0000.
- `callers-012`: F1 0.0000, citation accuracy 0.0000.
- `callers-016`: F1 0.0000, citation accuracy 0.0000.
- `callers-017`: F1 0.0000, citation accuracy 0.0000.
- `dead-code-007`: F1 0.6667, citation accuracy 1.0000.
- `find-007`: F1 0.6667, citation accuracy 1.0000.
- `find-014`: F1 0.6667, citation accuracy 1.0000.

See ../README.md for label policy, baseline details, empty-set conventions and limits.
