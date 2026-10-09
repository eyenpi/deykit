"""Exact, scope-aware resource selection over one captured project batch."""

from collections.abc import Iterable

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.ports import Collection, StoredRecord
from deykit.contracts.selection import ResourceChoice, ResourceKind, SelectionDetails

_COLLECTIONS: dict[ResourceKind, Collection] = {
    "decision": "decisions",
    "revision": "revisions",
    "dataset": "datasets",
    "case": "cases",
    "provider": "providers",
    "fixture": "fixtures",
    "run": "runs",
    "result_snapshot": "result_snapshots",
    "evaluation": "evaluations",
    "comparison": "comparisons",
    "regression": "regressions",
    "execution_group": "execution_groups",
    "diagnostic_snapshot": "diagnostic_snapshots",
    "check_snapshot": "check_snapshots",
    "report": "reports",
}


def _scope(scope: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if scope is None:
        return None
    if type(scope) is not tuple:
        raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_scope"))
    try:
        for component in scope:
            validate_resource_id(component)
    except (TypeError, ValueError):
        raise ServiceFailure(
            ServiceError(code="validation_error", reason="invalid_scope")
        ) from None
    return scope


def resource_choices(
    records: tuple[StoredRecord, ...],
    kind: ResourceKind,
    scope: tuple[str, ...] | None = None,
) -> tuple[ResourceChoice, ...]:
    """Return stable exact-ID alternatives from the supplied captured records only."""
    expected_scope = _scope(scope)
    collection = _COLLECTIONS[kind]
    choices = (
        ResourceChoice(kind=kind, resource_id=record.key.resource_id, scope=record.key.scope)
        for record in records
        if record.key.collection == collection
        and (expected_scope is None or record.key.scope == expected_scope)
    )
    return tuple(
        sorted(choices, key=lambda choice: (choice.kind, choice.scope, choice.resource_id))
    )


def choices_for_kinds(
    records: tuple[StoredRecord, ...],
    kinds: Iterable[ResourceKind],
    scopes: dict[ResourceKind, tuple[str, ...] | None] | None = None,
) -> tuple[ResourceChoice, ...]:
    """Return cross-kind candidates without collapsing equal IDs from different kinds."""
    selected = tuple(sorted(set(kinds)))
    return tuple(
        sorted(
            (
                choice
                for kind in selected
                for choice in resource_choices(
                    records, kind, scopes.get(kind) if scopes is not None else None
                )
            ),
            key=lambda choice: (choice.kind, choice.scope, choice.resource_id),
        )
    )


def require_resource(
    records: tuple[StoredRecord, ...],
    kind: ResourceKind,
    resource_id: str,
    scope: tuple[str, ...] | None = None,
) -> StoredRecord:
    """Resolve an exact ID in its declared scope or fail with safe alternatives."""
    expected_scope = _scope(scope)
    try:
        validated_id = validate_resource_id(resource_id)
    except (TypeError, ValueError):
        raise ServiceFailure(
            ServiceError(code="validation_error", reason="invalid_resource_id")
        ) from None

    collection = _COLLECTIONS[kind]
    matches = tuple(
        record
        for record in records
        if record.key.collection == collection
        and record.key.resource_id == validated_id
        and (expected_scope is None or record.key.scope == expected_scope)
    )
    if len(matches) == 1:
        return matches[0]

    alternatives = resource_choices(records, kind, expected_scope)
    if not matches:
        raise ServiceFailure(
            ServiceError(code="not_found", reason="selection_missing"),
            selection=SelectionDetails(choices=alternatives),
        )
    raise ServiceFailure(
        ServiceError(code="incompatible_data", reason="selection_ambiguous"),
        selection=SelectionDetails(
            choices=tuple(
                ResourceChoice(kind=kind, resource_id=item.key.resource_id, scope=item.key.scope)
                for item in sorted(matches, key=lambda item: (item.key.scope, item.key.resource_id))
            )
        ),
    )


def require_one_of(
    records: tuple[StoredRecord, ...],
    kinds: Iterable[ResourceKind],
    resource_id: str,
    scopes: dict[ResourceKind, tuple[str, ...] | None] | None = None,
) -> StoredRecord:
    """Resolve an exact ID across allowed kinds and reject genuine ambiguity."""
    selected = tuple(sorted(set(kinds)))
    try:
        exact_id = validate_resource_id(resource_id)
    except (TypeError, ValueError):
        raise ServiceFailure(
            ServiceError(code="validation_error", reason="invalid_resource_id")
        ) from None

    candidates = choices_for_kinds(records, selected, scopes)
    collection_by_kind = {collection: kind for kind, collection in _COLLECTIONS.items()}
    matches = tuple(
        record
        for record in records
        if record.key.resource_id == exact_id
        and (kind := collection_by_kind.get(record.key.collection)) in selected
        and (scopes is None or scopes.get(kind) is None or record.key.scope == scopes[kind])
    )
    if len(matches) == 1:
        return matches[0]
    choices = tuple(choice for choice in candidates if choice.resource_id == exact_id)
    if not matches:
        raise ServiceFailure(
            ServiceError(code="not_found", reason="selection_missing"),
            selection=SelectionDetails(choices=candidates),
        )
    raise ServiceFailure(
        ServiceError(code="incompatible_data", reason="selection_ambiguous"),
        selection=SelectionDetails(choices=choices),
    )
