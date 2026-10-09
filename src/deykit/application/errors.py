"""Safe application failure boundary shared by local adapters."""

from deykit.contracts.errors import ServiceError
from deykit.contracts.selection import SelectionDetails


class ServiceFailure(Exception):
    def __init__(self, error: ServiceError, *, selection: SelectionDetails | None = None) -> None:
        self.error = error
        self.selection = selection
        super().__init__(error.message)
