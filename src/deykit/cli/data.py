"""Dataset, case, and import commands over the application services."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from pydantic import ValidationError

from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.errors import ServiceFailure
from deykit.application.imports import ImportService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.input import source_text
from deykit.cli.output import execute
from deykit.cli.splits import split_dataset
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import parse_json

dataset_app = typer.Typer(help="Create datasets, import rows, and manage splits.")
case_app = typer.Typer(help="Manage individual dataset examples.")
T = TypeVar("T")


def register(root: typer.Typer) -> None:
    dataset_app.command("split")(split_dataset)
    root.add_typer(dataset_app, name="dataset")
    root.add_typer(case_app, name="case")


def _mutate(
    ctx: typer.Context, operation_id: str | None, work: Callable[[CliState, str], T]
) -> None:
    actual = new_operation_id(operation_id)
    execute(ctx, lambda cli: {"operation_id": actual, "result": work(cli, actual)})


def _case_input(text: str) -> CaseInput:
    parse_json(text)
    try:
        return CaseInput.model_validate_json(text)
    except ValidationError:
        raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_case")) from None


@dataset_app.command("list")
def list_datasets(
    ctx: typer.Context,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return DatasetService(source, SystemClock()).list(
                include_archived=include_archived, cursor=cursor, limit=limit
            )

    execute(ctx, work)


@dataset_app.command("show")
def show_dataset(ctx: typer.Context, dataset_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            service = DatasetService(source, SystemClock())
            return {"dataset": service.read(dataset_id), "cases": service.list_cases(dataset_id)}

    execute(ctx, work)


@dataset_app.command("create")
def create_dataset(
    ctx: typer.Context,
    dataset_id: str,
    name: Annotated[str, typer.Option("--name")],
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        metadata = source_text(file=file, stdin=stdin) if file is not None or stdin else "{}"
        with cli.source() as source:
            return DatasetService(source, SystemClock()).create(
                name, dataset_id=dataset_id, metadata_source=metadata, operation_id=op
            )

    _mutate(ctx, operation_id, work)


@dataset_app.command("edit")
def edit_dataset(
    ctx: typer.Context,
    dataset_id: str,
    name: Annotated[str | None, typer.Option("--name")] = None,
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        with cli.source() as source:
            service = DatasetService(source, SystemClock())
            view = service.read(dataset_id)
            metadata = (
                source_text(file=file, stdin=stdin)
                if file is not None or stdin
                else view.record.metadata_source
            )
            return service.update(
                dataset_id,
                name=name if name is not None else view.record.name,
                metadata_source=metadata,
                expected_etag=if_hash if if_hash is not None else view.etag,
                operation_id=op,
            )

    _mutate(ctx, operation_id, work)


def _dataset_state_change(
    ctx: typer.Context,
    dataset_id: str,
    if_hash: str | None,
    operation_id: str | None,
    *,
    restore: bool,
) -> None:
    def work(cli: CliState, op: str) -> object:
        with cli.source() as source:
            service = DatasetService(source, SystemClock())
            expected = if_hash if if_hash is not None else service.read(dataset_id).etag
            if restore:
                return service.restore(dataset_id, expected_etag=expected, operation_id=op)
            return service.archive(dataset_id, expected_etag=expected, operation_id=op)

    _mutate(ctx, operation_id, work)


@dataset_app.command("archive")
def archive_dataset(
    ctx: typer.Context,
    dataset_id: str,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _dataset_state_change(ctx, dataset_id, if_hash, operation_id, restore=False)


@dataset_app.command("restore")
def restore_dataset(
    ctx: typer.Context,
    dataset_id: str,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _dataset_state_change(ctx, dataset_id, if_hash, operation_id, restore=True)


@dataset_app.command("import")
def import_dataset(
    ctx: typer.Context,
    dataset_id: str,
    format: Annotated[str, typer.Option("--format")],
    mapping: Annotated[Path, typer.Option("--mapping")],
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    decision: Annotated[str | None, typer.Option("--decision")] = None,
    revision: Annotated[str | None, typer.Option("--revision")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    skip_invalid: Annotated[bool, typer.Option("--skip-invalid")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        text = source_text(file=file, stdin=stdin)
        mapping_text = mapping.read_text(encoding="utf-8")
        with cli.source() as source:
            service = ImportService(source, SystemClock())
            parsed = service.parse_mapping(mapping_text)
            preview = service.preview(
                dataset_id,
                text,
                format=format,  # type: ignore[arg-type]
                mapping=parsed,
                decision_id=decision,
                decision_selector=revision or "draft",
            )
            if dry_run:
                return {"preview": preview, "would_import": len(preview.valid_rows)}
            return service.commit(preview, operation_id=op, skip_invalid=skip_invalid)

    if dry_run:
        execute(ctx, lambda cli: work(cli, new_operation_id(operation_id)))
    else:
        _mutate(ctx, operation_id, work)


@case_app.command("list")
def list_cases(
    ctx: typer.Context,
    dataset: Annotated[str, typer.Option("--dataset")],
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
    tag: Annotated[str | None, typer.Option("--tag")] = None,
    group_id: Annotated[str | None, typer.Option("--group")] = None,
    split: Annotated[str | None, typer.Option("--split")] = None,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return DatasetService(source, SystemClock()).list_cases(
                dataset, cursor=cursor, limit=limit, tag=tag, group_id=group_id, split=split
            )

    execute(ctx, work)


@case_app.command("show")
def show_case(
    ctx: typer.Context,
    case_id: str,
    dataset: Annotated[str, typer.Option("--dataset")],
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return DatasetService(source, SystemClock()).case(dataset, case_id)

    execute(ctx, work)


@case_app.command("add")
def add_case(
    ctx: typer.Context,
    dataset: Annotated[str, typer.Option("--dataset")],
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    case_id: Annotated[str | None, typer.Option("--id")] = None,
    if_dataset_hash: Annotated[str | None, typer.Option("--if-dataset-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        value = _case_input(source_text(file=file, stdin=stdin))
        with cli.source() as source:
            service = DatasetService(source, SystemClock())
            expected = (
                if_dataset_hash if if_dataset_hash is not None else service.read(dataset).etag
            )
            return service.add_case(
                dataset, value, expected_dataset_etag=expected, operation_id=op, case_id=case_id
            )

    _mutate(ctx, operation_id, work)


@case_app.command("edit")
def edit_case(
    ctx: typer.Context,
    case_id: str,
    dataset: Annotated[str, typer.Option("--dataset")],
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    if_dataset_hash: Annotated[str | None, typer.Option("--if-dataset-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        value = _case_input(source_text(file=file, stdin=stdin))
        with cli.source() as source:
            service = DatasetService(source, SystemClock())
            expected_dataset = (
                if_dataset_hash if if_dataset_hash is not None else service.read(dataset).etag
            )
            expected_case = if_hash if if_hash is not None else service.case(dataset, case_id).etag
            return service.edit_case(
                dataset,
                case_id,
                value,
                expected_dataset_etag=expected_dataset,
                expected_case_etag=expected_case,
                operation_id=op,
            )

    _mutate(ctx, operation_id, work)


@case_app.command("remove")
def remove_case(
    ctx: typer.Context,
    case_id: str,
    dataset: Annotated[str, typer.Option("--dataset")],
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    if_dataset_hash: Annotated[str | None, typer.Option("--if-dataset-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        with cli.source() as source:
            service = DatasetService(source, SystemClock())
            expected_dataset = (
                if_dataset_hash if if_dataset_hash is not None else service.read(dataset).etag
            )
            expected_case = if_hash if if_hash is not None else service.case(dataset, case_id).etag
            return service.remove_case(
                dataset,
                case_id,
                expected_dataset_etag=expected_dataset,
                expected_case_etag=expected_case,
                operation_id=op,
            )

    _mutate(ctx, operation_id, work)
