"""Safe application failure boundary shared by local adapters."""

from deykit.contracts.errors import ServiceError


class ServiceFailure(Exception):
    def __init__(self, error: ServiceError) -> None:
        self.error = error
        super().__init__(error.message)
