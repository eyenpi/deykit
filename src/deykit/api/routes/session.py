"""Bootstrap does not open projects, resolve secrets or invoke providers."""

from fastapi import APIRouter

from ..dto.common import BootstrapReply, BootstrapRequest, Success
from ..errors import TransportFailure
from ..session import SessionCapability


def register(router: APIRouter, session: SessionCapability, origin: str) -> None:
    @router.post(
        "/session/bootstrap",
        response_model=Success[BootstrapReply],
        operation_id="bootstrapSession",
    )
    async def bootstrap(body: BootstrapRequest) -> Success[BootstrapReply]:
        if not session.active:
            raise TransportFailure(503, "service_unavailable", "service_stopping")
        return Success(data=BootstrapReply(capability=session.token, origin=origin))
