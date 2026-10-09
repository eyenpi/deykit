"""Transient, safe descriptions of resources available to an exact selector."""

from typing import Literal

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ResourceId

ResourceKind = Literal[
    "decision",
    "revision",
    "dataset",
    "case",
    "provider",
    "fixture",
    "run",
    "result_snapshot",
    "evaluation",
    "comparison",
    "regression",
    "execution_group",
    "diagnostic_snapshot",
    "check_snapshot",
    "report",
]


class ResourceChoice(FrozenModel):
    """One safe exact-ID alternative, scoped to its owning resource."""

    kind: ResourceKind
    resource_id: ResourceId
    scope: tuple[ResourceId, ...] = ()


class SelectionDetails(FrozenModel):
    """Alternatives available when a requested resource cannot be selected."""

    choices: tuple[ResourceChoice, ...]
