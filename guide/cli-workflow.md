# Run the installed CLI walkthrough

The packaged walkthrough exercises the browser-free decision workflow with six
independently authored cases and fixture responses. It makes no provider requests,
needs no key, and does not access the network. It creates a fresh project under a
new output directory and writes report artifacts beside it. The path may contain
spaces and non-ASCII characters.

Install Deykit, then launch the guide script from any directory:

```sh
python guide/examples/cli-workflow.py --output './walkthrough output'
```

The script uses the installed `deykit` executable. If it is not on `PATH`, pass
`--cli /absolute/path/to/deykit`. The output directory must not already exist.
The completed output contains the portable project, the exact authored resource
bundle, and Markdown/JSON reports. The driver prints a completion object only
after every command and numeric oracle succeeds.
It also writes `progress.jsonl` with command paths, exit codes, safe error codes,
and returned resource IDs, plus `workflow-state.json` after each completed phase.
Neither file stores request/response bodies or command source text.

The cases exercise exact large-integer and decimal request bytes, scoped fixture
bindings, expected-answer review, result inspection, report privacy switches,
zero-call reevaluation, comparisons, a bounded order diagnostic, and frozen
regression checks. Fixture A scores 2/3 on the labelled eligible set; fixture B
scores 3/3. These values describe authored test evidence and are not model
performance or live-provider measurements. Usage and latency are unavailable for
fixture evidence.

If the process stops on an oracle mismatch, keep the output directory. It contains
the real command state up to the reported step, so it can be inspected with
`deykit --project PATH --json project validate` and the relevant `runs`, `results`,
`report`, `diagnose`, or `checks` commands. The driver requires a fresh output path
on each run and does not automatically retry after a failure.
