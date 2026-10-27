"""Preview, run, inspect and resume multi-variant experiments."""

import asyncio
import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from time import sleep
from typing import Annotated

import typer
from pydantic import ValidationError

from deykit.application.dataset_support import fail
from deykit.application.errors import ServiceFailure
from deykit.application.experiment_reports import experiment_report
from deykit.application.experiments import ExperimentProgress, ExperimentService
from deykit.cli.commands.execution import _CANCEL_ACQUISITION_DELAYS_SECONDS, service
from deykit.cli.context import CliState, new_operation_id
from deykit.cli.output import CommandOutcome, _plain, execute, execute_outcome
from deykit.contracts.experiments import ExperimentRequest
from deykit.contracts.json_value import RECORD_LIMITS, JsonLimits, parse_json
from deykit.runner.group_models import GroupAcknowledged
from deykit.storage import FileProjectSource

app = typer.Typer(help="Coordinate frozen classification experiments and shared budgets.")
EXPERIMENT_PREVIEW_LIMITS = JsonLimits(
    max_bytes=64 * 1024 * 1024, max_depth=256, max_nodes=4_000_000
)


def register(root: typer.Typer) -> None:
    root.add_typer(app, name="experiments")


def _request(path: Path) -> ExperimentRequest:
    with path.open("rb") as stream:
        source = stream.read(RECORD_LIMITS.max_bytes + 1)
    parse_json(source, RECORD_LIMITS)
    try:
        return ExperimentRequest.model_validate_json(source)
    except ValidationError:
        fail("invalid_experiment_request")


def _review_hash(path: Path) -> str:
    with path.open("rb") as stream:
        source = stream.read(EXPERIMENT_PREVIEW_LIMITS.max_bytes + 1)
    value = parse_json(source, EXPERIMENT_PREVIEW_LIMITS)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        fail("invalid_preview_file")
    data = value.get("data")
    if not isinstance(data, dict):
        fail("invalid_preview_file")
    group = data.get("group")
    if not isinstance(group, dict) or group.get("kind") != "experiment" or not group.get("dry_run"):
        fail("invalid_preview_file")
    fingerprint = group.get("review_context_hash")
    if not isinstance(fingerprint, str):
        fail("invalid_preview_file")
    return fingerprint


def _require_readable_preview(preview: object) -> None:
    """A successful JSON preview must fit the same bounds used when reviewing it."""
    payload = {"schema_version": 1, "data": _plain(preview), "warnings": []}
    pending: list[object] = [payload]
    nodes = 0
    while pending:
        node = pending.pop()
        nodes += 1
        if nodes > EXPERIMENT_PREVIEW_LIMITS.max_nodes:
            fail("experiment_preview_resource_limit", "preflight_failed")
        if isinstance(node, dict):
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    size = 1  # CLI output includes a newline.
    for chunk in encoder.iterencode(payload):
        size += len(chunk.encode("utf-8"))
        if size > EXPERIMENT_PREVIEW_LIMITS.max_bytes:
            fail("experiment_preview_resource_limit", "preflight_failed")


def _outcome(result: ExperimentProgress) -> CommandOutcome:
    return CommandOutcome(result, result.group.exit_code)


def _created(value: GroupAcknowledged) -> None:
    action = "Replayed" if value.replayed else "Created"
    typer.echo(f"{action} {value.mode} experiment {value.group_id}", err=True)


def _resumed(value: GroupAcknowledged) -> None:
    action = "Replayed" if value.replayed else "Resumed"
    typer.echo(f"{action} experiment {value.group_id} segment {value.segment_id}", err=True)


@contextmanager
def _priority_admission(source: FileProjectSource) -> Iterator[None]:
    """Wait behind other inspections before claiming the source turnstile."""
    delay_index = 0
    while True:
        with ExitStack() as stack:
            try:
                stack.enter_context(source.priority_read())
            except ServiceFailure as error:
                if error.error.code != "conflict" or error.error.reason != "source_busy":
                    raise
                delay = _CANCEL_ACQUISITION_DELAYS_SECONDS[
                    min(delay_index, len(_CANCEL_ACQUISITION_DELAYS_SECONDS) - 1)
                ]
                sleep(delay)
                delay_index += 1
            else:
                yield
                return


