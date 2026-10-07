"""Neutral contracts for writing exact byte artifacts."""

from collections.abc import Callable
from typing import Protocol, Self

from pydantic import model_validator

from deykit.contracts.base import FrozenModel
from deykit.contracts.errors import ServiceError


class ArtifactWriteOutcome(FrozenModel):
    """Result of atomically replacing a destination with exact bytes."""

    success: bool
    destination: str | None
    error: ServiceError | None = None
    durability_warning: ServiceError | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        if self.success:
            if self.destination is None or self.error is not None:
                raise ValueError("invalid_successful_artifact_write")
        elif (
            self.destination is not None
            or self.error is None
            or self.durability_warning is not None
        ):
            raise ValueError("invalid_failed_artifact_write")
        return self


class ArtifactWriter(Protocol):
    """Narrow adapter for exact byte artifact replacement."""

    def write(
        self,
        destination: str,
        body: bytes,
        *,
        display_is_safe: Callable[[str], bool] | None = None,
    ) -> ArtifactWriteOutcome: ...
