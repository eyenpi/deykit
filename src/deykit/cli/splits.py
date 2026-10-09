"""Exact-ratio or explicit full-dataset split commands."""

from __future__ import annotations

from decimal import Decimal, localcontext
from pathlib import Path
from typing import Annotated, cast

import typer

from deykit.application.errors import ServiceFailure
from deykit.application.splits import SplitService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.output import execute
from deykit.cli.preview import split_preview
from deykit.cli.selection import selector_hint, selection_context
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonValue, dump_json, parse_json
from deykit.domain.splits import DEFAULT_RATIOS, Split


def _invalid(reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason=reason))


def _number(source: str) -> Decimal:
    value = parse_json(source)
    if not isinstance(value, Decimal) or value < 0 or value > 1:
        raise _invalid("invalid_split_ratios")
    return value


def _ratios(development: str, calibration: str | None, test: str | None) -> str:
    dev = _number(development)
    cal = _number(calibration) if calibration is not None else Decimal(0)
    test_value = _number(test) if test is not None else None
    if test_value is None:
        precision = max(
            50,
            sum(
                len(value.as_tuple().digits) + max(0, -cast(int, value.as_tuple().exponent))
                for value in (dev, cal)
            )
            + 2,
        )
        with localcontext() as context:
            context.prec = precision
            test_value = Decimal(1) - dev - cal
    parts: dict[str, Decimal] = {"development": dev}
    if calibration is not None:
        parts["calibration"] = cal
    parts["test"] = test_value
    return dump_json(cast(JsonValue, parts))


def _assignments(path: Path) -> tuple[tuple[str, Split], ...]:
    value = parse_json(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(
        type(case_id) is not str or type(split) is not str for case_id, split in value.items()
    ):
        raise _invalid("invalid_split_assignments")
    return tuple(sorted((case_id, cast(Split, split)) for case_id, split in value.items()))


def split_dataset(
    ctx: typer.Context,
    dataset_id: str,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    development: Annotated[str | None, typer.Option("--development")] = None,
    calibration: Annotated[str | None, typer.Option("--calibration")] = None,
    test: Annotated[str | None, typer.Option("--test")] = None,
    assignments: Annotated[Path | None, typer.Option("--assignments")] = None,
    preview: Annotated[Path | None, typer.Option("--preview")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        if preview is not None:
            if any(
                (
                    seed is not None,
                    development is not None,
                    calibration is not None,
                    test is not None,
                    assignments is not None,
                    dry_run,
                )
            ):
                raise _invalid("input_mode_conflict")
            frozen = split_preview(preview, dataset_id)
            with cli.source() as source:
                with selection_context(source, (selector_hint("dataset", dataset_id, ()),)):
                    return SplitService(source, SystemClock()).commit(frozen, operation_id=op)
        if assignments is not None and any(
            (seed is not None, development is not None, calibration is not None, test is not None)
        ):
            raise _invalid("assignments_exclude_seed_and_ratios")
        source_ratios = (
            DEFAULT_RATIOS
            if assignments is not None
            else _ratios(development if development is not None else "0.8", calibration, test)
        )
        chosen = _assignments(assignments) if assignments is not None else None
        with cli.source() as source:
            with selection_context(source, (selector_hint("dataset", dataset_id, ()),)):
                service = SplitService(source, SystemClock())
                plan = service.preview(
                    dataset_id,
                    seed=seed if seed is not None else 0,
                    ratios_source=source_ratios,
                    assignments=chosen,
                )
                if dry_run:
                    return {"preview": plan}
                return service.commit(plan, operation_id=op)

    if dry_run:
        execute(ctx, lambda cli: work(cli, new_operation_id(operation_id)))
    else:
        actual = new_operation_id(operation_id)
        execute(ctx, lambda cli: {"operation_id": actual, "result": work(cli, actual)})
