# CLI adapter boundary

`cli.main:app` is the sole command root. It owns global `--project` and
`--json`, parser error presentation, and registration. Project discovery uses
`ProjectService.nearest_project`, whose root marker is
`deykit.project.json`. `CliState.source()` gives each command a bounded
`FileProjectSource` lifetime. Commands call application services directly;
they do not call HTTP or a browser. `SystemClock` and generated operation IDs
are supplied at this boundary.

Project/decision/dataset/case/label command modules adapt typed service
results. Their input files and stdin are decoded as UTF-8; user JSON stays
source text and passes the contracts codec. The JSON output adapter only
serializes service DTOs and source strings. It never builds user input or
provider request bytes from Pydantic's Decimal JSON serializer. Parser and
service failures produce one safe error envelope in JSON mode. Unexpected
failures produce `internal_error` without an exception or source body.

`cli.commands` is an in-package extension point for later service owners.
Each public module exports `register(root: typer.Typer) -> None`; the root
loads them in sorted name order. Modules with leading underscores are not
loaded. Registration is synchronous and failures are visible, so a missing
command cannot silently masquerade as implemented. A feature module owns only
its group or top-level command, imports no transport/network module merely to
register it, and uses `CliState`, `execute` or `execute_outcome` for the common
result contract. `CommandOutcome` applies the run/check exit code after emitting
the result. The [command matrix](cli-command-matrix.json) tracks the full
planned surface and the commands actually registered; its implemented entries
are checked against `--help` in the offline suite.

The tested runtime is locked Typer 0.27.2. It bundles its own command parser,
so the CLI imports public Typer context/testing APIs without a separate Click
dependency. Global options and parent context follow the official
[Typer context](https://typer.tiangolo.com/tutorial/commands/context/),
[callback](https://typer.tiangolo.com/tutorial/options/callback-and-context/),
and [testing](https://typer.tiangolo.com/tutorial/testing/) guidance. The
explicit `--editor` path uses a temporary UTF-8 file and terminal-bound
subprocess argv, with no shell evaluation; no editor starts during ordinary
noninteractive use.

P07 automated checks use the installed `deykit` entrypoint through subprocess
and `CliRunner`. They cover project discovery in a Unicode/space path,
help/JSON errors, source precision, save replay/conflict, import atomicity,
reviewed label transitions/batch, and grouped split behavior. These checks
establish local software behavior, not manual UI, other-platform, or live
provider evidence.
