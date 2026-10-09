"""Failure-only selector enrichment for thin CLI command adapters."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, cast

from deykit.application.evaluations import admit_evaluation_record, frozen_evaluation_from_records
from deykit.application.errors import ServiceFailure
from deykit.application.selectors import require_one_of, require_resource
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import ResourceKey, SnapshotSource, StoredRecord
from deykit.contracts.records import CheckSnapshot, DiagnosticSnapshot
from deykit.contracts.selection import ResourceChoice, ResourceKind, SelectionDetails
from deykit.runner.group_evidence import admit_group_snapshots, group_budget
from deykit.runner.history import history_from_records

OwnerKind = Literal["run", "evaluation", "execution_group"]
GroupKind = Literal["choice_order", "regression_check"]


@dataclass(frozen=True)
class SelectorOwner:
    """A command-known parent used only to scope failure alternatives."""

    kind: OwnerKind
    resource_id: str
    group_kind: GroupKind | None = None


@dataclass(frozen=True)
class SelectorHint:
    """One explicit ID and its owner-known scope, without display/source text."""

    kinds: tuple[ResourceKind, ...]
    resource_id: str
    scopes: Mapping[ResourceKind, tuple[str, ...] | None] | None = None
    owner: SelectorOwner | None = None

    def __post_init__(self) -> None:
        if self.scopes is not None:
            object.__setattr__(self, "scopes", MappingProxyType(dict(self.scopes)))


def selector_hint(
    kind: ResourceKind,
    resource_id: str,
    scope: tuple[str, ...],
    *,
    owner: SelectorOwner | None = None,
) -> SelectorHint:
    """Build one explicit single-kind hint with its required owner scope."""
    return SelectorHint((kind,), resource_id, {kind: scope}, owner)


def _owned_choices(
    kind: ResourceKind, resource_ids: tuple[str, ...], scope: tuple[str, ...]
) -> SelectionDetails:
    choices = tuple(
        sorted(
            (ResourceChoice(kind=kind, resource_id=item, scope=scope) for item in resource_ids),
            key=lambda item: (item.kind, item.scope, item.resource_id),
        )
    )
    return SelectionDetails(choices=choices)


def resolve_hint(
    records: tuple[StoredRecord, ...], hint: SelectorHint
) -> SelectionDetails | None:
    """Resolve a selector against its admitted frozen owner, without source access."""
    if hint.owner is None:
        if len(hint.kinds) == 1:
            kind = hint.kinds[0]
            if hint.scopes is None or kind not in hint.scopes:
                return None
            try:
                require_resource(records, kind, hint.resource_id, hint.scopes[kind])
            except ServiceFailure as failure:
                return failure.selection
            return None
        try:
            require_one_of(records, hint.kinds, hint.resource_id, hint.scopes)
        except ServiceFailure as failure:
            return failure.selection
        return None

    owner = hint.owner
    try:
        if owner.kind == "run":
            history = history_from_records(records, owner.resource_id)
            if len(hint.kinds) != 1:
                return None
            kind = hint.kinds[0]
            if kind == "case":
                selected = history.manifest.case_ids
                if hint.resource_id in selected:
                    return None
                return _owned_choices(kind, selected, (history.manifest.dataset_id,))
            if kind == "evaluation":
                choices = []
                for stored in records:
                    if stored.key != ResourceKey("evaluations", stored.key.resource_id):
                        continue
                    admitted = admit_evaluation_record(stored)
                    if admitted.record.run_id == owner.resource_id:
                        choices.append(admitted.record.id)
                selected = tuple(sorted(choices))
            elif kind == "result_snapshot":
                selected = tuple(snapshot.id for snapshot in history.snapshots)
            else:
                return None
            if hint.resource_id in selected:
                return None
            return _owned_choices(kind, selected, ())

        if owner.kind == "evaluation":
            if len(hint.kinds) != 1:
                return None
            stored = next(
                (
                    record
                    for record in records
                    if record.key == ResourceKey("evaluations", owner.resource_id)
                ),
                None,
            )
            if stored is None:
                return None
            admitted = admit_evaluation_record(stored)
            if admitted.record.id != owner.resource_id:
                return None
            evaluation = admitted.record
            frozen_evaluation_from_records(
                records,
                evaluation.run_id,
                evaluation.result_snapshot_id,
                evaluation.label_snapshot_id,
                evaluation.mode,
            )
            kind = hint.kinds[0]
            if kind != "result_snapshot":
                return None
            history = history_from_records(records, evaluation.run_id)
            selected = tuple(snapshot.id for snapshot in history.snapshots)
            if hint.resource_id in selected:
                return None
            return _owned_choices(kind, selected, ())

        if owner.kind == "execution_group":
            budget = group_budget(records, owner.resource_id)
            if owner.group_kind is None or budget.group.kind != owner.group_kind:
                return None
            snapshots = admit_group_snapshots(records, owner.resource_id)
            if len(hint.kinds) != 1:
                return None
            kind = hint.kinds[0]
            if kind == "diagnostic_snapshot" and owner.group_kind == "choice_order":
                selected = tuple(
                    item.id for item in snapshots if isinstance(item, DiagnosticSnapshot)
                )
            elif kind == "check_snapshot" and owner.group_kind == "regression_check":
                selected = tuple(item.id for item in snapshots if isinstance(item, CheckSnapshot))
            else:
                return None
            if hint.resource_id in selected:
                return None
            return _owned_choices(kind, selected, ())
    except Exception:
        # Corrupt or legacy owner evidence must not replace the original service error.
        return None
    return None


@contextmanager
def selection_context(
    source: SnapshotSource, hints: tuple[SelectorHint, ...]
) -> Iterator[None]:
    """Add safe choices only after the real service fails to resolve explicit selectors."""
    try:
        yield
    except ServiceFailure as original:
        if original.selection is not None or original.error.code not in {
            "not_found",
            "incompatible_data",
        }:
            raise
        try:
            with source.consistent_read() as captured:
                records = cast(SnapshotSource, captured).capture_snapshot()
            for hint in hints:
                if not hint.kinds:
                    continue
                selection = resolve_hint(records, hint)
                if selection is not None:
                    raise ServiceFailure(original.error, selection=selection) from None
        except ServiceFailure as enriched:
            if enriched.selection is not None:
                raise
            raise original from None
        except Exception:
            raise original from None
        raise
