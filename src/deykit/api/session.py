"""A single memory-only capability for one service lifetime."""

import base64
import hmac
import re
import secrets


class SessionCapability:
    def __init__(self, token: str) -> None:
        self._token: str | None = token

    @classmethod
    def create(cls) -> "SessionCapability":
        return cls(base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii"))

    @property
    def active(self) -> bool:
        return self._token is not None

    @property
    def token(self) -> str:
        if self._token is None:
            raise RuntimeError("session_revoked")
        return self._token

    def verify(self, value: bytes) -> bool:
        return (
            self._token is not None
            and re.fullmatch(rb"[A-Za-z0-9_-]{43}", value) is not None
            and hmac.compare_digest(self._token.encode("ascii"), value)
        )

    def revoke(self) -> None:
        self._token = None
