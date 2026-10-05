"""Runner-owned capabilities; implementations provide no implicit dispatch or retry."""

from contextlib import AbstractContextManager
from typing import Protocol

from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import (
    ChoiceCompiler,
    ProviderTransport,
)
from deykit.contracts.records import ProviderProfile


class ExecutionProject(Protocol):
    def execution_owner(self) -> AbstractContextManager[None]: ...
    def execution_active(self) -> bool: ...
    def cancellation_requested(self, run_id: str) -> bool: ...
    def acknowledge_cancel(self, run_id: str, segment_id: str) -> None: ...


class Backend(Protocol):
    @property
    def compiler(self) -> ChoiceCompiler: ...
    def preflight(self, decision_id: str, dataset_id: str) -> ServiceError | None: ...
    def for_case(self, case_id: str) -> ProviderTransport: ...


class BackendFactory(Protocol):
    def profile(self, provider_id: str | None, fixture_set_id: str | None) -> ProviderProfile: ...
    def resolve(self, profile: ProviderProfile, fixture_set_id: str | None) -> Backend: ...


class Waiter(Protocol):
    async def wait(self, seconds: float) -> None: ...
