# Compare saved evaluations

Use two runs from the same decision and dataset. Comparison sends zero provider
requests and does not change either run, its labels or its saved evaluation.

```sh
uv run deykit --project ./study --json compare RUN_A RUN_B --operation-id comparison-1
uv run deykit --project ./study --json compare RUN_A RUN_B --evaluation-a EVAL_A --evaluation-b EVAL_B --operation-id comparison-2
```

The default freezes an original evaluation of each run's current result
snapshot. The response includes the actual evaluation and result IDs. Use
`--evaluation-a` and `--evaluation-b` to compare older results or an explicit
saved-answer re-evaluation. Pin those returned IDs and the operation ID when
retrying automation; changed evaluation selections using the same operation ID
conflict. Labels edited after a comparison cannot change its saved outcome.

Every case in the union of both selections receives one primary bucket. Quality
counts include only two valid answers with the same full frozen input, stable
question and option IDs, and equivalent applicable expectations. Instructions,
option names and presentation order may differ between revisions. Acceptable
sets compare as sets, so their ordering does not change compatibility.

The quality denominator covers both-correct, improved, regressed and both-wrong
cases. Cases found on only one side, changed inputs or expectations, unavailable
answers and excluded expectations remain separate. Valid unlabelled answers
have their own agreement/disagreement denominator. They establish no accuracy.
Side-specific status and label-exclusion counts can overlap; the primary bucket
counts always sum to the union size.

Fixture comparisons remain authored software-verification evidence. A live
comparison describes only its preserved inputs, results and expectations; it
does not establish quality on a wider population.