@contextmanager
def _priority_epoch(source: FileProjectSource) -> Iterator[None]:
    """Wait for the current source epoch while preventing another from starting."""
    delay_index = 0
    while True:
        with ExitStack() as stack:
            try:
                stack.enter_context(source.consistent_read())
            except ServiceFailure as error:
                if error.error.code != "conflict" or error.error.reason != "source_busy":
                    raise
                delay = _CANCEL_ACQUISITION_DELAYS_SECONDS[
                    min(delay_index, len(_CANCEL_ACQUISITION_DELAYS_SECONDS) - 1)
                ]
                sleep(delay)
                delay_index += 1
            else:
                yield
                return


@app.command("preview")
def preview(ctx: typer.Context, config: Path) -> None:
    """Expand a configuration without dispatching or writing an experiment."""

    def work(cli: CliState) -> object:
        request = _request(config)
        with cli.source() as source:
            result = ExperimentService(service(source)).preview(request)
        _require_readable_preview(result)
        return result

    execute(ctx, work)


@app.command("run")
def run(
    ctx: typer.Context,
    config: Path,
    preview: Annotated[Path, typer.Option("--preview")],
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Run exactly the reviewed configuration and frozen source context."""

    def work(cli: CliState) -> CommandOutcome:
        request = _request(config)
        reviewed_hash = _review_hash(preview)
        with cli.source() as source:
            result = asyncio.run(
                ExperimentService(service(source)).start(
                    request,
                    operation_id=new_operation_id(operation_id),
                    expected_review_context_hash=reviewed_hash,
                    on_created=_created,
                )
            )
            return _outcome(result)

    execute_outcome(ctx, work)


@app.command("show")
def show(ctx: typer.Context, experiment_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            runner = service(source)
            experiment = ExperimentService(runner)
            if runner.execution.execution_active():
                with _priority_admission(source):
                    with _priority_epoch(source):
                        records = source.capture_snapshot()
                return experiment.read_captured(records, experiment_id, active=True)
            return experiment.read(experiment_id)

    execute(ctx, work)


@app.command("report")
def report(
    ctx: typer.Context,
    experiment_id: str,
    snapshot: Annotated[str | None, typer.Option("--snapshot")] = None,
) -> None:
    """Report all members at one immutable group snapshot."""

    def work(cli: CliState) -> object:
        with cli.source() as source:
            with source.consistent_read():
                records = source.capture_snapshot()
        return experiment_report(records, experiment_id, snapshot)

    execute(ctx, work)


@app.command("resume")
def resume(
    ctx: typer.Context,
    experiment_id: str,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    retry_unknown: Annotated[bool, typer.Option("--retry-unknown")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Inspect or explicitly resume pending members without resetting the budget."""

    def work(cli: CliState) -> CommandOutcome:
        with cli.source() as source:
            experiment = ExperimentService(service(source))
            if dry_run:
                return CommandOutcome(
                    {
                        "preview": experiment.preview_resume(
                            experiment_id, retry_unknown=retry_unknown
                        ),
                        "experiment": experiment.read(experiment_id),
                    }
                )
            return _outcome(
                asyncio.run(
                    experiment.resume(
                        experiment_id,
                        retry_unknown=retry_unknown,
                        operation_id=new_operation_id(operation_id),
                        on_resumed=_resumed,
                    )
                )
            )

    execute_outcome(ctx, work)


@app.command("cancel")
def cancel(
    ctx: typer.Context,
    experiment_id: str,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            experiment = ExperimentService(service(source))
            with _priority_admission(source):
                with _priority_epoch(source):
                    pass
                experiment.groups.cancel(
                    experiment_id,
                    operation_id=new_operation_id(operation_id),
                    expected_kind="experiment",
                )
                return experiment.read(experiment_id)

    execute(ctx, work)
