"""Configuration comes from the listening socket, never request headers."""

import re
from dataclasses import dataclass

from .assets import AssetCatalog


@dataclass(frozen=True)
class LocalServerConfig:
    authority: str
    origin: str
    ui_assets: AssetCatalog
    max_registrations: int = 32

    def __post_init__(self) -> None:
        match = re.fullmatch(r"127\.0\.0\.1:([1-9][0-9]{0,4})", self.authority)
        if match is None or int(match[1]) > 65535:
            raise ValueError("invalid_local_authority")
        if self.origin != f"http://{self.authority}":
            raise ValueError("invalid_local_origin")
        if type(self.max_registrations) is not int or not 1 <= self.max_registrations <= 32:
            raise ValueError("invalid_registration_limit")
