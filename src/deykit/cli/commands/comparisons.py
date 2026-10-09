"""Freeze explicit evaluation selectors and persist a zero-call comparison."""

from typing import Annotated

import typer

from deykit.application.comparisons import ComparisonService
from deykit.application.dataset_support import fail
from deykit.application.evaluations import EvaluationService, EvaluationView
from deykit.application.results import ResultInspection
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.output import execute
from deykit.cli.selection import SelectorOwner, selection_context, selector_hint
from deykit.contracts.json_value import semantic_hash
from deykit.contracts.ports import SnapshotSource


def register(root: typer.Typer) -> None:
    root.command("compare")(compare)


def selected_evaluation(
    source: SnapshotSource, service: EvaluationService, run_id: str, evaluation_id: str | None
) -> str:
    if evaluation_id is not None:
        selected = service.read(evaluation_id)
        if selected.record.run_id != run_id:
            fail("evaluation_run_mismatch", "incompatible_data")
        return selected.record.id
    result_id = ResultInspection(source).list(run_id, limit=1).result_snapshot_id
    # Defaults select an original evaluation of the current immutable result.
    # Re-evaluated labels are an explicit --evaluation pin, so no label context is
    # silently chosen by a mutable current label or arbitrary UUID ordering.
    matching: list[EvaluationView] = []
    cursor: str | None = None
    while True:
        page = service.list(run_id, cursor=cursor, limit=500)
        matching.extend(
            view
            for view in page.items
            if view.record.result_snapshot_id == result_id and view.record.mode == "original"
        )
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    if matching:
        return max(matching, key=lambda view: (view.record.created_at, view.record.id)).record.id
    operation_id = "comparison-eval-" + semantic_hash(
        {"run_id": run_id, "result_snapshot_id": result_id}
    )
    return service.evaluate_saved(run_id, result_id, operation_id=operation_id).record.id


def compare(
    ctx: typer.Context,
    run_a: str,
    run_b: str,
    evaluation_a: Annotated[str | None, typer.Option("--evaluation-a")] = None,
    evaluation_b: Annotated[str | None, typer.Option("--evaluation-b")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    """Compare saved answers using compatible frozen inputs and expectations."""
    actual = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        with cli.source() as source:
            hints = (
                (
                    selector_hint("run", run_a, ()),
                    selector_hint("run", run_b, ()),
                )
                + (
                    (
                        selector_hint(
                            "evaluation", evaluation_a, (), owner=SelectorOwner("run", run_a)
                        ),
                    )
                    if evaluation_a
                    else ()
                )
                + (
                    (
                        selector_hint(
                            "evaluation", evaluation_b, (), owner=SelectorOwner("run", run_b)
                        ),
                    )
                    if evaluation_b
                    else ()
                )
            )
            with selection_context(source, hints):
                # Hold one source boundary while defaults resolve, evaluations freeze,
                # and the comparison commits. All helpers use the same source port.
                with source.consistent_read():
                    clock = SystemClock()
                    evaluations = EvaluationService(source, clock)
                    left = selected_evaluation(source, evaluations, run_a, evaluation_a)
                    right = selected_evaluation(source, evaluations, run_b, evaluation_b)
                    saved = ComparisonService(source, clock).create(
                        left, right, operation_id=actual
                    )
                return {
                    "operation_id": actual,
                    "comparison_id": saved.record.id,
                    "left_evaluation_id": left,
                    "right_evaluation_id": right,
                    "left_result_snapshot_id": saved.record.left_result_snapshot_id,
                    "right_result_snapshot_id": saved.record.right_result_snapshot_id,
                    "outcomes": saved.outcomes,
                    "replayed": saved.replayed,
                    "dispatch_count": 0,
                }

    execute(ctx, work)
